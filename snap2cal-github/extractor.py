"""Screenshot -> structured calendar events via a vision model.

Backends (set EXTRACTOR_BACKEND):
  gemini    (default) Google Gemini API free tier. No credit card needed.
  anthropic Claude API (paid).

The image lives only in memory: it is resized, sent, and discarded.
"""
import base64
import io
import json
import os
import re

from PIL import Image

BACKEND = os.getenv("EXTRACTOR_BACKEND", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
DATE_ORDER = os.getenv("DATE_ORDER", "DMY")  # your usual order; only a tie-breaker
MAX_SIDE = 1568

SYSTEM = """You read a screenshot of an email, text message, or web page and extract calendar events from it.
Reply with ONLY a JSON object (no prose, no code fences) shaped like:
{"events":[{
  "title": string|null,
  "category": "meeting"|"interview"|"exam"|"appointment"|"reservation"|"deadline"|"travel"|"other",
  "start_date": "YYYY-MM-DD"|null,
  "start_time": "HH:MM"|null,        (24-hour)
  "end_date": "YYYY-MM-DD"|null,
  "end_time": "HH:MM"|null,
  "all_day": boolean,
  "timezone": IANA name|null,        (only if the screenshot states or clearly implies one, e.g. "2pm EST" -> "America/New_York")
  "location": string|null,
  "notes": string|null,              (meeting link, dial-in, short useful context; max 300 chars)
  "confidence": "high"|"medium"|"low",
  "date_alternatives": ["YYYY-MM-DD", ...],
  "date_issues": [ ... ]
}]}

date_issues may contain any of:
- "ambiguous_date_format": day/month order cannot be determined (both numbers <= 12 and no month name or other clue). Put your best guess in start_date and every plausible reading in date_alternatives.
- "relative_date_no_anchor": the date is relative ("tomorrow", "next Friday") and the screenshot shows no sent date/timestamp to anchor it.
- "no_time": no start time is shown (and the event is not explicitly all-day).
- "timezone_unclear": the time seems to belong to another time zone (abbreviation you cannot resolve, another city) and you cannot determine it.
- "title_unclear": you cannot tell what the event is.

Rules:
- Never invent details. Leave a field null instead of guessing.
- Resolve relative dates against the visible sent timestamp if there is one; otherwise do NOT resolve them, and flag relative_date_no_anchor (still give your best guess using today's date).
- One entry per distinct event. Ignore promotional boilerplate and unsubscribe text.
- A date range gives start_date and end_date.
- confidence is "high" only if every field you filled is explicit in the screenshot.
- If there is no event, return {"events":[]}."""


def key_problem():
    """Return a human-readable message if the API key is missing, else None."""
    if BACKEND == "gemini":
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            return "Set GEMINI_API_KEY first (free key: https://aistudio.google.com/apikey). See README."
    elif BACKEND == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "Set ANTHROPIC_API_KEY first. See README."
    else:
        return f"Unknown EXTRACTOR_BACKEND '{BACKEND}' (use gemini or anthropic)."
    return None


def _resized(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The model did not return JSON.")
    return json.loads(text[start : end + 1])


def _call_gemini(img: Image.Image, context: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[img, context],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
        ),
    )
    return resp.text or ""


def _call_anthropic(img: Image.Image, context: str) -> str:
    import anthropic

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.standard_b64encode(buf.getvalue()).decode()
    msg = anthropic.Anthropic().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                {"type": "text", "text": context},
            ],
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def extract_events(img: Image.Image, now, tzname: str) -> list[dict]:
    context = (
        f"Today is {now:%A %Y-%m-%d}; the current local time is {now:%H:%M}. "
        f"The user's time zone is {tzname}. Their usual date order is {DATE_ORDER} "
        "(use it only to make your best guess, never to hide an ambiguity)."
    )
    img = _resized(img)
    text = _call_gemini(img, context) if BACKEND == "gemini" else _call_anthropic(img, context)
    events = _parse_json(text).get("events", [])
    return [e for e in events if isinstance(e, dict)]
