"""

"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
sys.path.insert(0, str(Path(__file__).parent))
from config import DIRECTORIES
from mongo import (
    is_pet_downloaded, mark_pet_downloaded,
    is_rain_downloaded, mark_rain_downloaded,
)

# SFTP download pipeline — used after browser places the order
try:
    from mosdac_downloader import (
        download_pet      as _sftp_download_pet,
        download_rainfall as _sftp_download_rain,
        _discover_orders,
        _make_sftp_connection,
    )
    SFTP_PIPELINE_AVAILABLE = True
except ImportError as _e:
    SFTP_PIPELINE_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"mosdac_downloader not importable — SFTP fallback disabled: {_e}"
    )

logger = logging.getLogger(__name__)

# ── Legacy disk directories (searched alongside config dirs) ──────────────────
MOSDAC_DISK_DIRS_PET: List[Path] = DIRECTORIES["raw"]["insat_pet"]
MOSDAC_DISK_DIRS_RAIN: List[Path] = DIRECTORIES["raw"]["insat_rain"]

# ── Constants ─────────────────────────────────────────────────────────────────
MOSDAC_BASE      = "https://mosdac.gov.in"
MOSDAC_LOGIN_URL = f"{MOSDAC_BASE}/user/login"
MOSDAC_UOPS_URL  = f"{MOSDAC_BASE}/uops/index.php"

# The operational Rabi collection window is extended through September.
RABI_MONTHS   = {11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9}
HISTORY_START = 2021
LOOKBACK_DAYS = 7

# Serial numbers in the UOPS catalog table
PRODUCT_SERIAL = {"pet": "37", "rain": "40"}
PRODUCT_CODE   = {"pet": "3RIMG_L3C_PET_DLY", "rain": "3RIMG_L3G_IMR_DLY"}

# All new MOSDAC orders request GeoTIFF; the SFTP downloader accepts only GeoTIFF.
PRODUCT_EXT = {"pet": ".tif", "rain": ".tif"}

# AOI requested from MOSDAC, in WGS84 longitude/latitude.
BBOX = {
    "north": "29.385337674489623",
    "south": "28.715620860521323",
    "west":  "78.71385772007373",
    "east":  "80.15672470945724",
}

PAGE_TIMEOUT     = 30_000   # ms
ORDER_POLL_MAX   = 1800     # s — max wait for order to become READY (agent-side)
ORDER_POLL_EVERY = 30       # s
DOWNLOAD_TIMEOUT = 300      # s


MOSDAC_DATA_LAG_DAYS = 2


# ── Product helpers ───────────────────────────────────────────────────────────
class Product:
    PET  = "pet"
    RAIN = "rain"

    @staticmethod
    def raw_dir(product: str) -> Path:
        dirs = DIRECTORIES["raw"]
        return dirs["insat_pet"] if product == Product.PET else dirs["insat_rain"]

    @staticmethod
    def all_search_dirs(product: str) -> List[Path]:
        extra = MOSDAC_DISK_DIRS_PET if product == Product.PET else MOSDAC_DISK_DIRS_RAIN
        if isinstance(extra, Path):
            extra = [extra]
        seen, result = set(), []
        for d in [Product.raw_dir(product)] + list(extra):
            key = d.resolve()
            if key not in seen:
                seen.add(key)
                result.append(d)
        return result

    @staticmethod
    def filename(date: datetime, product: str) -> str:
        stamp = date.strftime("%d%b%Y").upper()
        if product == Product.PET:
            return f"3RIMG_{stamp}_0015_L3C_PET_DLY_V01R00.tif"
        return f"3RIMG_{stamp}_0015_L3G_IMR_DLY_V01R00.tif"

    @staticmethod
    def find_on_disk(date: datetime, product: str) -> Optional[Path]:
        """
        Find the final GeoTIFF for this product on disk.
        """
        name      = Product.filename(date, product)
        stamp     = date.strftime("%d%b%Y").upper()
        code_frag = "L3C_PET_DLY" if product == Product.PET else "L3G_IMR_DLY"
        glob_pat  = f"3RIMG_{stamp}_0015_{code_frag}*"

        for d in Product.all_search_dirs(product):
            if not d.exists():
                continue
            f = d / name
            if f.exists() and f.stat().st_size > 1024:
                return f
            for f in d.glob(f"{glob_pat}.tif"):
                if f.stat().st_size > 1024:
                    return f
        return None

    @staticmethod
    def is_downloaded(date: datetime, product: str) -> bool:
        fn = is_pet_downloaded if product == Product.PET else is_rain_downloaded
        return fn(date)

    @staticmethod
    def mark_downloaded(date: datetime, filepath: str, product: str) -> bool:
        fn = mark_pet_downloaded if product == Product.PET else mark_rain_downloaded
        return fn(date, filepath)


# ── MOSDAC browser (Playwright selectors) ─────────────────────────────────────
class MosdacBrowser:
    """
    Wraps a Playwright browser session for the MOSDAC UOPS portal.

    Responsibilities:
      - Login
      - Navigate catalog (with INSAT-3DR datasource + pagination)
      - Discover latest available date per product
      - Place orders (leave dates blank, set GeoTIFF/AOI, agree T&C, confirm)
      - Poll order status (used by both the agent and the Scheduler's OrderPoller)
      - Download completed order files
    """

    def __init__(self, headless: bool = True):
        self.headless     = headless
        self.download_dir = Path("/tmp/mosdac_downloads")
        self.debug_dir    = Path("/tmp/mosdac_debug")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._pw = self._browser = self._ctx = self._page = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError:
            raise RuntimeError(
                "\n\nPlaywright is not installed.\n\n"
                "Run once in your conda env:\n"
                "    pip install playwright\n"
                "    playwright install chromium\n"
            )
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._ctx = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._ctx.new_page()
        self._page.set_default_timeout(PAGE_TIMEOUT)
        logger.info(f"Browser started (headless={self.headless})")

    def stop(self):
        for obj, method in [
            (self._ctx,     "close"),
            (self._browser, "close"),
            (self._pw,      "stop"),
        ]:
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self._page = self._ctx = self._browser = self._pw = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _goto(self, url: str, wait: float = 1.5):
        self._page.goto(url, wait_until="domcontentloaded")
        time.sleep(wait)

    def _dbg(self, label: str):
        path = self.debug_dir / f"{label}_{datetime.now().strftime('%H%M%S')}.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
            logger.info(f"  📸 debug screenshot → {path.name}")
        except Exception:
            pass

    def _fill(self, selectors: List[str], value: str) -> bool:
        for sel in selectors:
            try:
                el = self._page.locator(sel).first
                el.wait_for(state="visible", timeout=4000)
                el.clear()
                el.fill(value)
                return True
            except Exception:
                continue
        return False

    def _click(self, selectors: List[str], timeout: int = 6000) -> bool:
        for sel in selectors:
            try:
                el = self._page.locator(sel).first
                el.wait_for(state="visible", timeout=timeout)
                el.click()
                return True
            except Exception:
                continue
        return False

    def _agree_to_mosdac_terms(self) -> bool:
        """Tick the T&C checkbox in the cart and confirm that it is checked.

        The cart contains other (sometimes hidden) checkbox inputs.  Selecting
        the first generic ``input[type=checkbox]`` therefore regularly targets
        the wrong element.  Scope every locator to the row containing MOSDAC's
        agreement text, then use Playwright's checkbox-aware ``check`` call.
        """
        terms_text = "Terms and Conditions of MOSDAC"
        selectors = [
            # Current cart markup: input and agreement text live in one row.
            f"tr:has-text('{terms_text}') input[type='checkbox']",
            f"tr:has-text('{terms_text}') input",
            # Fallbacks for portal versions that use a div instead of a table.
            f"label:has-text('{terms_text}')",
            f"xpath=//*[contains(normalize-space(.), '{terms_text}')]/preceding-sibling::input[@type='checkbox'][1]",
            f"xpath=//*[contains(normalize-space(.), '{terms_text}')]/preceding::input[@type='checkbox'][1]",
        ]

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for selector in selectors:
                try:
                    matches = self._page.locator(selector)
                    count = matches.count()
                    for index in range(count):
                        checkbox = matches.nth(index)
                        if not checkbox.is_visible(timeout=1000):
                            continue
                        checkbox.scroll_into_view_if_needed(timeout=3000)

                        # ``check`` handles a normal native checkbox.  A label
                        # locator may not itself be checkable, so click it as a
                        # secondary path.
                        try:
                            checkbox.check(timeout=5000, force=True)
                        except Exception:
                            checkbox.click(timeout=5000, force=True)

                        # A label can wrap its input; inspect both possibilities.
                        input_el = checkbox
                        if checkbox.evaluate("el => el.tagName.toLowerCase()") == "label":
                            input_el = checkbox.locator("input[type='checkbox']").first
                        if input_el.is_checked(timeout=3000):
                            logger.info("  ✓ Terms & Conditions agreed (via %s)", selector)
                            return True
                except Exception:
                    continue
            time.sleep(0.5)

        return False

    def _cart_is_ready(self) -> bool:
        """Return whether the cart's agreement/order controls have rendered."""
        try:
            return (
                self._page.locator(
                    "tr:has-text('Terms and Conditions of MOSDAC'), "
                    "button:has-text('Click here to Place Order'), "
                    "a:has-text('Click here to Place Order')"
                ).count() > 0
            )
        except Exception:
            return False

    def _open_cart(self) -> bool:
        """Open the UOPS cart rather than the empty MyOrder landing view."""
        # MOSDAC deployments have used both route names.  Use the route first,
        # then the visible cart icon in the header as a fallback.
        for route in ("#/MyCart", "#/Cart"):
            try:
                self._goto(MOSDAC_UOPS_URL + route, wait=3)
                if self._cart_is_ready():
                    logger.info("  ✓ Cart opened via %s", route)
                    return True
            except Exception:
                continue

        # The cart icon contains no text in the current UI, so target its link
        # and common Bootstrap/FontAwesome/image variants explicitly.
        cart_selectors = [
            "a[href*='cart' i]", "a[routerlink*='cart' i]",
            "a:has(i[class*='cart'])", "a:has(span[class*='cart'])",
            "a:has(img[src*='cart' i])", "i[class*='cart']",
            "span[class*='cart']", "img[src*='cart' i]",
        ]
        for selector in cart_selectors:
            try:
                cart = self._page.locator(selector).first
                if not cart.is_visible(timeout=2000):
                    continue
                cart.scroll_into_view_if_needed(timeout=3000)
                cart.click(timeout=5000, force=True)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if self._cart_is_ready():
                        logger.info("  ✓ Cart opened via %s", selector)
                        return True
                    time.sleep(0.5)
            except Exception:
                continue

        return False

    def _clear_dl(self):
        for f in self.download_dir.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)

    def _wait_file(
        self,
        extensions: tuple = (".h5", ".hdf", ".tif"),
        timeout: int = DOWNLOAD_TIMEOUT,
    ) -> Optional[Path]:
        waited = 0
        while waited < timeout:
            hits = [
                f for f in self.download_dir.iterdir()
                if f.suffix.lower() in extensions
                and not f.name.endswith((".crdownload", ".part"))
            ]
            if hits:
                time.sleep(1)
                return hits[0]
            time.sleep(2)
            waited += 2
        return None

    def _wait_tif(self, timeout: int = DOWNLOAD_TIMEOUT) -> Optional[Path]:
        """Legacy alias."""
        return self._wait_file(extensions=(".tif",), timeout=timeout)

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> bool:
        logger.info("Logging in to MOSDAC …")
        self._goto(MOSDAC_LOGIN_URL, wait=2)

        if not self._fill(
            ["input#edit-name", "input[name='name']", "input[id*='name']"],
            username,
        ):
            self._dbg("login_no_username")
            logger.error("Login: username field not found")
            return False

        if not self._fill(
            ["input#edit-pass", "input[name='pass']", "input[type='password']"],
            password,
        ):
            self._dbg("login_no_password")
            logger.error("Login: password field not found")
            return False

        if not self._click([
            "input#edit-submit", "input[type='submit']",
            "button[type='submit']", "input[value='Log in']",
        ]):
            self._dbg("login_no_submit")
            logger.error("Login: submit button not found")
            return False

        time.sleep(3)
        html = self._page.content().lower()

        if "logout" in html or "log out" in html:
            logger.info("Login successful ✓")
            return True

        if any(w in html for w in ("unrecognized", "incorrect", "invalid", "error")):
            logger.error(
                "Login failed: MOSDAC rejected credentials. "
                "Check MOSDAC_USERNAME / MOSDAC_PASSWORD in .env"
            )
        else:
            self._dbg("login_unknown")
            logger.error(
                f"Login result unclear — check debug screenshot in {self.debug_dir}"
            )
        return False

    # ── Dump page structure (diagnostic) ─────────────────────────────────────

    def dump_page_structure(self, label: str = "diagnostic"):
        self._dbg(label)
        html_path = self.debug_dir / f"{label}_{datetime.now().strftime('%H%M%S')}.html"
        try:
            html = self._page.content()
            html_path.write_text(html, encoding="utf-8")
            logger.info(f"  📄 page HTML → {html_path.name}")
        except Exception as e:
            logger.warning(f"  HTML dump failed: {e}")

        try:
            rows = self._page.locator("tr").all()
            logger.info(f"  Table rows found: {len(rows)}")
            for i, row in enumerate(rows[:50]):
                try:
                    txt = row.inner_text(timeout=500).strip().replace("\n", " | ")
                    if txt:
                        logger.info(f"    row[{i:02d}]: {txt[:120]}")
                except Exception:
                    pass
        except Exception:
            pass

        try:
            buttons = self._page.locator(
                "button, input[type='button'], input[type='submit']"
            ).all()
            logger.info(f"  Buttons found: {len(buttons)}")
            for i, btn in enumerate(buttons[:20]):
                try:
                    txt = (
                        btn.inner_text(timeout=300)
                        or btn.get_attribute("value")
                        or btn.get_attribute("title")
                        or btn.get_attribute("class")
                        or "?"
                    )
                    logger.info(f"    btn[{i:02d}]: {str(txt).strip()[:80]}")
                except Exception:
                    pass
        except Exception:
            pass

    # ── Navigate to INSAT-3DR catalog ─────────────────────────────────────────

    def _navigate_to_catalog(self) -> bool:
        """
        Opens the MOSDAC UOPS portal, navigates Order → Archived Data → Satellite,
        then selects INSAT-3DR from the Datasource dropdown.
        Returns True when 3RIMG* product rows are visible.
        """
        self._goto(MOSDAC_UOPS_URL + "#/MyOrder", wait=5)

        # Step 1: Order top-nav
        if not self._click([
            "a:has-text('Order')",
            "li:has-text('Order') > a",
            "button:has-text('Order')",
            "[class*='nav'] a:has-text('Order')",
            "nav a:has-text('Order')",
        ]):
            self.dump_page_structure("nav_no_order_menu")
            logger.error("Cannot find 'Order' top-nav menu item")
            return False
        logger.info("  ✓ 'Order' menu opened")
        time.sleep(1.5)

        # Step 2: Archived Data
        if not self._click([
            "a:has-text('Archived Data')",
            "li:has-text('Archived Data') > a",
            "[class*='dropdown'] a:has-text('Archived')",
            "a:has-text('Archived')",
        ]):
            self.dump_page_structure("nav_no_archived_data")
            logger.error("Cannot find 'Archived Data' submenu item")
            return False
        logger.info("  ✓ 'Archived Data' clicked")
        time.sleep(1.5)

        # Step 3: Satellite
        if not self._click([
            "a:has-text('Satellite')",
            "li:has-text('Satellite') > a",
            "[class*='dropdown'] a:has-text('Satellite')",
        ]):
            self.dump_page_structure("nav_no_satellite")
            logger.error("Cannot find 'Satellite' submenu item")
            return False
        logger.info("  ✓ 'Satellite' clicked — waiting for catalog rows …")
        time.sleep(3)

        # Step 4: Select INSAT-3DR datasource
        time.sleep(2)
        selected_ds = False

        for sel in [
            "select[id*='datasource']", "select[name*='datasource']",
            "select[id*='Datasource']", "select[name*='Datasource']",
            "select[id*='data']",       "select[ng-model*='datasource']",
            "select[ng-model*='source']", "select",
        ]:
            try:
                el = self._page.locator(sel).first
                if el.count() == 0:
                    continue
                el.wait_for(state="visible", timeout=9000)
                el.select_option(label="INSAT-3DR")
                selected_ds = True
                logger.info("  ✓ Datasource set to INSAT-3DR (select label)")
                break
            except Exception:
                try:
                    el.select_option(value="INSAT-3DR")
                    selected_ds = True
                    logger.info("  ✓ Datasource set to INSAT-3DR (select value)")
                    break
                except Exception:
                    continue

        if not selected_ds:
            try:
                for ds_sel in [
                    "[class*='datasource']", "[id*='datasource']",
                    "[class*='Datasource']", "[placeholder*='atasource']",
                ]:
                    try:
                        self._page.locator(ds_sel).first.click(timeout=9000)
                        time.sleep(0.5)
                        break
                    except Exception:
                        continue
                self._page.locator(
                    "option:has-text('INSAT-3DR'), "
                    "li:has-text('INSAT-3DR'), "
                    "a:has-text('INSAT-3DR'), "
                    "[value='INSAT-3DR']"
                ).first.click(timeout=4000)
                selected_ds = True
                logger.info("  ✓ Datasource set to INSAT-3DR (dropdown option)")
            except Exception:
                pass

        if not selected_ds:
            self.dump_page_structure("no_datasource_insat3dr")
            logger.error(
                "Could not select INSAT-3DR from Datasource dropdown.\n"
                f"  Debug screenshot: {self.debug_dir}"
            )
            return False

        time.sleep(2)

        # Step 5: Wait for 3RIMG product rows
        for wait_sel in [
            "tr:has-text('3RIMG_L3C_PET_DLY')",
            "tr:has-text('3RIMG_L3G_IMR_DLY')",
            "tr:has-text('3RIMG')",
            "td:has-text('3RIMG')",
        ]:
            try:
                self._page.wait_for_selector(wait_sel, timeout=20_000)
                logger.info(f"  ✓ INSAT-3DR catalog loaded ({wait_sel})")
                time.sleep(1)
                return True
            except Exception:
                continue

        self.dump_page_structure("catalog_not_loaded")
        logger.error(
            "INSAT-3DR catalog rows (3RIMG*) did not appear after selecting datasource.\n"
            f"  Debug files: {self.debug_dir}"
        )
        return False

    # ── Paginate to product row ────────────────────────────────────────────────

    def _paginate_to_product(self, code: str, max_pages: int = 10) -> bool:
        """
        Paginate the MOSDAC catalog until the row containing `code` is visible.

        MOSDAC's current Angular UI uses ``mat-paginator`` (with a
        ``Next page`` aria-label); older deployments used DataTables.  Keep
        selectors for both versions because the portal has changed this UI
        more than once.
        PET (37) and RAIN (40) are both on page 4 (rows 31-40).
        """
        for page_num in range(max_pages):
            try:
                loc = self._page.locator(f"tr:has-text('{code}')")
                if loc.count() > 0:
                    logger.info(f"  ✓ Found '{code}' on catalog page {page_num + 1}")
                    return True
            except Exception:
                pass

            clicked_next = False
            next_selectors = [
                # Current Angular Material paginator.  These must come first:
                # its arrow-only button has no visible "Next" text.
                "mat-paginator button[aria-label='Next page']:not([disabled])",
                "button.mat-mdc-paginator-navigation-next:not(.mat-mdc-button-disabled)",
                "button.mat-paginator-navigation-next:not(.mat-button-disabled)",
                "button[aria-label*='Next page' i]:not([disabled])",
                # Legacy DataTables paginator.
                "a.paginate_button.next:not(.disabled)",
                "#DataTables_Table_0_next a",
                "[id*='DataTables'][id*='next'] a",
                ".dataTables_paginate .next:not(.disabled)",
                "li.next:not(.disabled) > a",
                "li.pagination-next:not(.disabled) > a",
                "a[aria-label='Next']",
                "button[aria-label='Next']",
                "a:has-text('Next')",
                "button:has-text('Next')",
                "a:has-text('›')",
                "a:has-text('»')",
                "li:has-text('›') > a",
                "li:has-text('»') > a",
                "[class*='next']:not([class*='disabled'])",
            ]
            for next_sel in next_selectors:
                try:
                    el = self._page.locator(next_sel).first
                    if el.count() == 0:
                        continue
                    if not el.is_visible(timeout=1500):
                        continue
                    if (
                        el.is_disabled(timeout=1500)
                        or el.get_attribute("aria-disabled") == "true"
                    ):
                        continue

                    range_label = self._page.locator(
                        "mat-paginator .mat-mdc-paginator-range-label, "
                        ".mat-paginator .mat-paginator-range-label"
                    ).first
                    old_range = range_label.inner_text(timeout=1000) if range_label.count() else ""
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(timeout=9000)
                    # Wait for the Angular table to actually replace its rows,
                    # rather than issuing several clicks against the same page.
                    if old_range:
                        try:
                            self._page.wait_for_function(
                                "([selector, previous]) => {"
                                "const el = document.querySelector(selector);"
                                "return el && el.innerText.trim() !== previous.trim();"
                                "}",
                                [
                                    "mat-paginator .mat-mdc-paginator-range-label, "
                                    ".mat-paginator .mat-paginator-range-label",
                                    old_range,
                                ],
                                timeout=5000,
                            )
                        except Exception:
                            time.sleep(1)
                    else:
                        time.sleep(1)
                    clicked_next = True
                    logger.info(
                        f"  → Catalog page {page_num + 2} (looking for {code}; "
                        f"via {next_sel})"
                    )
                    break
                except Exception:
                    continue

            if not clicked_next:
                logger.warning(
                    f"  No active 'Next' button on page {page_num + 1} "
                    f"— '{code}' not in catalog"
                )
                return False

        logger.warning(f"  Gave up after {max_pages} pages — '{code}' not found")
        return False

    # ── Click catalog cart ─────────────────────────────────────────────────────

    def _click_catalog_cart(self, serial: str, code: str) -> bool:
        """
        Click the "Order Data" cart icon for `serial`/`code`.
        Tries three strategies: XPath serial match, code text match, nth-child.
        """
        if not self._paginate_to_product(code):
            logger.error(
                f"  Product '{code}' (serial {serial}) not found in catalog — cannot click cart"
            )
            return False

        # Strategy 1: XPath by serial number text
        try:
            xpath_row = f"//tr[td[normalize-space(text())='{serial}']]"
            row_loc   = self._page.locator(f"xpath={xpath_row}").first
            row_loc.wait_for(state="attached", timeout=5000)
            for btn_sel in ["a", "button", "img", "i",
                            "[class*='cart']", "[class*='order']", "[class*='add']"]:
                try:
                    btn = row_loc.locator(btn_sel).last
                    if btn.count() > 0:
                        btn.scroll_into_view_if_needed(timeout=3000)
                        btn.click(timeout=4000)
                        logger.info(f"  ✓ cart clicked (XPath serial={serial} / {btn_sel})")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 2: product code text in row
        try:
            row_loc = self._page.locator(f"tr:has-text('{code}')").first
            for btn_sel in ["a", "button", "img", "i",
                            "[class*='cart']", "[class*='order']", "[class*='add']"]:
                try:
                    btn = row_loc.locator(btn_sel).last
                    if btn.count() > 0:
                        btn.scroll_into_view_if_needed(timeout=3000)
                        btn.click(timeout=9000)
                        logger.info(f"  ✓ cart clicked (code text={code} / {btn_sel})")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 3: nth-child fallback (only reliable on page 1)
        try:
            row_loc = self._page.locator(
                f"table tbody tr:nth-child({serial})"
            ).first
            row_loc.wait_for(state="attached", timeout=4000)
            for btn_sel in ["a", "button", "[class*='cart']", "[class*='add']", "img"]:
                try:
                    btn = row_loc.locator(btn_sel).last
                    if btn.count() > 0:
                        btn.scroll_into_view_if_needed(timeout=3000)
                        btn.click(timeout=9000)
                        logger.info(f"  ✓ cart clicked (nth-child({serial}) / {btn_sel})")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    # ── Output format and AOI selectors ───────────────────────────────────────

    def _select_geotiff_format(self) -> bool:
        """Select GeoTIFF output for either PET or Rainfall."""
        selectors = [
            ("md-radio-button[value='GeoTIFF']",             "md_radio_geotiff"),
            ("md-radio-button[value='GEOTIFF']",             "md_radio_geotiff_upper"),
            ("input[type='radio'][value='GeoTIFF']",         "input_radio_geotiff"),
            ("input[type='radio'][value='GEOTIFF']",         "input_radio_geotiff_upper"),
            ("input[value*='GeoTIFF' i]",                    "input_geotiff"),
            ("label:has-text('GeoTIFF')",                    "label_geotiff"),
            ("label:has-text('Geo Tiff')",                   "label_geo_tiff"),
            ("[role='radio'][aria-label*='GeoTIFF' i]",      "role_radio_geotiff"),
            # Current portal markup places the text beside an unlabelled
            # native radio input (as shown in its order dialog).
            ("xpath=//*[normalize-space(text())='GEOTIFF']/preceding-sibling::input[@type='radio'][1]", "native_radio_geotiff"),
            ("xpath=//*[normalize-space(text())='GeoTIFF']/preceding-sibling::input[@type='radio'][1]", "native_radio_geotiff_mixed"),
        ]

        for selector, desc in selectors:
            try:
                el = self._page.locator(selector).first
                if el.count() > 0:
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.wait_for(state="visible", timeout=9000)
                    el.click(timeout=9000)
                    time.sleep(0.8)

                    if (
                        el.get_attribute("aria-checked") == "true"
                        or el.get_attribute("ng-checked") == "true"
                    ):
                        logger.info(f"    ✓ GeoTIFF selected via {desc}")
                        return True

                    logger.debug(f"    GeoTIFF click attempted ({desc})")
                    return True

            except Exception:
                continue

        logger.error("    GeoTIFF output option was not found")
        return False

    def _select_aoi(self) -> bool:
        """Select the AOI delivery mode for either product."""
        selectors = [
            ("md-radio-button:has-text('Area of Interest')", "md_radio_aoi_long"),
            ("md-radio-button:has-text('AOI')",              "md_radio_aoi"),
            ("label:has-text('Area of Interest')",           "label_aoi_long"),
            ("label:has-text('AOI')",                         "label_aoi"),
            ("input[value='AOI']",                            "input_aoi"),
            ("input[value*='Area of Interest' i]",            "input_aoi_long"),
            ("[role='radio'][aria-label*='AOI' i]",           "role_radio_aoi"),
            # MOSDAC's current UI labels the AOI mode "Browse Images Only".
            # It opens the spatial/AOI controls in place of the former AOI label.
            ("label:has-text('Browse Images Only')",          "label_browse_images_aoi"),
            ("xpath=//*[normalize-space(text())='Browse Images Only']/preceding-sibling::input[@type='radio'][1]", "native_browse_images_aoi"),
        ]

        for selector, desc in selectors:
            try:
                el = self._page.locator(selector).first
                if el.count() > 0:
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.wait_for(state="visible", timeout=9000)
                    el.click(timeout=9000)
                    time.sleep(0.8)

                    if (
                        el.get_attribute("aria-checked") == "true"
                        or el.get_attribute("ng-checked") == "true"
                    ):
                        logger.info(f"    ✓ AOI selected via {desc}")
                        return True

                    logger.debug(f"    AOI click attempted ({desc})")
                    return True

            except Exception:
                continue

        logger.error("    AOI delivery option was not found")
        return False

    def _configure_geotiff_aoi(self) -> bool:
        """Set GeoTIFF output and apply the configured WGS84 AOI bounds."""
        if not self._select_geotiff_format() or not self._select_aoi():
            return False

        # Selecting AOI can cause Angular to render the coordinate fields.
        time.sleep(1)
        coordinate_selectors = {
            "north": ["input[id*='north' i]", "input[name*='north' i]", "input[placeholder*='north' i]",
                      "xpath=//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'north')]/following::input[1]"],
            "south": ["input[id*='south' i]", "input[name*='south' i]", "input[placeholder*='south' i]",
                      "xpath=//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'south')]/following::input[1]"],
            "west":  ["input[id*='west' i]", "input[name*='west' i]", "input[placeholder*='west' i]",
                      "xpath=//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'west')]/following::input[1]"],
            "east":  ["input[id*='east' i]", "input[name*='east' i]", "input[placeholder*='east' i]",
                      "xpath=//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'east')]/following::input[1]"],
        }
        for direction, selectors in coordinate_selectors.items():
            if not self._fill(selectors, BBOX[direction]):
                logger.error("    AOI %s coordinate field was not found", direction)
                return False
        logger.info("    ✓ AOI bounds filled: N=%s S=%s W=%s E=%s", BBOX["north"], BBOX["south"], BBOX["west"], BBOX["east"])

        # Some MOSDAC forms apply the extent immediately; others require this button.
        apply_clicked = self._click([
            "button:has-text('Apply')", "button:has-text('Update')",
            "input[value='Apply']", "input[value='Update']",
        ], timeout=9000)
        if not apply_clicked:
            logger.info("    AOI has no Apply/Update control; treating field entry as immediate apply")
            return True

        deadline = time.monotonic() + 15
        success_terms = ("aoi applied", "aoi updated", "area of interest applied", "area of interest updated")
        while time.monotonic() < deadline:
            try:
                body_text = self._page.locator("body").inner_text(timeout=3000).lower()
                if any(term in body_text for term in success_terms):
                    logger.info("    ✓ AOI accepted by MOSDAC")
                    return True
                if any(term in body_text for term in ("invalid aoi", "invalid coordinate", "invalid bounding")):
                    logger.error("    MOSDAC rejected the AOI bounds")
                    return False
            except Exception:
                pass
            time.sleep(2)

        # The fields remain populated after a successful asynchronous map update on
        # some portal versions, without a textual toast.  Wait the full interval
        # above before allowing the workflow to continue.
        logger.info("    AOI apply wait completed; no portal status text was exposed")
        return True

    # ── Discover latest available date ────────────────────────────────────────

    def discover_latest_available_date(self, product: str) -> datetime:
        """
        Open the order modal for `product` and read the "Data available from
        YYYY-MM-DD to YYYY-MM-DD" sentence to find the latest available date.
        Falls back to today − MOSDAC_DATA_LAG_DAYS if the modal cannot be read.
        """
        today    = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        fallback = today - timedelta(days=MOSDAC_DATA_LAG_DAYS)
        serial   = PRODUCT_SERIAL[product]
        code     = PRODUCT_CODE[product]

        logger.info(f"[discover] Finding latest available date for {product.upper()} …")

        try:
            if not self._navigate_to_catalog():
                logger.warning(f"[discover] Catalog not loaded — fallback {fallback.date()}")
                return fallback

            if not self._click_catalog_cart(serial, code):
                logger.warning(
                    f"[discover] Could not click cart for {product} — fallback {fallback.date()}"
                )
                return fallback

            time.sleep(3)

            modal_text = ""
            for modal_sel in [
                "[class*='modal-body']", "[class*='modal-content']",
                "[class*='dialog']",     ".modal",
                "[role='dialog']",       "div[style*='display: block']",
            ]:
                try:
                    el = self._page.locator(modal_sel).first
                    if el.count() > 0:
                        modal_text = el.inner_text(timeout=9000)
                        if "available" in modal_text.lower():
                            break
                except Exception:
                    continue

            if "available" not in modal_text.lower():
                modal_text = self._page.inner_text("body")

            m = re.search(
                r"Data available from.*?to\s+(\d{4}-\d{2}-\d{2})",
                modal_text, re.IGNORECASE
            )
            if m:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
                logger.info(f"[discover] {product.upper()} latest: {d.date()} (from modal text)")
                self._click([
                    "button:has-text('×')", "button:has-text('X')",
                    "button.close", "[class*='close']", "[aria-label='Close']",
                ])
                time.sleep(1)
                return d

            logger.warning(
                f"[discover] Modal text missing availability range "
                f"(got: {modal_text[:200]!r}) — fallback {fallback.date()}"
            )
            self._click([
                "button:has-text('×')", "button:has-text('X')",
                "button.close", "[class*='close']",
            ])

        except Exception as exc:
            logger.warning(f"[discover] Unexpected error for {product}: {exc}")

        logger.warning(
            f"[discover] Using fallback date for {product.upper()}: {fallback.date()}"
        )
        return fallback

    # ── Place order ───────────────────────────────────────────────────────────

    def place_order(
        self,
        product: str,
        start_date: datetime,
        end_date: datetime,
    ) -> bool:
        """
        Place a UOPS order for `product` with MOSDAC's default date selection.

        The supplied dates identify the data being tracked locally and are used
        to find its order/download. They are intentionally not entered in the
        MOSDAC form: its Start Date and End Date controls must remain blank.
        Returns True if the order was submitted (optimistic), False on hard failure.
        """
        serial    = PRODUCT_SERIAL[product]
        code      = PRODUCT_CODE[product]

        logger.info(
            f"Placing order: {product.upper()} | "
            f"{start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}"
        )

        if not self._navigate_to_catalog():
            return False

        if not self._click_catalog_cart(serial, code):
            self.dump_page_structure(f"order_no_cart_{product}")
            logger.error(
                f"Cannot find cart button for serial={serial} / code={code}.\n"
                f"  Debug files: {self.debug_dir}"
            )
            return False

        time.sleep(3)

        # Do not interact with the Start Date or End Date controls. MOSDAC
        # should receive them blank and apply its portal-side default range.
        logger.info("  Start Date and End Date left blank")

        time.sleep(2)
        if not self._configure_geotiff_aoi():
            self._dbg(f"order_invalid_aoi_{product}")
            logger.error("  GeoTIFF/AOI configuration failed — order not submitted")
            return False

        time.sleep(1)

        if not self._click([
            "button:has-text('Add to cart')",
            "button:has-text('Add to Cart')",
            "button:has-text('add to cart')",
            "input[value='Add to cart']",
            "[class*='add-to-cart']",
            "[class*='addtocart']",
        ]):
            self._dbg(f"order_no_addtocart_{product}")
            logger.error("'Add to cart' button not found — saved debug screenshot")
            return False

        logger.info("  ✓ 'Add to cart' clicked")
        time.sleep(10)

        if not self._open_cart():
            self.dump_page_structure(f"order_no_cart_page_{product}")
            logger.error(
                "Cart page did not open after 'Add to cart' — order not submitted"
            )
            return False

        agreed = self._agree_to_mosdac_terms()
        if agreed:
            logger.info("  ✓ Terms & Conditions agreed")
        else:
            self._dbg(f"order_no_terms_{product}")
            logger.error("Terms & Conditions checkbox not found — order not submitted")
            return False

        time.sleep(1)

        if not self._click([
            "button:has-text('Click here to Place Order')",
            "a:has-text('Click here to Place Order')",
            "input[value='Click here to Place Order']",
            "button:has-text('Place Order')",
            "a:has-text('Place Order')",
        ]):
            self._dbg(f"order_no_placeorder_{product}")
            logger.error("'Click here to Place Order' button not found")
            return False

        logger.info("  ✓ 'Click here to Place Order' clicked")
        time.sleep(4)

        for sel in [
            "button:has-text('Yes')", "button:has-text('Confirm')",
            "button:has-text('OK')",  "[class*='confirm']",
        ]:
            try:
                el = self._page.locator(sel).first
                if el.is_visible(timeout=3000):
                    el.click()
                    time.sleep(2)
                    break
            except Exception:
                continue

        # Do not hand off to the existing status poller until MOSDAC has created
        # an order row.  Creation normally takes a few seconds; readiness is
        # still handled by ``wait_for_order_ready`` below.
        date_tokens = (
            start_date.strftime("%d%b%Y").upper(),
            start_date.strftime("%Y-%m-%d"),
            start_date.strftime("%d-%m-%Y"),
        )
        creation_deadline = time.monotonic() + 120
        while time.monotonic() < creation_deadline:
            self._goto(MOSDAC_UOPS_URL + "#/MyOrder", wait=2)
            page_text = self._page.content().upper()
            has_product = code in page_text
            has_date = any(token.upper() in page_text for token in date_tokens)
            status = self._read_row_status(code, date_tokens[0])
            if has_product and (has_date or status is not None):
                if status in {"FAILED", "ERROR", "CANCELLED", "REJECTED"}:
                    logger.error("  Order was created but immediately failed (%s)", status)
                    return False
                logger.info("  ✓ Order created in order history (status=%s)", status or "NEW")
                return True
            time.sleep(3)

        self._dbg(f"order_not_created_{product}")
        logger.error("MOSDAC did not create an order row within 120 seconds")
        return False

    # ── Read row status (used by agent + Scheduler's OrderPoller) ─────────────

    def _read_row_status(self, code: str, date_tok: str) -> Optional[str]:
        """
        Read the status keyword from the order row matching `code` or `date_tok`.
        Returns a normalised uppercase status string, or None if not found.
        """
        try:
            row = None
            for sel in [f"tr:has-text('{date_tok}')", f"tr:has-text('{code}')"]:
                loc = self._page.locator(sel).last
                if loc.count() > 0:
                    row = loc
                    break
            if row is None:
                return None
            txt = row.inner_text().upper()
            for kw in [
                "COMPLETED", "READY", "DONE", "SUCCESS", "AVAILABLE",
                "FAILED", "ERROR", "CANCELLED", "REJECTED",
                "PROCESSING", "PENDING", "QUEUED", "IN PROGRESS",
            ]:
                if kw in txt:
                    return kw
        except Exception:
            pass
        return None

    # ── Agent-side order polling (standalone / CLI mode only) ─────────────────

    def wait_for_order_ready(self, product: str, start_date: datetime) -> bool:
        """
        Poll MyOrder page until the order is READY or fails.
        Used only in standalone CLI mode (download_dates).
        """
        start_str = start_date.strftime("%Y-%m-%d")
        date_tok  = start_date.strftime("%d%b%Y").upper()
        code      = PRODUCT_CODE[product]
        waited    = 0

        READY  = {"COMPLETED", "READY", "DONE", "SUCCESS", "AVAILABLE"}
        FAILED = {"FAILED", "ERROR", "CANCELLED", "REJECTED"}

        logger.info(f"Polling order status: {product.upper()} / {start_str} …")

        while waited < ORDER_POLL_MAX:
            self._goto(MOSDAC_UOPS_URL + "#/MyOrder", wait=2)
            try:
                self._page.wait_for_selector(
                    "table, [class*='order'], [class*='result']",
                    timeout=10_000,
                )
            except Exception:
                pass

            status = self._read_row_status(code, date_tok)

            if status in READY:
                logger.info(f"  ✓ Order READY ({status})")
                return True
            if status in FAILED:
                logger.error(f"  ✗ Order {status}")
                return False

            page_text = self._page.content().upper()
            for st in READY:
                if st in page_text and (code in page_text or date_tok in page_text):
                    logger.info(f"  ✓ Order ready (page scan: {st})")
                    return True
            for st in FAILED:
                if st in page_text and (code in page_text or date_tok in page_text):
                    logger.error(f"  ✗ Order failed (page scan: {st})")
                    return False

            logger.info(
                f"  Waiting … {waited}s elapsed "
                f"(status={status or 'UNKNOWN'}, retry in {ORDER_POLL_EVERY}s)"
            )
            time.sleep(ORDER_POLL_EVERY)
            waited += ORDER_POLL_EVERY

        logger.error(f"Order timed out after {ORDER_POLL_MAX}s")
        return False

    def get_ready_order_key(self, product: str, start_date: datetime) -> Optional[str]:
        """Return the MOSDAC order-folder key shown for a ready order row.

        This deliberately only reads the existing MyOrder table.  The agent
        never opens an SFTP connection; Stage 3 owns that responsibility.

        MOSDAC's real /Order delivery folders are named like "Jul26_186162"
        (3-letter month + 2-digit year + underscore + sequence number), NOT
        "ORD_...". That pattern is checked first since it's confirmed against
        the live portal; the old "ORD_" convention and a generic labelled
        "Order ID: ..." value are kept as lower-priority fallbacks in case a
        different product/portal view ever uses them instead.
        """
        code = PRODUCT_CODE[product]
        date_tokens = (
            start_date.strftime("%d%b%Y").upper(),
            start_date.strftime("%Y-%m-%d"),
            start_date.strftime("%d-%m-%Y"),
        )
        try:
            self._goto(MOSDAC_UOPS_URL + "#/MyOrder", wait=2)
            for selector in (f"tr:has-text('{date_tokens[0]}')", f"tr:has-text('{code}')"):
                row = self._page.locator(selector).last
                if row.count() == 0:
                    continue
                text = row.inner_text()

                # Confirmed real convention, e.g. "Jul26_186162".
                real_folder_key = re.search(r"\b[A-Za-z]{3}\d{2}_\d{4,}\b", text)
                if real_folder_key:
                    return real_folder_key.group(0)

                # Legacy / other-portal convention, kept as a fallback.
                folder_key = re.search(r"\bORD[_-][A-Za-z0-9_-]+\b", text, re.IGNORECASE)
                if folder_key:
                    return folder_key.group(0)

                # Last resort: an explicitly labelled "Order ID:"-style value.
                # Lowest priority because it can capture an internal request/
                # ticket number that doesn't match the real SFTP folder name.
                labelled = re.search(
                    r"(?:order\s*(?:id|no\.?|number|key)\s*[:#-]?\s*)([A-Za-z0-9_-]+)",
                    text,
                    re.IGNORECASE,
                )
                if labelled:
                    return labelled.group(1)
        except Exception as exc:
            logger.warning("Could not read ready order key for %s: %s", product.upper(), exc)
        return None

    # ── Download files ────────────────────────────────────────────────────────

    def _do_download(
        self,
        date:     datetime,
        product:  str,
        date_tok: str,
        code:     str,
        filename: str,
    ) -> Optional[Path]:
        selectors = [
            f"a[href*='{filename}']",
            f"a[href*='{date_tok}']",
            f"a:has-text('{date_tok}')",
            f"tr:has-text('{date_tok}') a[href*='.h5']",
            f"tr:has-text('{date_tok}') a[download]",
            f"tr:has-text('{date_tok}') button",
            f"tr:has-text('{date_tok}') [class*='download']",
            f"tr:has-text('{date_tok}') [title*='Download']",
            f"tr:has-text('{date_tok}') a[href*='.hdf']",
            f"tr:has-text('{date_tok}') a[href*='.tif']",
        ]

        for sel in selectors:
            try:
                el = self._page.locator(sel).first
                if el.count() == 0:
                    continue
                el.wait_for(state="visible", timeout=4000)
                with self._ctx.expect_download(
                    timeout=DOWNLOAD_TIMEOUT * 1000
                ) as dl_info:
                    el.click()
                dl   = dl_info.value
                path = self.download_dir / dl.suggested_filename
                dl.save_as(str(path))
                if path.stat().st_size > 1024:
                    logger.info(f"  ✓ download via selector: {sel}")
                    return path
                path.unlink(missing_ok=True)
            except Exception:
                continue

        self._dbg(f"dl_fail_{product}_{date.strftime('%Y%m%d')}")
        return None


# ── Main agent ────────────────────────────────────────────────────────────────
class MosdacAgent:
    """
    High-level orchestrator for MOSDAC UOPS ordering and downloading.
    """

    def __init__(self, headless: bool = True):
        self.username = os.getenv("MOSDAC_USERNAME", "")
        self.password = os.getenv("MOSDAC_PASSWORD", "")
        if not self.username or not self.password:
            raise EnvironmentError(
                "Set MOSDAC_USERNAME and MOSDAC_PASSWORD in .env"
            )
        self._browser   = MosdacBrowser(headless=headless)
        self._started   = False
        self._logged_in = False

        for product in (Product.PET, Product.RAIN):
            Product.raw_dir(product).mkdir(parents=True, exist_ok=True)

        logger.info("MosdacAgent initialised (Playwright, no API key needed).")

    def _ensure_logged_in(self) -> bool:
        """
        Start browser and log in if not already done.

        ASYNCIO GUARD: Playwright's sync API calls asyncio.get_event_loop()
        internally and raises an error if a loop is already running (e.g.
        uvicorn's loop, which APScheduler worker threads can inherit).
        We assign a fresh idle event loop to the current thread so Playwright
        always sees is_running() == False — regardless of how many times the
        scheduler fires this method.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.set_event_loop(asyncio.new_event_loop())
                logger.debug("_ensure_logged_in: replaced running loop with fresh idle loop")
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        if not self._started:
            self._browser.start()
            self._started = True
        if not self._logged_in:
            self._logged_in = self._browser.login(self.username, self.password)
        return self._logged_in

    def _stop(self):
        """Close browser."""
        if self._started:
            self._browser.stop()
            self._started = self._logged_in = False

    # ── Core download logic ───────────────────────────────────────────────────

    def download_date(self, date: datetime, product: str) -> Dict:
        """Check DB / disk. Returns skipped=True if available, ok=False if missing."""
        ds   = date.strftime("%Y-%m-%d")
        dest = Product.raw_dir(product) / Product.filename(date, product)

        if Product.is_downloaded(date, product):
            logger.debug(f"[{ds}][{product}] DB → skip")
            return {"date": date, "product": product, "filepath": dest,
                    "skipped": True, "ok": True}

        found = Product.find_on_disk(date, product)
        if found:
            logger.info(f"[{ds}][{product}] disk → {found.name}")
            Product.mark_downloaded(date, str(found), product)
            return {"date": date, "product": product, "filepath": found,
                    "skipped": True, "ok": True}

        logger.info(f"[{ds}][{product}] not found → queued for ordering")
        return {"date": date, "product": product, "filepath": None,
                "skipped": False, "ok": False}

    # ── Public entry points ───────────────────────────────────────────────────

    def place_orders_and_return_keys(self) -> List[str]:
        """
        Discover the latest available MOSDAC date per product, place orders for
        any dates missing from disk/DB, wait for them to become ready, and
        return their MOSDAC SFTP order-folder names.

        Returns
        -------
        A list of SFTP folder names (for example ``["Jul26_186162"]``).
        An empty list means no order was required, no order was successfully
        placed, or a ready order did not expose its folder key in MyOrder.
        Note that even a non-empty list is only a hint: Stage 3's
        _discover_orders() falls back to an unrestricted /Order scan if none
        of these keys turn out to match a real folder.
        """
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        if today.month not in RABI_MONTHS:
            logger.info("Outside Rabi season – no orders placed")
            return []

        # ── Discover latest available date per product ────────────────────────
        logger.info("Discovering latest available MOSDAC dates …")
        latest_available: Dict[str, datetime] = {}

        if self._ensure_logged_in():
            for product in (Product.PET, Product.RAIN):
                latest_available[product] = self._browser.discover_latest_available_date(product)
        else:
            fallback = today - timedelta(days=MOSDAC_DATA_LAG_DAYS)
            for product in (Product.PET, Product.RAIN):
                latest_available[product] = fallback

        # ── Check which dates are missing ─────────────────────────────────────
        missing: Dict[str, List[datetime]] = {Product.PET: [], Product.RAIN: []}

        for product in (Product.PET, Product.RAIN):
            date = latest_available[product]
            if not Product.is_downloaded(date, product):
                found = Product.find_on_disk(date, product)
                if found:
                    Product.mark_downloaded(date, str(found), product)
                else:
                    missing[product].append(date)

        if not any(missing.values()):
            logger.info("No missing MOSDAC data – no orders needed")
            return []

        # ── Place orders ──────────────────────────────────────────────────────
        # NOTE: each product/date is handled in its own try/except below.
        # A failure while placing, polling, or reading the key for ONE order
        # must never discard keys already collected for ANOTHER order —
        # previously a single outer try/except wrapped the whole two-product
        # loop, so an exception while processing product #2 (e.g. RAIN)
        # would wipe out an order_key already found for product #1 (e.g. PET)
        # and silently return [] even though Stage 2 logs showed a key was
        # found. That caused Stage 3 to skip with "No order_keys provided".
        placed_orders: List[Tuple[str, datetime]] = []
        order_keys: List[str] = []

        if not self._ensure_logged_in():
            logger.error("Order placement failed: cannot log in to MOSDAC")
            return []

        for product in (Product.PET, Product.RAIN):
            for d in missing[product]:
                try:
                    if self._browser.place_order(product, d, d):
                        placed_orders.append((product, d))
                        logger.info(
                            f"Order placed for {product} on {d.date()}"
                        )
                    else:
                        logger.error(
                            f"Order placement failed for {product} on {d.date()}"
                        )
                except Exception as exc:
                    logger.error(
                        "Order placement raised for %s on %s: %s",
                        product, d.date(), exc, exc_info=True,
                    )

        for product, date in placed_orders:
            try:
                if not self._browser.wait_for_order_ready(product, date):
                    logger.error(
                        "Order did not become READY for %s on %s",
                        product.upper(), date.date(),
                    )
                    continue
                order_key = self._browser.get_ready_order_key(product, date)
                if order_key:
                    order_keys.append(order_key)
                    logger.info("Ready MOSDAC order: %s", order_key)
                else:
                    logger.error(
                        "Ready %s order for %s has no folder key in MyOrder; "
                        "Stage 3 cannot safely select an SFTP folder.",
                        product.upper(), date.date(),
                    )
            except Exception as exc:
                # Isolated to this (product, date) pair — any keys already
                # collected for other orders above are preserved.
                logger.error(
                    "Polling/key-lookup raised for %s on %s: %s",
                    product, date.date(), exc, exc_info=True,
                )

        return order_keys

    def download_dates(self, missing_dates: Dict[str, List[datetime]]) -> Dict[str, int]:
        """
        Download missing dates by placing orders via browser, then fetching
        the delivered files over SFTP using mosdac_downloader's pipeline.

        Flow per date:
          1. Browser: place order
          2. Browser: poll MyOrder until status = AVAILABLE
          3. SFTP: _discover_orders() → download_pet / download_rainfall
        """
        results = {"pet": 0, "rain": 0}

        if not self._ensure_logged_in():
            logger.error("Cannot log in to MOSDAC")
            return results

        for product, dates in missing_dates.items():
            if not dates:
                continue

            for date in dates:
                if not self._browser.place_order(product, date, date):
                    logger.error(f"Failed to place order for {product.upper()} on {date.date()}")
                    continue

                logger.info(f"Order placed for {product.upper()} on {date.date()}")

                if not self._browser.wait_for_order_ready(product, date):
                    logger.error(f"Order timed-out / failed for {product.upper()} on {date.date()}")
                    continue

                logger.info(f"Order ready for {product.upper()} on {date.date()}")

                if not SFTP_PIPELINE_AVAILABLE:
                    logger.error(
                        "mosdac_downloader not available — cannot SFTP-download. "
                        "Run mosdac_downloader.py manually to fetch the file."
                    )
                    continue

                try:
                    with _make_sftp_connection() as sftp:
                        orders = _discover_orders(sftp)
                        if product == Product.PET:
                            ok = _sftp_download_pet(
                                date.date(), sftp, orders["pet_order"]
                            )
                        else:
                            rain_order = orders.get("rain_order")
                            if not rain_order:
                                logger.error(
                                    f"[RAIN] {date.date()} — no rain order folder on SFTP yet. "
                                    "Wait a few minutes and re-run mosdac_downloader.py."
                                )
                                continue
                            ok = _sftp_download_rain(
                                date.date(), sftp, rain_order
                            )

                    if ok:
                        results[product] += 1
                        logger.info(f"✓ SFTP download complete: {product.upper()} {date.date()}")
                    else:
                        logger.error(f"SFTP download returned False: {product.upper()} {date.date()}")

                except Exception as exc:
                    logger.error(f"SFTP error for {product.upper()} {date.date()}: {exc}")

        return results   # ← single return, duplicate removed

    def download_new_only(self) -> Dict:
        """
        Discover latest available date per product and download if missing.
        Only checks the single latest date (no 7-day lookback).
        """
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

        if today.month not in RABI_MONTHS:
            logger.info(f"Outside Rabi season ({today.strftime('%b')}) — skipped")
            return {p: {"downloaded": 0, "failed": 0} for p in (Product.PET, Product.RAIN)}

        logger.info("Discovering latest available MOSDAC dates …")
        latest_available: Dict[str, datetime] = {}

        try:
            if self._ensure_logged_in():
                for product in (Product.PET, Product.RAIN):
                    latest_available[product] = (
                        self._browser.discover_latest_available_date(product)
                    )
            else:
                logger.error("Login failed during discovery — falling back to today−2")
                for product in (Product.PET, Product.RAIN):
                    latest_available[product] = today - timedelta(days=MOSDAC_DATA_LAG_DAYS)
        except Exception as exc:
            logger.warning(f"Discovery error: {exc} — using conservative fallback")
            for product in (Product.PET, Product.RAIN):
                latest_available[product] = today - timedelta(days=MOSDAC_DATA_LAG_DAYS)

        for product, ld in latest_available.items():
            tag = "PET " if product == Product.PET else "RAIN"
            logger.info(f"  [{tag}] Latest available date: {ld.date()}")

        missing: Dict[str, List[datetime]] = {Product.PET: [], Product.RAIN: []}
        for product in (Product.PET, Product.RAIN):
            end = latest_available[product]
            tag = "PET " if product == Product.PET else "RAIN"

            if not Product.is_downloaded(end, product):
                found = Product.find_on_disk(end, product)
                if found:
                    logger.info(f"  [{tag}] {end.date()} found on disk → registered")
                    Product.mark_downloaded(end, str(found), product)
                else:
                    logger.info(f"  [{tag}] {end.date()} missing → queued for download")
                    missing[product].append(end)
            else:
                logger.info(f"  [{tag}] {end.date()} already registered")

        if not any(missing.values()):
            logger.info("Latest dates already available — nothing to download")
            return {p: {"downloaded": 0, "failed": 0} for p in (Product.PET, Product.RAIN)}

        for p, dates in missing.items():
            if dates:
                tag = "PET " if p == Product.PET else "RAIN"
                logger.info(
                    f"  [{tag}] missing: "
                    + ", ".join(d.strftime("%Y-%m-%d") for d in dates)
                )

        saved = self.download_dates(missing)

        result = {}
        print(f"\n{'='*55}")
        for product in (Product.PET, Product.RAIN):
            n_saved   = saved.get(product, 0)
            n_missing = len(missing[product])
            tag = "PET " if product == Product.PET else "RAIN"
            print(f"  {tag} | downloaded={n_saved}  failed={n_missing - n_saved}")
            result[product] = {"downloaded": n_saved, "failed": n_missing - n_saved}
        print("=" * 55)
        return result

    def download_historical(self) -> Dict:
        """Seed from disk, then order all gaps in all Rabi seasons since 2021."""
        self.seed_from_disk()

        today   = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        seasons = _get_rabi_seasons(HISTORY_START, today)

        print(f"\n{'='*65}")
        print(f"  MOSDAC HISTORICAL — {len(seasons)} Rabi season(s)")
        print(f"{'='*65}")
        for s, e in seasons:
            print(f"    {s.date()}  →  {e.date()}")
        print("\n  Dates already on disk or in DB are skipped instantly.\n")

        if input("  Start? (y/n): ").strip().lower() != "y":
            print("  Cancelled.")
            return {}

        total       = {p: {"downloaded": 0, "skipped": 0, "failed": 0}
                       for p in (Product.PET, Product.RAIN)}
        needs_order = {Product.PET: [], Product.RAIN: []}

        for start, end in seasons:
            print(f"\n  -- {start.date()} → {end.date()} --")
            d = start
            while d <= end:
                if d.month in RABI_MONTHS:
                    for product in (Product.PET, Product.RAIN):
                        r = self.download_date(d, product)
                        if r["skipped"]:
                            total[product]["skipped"] += 1
                        else:
                            needs_order[product].append(d)
                d += timedelta(days=1)

        if any(needs_order.values()):
            saved_counts = self.download_dates(needs_order)
            for product in (Product.PET, Product.RAIN):
                n_saved = saved_counts.get(product, 0)
                n_tried = len(needs_order[product])
                total[product]["downloaded"] += n_saved
                total[product]["failed"]     += n_tried - n_saved
        else:
            print("  All dates already on disk — nothing to order.")

        _print_summary(total)

        still_failed = {
            p: [d.strftime("%Y-%m-%d") for d in needs_order[p]
                if not Product.is_downloaded(d, p)]
            for p in (Product.PET, Product.RAIN)
        }

        if any(still_failed.values()):
            print(f"\n{'='*65}")
            print("  DATES STILL MISSING — manual download at:")
            print(f"  {MOSDAC_UOPS_URL}#/MyOrder")
            print(f"{'='*65}")
            for product in (Product.PET, Product.RAIN):
                if still_failed[product]:
                    tag = "PET " if product == Product.PET else "RAIN"
                    print(f"\n  [{tag}] {PRODUCT_CODE[product]}")
                    for rng in _compress_date_ranges(still_failed[product]):
                        print(f"    {rng}")
            print("\n  After downloading manually, run --seed.\n")
            print("=" * 65)

        return total

    def seed_from_disk(self) -> Dict:
        """Register all existing HDF5/HDF/TIF files in MongoDB. No network calls."""
        print(f"\n{'='*65}\n  MOSDAC — SEED FROM DISK\n{'='*65}")

        stats = {p: {"found": 0, "registered": 0, "already_in_db": 0}
                 for p in (Product.PET, Product.RAIN)}

        for product in (Product.PET, Product.RAIN):
            tag  = "PET " if product == Product.PET else "RAIN"
            seen: set = set()

            for search_dir in Product.all_search_dirs(product):
                if not search_dir.exists():
                    print(f"  [{tag}] ⚠  not found: {search_dir}")
                    continue
                files = sorted(
                    list(search_dir.glob("3RIMG_*.h5"))
                    + list(search_dir.glob("3RIMG_*.hdf"))
                    + list(search_dir.glob("3RIMG_*.tif"))
                )
                code_fragment = "L3C_PET_DLY" if product == Product.PET else "L3G_IMR_DLY"
                tifs = [f for f in files if code_fragment in f.name.upper()]
                print(f"  [{tag}] {search_dir}  ({len(tifs)} files)")

                for tif in tifs:
                    r = tif.resolve()
                    if r in seen:
                        continue
                    seen.add(r)
                    if tif.stat().st_size < 1024:
                        continue
                    m = re.search(r"\d{2}[A-Z]{3}\d{4}", tif.name.upper())
                    if not m:
                        continue
                    try:
                        date = datetime.strptime(m.group(), "%d%b%Y")
                    except ValueError:
                        continue

                    stats[product]["found"] += 1
                    if Product.is_downloaded(date, product):
                        stats[product]["already_in_db"] += 1
                        continue

                    Product.mark_downloaded(date, str(tif), product)
                    stats[product]["registered"] += 1
                    n = stats[product]["registered"]
                    if n <= 10:
                        print(f"  [{tag}] ✓ {date.date()}  {tif.name}")
                    elif n == 11:
                        print(f"  [{tag}]   … (suppressing output) …")

            print(
                f"  [{tag}] found={stats[product]['found']}  "
                f"registered={stats[product]['registered']}  "
                f"already_in_db={stats[product]['already_in_db']}"
            )

        print(f"\n{'='*65}\n  Seed complete.\n{'='*65}\n")
        return stats


# ── Helper functions ───────────────────────────────────────────────────────────
def _get_rabi_seasons(from_year: int, today: datetime) -> List[Tuple[datetime, datetime]]:
    seasons, year = [], from_year
    while True:
        s = datetime(year, 11, 1)
        # Extended collection season: 1 November through 30 September.
        e = datetime(year + 1, 9, 30)
        if s > today:
            break
        seasons.append((s, min(e, today)))
        year += 1
    return seasons


def _print_summary(results: Dict) -> None:
    print(f"\n{'='*55}")
    for product, stats in results.items():
        tag = "PET " if product == Product.PET else "RAIN"
        print(f"  {tag} | downloaded={stats.get('downloaded',0):3d} | "
              f"skipped={stats.get('skipped',0):3d} | "
              f"failed={stats.get('failed',0):3d}")
    print("=" * 55)


def _compress_date_ranges(date_strs: List[str]) -> List[str]:
    if not date_strs:
        return []
    dates = sorted(datetime.strptime(d, "%Y-%m-%d") for d in date_strs)
    ranges = []
    s = prev = dates[0]
    for d in dates[1:]:
        if (d - prev).days == 1:
            prev = d
        else:
            ranges.append(s.strftime("%Y-%m-%d") if s == prev
                          else f"{s.strftime('%Y-%m-%d')} → {prev.strftime('%Y-%m-%d')}")
            s = prev = d
    ranges.append(s.strftime("%Y-%m-%d") if s == prev
                  else f"{s.strftime('%Y-%m-%d')} → {prev.strftime('%Y-%m-%d')}")
    return ranges


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    _log_dir = Path(__file__).parent / "data" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(_log_dir / "mosdac_agent.log", mode="a"),
        ],
    )

    ap = argparse.ArgumentParser(
        description="MOSDAC PET + Rainfall downloader (Playwright, no API key)"
    )
    ap.add_argument("--seed",         action="store_true",
                    help="Register existing files on disk into MongoDB")
    ap.add_argument("--new-only",     action="store_true",
                    help="Download latest available date only (default daily mode)")
    ap.add_argument("--historical",   action="store_true",
                    help="Download all gaps across all Rabi seasons since 2021")
    ap.add_argument("--diagnose",     action="store_true",
                    help="Login, navigate to UOPS, dump page structure to /tmp/mosdac_debug/")
    ap.add_argument("--start",        metavar="YYYY-MM-DD",
                    help="Custom start date for range download")
    ap.add_argument("--end",          metavar="YYYY-MM-DD",
                    help="Custom end date for range download")
    ap.add_argument("--product",      choices=["pet", "rain", "both"], default="both")
    ap.add_argument("--show-browser", action="store_true",
                    help="Show Chrome window (recommended for first run / debugging)")
    args = ap.parse_args()

    headless = not args.show_browser
    agent    = MosdacAgent(headless=headless)

    if args.diagnose:
        print("\n=== DIAGNOSTIC MODE ===")
        print(f"Debug output: /tmp/mosdac_debug/")
        agent._browser.start()
        agent._started = True
        if agent._browser.login(agent.username, agent.password):
            agent._logged_in = True
            print("Login OK. Navigating to UOPS catalog …")
            agent._browser._goto(MOSDAC_UOPS_URL, wait=6)
            agent._browser.dump_page_structure("diagnostic_catalog")
            print("\nAlso checking #/MyOrder page …")
            agent._browser._goto(MOSDAC_UOPS_URL + "#/MyOrder", wait=4)
            agent._browser.dump_page_structure("diagnostic_myorder")
            print(f"\nDone. Check /tmp/mosdac_debug/ for screenshots and HTML files.")
        else:
            print("Login failed.")
        agent._stop()
        sys.exit(0)

    if args.seed:
        agent.seed_from_disk()
    elif args.new_only:
        agent.download_new_only()
    elif args.historical:
        agent.download_historical()
    elif args.start and args.end:
        products = (
            [Product.PET]  if args.product == "pet"  else
            [Product.RAIN] if args.product == "rain" else
            [Product.PET, Product.RAIN]
        )
        start = datetime.fromisoformat(args.start)
        end   = datetime.fromisoformat(args.end)
        missing: Dict[str, List[datetime]] = {p: [] for p in products}
        d = start
        while d <= end:
            if d.month in RABI_MONTHS:
                for p in products:
                    if not Product.is_downloaded(d, p):
                        found = Product.find_on_disk(d, p)
                        if found:
                            Product.mark_downloaded(d, str(found), p)
                        else:
                            missing[p].append(d)
            d += timedelta(days=1)
        print("\nResult:", agent.download_dates(missing))
    else:
        print(
            "\nUsage:\n"
            "  python mosdac_agent.py --seed\n"
            "  python mosdac_agent.py --new-only\n"
            "  python mosdac_agent.py --new-only --show-browser\n"
            "  python mosdac_agent.py --historical\n"
            "  python mosdac_agent.py --start 2026-01-01 --end 2026-03-16\n\n"
            "Run via scheduler (recommended):\n"
            "  python scheduler.py\n\n"
            "First-run checklist:\n"
            "  1. pip install playwright python-dotenv\n"
            "  2. playwright install chromium\n"
            "  3. Add MOSDAC_USERNAME + MOSDAC_PASSWORD to .env\n"
            "  4. python mosdac_agent.py --new-only --show-browser\n"
        )
