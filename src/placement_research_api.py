from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from src import research_settings as _rs
except ImportError:
    try:
        import research_settings as _rs  # type: ignore
    except ImportError:
        _rs = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT_ROOT / "ui"
DATA_DIR = PROJECT_ROOT / "data"
RESEARCH_CACHE_FILE = DATA_DIR / "placement_research_by_college.json"

_cache_lock = threading.Lock()

MAIN_REPORT_USER_PROMPT = (
    "Use Google Search extensively and generate a detailed placement intelligence report "
    "for this college from a recruiter/company hiring perspective, not just a student marketing perspective.\n\n"

    "Do NOT rely only on CollegeDunia, Shiksha, or Careers360. Search across:\n"
    "- official college placement reports\n"
    "- company hiring pages\n"
    "- LinkedIn posts\n"
    "- recruiter experiences\n"
    "- alumni outcomes\n"
    "- Reddit discussions\n"
    "- Glassdoor discussions\n"
    "- placement brochures\n"
    "- internship reports\n"
    "- news articles\n"
    "- GitHub/student achievements\n"
    "- hackathon participation\n"
    "- coding contest presence\n"
    "- startup activity\n"
    "- company campus hiring announcements\n\n"

    "Analyze the college from the viewpoint of a company deciding whether to recruit there.\n\n"

    "Include:\n"
    "1. Placement quality and consistency\n"
    "2. Real recruiter presence and recurring hiring companies\n"
    "3. Quality of engineering talent inferred from outcomes\n"
    "4. Internship culture\n"
    "5. Product vs service company hiring ratio\n"
    "6. Evidence of strong CS/AI/developer ecosystem\n"
    "7. Alumni presence in notable companies\n"
    "8. Hiring trends over recent years\n"
    "9. Credibility of placement claims\n"
    "10. Any concerns, exaggerations, or lack of transparency\n"
    "11. Comparison with peer colleges when relevant\n"
    "12. Signals companies may use to evaluate this campus\n\n"

    "Use Indian placement terminology (LPA, recruiters, on-campus drives). "
    "Clearly distinguish verified facts from inferred insights. "
    "If information is weak or contradictory, explicitly mention uncertainty."
)

SYSTEM_INSTRUCTION = (
    "You are an AI placement research analyst helping evaluate Indian colleges from a recruiter and hiring perspective.\n\n"

    "Your job is NOT to produce promotional student-facing summaries.\n\n"

    "Instead, analyze:\n"
    "- actual hiring quality\n"
    "- recruiter trust signals\n"
    "- talent quality indicators\n"
    "- placement credibility\n"
    "- engineering ecosystem strength\n"
    "- alumni outcomes\n"
    "- internship culture\n"
    "- technical reputation\n"
    "- consistency of recruiter engagement\n\n"

    "Use grounded web research with Google Search. "
    "Prioritize official reports, recruiter evidence, LinkedIn, GitHub, alumni outcomes, "
    "technical achievements, and independent discussions over marketing websites.\n\n"

    "Do not invent salary numbers, recruiter names, or placement statistics. "
    "Clearly state confidence levels and limitations in the available data.\n\n"

    "Provide nuanced analysis rather than generic praise."
)

app = FastAPI(title="Placement research")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _env_or_settings(env_names: tuple[str, ...], settings_attr: str) -> str:
    for name in env_names:
        v = os.environ.get(name, "").strip()
        if v:
            return v
    if _rs is not None:
        v = str(getattr(_rs, settings_attr, "") or "").strip()
        if v:
            return v
    return ""


def _gemini_key() -> str:
    return _env_or_settings(("GEMINI_API_KEY", "GOOGLE_API_KEY"), "GEMINI_API_KEY")


def _gemini_model() -> str:
    v = os.environ.get("GEMINI_MODEL", "").strip()
    if v:
        return v
    if _rs is not None:
        v = str(getattr(_rs, "GEMINI_MODEL", "") or "").strip()
        if v:
            return v
    return "gemini-2.5-flash"


# Tried after the configured model on 429 / RESOURCE_EXHAUSTED (deduped with user model).
_BUILTIN_MODEL_FALLBACKS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
)


def _model_try_chain() -> list[str]:
    configured = _gemini_model()
    raw = os.environ.get("GEMINI_MODEL_FALLBACKS", "").strip()
    custom = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
    chain: list[str] = [configured] + custom + list(_BUILTIN_MODEL_FALLBACKS)
    seen: set[str] = set()
    out: list[str] = []
    for m in chain:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _is_quota_exhausted_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "429" in str(exc)
        or "resource_exhausted" in s
        or "quota" in s and "exceeded" in s
    )


def _quota_user_hint(tried: list[str], last_exc: Exception) -> str:
    return (
        f"Tried models in order: {', '.join(tried)}. Last error: {last_exc}\n\n"
        "About **limit: 0** on `generate_content_free_tier_*`: Google often allocates **no free quota** "
        "for that exact model on your API key/project. Fix: set `GEMINI_MODEL` in `src/research_settings.py` "
        "to **gemini-2.5-flash** or **gemini-2.5-flash-lite**, or set env `GEMINI_MODEL_FALLBACKS` to a "
        "comma-separated list to try first.\n\n"
        "Other causes: **per-minute/day free caps** (wait for the retry time in the message), many "
        "grounded searches in a short window, or you need **paid billing** enabled in AI Studio / Google Cloud.\n\n"
        "See: https://ai.google.dev/gemini-api/docs/rate-limits and https://ai.dev/rate-limit"
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ResearchChatRequest(BaseModel):
    college_name: str = Field(..., min_length=1, max_length=500)
    messages: list[ChatMessage] = Field(default_factory=list)
    main_report: bool = False
    force_refresh: bool = False


def _cache_load_unlocked() -> dict[str, Any]:
    if not RESEARCH_CACHE_FILE.is_file():
        return {}
    try:
        return json.loads(RESEARCH_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _cache_save_unlocked(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RESEARCH_CACHE_FILE.with_suffix(".json.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(RESEARCH_CACHE_FILE)


def _cache_get_entry(college: str) -> dict[str, Any] | None:
    with _cache_lock:
        data = _cache_load_unlocked()
        if college in data:
            entry = data[college]
            return dict(entry) if isinstance(entry, dict) else None
        
        import re
        c_norm = re.sub(r'[^a-z0-9]', '', college.lower().replace("&", "and"))
        for k, v in data.items():
            if re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm:
                return dict(v) if isinstance(v, dict) else None
        return None


def _cache_save_main_report(
    college: str,
    reply: str,
    sources: list[dict[str, str]],
    messages: list[dict[str, str]],
) -> None:
    with _cache_lock:
        data = _cache_load_unlocked()
        import re
        c_norm = re.sub(r'[^a-z0-9]', '', college.lower().replace("&", "and"))
        matched_key = college
        for k in data.keys():
            if re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm:
                matched_key = k
                break
        
        prev = data.get(matched_key) if isinstance(data.get(matched_key), dict) else {}
        entry: dict[str, Any] = {
            **prev,
            "college_name": matched_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "main_report_markdown": reply,
            "main_sources": sources,
            # Internal research trace — not exposed to the frontend
            "internal_research": {"messages": messages},
        }
        data[matched_key] = entry
        _cache_save_unlocked(data)


def _cache_save_chat(
    college: str,
    messages: list[dict[str, str]],
    last_sources: list[dict[str, str]],
) -> None:
    with _cache_lock:
        data = _cache_load_unlocked()
        import re
        c_norm = re.sub(r'[^a-z0-9]', '', college.lower().replace("&", "and"))
        matched_key = college
        for k in data.keys():
            if re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm:
                matched_key = k
                break
        
        prev = data.get(matched_key) if isinstance(data.get(matched_key), dict) else {}
        entry = {
            **prev,
            "college_name": matched_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            # Internal research trace — not exposed to the frontend
            "internal_research": {"messages": messages},
            "last_sources": last_sources,
        }
        data[matched_key] = entry
        _cache_save_unlocked(data)


def _grounding_sources_from_response(response: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands:
            return out
        gm = getattr(cands[0], "grounding_metadata", None)
        if gm is None:
            return out
        chunks = getattr(gm, "grounding_chunks", None) or []
        for ch in chunks:
            web = getattr(ch, "web", None)
            if web is None:
                continue
            uri = str(getattr(web, "uri", "") or "")
            title = str(getattr(web, "title", "") or "")
            if uri or title:
                out.append({"title": title, "link": uri, "snippet": ""})
    except Exception:
        return out
    return out[:24]


def _response_text(response: Any) -> str:
    try:
        t = (getattr(response, "text", None) or "").strip()
        if t:
            return t
    except Exception:
        pass
    cands = getattr(response, "candidates", None) or []
    if not cands:
        return ""
    parts = getattr(getattr(cands[0], "content", None), "parts", None) or []
    chunks: list[str] = []
    for p in parts:
        pt = getattr(p, "text", None)
        if pt:
            chunks.append(str(pt))
    return "\n".join(chunks).strip()


def _messages_to_contents(college: str, messages: list[ChatMessage]) -> list[Any]:
    from google.genai import types

    contents: list[Any] = []
    for i, m in enumerate(messages):
        text = m.content
        if i == 0 and m.role == "user":
            text = f"(Placement research for **{college}** in India.)\n\n{text}"
        role = "user" if m.role == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=text)])
        )
    return contents


def _generate_grounded(
    college: str,
    messages: list[ChatMessage],
) -> tuple[str, list[dict[str, str]], str]:
    api_key = _gemini_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Set GEMINI_API_KEY in src/research_settings.py (or environment).",
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="Install google-genai (see requirements.txt).",
        ) from e

    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[grounding_tool],
        temperature=0.35,
        max_output_tokens=8192,
    )

    contents = _messages_to_contents(college, messages)
    chain = _model_try_chain()

    for idx, model_id in enumerate(chain):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=config,
            )
        except Exception as e:
            if _is_quota_exhausted_error(e) and idx < len(chain) - 1:
                continue
            if _is_quota_exhausted_error(e):
                raise HTTPException(
                    status_code=429,
                    detail=_quota_user_hint(chain, e),
                ) from e
            raise HTTPException(status_code=502, detail=f"Gemini request failed: {e}") from e

        text = _response_text(response)
        if not text:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty response (blocked, safety, or no text).",
            )
        sources = _grounding_sources_from_response(response)
        return text, sources, model_id

    raise HTTPException(status_code=502, detail="Gemini request failed for an unknown reason.")


@app.post("/api/placement-research")
def placement_research(req: ResearchChatRequest) -> dict[str, Any]:
    college = req.college_name.strip()
    if not college:
        raise HTTPException(status_code=400, detail="college_name is required")

    if req.main_report:
        return _handle_main_report(college, req.force_refresh)

    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must include at least one user message")

    last_user = ""
    for m in reversed(req.messages):
        if m.role == "user":
            last_user = m.content.strip()
            break
    if not last_user:
        raise HTTPException(status_code=400, detail="Include a user message")

    reply, sources, model_used = _generate_grounded(college, req.messages)

    # Build full internal message log (includes all turns) for caching
    serial_messages = [m.model_dump() for m in req.messages]
    serial_messages.append({"role": "assistant", "content": reply})
    _cache_save_chat(college, serial_messages, sources[:12])

    # Return only the assistant reply — never expose internal message history
    return {
        "reply": reply,
        "sources": sources[:12],
        "cached": False,
        "messages": [],
        "model_used": model_used,
    }


def _handle_main_report(college: str, force_refresh: bool) -> dict[str, Any]:
    # --- Cache-aware: return saved report immediately if available ---
    if not force_refresh:
        entry = _cache_get_entry(college)
        if entry and entry.get("main_report_markdown"):
            src = entry.get("main_sources") or entry.get("last_sources") or []
            sources = [dict(x) for x in src if isinstance(x, dict)] if isinstance(src, list) else []
            return {
                "reply": entry["main_report_markdown"],
                "sources": sources[:12],
                "cached": True,
                # Never expose internal prompts/messages to the frontend
                "messages": [],
                "model_used": None,
            }

    chat_messages = [ChatMessage(role="user", content=MAIN_REPORT_USER_PROMPT)]
    reply, sources, model_used = _generate_grounded(college, chat_messages)

    internal_messages = [
        {"role": "user", "content": MAIN_REPORT_USER_PROMPT},
        {"role": "assistant", "content": reply},
    ]
    _cache_save_main_report(college, reply, sources[:12], internal_messages)

    return {
        "reply": reply,
        "sources": sources[:12],
        "cached": False,
        # Never expose internal prompts/messages to the frontend
        "messages": [],
        "model_used": model_used,
    }

@app.get("/api/university-groups")
def get_university_groups():
    """Returns the entire grouped JSON structure (large payload, ~26MB)."""
    path = DATA_DIR / "university_grouped_colleges.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Grouped university file not found. Run grouping script first.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read grouped file: {e}")


@app.get("/api/universities")
def get_universities():
    """Returns a lightweight list of all universities with metadata and college counts (no nested college details)."""
    path = DATA_DIR / "university_grouped_colleges.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Grouped university file not found. Run grouping script first.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Filter out the nested colleges array to keep the initial load super light
        summary_list = []
        for item in data:
            summary_list.append({
                "university_aishe_code": item.get("university_aishe_code"),
                "university_name": item.get("university_name"),
                "university_type": item.get("university_type"),
                "state": item.get("state"),
                "college_count": item.get("college_count")
            })
        return summary_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read grouped file: {e}")


@app.get("/api/universities/{u_code}/colleges")
def get_university_colleges(u_code: str):
    """Returns the list of affiliated colleges for a specific university AISHE code."""
    path = DATA_DIR / "university_grouped_colleges.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Grouped university file not found. Run grouping script first.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            if item.get("university_aishe_code") == u_code:
                return item.get("colleges") or []
        raise HTTPException(status_code=404, detail=f"University with AISHE code {u_code} not found.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read grouped file: {e}")


# Mount college intelligence router
try:
    from src.college_intelligence_api import router as intel_router
except ImportError:

    from college_intelligence_api import router as intel_router  # type: ignore
app.include_router(intel_router)

if DATA_DIR.is_dir():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")