

"""
init_geoserver.py
─────────────────────────────────────────────────────────────────────────────
GeoServer REST API wrapper.

Fixes applied:
  - <n> → <n> in all XML payloads (GeoServer was rejecting every POST)
  - Removed all references to GEOSERVER['datastore'] (key does not exist).
    Methods that need a store name now accept `store_name` as a parameter.
  - publish_all_layers: fixed date_strings crash (was iterating dicts as
    tuples); now uses processed_collection properly.
  - create_datastores: each store points at the correct per-parameter dir
    so GeoServer can serve the right rasters.
  - update_coverage_store_file: unchanged — used by main.py to swap rasters.

FIX-GEOSERVER-1 (2026-04-16):
  Added publish_coverage() — POSTs to .../coveragestores/{store}/coverages
  to register the layer in GeoServer for the first time.  This is the missing
  step that caused configure_layer to always return 404 and assign_style to
  always return 500: update_coverage_store_file() only updates the file
  pointer; it does NOT auto-publish the coverage.

  configure_layer() now calls publish_coverage() on 404 and retries the GET
  before proceeding with the PUT, so the full sequence is safe on both first
  run (new store) and subsequent runs (existing layer refresh).

  push_to_geoserver() in main.py now checks return values and only logs
  when configure_layer + assign_style both succeed, eliminating the
  false-positive "Forecast layer ready" messages.
"""

import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from config import GEOSERVER, STUDY_AREA, DIRECTORIES, SARIMAX_CONFIG
from mongo import processed_collection

logger = logging.getLogger(__name__)


class GeoServerAPI:
    """Handle GeoServer operations via REST API."""

    def __init__(self):
        self.base_url  = GEOSERVER["url"]
        self.workspace = GEOSERVER["workspace"]
        self.auth      = HTTPBasicAuth(GEOSERVER["username"], GEOSERVER["password"])

    # ── Helpers ────────────────────────────────────────────────────────────

    def _headers(self, content_type: str = "application/xml") -> Dict:
        return {
            "Accept": "application/xml",
            "Content-Type": content_type,
            # GeoServer 2.12+ CSRF protection requires this on all POST/PUT
            # requests via the REST API. Without it, the CSRF filter returns 403
            # even when credentials are valid.
            "X-Requested-With": "XMLHttpRequest",
        }

    def _safe_xml(self, response: requests.Response) -> ET.Element:
        body = response.content.strip()
        if not body.startswith(b"<"):
            raise RuntimeError(
                f"GeoServer returned non-XML ({response.status_code}):\n"
                f"{response.text[:300]}"
            )
        return ET.fromstring(body)

    def _get(self, path: str) -> requests.Response:
        return requests.get(
            f"{self.base_url}{path}",
            auth=self.auth,
            headers=self._headers(),
            timeout=30,
        )

    def _post(self, path: str, data: str, content_type: str = "application/xml") -> requests.Response:
        return requests.post(
            f"{self.base_url}{path}",
            data=data,
            auth=self.auth,
            headers=self._headers(content_type),
            timeout=30,
        )

    def _put(self, path: str, data: str, content_type: str = "application/xml") -> requests.Response:
        return requests.put(
            f"{self.base_url}{path}",
            data=data,
            auth=self.auth,
            headers=self._headers(content_type),
            timeout=30,
        )

    # ── Workspace ──────────────────────────────────────────────────────────

    def create_workspace(self) -> bool:
        """Create workspace if it does not already exist."""
        resp = self._get("/rest/workspaces")
        existing = []
        if resp.status_code == 200:
            try:
                root     = self._safe_xml(resp)
                existing = [e.text for e in root.findall(".//name")]
            except Exception:
                pass

        if self.workspace in existing:
            logger.info(f"Workspace '{self.workspace}' already exists")
            return True

        xml = f"<workspace><name>{self.workspace}</name></workspace>"
        resp = self._post("/rest/workspaces", xml)

        if resp.status_code == 201:
            logger.info(f"Created workspace: {self.workspace}")
            return True

        logger.error(f"Failed to create workspace: {resp.status_code} {resp.text}")
        return False

    # ── Coverage Stores ────────────────────────────────────────────────────

    def create_datastores(self) -> None:
        """
        Create one GeoTIFF coverage store per parameter, pointing at
        the forecast raster directory.
        """
        forecast_dir = SARIMAX_CONFIG["forecast_raster_dir"]
        forecast_dir.mkdir(parents=True, exist_ok=True)

        for param, store_name in GEOSERVER["stores"].items():
            url  = f"/rest/workspaces/{self.workspace}/coveragestores"
            xml  = f"""<coverageStore>
  <name>{store_name}</name>
  <type>GeoTIFF</type>
  <enabled>true</enabled>
  <workspace>{self.workspace}</workspace>
  <url>file:{forecast_dir}</url>
</coverageStore>"""
            resp = self._post(url, xml)
            if resp.status_code in (201, 200):
                logger.info(f"Coverage store created/updated: {store_name}")
            elif resp.status_code == 500 and "already exists" in resp.text.lower():
                logger.info(f"Coverage store already exists: {store_name}")
            else:
                logger.warning(
                    f"Coverage store '{store_name}' response: "
                    f"{resp.status_code} {resp.text[:200]}"
                )

    # ── Upload GeoTIFF ─────────────────────────────────────────────────────

    def upload_geotiff(
        self,
        layer_name: str,
        tiff_path: Path,
        store_name: str,
        style: Optional[str] = None,
    ) -> bool:
        """Upload a GeoTIFF file to an existing coverage store."""
        logger.info(f"Uploading {layer_name} → store:{store_name}")

        url = (
            f"/rest/workspaces/{self.workspace}"
            f"/coveragestores/{store_name}/file.geotiff"
        )
        with open(tiff_path, "rb") as fh:
            resp = requests.put(
                f"{self.base_url}{url}",
                data=fh,
                auth=self.auth,
                headers={
                    "Content-Type": "image/tiff",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=120,
            )

        if resp.status_code in (200, 201):
            logger.info(f"Uploaded {layer_name}")
            if style:
                self.assign_style(layer_name, style)
            return True

        logger.error(f"Upload failed for {layer_name}: {resp.status_code} {resp.text[:300]}")
        return False

    # ── Publish coverage (FIX-GEOSERVER-1) ────────────────────────────────

    def publish_coverage(self, store_name: str, layer_name: str) -> bool:
        """
        Publish a coverage from an existing store, creating the GeoServer layer.

        This is the missing step between "store points at a file" and
        "layer is accessible via WMS/WCS".  update_coverage_store_file() only
        updates the file pointer; it does NOT auto-publish the coverage.
        Without this call, configure_layer() always gets 404 and assign_style()
        always returns 500.

        GeoServer auto-detects CRS, native envelope, and grid geometry from
        the GeoTIFF when no explicit values are provided.
        """
        # Check whether the coverage is already published to avoid duplicate-name errors.
        check_url = (
            f"/rest/workspaces/{self.workspace}"
            f"/coveragestores/{store_name}/coverages/{layer_name}"
        )
        if self._get(check_url).status_code == 200:
            logger.debug(f"Coverage already published: {layer_name}")
            return True

        url = (
            f"/rest/workspaces/{self.workspace}"
            f"/coveragestores/{store_name}/coverages"
        )
        xml = f"""<coverage>
  <name>{layer_name}</name>
  <nativeName>{layer_name}</nativeName>
  <title>{layer_name}</title>
  <enabled>true</enabled>
</coverage>"""
        resp = self._post(url, xml)

        if resp.status_code in (200, 201):
            logger.info(f"Published coverage: {layer_name} (store={store_name})")
            return True

        # GeoServer sometimes returns 500 with "already exists" on a race condition
        if resp.status_code == 500 and "already exists" in resp.text.lower():
            logger.debug(f"Coverage already exists (race): {layer_name}")
            return True

        logger.error(
            f"publish_coverage failed for '{layer_name}' (store={store_name}): "
            f"{resp.status_code} {resp.text[:300]}"
        )
        return False

    # ── Layer configuration ────────────────────────────────────────────────

    def configure_layer(self, layer_name: str, store_name: str, style: Optional[str] = None) -> bool:
        """
        Enable layer and optionally assign style.

        FIX-GEOSERVER-1: If the coverage GET returns 404 (layer was never
        published), call publish_coverage() first and then retry.  This makes
        the method safe on both first run and subsequent runs.
        """
        coverage_url = (
            f"/rest/workspaces/{self.workspace}"
            f"/coveragestores/{store_name}/coverages/{layer_name}"
        )
        resp = self._get(coverage_url)

        if resp.status_code == 404:
            # Layer not published yet — publish it first, then retry.
            logger.debug(
                f"configure_layer: coverage not found (404) for {layer_name} — publishing now"
            )
            if not self.publish_coverage(store_name, layer_name):
                logger.error(
                    f"configure_layer: publish_coverage failed for {layer_name} — cannot configure"
                )
                return False
            # Retry the GET after publish
            resp = self._get(coverage_url)

        if resp.status_code != 200:
            logger.warning(
                f"configure_layer: GET failed ({resp.status_code}) for {layer_name} "
                f"even after publish attempt"
            )
            return False

        root = self._safe_xml(resp)

        # Ensure enabled = true
        for elem in root.iter("enabled"):
            elem.text = "true"

        xml_str  = ET.tostring(root, encoding="unicode")
        resp_put = self._put(coverage_url, xml_str)

        if resp_put.status_code in (200, 201):
            logger.info(f"Configured layer: {layer_name}")
            if style:
                self.assign_style(layer_name, style)
            return True

        logger.error(f"configure_layer PUT failed: {resp_put.status_code}")
        return False

    def enable_time_dimension(self, layer_name: str) -> bool:
        """Enable time dimension for a coverage layer."""
        url  = f"/rest/layers/{self.workspace}:{layer_name}"
        resp = self._get(url)

        if resp.status_code != 200:
            logger.warning(f"enable_time_dimension: layer not found: {layer_name}")
            return False

        root    = self._safe_xml(resp)
        layer   = root.find(".//layer")
        if layer is None:
            logger.warning("enable_time_dimension: <layer> element not found")
            return False

        enabled = layer.find("enabled")
        if enabled is None:
            enabled      = ET.SubElement(layer, "enabled")
        enabled.text = "true"

        metadata = layer.find("metadata")
        if metadata is None:
            metadata = ET.SubElement(layer, "metadata")

        entry     = ET.SubElement(metadata, "entry", key="time")
        dim_info  = ET.SubElement(entry, "dimensionInfo")
        ET.SubElement(dim_info, "enabled").text      = "true"
        ET.SubElement(dim_info, "presentation").text = "LIST"
        ET.SubElement(dim_info, "resolution").text   = "P1D"
        ET.SubElement(dim_info, "units").text        = "ISO8601"

        xml_str  = ET.tostring(root, encoding="unicode")
        resp_put = self._put(url, xml_str)

        if resp_put.status_code in (200, 201):
            logger.info(f"Enabled time dimension for {layer_name}")
            return True

        logger.error(f"enable_time_dimension PUT failed: {resp_put.status_code}")
        return False

    def assign_style(self, layer_name: str, style_name: str) -> bool:
        """Assign a default SLD style to a layer."""
        url = f"/rest/layers/{self.workspace}:{layer_name}"
        xml = f"""<layer>
  <defaultStyle>
    <name>{style_name}</name>
    <workspace>{self.workspace}</workspace>
  </defaultStyle>
</layer>"""
        resp = self._put(url, xml)
        if resp.status_code in (200, 201):
            logger.info(f"Assigned style '{style_name}' to {layer_name}")
            return True
        logger.error(f"assign_style failed: {resp.status_code} {resp.text[:200]}")
        return False

    def create_style(self, style_name: str, sld_content: str) -> bool:
        """Create an SLD style in the workspace."""
        check = self._get(f"/rest/workspaces/{self.workspace}/styles/{style_name}")
        if check.status_code == 200:
            return True   # already exists

        resp = requests.post(
            f"{self.base_url}/rest/workspaces/{self.workspace}/styles",
            params={"name": style_name},
            data=sld_content,
            auth=self.auth,
            headers={"Content-Type": "application/vnd.ogc.sld+xml"},
            timeout=30,
        )
        if resp.status_code == 201:
            logger.info(f"Created style: {style_name}")
            return True
        logger.error(f"create_style failed: {resp.status_code} {resp.text[:200]}")
        return False

    # ── Live store file swap ───────────────────────────────────────────────

    def update_coverage_store_file(self, store_name: str, new_tiff_path: Path) -> bool:
        """
        Point an existing coverage store at a new GeoTIFF on disk.
        Used by main.py to swap which forecast raster is 'live'.

        Note: this only updates the file pointer.  If the coverage has never
        been published, call publish_coverage() afterwards (configure_layer
        now handles this automatically).
        """
        url = f"/rest/workspaces/{self.workspace}/coveragestores/{store_name}"
        xml = f"""<coverageStore>
  <url>file:{new_tiff_path}</url>
  <enabled>true</enabled>
</coverageStore>"""
        resp = self._put(url, xml)
        ok   = resp.status_code in (200, 201)
        if ok:
            logger.info(f"Store '{store_name}' now points at {new_tiff_path.name}")
        else:
            logger.error(
                f"update_coverage_store_file failed for '{store_name}': "
                f"{resp.status_code} {resp.text[:200]}"
            )
        return ok

    # ── Bulk publish ───────────────────────────────────────────────────────

    def publish_all_layers(self) -> Dict:
        """Publish all processed layers to GeoServer."""
        logger.info("Publishing all layers to GeoServer")
        self.create_workspace()
        self.create_datastores()

        results = {}
        for param, layer_cfg in GEOSERVER["layers"].items():
            layer_name = layer_cfg["name"]
            store_name = GEOSERVER["stores"].get(param)
            if not store_name:
                continue

            tiff_dir   = DIRECTORIES["export"]["geoserver"]
            tiff_files = list(tiff_dir.glob(f"{param}_*.tif"))
            if not tiff_files:
                logger.warning(f"No GeoTIFF for '{param}'")
                results[param] = {"status": "no_file", "layer": layer_name}
                continue

            latest = max(tiff_files, key=lambda x: x.stat().st_mtime)
            ok     = self.upload_geotiff(
                layer_name=layer_name,
                tiff_path=latest,
                store_name=store_name,
                style=layer_cfg.get("style"),
            )

            if ok:
                cursor       = processed_collection.find(
                    {"parameter": param}
                ).sort("date", 1)
                date_strings = [
                    doc["date"].strftime("%Y-%m-%d")
                    for doc in cursor
                    if "date" in doc
                ]
                results[param] = {
                    "status": "published",
                    "layer":  layer_name,
                    "dates":  date_strings,
                    "wms_url": f"{self.base_url}/{self.workspace}/wms",
                }
            else:
                results[param] = {"status": "failed", "layer": layer_name}

        return results

    # ── Layer info ─────────────────────────────────────────────────────────

    def get_layer_info(self, layer_name: str) -> Optional[Dict]:
        url  = f"/rest/layers/{self.workspace}:{layer_name}"
        resp = self._get(url)
        if resp.status_code != 200:
            return None

        root = self._safe_xml(resp)
        info: Dict = {
            "name":      layer_name,
            "enabled":   False,
            "workspace": self.workspace,
        }
        enabled_elem = root.find(".//enabled")
        if enabled_elem is not None:
            info["enabled"] = enabled_elem.text == "true"

        style_elem = root.find(".//defaultStyle")
        if style_elem is not None:
            name_elem = style_elem.find("name")
            ws_elem   = style_elem.find("workspace")
            info["style"] = {
                "name":      name_elem.text if name_elem is not None else None,
                "workspace": ws_elem.text   if ws_elem   is not None else None,
            }
        return info

    # ── Cache ──────────────────────────────────────────────────────────────

    def clear_tile_cache(self, layer_name: str) -> bool:
        """Clear GeoWebCache tiles for a layer."""
        url  = f"/gwc/rest/layers/{self.workspace}:{layer_name}/truncate"
        resp = requests.post(f"{self.base_url}{url}", auth=self.auth, timeout=30)
        if resp.status_code == 200:
            logger.info(f"Cleared GWC cache for {layer_name}")
            return True
        logger.warning(f"clear_tile_cache: {resp.status_code} {resp.text[:200]}")
        return False

    def update_layer_time(self, layer_name: str, store_name: str, dates: List[str]) -> bool:
        """Update available time values on a coverage layer."""
        url  = (
            f"/rest/workspaces/{self.workspace}"
            f"/coveragestores/{store_name}/coverages/{layer_name}"
        )
        resp = self._get(url)
        if resp.status_code != 200:
            return False

        root      = self._safe_xml(resp)
        time_info = root.find(".//dimensionInfo")
        if time_info is not None:
            time_elem = time_info.find("time")
            if time_elem is not None:
                res = time_elem.find("resolution")
                if res is None:
                    res = ET.SubElement(time_elem, "resolution")
                res.text = "P1D"

                avail = time_elem.find("availableTimes")
                if avail is None:
                    avail = ET.SubElement(time_elem, "availableTimes")
                for child in list(avail):
                    avail.remove(child)
                for d in dates:
                    ET.SubElement(avail, "time").text = d

        xml_str  = ET.tostring(root, encoding="unicode")
        resp_put = self._put(url, xml_str)
        if resp_put.status_code in (200, 201):
            logger.info(f"Updated time dimension for {layer_name}")
            return True
        return False

    def create_coverage_store(self, store_name: str, file_path: Path) -> bool:
        url = f"/rest/workspaces/{self.workspace}/coveragestores"
        xml = f"""<coverageStore>
  <name>{store_name}</name>
  <type>GeoTIFF</type>
  <enabled>true</enabled>
  <workspace>{self.workspace}</workspace>
  <url>file:{file_path}</url>
</coverageStore>"""
        resp = self._post(url, xml)
        if resp.status_code in (200, 201):
            logger.info(f"Created coverage store: {store_name}")
            return True
        logger.error(f"Failed to create store {store_name}: {resp.status_code} {resp.text}")
        return False

    def coverage_store_exists(self, store_name: str) -> bool:
        resp = self._get(
            f"/rest/workspaces/{self.workspace}/coveragestores/{store_name}.json"
        )
        return resp.status_code == 200

    def create_coverage_store_if_not_exists(
        self, store_name: str, file_path: Path
    ) -> bool:
        try:
            if not self.coverage_store_exists(store_name):
                logger.info(f"[geoserver] Creating store: {store_name}")
                return self.create_coverage_store(store_name, file_path)
            return True
        except Exception as e:
            logger.error(f"Error checking/creating store {store_name}: {e}")
            return False