"""
college_intelligence_api.py

FastAPI router mounted into placement_research_api.py.

Endpoints:
  POST /api/college/collect          <- single button: discover URL + official + external
  POST /api/college/confirm-url      <- manual URL override only
  GET  /api/college/profile/{name}   <- return cached profile
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INTEL_CACHE_FILE = DATA_DIR / "college_intelligence_by_college.json"

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/college", tags=["college-intelligence"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CollectRequest(BaseModel):
    college_name: str = Field(..., min_length=1, max_length=500)
    force_refresh: bool = False

class ConfirmUrlRequest(BaseModel):
    college_name: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=2000)

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _load() -> dict[str, Any]:
    if not INTEL_CACHE_FILE.is_file():
        return {}
    try:
        return json.loads(INTEL_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INTEL_CACHE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INTEL_CACHE_FILE)


def _get_entry(college: str) -> dict[str, Any]:
    with _lock:
        data = _load()
        if college in data:
            return dict(data[college] or {})
        
        import re
        c_norm = re.sub(r'[^a-z0-9]', '', college.lower().replace("&", "and"))
        for k, v in data.items():
            if re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm:
                return dict(v or {})
        return {}


def _update_entry(college: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = _load()
        import re
        c_norm = re.sub(r'[^a-z0-9]', '', college.lower().replace("&", "and"))
        matched_key = college
        for k in data.keys():
            if re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm:
                matched_key = k
                break
        
        entry = dict(data.get(matched_key) or {})
        entry.update(patch)
        entry["college_name"] = matched_key
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        data[matched_key] = entry
        _save(data)
        return dict(entry)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_scraper():
    try:
        from src import college_scraper as cs
    except ImportError:
        import college_scraper as cs  # type: ignore
    return cs


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/collect")
def collect_all(req: CollectRequest) -> dict[str, Any]:
    """
    Single endpoint triggered by the Generate button.
    Does everything in sequence:
      1. Discover + auto-confirm official URL (uses cached URL if already known)
      2. Fetch and parse official website pages
      3. Gemini grounding for all external sources
    Returns the full profile.
    All steps are cache-aware unless force_refresh=True.
    """
    college = req.college_name.strip()
    if not college:
        raise HTTPException(status_code=400, detail="college_name is required")

    cs = _get_scraper()
    entry = _get_entry(college)

    # Return fully cached profile if both sections already exist
    if (not req.force_refresh
            and entry.get("official", {}).get("markdown")
            and entry.get("external", {}).get("markdown")):
        return {
            "profile": entry,
            "cached": True,
        }

    errors: dict[str, str] = {}

    # ----------------------------------------------------------------
    # Step 1: URL discovery (silent — never shown to user)
    # ----------------------------------------------------------------
    official_url: str | None = (
        entry.get("official_url") if entry.get("official_url_confirmed") else None
    )

    if not official_url:
        try:
            discovered = cs.discover_official_url(college)
            if discovered:
                confirmed, reason = cs.auto_confirm_url(college, discovered)
                url_patch: dict[str, Any] = {
                    "official_url": discovered,
                    "official_url_confirmed": confirmed,
                    "official_url_confirm_reason": reason,
                }
                if confirmed:
                    url_patch["official_url_confirmed_at"] = _now_iso()
                    official_url = discovered
                entry = _update_entry(college, url_patch)
            else:
                errors["url_discovery"] = "Could not find official URL"
        except Exception as e:
            errors["url_discovery"] = str(e)

    # ----------------------------------------------------------------
    # Step 2: Official website scrape + Gemini parse
    # ----------------------------------------------------------------
    if official_url and (req.force_refresh or not entry.get("official", {}).get("markdown")):
        try:
            official_result = cs.fetch_official(college, official_url)
            entry = _update_entry(college, {"official": official_result})
        except Exception as e:
            errors["official"] = str(e)
            entry = _update_entry(college, {
                "official": {
                    "fetched_at": _now_iso(),
                    "error": str(e),
                    "markdown": "",
                    "pages_crawled": [],
                }
            })
    elif not official_url:
        entry = _update_entry(college, {
            "official": {
                "fetched_at": _now_iso(),
                "error": errors.get("url_discovery", "No official URL found"),
                "markdown": "",
                "pages_crawled": [],
            }
        })

    # ----------------------------------------------------------------
    # Step 3: External sources via Gemini grounding
    # ----------------------------------------------------------------
    if req.force_refresh or not entry.get("external", {}).get("markdown"):
        try:
            external_result = cs.fetch_external(college)
            entry = _update_entry(college, {"external": external_result})
        except Exception as e:
            errors["external"] = str(e)
            entry = _update_entry(college, {
                "external": {
                    "fetched_at": _now_iso(),
                    "error": str(e),
                    "markdown": "",
                    "sources": [],
                }
            })

    entry = _get_entry(college)

    return {
        "profile": entry,
        "cached": False,
        "errors": errors or None,
    }


@router.post("/confirm-url")
def confirm_url(req: ConfirmUrlRequest) -> dict[str, Any]:
    """
    Manual URL override — user pastes the correct URL.
    Clears cached official data so next collect re-scrapes with the new URL.
    """
    college = req.college_name.strip()
    url = req.url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url

    cs = _get_scraper()
    confirmed, reason = cs.auto_confirm_url(college, url)

    _update_entry(college, {
        "official_url": url,
        "official_url_confirmed": True,
        "official_url_confirm_reason": reason,
        "official_url_confirmed_at": _now_iso(),
        "official_url_manually_set": True,
        "official": {},  # clear so next collect re-scrapes
    })

    return {"url": url, "confirmed": confirmed, "reason": reason}


@router.get("/profile/{college_name:path}")
def get_profile(college_name: str) -> dict[str, Any]:
    """Return the full cached intelligence profile for a college."""
    return _get_entry(college_name.strip()) or {}