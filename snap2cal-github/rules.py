"""Decides whether an extracted event can be created silently or needs a question.

Plain code on purpose: the behaviour is predictable and easy to tweak.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dateutil import parser as dparser


class Cancelled(Exception):
    pass


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    try:
        return dparser.parse(s, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def parse_time(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        return time.fromisoformat(s)
    except ValueError:
        pass
    try:
        return dparser.parse(s).time()
    except (ValueError, OverflowError):
        return None


def valid_tz(name) -> bool:
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def _q(field, prompt, options=None):
    return {"field": field, "prompt": prompt, "options": [o for o in (options or []) if o]}


def decide(ev: dict, now: datetime, local_tz: str) -> list[dict]:
    """Return a list of questions. Empty list = safe to auto-create."""
    issues = set(ev.get("date_issues") or [])
    qs = []

    title = (ev.get("title") or "").strip()
    if not title or "title_unclear" in issues:
        qs.append(_q("title", "What should this event be called?", [title]))

    d = parse_date(ev.get("start_date"))
    t = parse_time(ev.get("start_time"))
    tzname = ev.get("timezone")
    tz_ok = (not tzname) or valid_tz(tzname)

    date_asked = False
    if d is None or issues & {"ambiguous_date_format", "relative_date_no_anchor"}:
        alts = [x for x in (ev.get("date_alternatives") or [])]
        if ev.get("start_date"):
            alts.insert(0, ev["start_date"])
        seen, opts = set(), []
        for a in alts:
            pd = parse_date(a)
            if pd and pd.isoformat() not in seen:
                seen.add(pd.isoformat())
                opts.append(pd.isoformat())
        prompt = "Which date is it?" if opts else "I couldn't find a date. Which date? (YYYY-MM-DD)"
        qs.append(_q("start_date", prompt, opts))
        date_asked = True

    if (t is None and not ev.get("all_day")) or "no_time" in issues:
        qs.append(_q("start_time", "No time was shown. What time? (HH:MM, or pick All day)", ["All day"]))

    tz_asked = False
    if "timezone_unclear" in issues or not tz_ok:
        qs.append(_q("timezone", "Which time zone is this time in?", [local_tz, tzname if tz_ok else None, "UTC"]))
        tz_asked = True

    # Past dates are almost always a misread (wrong year, wrong day/month order).
    if d and t and not date_asked and not tz_asked and tz_ok:
        when = datetime.combine(d, t, tzinfo=ZoneInfo(tzname or local_tz))
        if when < now:
            qs.append(_q("start_date", "That date has already passed. Which date did you mean? (YYYY-MM-DD)", []))

    if not qs and ev.get("confidence") != "high":
        qs.append(_q("confirm", "I'm not fully sure I read this right. Add it anyway?"))

    return qs


def apply_answers(ev: dict, answers: dict) -> None:
    for field, val in answers.items():
        val = (val or "").strip()
        if field == "confirm":
            continue
        if field == "title":
            if val:
                ev["title"] = val
        elif field == "start_date":
            d = parse_date(val)
            if d is None:
                raise ValueError(f"Couldn't read the date '{val}'. Use YYYY-MM-DD.")
            ev["start_date"] = d.isoformat()
            ev["end_date"] = None
        elif field == "start_time":
            if val.lower().startswith("all"):
                ev["all_day"], ev["start_time"], ev["end_time"] = True, None, None
            else:
                t = parse_time(val)
                if t is None:
                    raise ValueError(f"Couldn't read the time '{val}'. Use HH:MM.")
                ev["start_time"], ev["all_day"] = t.strftime("%H:%M"), False
        elif field == "timezone":
            if not valid_tz(val):
                raise ValueError(f"Unknown time zone '{val}'. Use a name like Europe/Paris.")
            ev["timezone"] = val
    ev["date_issues"] = []
