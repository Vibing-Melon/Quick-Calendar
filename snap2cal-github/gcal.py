"""Google Calendar: one-time browser sign-in, then silent create/delete."""
import os
from datetime import datetime, timedelta

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import paths
import rules

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN = os.path.join(paths.APP_DIR, "token.json")
CLIENT_SECRET = os.path.join(paths.APP_DIR, "credentials.json")

# Used when the screenshot gives no end time (minutes).
DURATIONS = {"exam": 120, "interview": 60, "meeting": 60, "appointment": 60,
             "reservation": 90, "deadline": 30, "travel": 60, "other": 60}


def get_creds() -> Credentials:
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # revoked or expired: fall through to a fresh browser sign-in
    if not creds or not creds.valid:
        creds = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES).run_local_server(port=0)
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
    return creds


def _service():
    return build("calendar", "v3", credentials=get_creds(), cache_discovery=False)


def build_body(ev: dict, local_tz: str) -> dict:
    d = rules.parse_date(ev["start_date"])
    end_d = rules.parse_date(ev.get("end_date")) or d
    tzname = ev.get("timezone") or local_tz
    notes = [ev["notes"]] if ev.get("notes") else []

    body = {"summary": ev["title"]}
    if ev.get("location"):
        body["location"] = ev["location"]

    if ev.get("all_day"):
        body["start"] = {"date": d.isoformat()}
        body["end"] = {"date": (end_d + timedelta(days=1)).isoformat()}
    else:
        t = rules.parse_time(ev["start_time"])
        start = datetime.combine(d, t)
        duration = timedelta(minutes=DURATIONS.get(ev.get("category"), 60))
        end_t = rules.parse_time(ev.get("end_time"))
        end = datetime.combine(end_d, end_t) if end_t else start + duration
        if end <= start:
            end = start + duration
        body["start"] = {"dateTime": start.isoformat(), "timeZone": tzname}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": tzname}
        if tzname != local_tz:
            notes.append(f"Original time: {start:%H:%M} ({tzname})")

    notes.append("Added from screenshot")
    body["description"] = "\n".join(notes)
    return body


def create_event(ev: dict, local_tz: str) -> dict:
    res = _service().events().insert(calendarId="primary", body=build_body(ev, local_tz)).execute()
    return {"id": res["id"], "link": res.get("htmlLink")}


def delete_event(event_id: str) -> None:
    _service().events().delete(calendarId="primary", eventId=event_id).execute()
