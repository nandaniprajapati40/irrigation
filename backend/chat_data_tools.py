"""
chat_data_tools.py
==================
Structured query tools for AquaBot / Jaldrishti chat pipeline.

Provides:
  - QueryResult  — typed result returned by DataTools.answer()
  - DataTools    — classifies user queries and optionally runs structured
                   lookups (history, forecast, live-data) to inject grounded
                   context into the LLM prompt.
  - LiveStore    — lightweight in-memory store for sensor / API readings.
  - get_data_tools()    — module-level singleton accessor.
  - safe_llm_context()  — converts a QueryResult to a compact string block
                          ready to be prepended to the LLM system prompt.

This module has NO GIS or raster dependencies.  All heavy lifting is done
by the Jaldrishti backend endpoints; this module only interprets the
already-computed values that are passed to it.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter aliases  (shared with /api/live-data/latest)
# ---------------------------------------------------------------------------
PARAM_ALIASES: Dict[str, str] = {
    # IWR variants
    "iwr":                         "iwr",
    "irrigation water requirement": "iwr",
    "irrigation":                   "iwr",
    "sinchai":                      "iwr",
    # CWR variants
    "cwr":                         "cwr",
    "crop water requirement":       "cwr",
    "crop water":                   "cwr",
    "fasal paani":                  "cwr",
    # SAVI variants
    "savi":                        "savi",
    "vegetation index":             "savi",
    "canopy":                       "savi",
    # Kc variants
    "kc":                          "kc",
    "crop coefficient":             "kc",
    "fasal gunank":                 "kc",
    # ETc variants
    "etc":                         "etc",
    "etcrop":                       "etc",
    "evapotranspiration":           "etc",
    # PET variants
    "pet":                         "pet",
    "et0":                         "pet",
    "reference et":                 "pet",
    "reference evapotranspiration": "pet",
}

# ---------------------------------------------------------------------------
# Query-type classifier patterns
# ---------------------------------------------------------------------------
_QUERY_PATTERNS: List[tuple[str, str]] = [
    # Forecast / future intent
    (r"\bforecast|predict|next\s+\d+\s*day|agle|bhavishya|5[- ]day|10[- ]day|15[- ]day|upcoming", "forecast"),
    # Live / current pixel intent
    (r"\bmy field|my location|this field|clicked|current (iwr|cwr|savi|kc)|live (value|data)", "live_pixel"),
    # Irrigation decision
    (r"\bshould i irrigat|do i need water|when to irrigat|kab sinchai|irrigate today|"
     r"irrigate now|paani kab|need water|water my crop", "irrigation_decision"),
    # Growth stage
    (r"\bstage|das\b|tillering|jointing|heading|grain fill|maturat|germination|booting|"
     r"paka|anaj|bali|paudha|kya stage", "growth_stage"),
    # Soil / interval
    (r"\bsoil|mitti|clay|loam|sandy|interval|how often|kitni baar|kitne din", "soil_schedule"),
    # Formula / technical
    (r"\bformula|calculate|how is .+ calculated|what is (cwr|iwr|savi|kc|etc|pet)\b|"
     r"explain (cwr|iwr|savi|kc)", "formula_technical"),
    # Historical trend
    (r"\bhist(ory|orical)|past|season|trend|compare|pichhle", "historical_trend"),
    # System / identity
    (r"\bjaldrishti|aquabot|iirs|isro|system|who are you|what are you|project", "system_identity"),
    # Rainfall / Peff
    (r"\brain(fall)?|rainfall|barish|peff|effective rain|monsoon", "rainfall"),
]


def classify_query(query: str) -> str:
    """Return the most specific query-type label for the given text."""
    q = (query or "").lower()
    for pattern, label in _QUERY_PATTERNS:
        if re.search(pattern, q):
            return label
    return "knowledge_based"


# ---------------------------------------------------------------------------
# QueryResult
# ---------------------------------------------------------------------------
@dataclass
class QueryResult:
    query_type:  str
    answer:      Optional[str] = None
    sources:     List[str]     = field(default_factory=list)
    context:     Dict[str, Any] = field(default_factory=dict)
    extra_blocks: List[str]    = field(default_factory=list)


# ---------------------------------------------------------------------------
# LiveStore  — in-memory sensor / API readings
# ---------------------------------------------------------------------------
class LiveStore:
    """
    Thread-safe ring-buffer for live sensor ingestion.

    Values stored as: { param_name: {"value": float, "ts": iso_str, "source": str} }
    """
    _MAX_AGE_SECONDS = 3600  # 1 hour TTL

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def ingest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Accept a sensor payload dict and store normalised values.

        Expected format::

            {
              "sensor_id": "field-01",
              "timestamp":  "2025-01-15T08:30:00Z",   # optional
              "source":     "api",                     # optional
              "values": {
                  "iwr":  3.2,
                  "cwr":  4.8,
                  "savi": 0.42,
              }
            }
        """
        ts     = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
        source = payload.get("source", "sensor")
        values = payload.get("values", {})
        stored: List[str] = []

        with self._lock:
            for raw_key, raw_val in values.items():
                param = PARAM_ALIASES.get(str(raw_key).lower(), str(raw_key).lower())
                try:
                    val = float(raw_val)
                except (TypeError, ValueError):
                    continue
                self._data[param] = {"value": val, "ts": ts, "source": source}
                stored.append(param)

        logger.debug("[live_store] ingested: %s", stored)
        return {"stored_params": stored, "ts": ts}

    def latest(self, param: Optional[str] = None) -> Dict[str, Any]:
        """
        Return live readings, optionally filtered to a single param.
        Stale entries (older than _MAX_AGE_SECONDS) are excluded.
        """
        now = time.time()
        out: Dict[str, Any] = {}

        with self._lock:
            data_copy = dict(self._data)

        for key, entry in data_copy.items():
            try:
                ts_epoch = datetime.fromisoformat(
                    entry["ts"].replace("Z", "+00:00")
                ).timestamp()
                if now - ts_epoch > self._MAX_AGE_SECONDS:
                    continue
            except Exception:
                pass  # keep entries whose timestamp can't be parsed

            if param is None or key == param:
                out[key] = entry

        return out

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# ---------------------------------------------------------------------------
# DataTools  — structured context builder
# ---------------------------------------------------------------------------
class DataTools:
    """
    Classifies each incoming query, optionally fetches structured context
    (from the LiveStore or passed-in live_data dict), and returns a
    QueryResult that main.py can inject into the LLM system prompt.

    All raster / pixel lookups happen in main.py via the /api/point and
    /api/forecast endpoints — this module never touches GeoTIFFs directly.
    """

    def __init__(self, live_store: Optional[LiveStore] = None) -> None:
        self.live_store = live_store or LiveStore()

    # ------------------------------------------------------------------ #
    #  Ingestion helper (called from /api/live-data POST)                 #
    # ------------------------------------------------------------------ #

    def ingest_live(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.live_store.ingest(payload)

    # ------------------------------------------------------------------ #
    #  Core method called from _prepare_chat_context in main.py           #
    # ------------------------------------------------------------------ #

    def answer(
        self,
        query: str,
        live_data: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """
        Classify the query and build a structured answer / context block.

        Parameters
        ----------
        query:      the raw user message.
        live_data:  optional dict of {param: value} pulled from the
                    /api/point or /api/history endpoint by the caller.
                    When present, values are injected into the context so
                    the LLM can give grounded numeric answers.

        Returns
        -------
        QueryResult with .query_type, .answer (may be None),
        .sources, and .context (a free-form dict for safe_llm_context).
        """
        q_type = classify_query(query)
        result = QueryResult(query_type=q_type)

        # ── 1. Pull fresh live values (LiveStore + caller-supplied) ───────
        store_latest = self.live_store.latest()
        live_values: Dict[str, float] = {}

        for param, entry in store_latest.items():
            try:
                live_values[param] = float(entry["value"])
            except (TypeError, ValueError):
                pass

        if live_data:
            for k, v in live_data.items():
                p = PARAM_ALIASES.get(str(k).lower(), str(k).lower())
                try:
                    live_values[p] = float(v)
                except (TypeError, ValueError):
                    pass

        if live_values:
            result.sources.append("live_sensor_data")
            result.context["live_values"] = live_values

        # ── 2. Build answer / extra context per query type ────────────────
        if q_type == "irrigation_decision":
            result.answer = self._irrigation_decision(live_values)
            result.sources.append("IWR_decision_rules")

        elif q_type == "live_pixel":
            if live_values:
                lines = ["**Live field values:**"]
                for p, v in live_values.items():
                    lines.append(f"  • {p.upper()} = {v:.3f}")
                result.answer = "\n".join(lines)
            else:
                result.answer = (
                    "No live field data is currently available. "
                    "Please click a field location on the Jaldrishti map to load pixel values."
                )
            result.sources.append("pixel_api")

        elif q_type == "forecast":
            result.context["forecast_note"] = (
                "The Jaldrishti 5/10/15-day forecast is available on the map. "
                "5-day IWR > 20 mm → irrigate now. "
                "10-day IWR > 35 mm → schedule within 5 days. "
                "15-day IWR > 50 mm → plan the fortnight schedule."
            )
            result.sources.append("forecast_rules")

        elif q_type == "growth_stage":
            stage_info = self._current_stage_context()
            if stage_info:
                result.context["growth_stage"] = stage_info
                result.sources.append("wheat_stage_kb")

        elif q_type == "rainfall":
            result.context["peff_note"] = (
                "Effective rainfall (Peff) is the portion of rain that reaches the root zone. "
                "Jaldrishti uses the FAO USDA method: "
                "Peff = 0.6 × Rain − 10 mm/month  (for Rain ≤ 75 mm/month), "
                "Peff = 0.8 × Rain − 25 mm/month  (for Rain > 75 mm/month). "
                "IWR = max(CWR − Peff, 0)."
            )
            result.sources.append("peff_formula")

        elif q_type in ("formula_technical", "knowledge_based"):
            # No structured answer — RAG handles these well on its own.
            pass

        return result

    # ------------------------------------------------------------------ #
    #  Helper: IWR-based irrigation decision                              #
    # ------------------------------------------------------------------ #

    def _irrigation_decision(self, live_values: Dict[str, float]) -> Optional[str]:
        iwr = live_values.get("iwr")
        cwr = live_values.get("cwr")
        kc  = live_values.get("kc")
        savi = live_values.get("savi")

        if iwr is None:
            return None  # let RAG handle it with typical ranges

        lines: List[str] = []
        iwr_f = float(iwr)

        if iwr_f > 4.0:
            lines.append(f"**IRRIGATE** — IWR is {iwr_f:.2f} mm/day (HIGH). Irrigate within 1–3 days.")
        elif iwr_f > 2.0:
            lines.append(f"**MONITOR / PLAN** — IWR is {iwr_f:.2f} mm/day (MODERATE). Plan irrigation within 7–10 days.")
        elif iwr_f > 0.1:
            lines.append(f"**WAIT** — IWR is {iwr_f:.2f} mm/day (LOW). Check 5-day forecast first.")
        else:
            lines.append(f"**WAIT** — IWR is {iwr_f:.2f} mm/day. Rainfall or soil moisture is sufficient. No irrigation needed now.")

        if cwr is not None:
            lines.append(f"Crop water need (CWR): {float(cwr):.2f} mm/day.")
        if kc is not None:
            lines.append(f"Crop coefficient (Kc): {float(kc):.3f}.")
        if savi is not None:
            savi_f = float(savi)
            if savi_f < 0.10:
                interp = "bare soil / very sparse canopy"
            elif savi_f < 0.25:
                interp = "sparse cover / early establishment"
            elif savi_f < 0.45:
                interp = "moderate canopy / active vegetative growth"
            else:
                interp = "dense canopy / heading or grain filling"
            lines.append(f"SAVI: {savi_f:.3f} → {interp}.")

        return "  \n".join(lines)

    # ------------------------------------------------------------------ #
    #  Helper: approximate current wheat growth stage from calendar month  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _current_stage_context() -> Optional[Dict[str, Any]]:
        month = datetime.now().month
        stage_map = {
            11: {"stage": "Germination/Establishment",
                 "das_range": "0–20",
                 "kc_range": "0.30–0.40",
                 "cwr_range": "1.5–2.0 mm/day",
                 "action": "First critical irrigation at crown root initiation (DAS ~20–25)."},
            12: {"stage": "Tillering",
                 "das_range": "21–55",
                 "kc_range": "0.40–0.70",
                 "cwr_range": "2.0–3.5 mm/day",
                 "action": "Irrigation around DAS 40–45 supports tiller development."},
            1:  {"stage": "Jointing / Stem Elongation",
                 "das_range": "56–85",
                 "kc_range": "0.70–1.05",
                 "cwr_range": "3.0–4.5 mm/day",
                 "action": "CRITICAL stage. Water deficit here directly reduces yield."},
            2:  {"stage": "Booting / Heading",
                 "das_range": "86–105",
                 "kc_range": "1.05–1.15",
                 "cwr_range": "4.0–5.5 mm/day",
                 "action": "MOST CRITICAL irrigation stage for Rabi wheat."},
            3:  {"stage": "Grain Filling",
                 "das_range": "106–130",
                 "kc_range": "0.85–1.10",
                 "cwr_range": "3.5–5.0 mm/day",
                 "action": "Irrigation supports grain weight. Avoid waterlogging."},
            4:  {"stage": "Maturation",
                 "das_range": "131–150",
                 "kc_range": "0.25–0.45",
                 "cwr_range": "1.5–2.5 mm/day",
                 "action": "Stop irrigation 10–15 days before harvest unless crop stress is severe."},
        }
        return stage_map.get(month)


# ---------------------------------------------------------------------------
# safe_llm_context  — convert QueryResult to compact string block
# ---------------------------------------------------------------------------
def safe_llm_context(result: QueryResult) -> str:
    """
    Serialise a QueryResult into a compact string that can be prepended to
    the LLM system prompt without blowing the token budget.

    Returns an empty string when there is no useful structured content.
    """
    if not result:
        return ""

    parts: List[str] = []

    # Query type hint
    if result.query_type and result.query_type != "knowledge_based":
        parts.append(f"**Query type:** {result.query_type.replace('_', ' ').title()}")

    # Live values
    lv = result.context.get("live_values")
    if lv:
        rows = [f"  • {k.upper()} = {v:.3f}" for k, v in sorted(lv.items())]
        parts.append("**Live field values (from sensor/API):**\n" + "\n".join(rows))

    # Growth stage
    gs = result.context.get("growth_stage")
    if gs:
        parts.append(
            f"**Current growth stage (calendar estimate):** {gs.get('stage', '')}\n"
            f"  DAS: {gs.get('das_range', '')}, Kc: {gs.get('kc_range', '')}, "
            f"CWR: {gs.get('cwr_range', '')}\n"
            f"  Advisory: {gs.get('action', '')}"
        )

    # Forecast note
    fn = result.context.get("forecast_note")
    if fn:
        parts.append(f"**Forecast context:** {fn}")

    # Peff note
    pn = result.context.get("peff_note")
    if pn:
        parts.append(f"**Rainfall/Peff context:** {pn}")

    # Extra text blocks
    for block in (result.extra_blocks or []):
        if block and block.strip():
            parts.append(block.strip())

    # Sources
    if result.sources:
        parts.append(f"**Data sources used:** {', '.join(result.sources)}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_tools_instance: Optional[DataTools] = None
_tools_lock = threading.Lock()


def get_data_tools() -> DataTools:
    """Return the module-level DataTools singleton (thread-safe)."""
    global _tools_instance
    if _tools_instance is None:
        with _tools_lock:
            if _tools_instance is None:
                _tools_instance = DataTools()
                logger.info("[chat_data_tools] DataTools singleton initialised")
    return _tools_instance
