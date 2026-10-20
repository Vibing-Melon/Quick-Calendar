# Quick-Calendar
<img width="1672" height="941" alt="From Inbox to Calendar" src="https://github.com/user-attachments/assets/b137cba4-7f05-4f46-8da4-f039043bfedf" />

**Press a hotkey, drag a box over an email or text message, and the event lands in your Google Calendar.**

Quick-Calendar is a small Windows tray app. A vision model reads the part of the screen you select and extracts the event (meeting, interview, event poster, appointment, reservation, hangout). If everything is clear, the event is created silently and automatically with an **Undo** button. If something is ambiguous (is `04/05` April 5th or May 4th? what time zone? what year?), it asks you a quick question about only that field.

Everything here was vibe coded, I built this mainly for myself. It solved a problem for me and hopefully it will for you. 

- Windows 10/11, runs in the system tray, optionally starts with Windows
- Free to run: Google Calendar API (free) + Gemini API free tier (no credit card)
- **Bring your own keys.** You create your own Google Cloud project and Gemini key. Nothing is shared with the author or anyone else.

> This project is not affiliated with Google. "Google Calendar" and "Gemini" are Google trademarks.

---

## How it decides: create or ask

The model only *reports* what it saw and flags uncertainty. Plain code (`rules.py`) makes the decision, so behavior is predictable.

| Situation | What happens |
|---|---|
| One event, explicit date and time, future, high confidence | Created immediately, toast with **Undo** / **Edit** |
| Ambiguous date format, relative date with no anchor ("next Friday"), missing time, unclear time zone, date in the past, unclear title, low confidence | A small popup asks only about the uncertain field |
| Several events in one screenshot | Checklist to pick which to add |

Events in another time zone keep that zone (e.g. "2pm EST"), and the original time is noted in the description. If no end time is shown, a default duration is used per category (exam 2h, interview 1h, and so on, see `DURATIONS` in `gcal.py`).

## Privacy

- Screenshots are held in memory, resized, sent to the Gemini API, and discarded. They are never saved to disk or logged.
- **On the Gemini free tier, Google may use your inputs to improve its products and human reviewers may read them** (see the [Gemini API terms](https://ai.google.dev/gemini-api/terms)). Don't snip anything sensitive (passwords, medical, financial). Using a paid key changes this; check Google's current terms.
- The app asks Google for permission to view and edit events on your calendars. It only creates events and deletes the ones it just created (Undo).
- Your Google sign-in is stored in `token.json` next to the app. Keep it private.

## Cost

| Part | Cost |
|---|---|
| Google Calendar API | Free for personal use |
| Gemini API (reads the screenshot) | Free tier, with per-minute and per-day limits |

Gemini's free-tier limits are per project and per model, and Google shows your exact numbers at <https://aistudio.google.com/rate-limit> (you must be logged in). Each screenshot is one request. If you hit the limit you'll see an "Extraction failed ... 429" toast; it resets daily. Lighter "Flash-Lite" models usually have higher free limits but may misread messy screenshots more often. Set `GEMINI_MODEL` to change model.

---

## Setup

You need: Windows, Python 3.11+, a Google account.

### 1. Get the code

```
git clone https://github.com/Vibing-Melon/Quick-Calendar.git
cd snap2cal
pip install -r requirements.txt
```

(Or download the ZIP from GitHub and extract it.)

### 2. Get a free Gemini API key

1. Go to <https://aistudio.google.com/apikey> and sign in.
2. Create an API key and copy it.
3. Copy `config.env.example` to `config.env` and paste the key:

```
GEMINI_API_KEY=your-key-here
```

### 3. Create your own Google Calendar access (one time, about 10 minutes)

This app needs permission to add events to *your* calendar. Google requires every app to have its own "OAuth client", so you create one in your own free Google Cloud project. No billing or credit card is needed. (Menu names change occasionally; use the search bar at the top of the console if you can't find something.)

1. Open <https://console.cloud.google.com> and create a **new project** (any name, e.g. `snap2cal`).
2. **Enable the Calendar API:** *APIs & Services → Library*, search **Google Calendar API**, click **Enable**.
3. **Set up the consent screen:** open *Google Auth Platform* (older console: *APIs & Services → OAuth consent screen*) and click **Get started**.
   - App name: `snap2cal`; support email: yours.
   - Audience: **External**.
   - Contact email: yours. Accept the terms and **Create**.
4. **Create the OAuth client:** *Clients → Create client* (older console: *Credentials → Create credentials → OAuth client ID*).
   - Application type: **Desktop app**. Name it anything.
   - Click **Download JSON**.
5. Rename the downloaded file to **`credentials.json`** and put it in the snap2cal folder (next to `main.py`).
6. **Avoid weekly sign-ins:** open the **Audience** page.
   - Recommended: click **Publish app** (it's your own private project, so this is fine). Otherwise Google limits sign-ins for apps in "Testing" to about 7 days, and you'd have to re-approve weekly. If you stay in Testing, add your own email under **Test users** or sign-in will be blocked.

### 4. Run it

Double-click **`snap2cal.pyw`** (runs with no console window), or run `python main.py` to see errors in the terminal.

The first time, your browser opens for Google sign-in. Because your own app isn't verified by Google, you'll see **"Google hasn't verified this app"**. That's expected: click **Advanced → Go to snap2cal (unsafe)**, then allow calendar access. This only happens once.

A calendar icon appears in the system tray (bottom right, maybe under the ^ arrow).

---

## Using it

1. Press **Ctrl+Shift+E** (or use the tray menu: *Add event from screen*).
2. The screen dims. Drag a box over the message. `Esc` cancels.
3. A toast shows what was added. **Undo** deletes it; **Edit** opens it in Google Calendar.

**Tray menu:** Add event from screen · Open Google Calendar · Start with Windows (checkbox) · Open log file · Quit.

On first launch, *Start with Windows* is turned on automatically; untick it in the tray menu to turn it off.

### Settings

Set in `config.env` or as environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | required | Your Gemini key |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Any Gemini model available to your key |
| `SNAP2CAL_HOTKEY` | `ctrl+shift+e` | Global hotkey, e.g. `ctrl+alt+c` |
| `DATE_ORDER` | `DMY` | Your usual date order (`DMY` or `MDY`), only a tie-breaker |
| `EXTRACTOR_BACKEND` | `gemini` | `anthropic` to use the paid Claude API instead (needs `pip install anthropic` and `ANTHROPIC_API_KEY`) |

## Build a standalone `snap2cal.exe` (optional)

1. Double-click **`build_exe.bat`**. It installs PyInstaller and builds `dist\snap2cal.exe`.
2. Copy `snap2cal.exe`, `credentials.json`, `token.json` (after first sign-in) and `config.env` into a permanent folder, e.g. `C:\snap2cal`. The exe looks for these next to itself.
3. Quit any running copy (tray → Quit), then run the exe.

The exe is unsigned, so Windows SmartScreen may say "Windows protected your PC" (click *More info → Run anyway*), and some antivirus tools flag PyInstaller one-file exes. If that happens, change `--onefile` to `--onedir` in `build_exe.bat`. Building it yourself from source is the safest option.

## Troubleshooting

| Problem | Fix |
|---|---|
| "credentials.json was not found" | Finish step 3 and save the file next to `main.py` / the exe |
| Google says `Error 403: access_denied` | Your app is in Testing and your email isn't a test user: add it under *Audience → Test users*, or click **Publish app** |
| Asked to sign in again every week | The app is in Testing mode. Click **Publish app** (step 3.6), then delete `token.json` and sign in once more |
| `404 NOT_FOUND ... model ... no longer available` | Google retired the model. Set `GEMINI_MODEL` to a current model shown in AI Studio |
| `429 RESOURCE_EXHAUSTED` | Free-tier limit reached. Wait (daily limits reset at midnight Pacific time) or try a Flash-Lite model |
| `API key not valid` | Check `GEMINI_API_KEY` in `config.env` (no quotes or spaces needed) |
| Hotkey does nothing in some windows | Windows blocks global hotkeys over apps running as administrator. Use the tray menu, or run snap2cal as admin |
| Hotkey conflicts with another app | Change `SNAP2CAL_HOTKEY` |
| Nothing happens at startup | Open the tray menu → *Open log file* (`snap2cal.log`) |

## Project layout

```
main.py         tray app, hotkey, region selection, popups, toasts
extractor.py    screenshot -> structured events (Gemini; optional Claude)
rules.py        auto-create-or-ask decision logic (unit tested)
gcal.py         Google Calendar sign-in, create, delete
autostart.py    start with Windows (per-user registry Run key)
paths.py        app folder, config.env loading, logging
icon.py         tray icon drawn in code
tests/          unit tests for rules.py
```

Run the tests: `python -m unittest discover tests`

## Limitations

- Windows only (uses the Windows registry, `ctypes.windll`, and global hotkeys).
- Reading screenshots depends on an AI model and can be wrong. The ask-when-unsure rules are a safety net, not a guarantee. Check your calendar for anything important. (Though I haven't encountered any mistake yet but it's still better to be safe) 
- Only Google Calendar is supported (primary calendar).
- Provided as-is, with no warranty or support.

## License

[MIT](LICENSE)
