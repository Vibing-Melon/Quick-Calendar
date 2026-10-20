"""snap2cal: press a hotkey, drag over an email/text, get a calendar event."""
import ctypes
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk
from zoneinfo import ZoneInfo

import keyboard
import mss
import pystray
from PIL import Image
from tzlocal import get_localzone_name

import paths

paths.load_env()  # must run before extractor reads its settings

import autostart  # noqa: E402
import extractor  # noqa: E402
import gcal  # noqa: E402
import icon  # noqa: E402
import rules  # noqa: E402

log = logging.getLogger("snap2cal")

HOTKEY = os.getenv("SNAP2CAL_HOTKEY", "ctrl+shift+e")

try:  # make Tk coordinates match real screen pixels on scaled displays
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class App:
    def __init__(self):
        self.tzname = get_localzone_name()
        self.tz = ZoneInfo(self.tzname)
        self.root = tk.Tk()
        self.root.withdraw()
        self.q = queue.Queue()
        self.busy = False
        self._toast = None
        keyboard.add_hotkey(HOTKEY, lambda: self.q.put(("hotkey", None)))
        self.root.report_callback_exception = lambda *exc: log.error("UI error", exc_info=exc)
        self.icon = self.make_tray()
        self.icon.run_detached()
        self.root.after(100, self.poll)

    # ---------- tray ----------
    def make_tray(self):
        def open_log(*_):
            if os.path.exists(paths.LOG_FILE):
                os.startfile(paths.LOG_FILE)

        menu = pystray.Menu(
            pystray.MenuItem(f"Add event from screen ({HOTKEY})", lambda *_: self.q.put(("tray_capture", None)), default=True),
            pystray.MenuItem("Open Google Calendar", lambda *_: webbrowser.open("https://calendar.google.com")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start with Windows", lambda *_: autostart.toggle(), checked=lambda _i: autostart.is_enabled()),
            pystray.MenuItem("Open log file", open_log),
            pystray.MenuItem("Quit", lambda *_: self.q.put(("quit", None))),
        )
        return pystray.Icon("snap2cal", icon.make_icon_image(), "snap2cal", menu)

    def quit(self):
        try:
            self.icon.stop()
        except Exception:
            pass
        keyboard.unhook_all()
        self.root.destroy()

    # ---------- event loop ----------
    def poll(self):
        self.root.after(100, self.poll)
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "hotkey" and not self.busy:
                    self.capture()
                elif kind == "events":
                    self.handle_events(payload)
                elif kind == "created":
                    self.on_created(*payload)
                elif kind == "error":
                    self.busy = False
                    self.toast("⚠ " + payload, ms=10000)
                elif kind == "undone":
                    self.toast("Removed from your calendar.", ms=3000)
                elif kind == "tray_capture":
                    # small delay so the tray menu has closed before the screen is grabbed
                    self.root.after(300, lambda: None if self.busy else self.capture())
                elif kind == "quit":
                    return self.quit()
        except queue.Empty:
            pass
        except Exception as e:
            log.exception("poll error")
            self.busy = False
            self.toast(f"⚠ {e}", ms=10000)

    # ---------- capture ----------
    def capture(self):
        self.busy = True
        with mss.mss() as sct:
            mon = sct.monitors[0]  # all screens
            raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.3)
        cv = tk.Canvas(ov, bg="black", highlightthickness=0, cursor="crosshair")
        cv.pack(fill="both", expand=True)
        st = {}

        def down(e):
            st["x0"], st["y0"] = e.x, e.y
            st["r"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#4ade80", width=2)

        def move(e):
            if "r" in st:
                cv.coords(st["r"], st["x0"], st["y0"], e.x, e.y)

        def up(e):
            if "x0" not in st:
                return cancel()
            x0, x1 = sorted((st["x0"], e.x))
            y0, y1 = sorted((st["y0"], e.y))
            ov.destroy()
            if x1 - x0 < 15 or y1 - y0 < 15:
                self.busy = False
                return
            self.extract(img.crop((x0, y0, x1, y1)))

        def cancel(_e=None):
            ov.destroy()
            self.busy = False

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        ov.bind("<Escape>", cancel)
        ov.focus_force()

    def extract(self, crop):
        self.toast("Reading…", ms=20000)

        def work():
            try:
                evs = extractor.extract_events(crop, datetime.now(self.tz), self.tzname)
            except Exception as e:
                log.exception("extraction failed")
                self.q.put(("error", f"Extraction failed: {e}"))
            else:
                self.q.put(("events", evs))

        threading.Thread(target=work, daemon=True).start()

    # ---------- decide / ask / create ----------
    def handle_events(self, events):
        if not events:
            self.busy = False
            return self.toast("No event found in that selection.", ms=4000)
        self.close_toast()
        if len(events) > 1:
            events = self.select_events(events)
        now = datetime.now(self.tz)
        ready = []
        for ev in events:
            qs = rules.decide(ev, now, self.tzname)
            if qs:
                answers = self.ask(ev, qs)
                if answers is None:
                    continue
                try:
                    rules.apply_answers(ev, answers)
                except rules.Cancelled:
                    continue
                except ValueError as e:
                    self.toast(f"⚠ {e}", ms=8000)
                    continue
            ready.append(ev)
        if not ready:
            self.busy = False
            return
        self.toast("Adding to calendar…", ms=20000)
        threading.Thread(target=self.create_all, args=(ready,), daemon=True).start()

    def create_all(self, events):
        results, errors = [], []
        for ev in events:
            try:
                r = gcal.create_event(ev, self.tzname)
                r["summary"] = self.describe(ev)
                results.append(r)
            except Exception as e:
                log.exception("calendar create failed")
                errors.append(str(e))
        if results:
            self.q.put(("created", (results, errors)))
        else:
            self.q.put(("error", "Calendar error: " + "; ".join(errors)))

    def on_created(self, results, errors):
        self.busy = False
        text = "✓ " + (results[0]["summary"] if len(results) == 1 else f"{len(results)} events added")
        if errors:
            text += f"  ({len(errors)} failed)"
        self.toast(text, actions=[
            ("Undo", lambda: self.undo(results)),
            ("Edit", lambda: webbrowser.open(results[0]["link"])),
        ], ms=9000)

    def undo(self, results):
        def work():
            for r in results:
                try:
                    gcal.delete_event(r["id"])
                except Exception:
                    pass
            self.q.put(("undone", None))
        threading.Thread(target=work, daemon=True).start()

    # ---------- UI helpers ----------
    def describe(self, ev):
        s = f"{ev.get('title') or 'Untitled'} · {ev.get('start_date') or '?'}"
        if ev.get("start_time"):
            s += f" {ev['start_time']}"
        elif ev.get("all_day"):
            s += " (all day)"
        if ev.get("timezone"):
            s += f" ({ev['timezone']})"
        return s

    def close_toast(self):
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
            self._toast = None

    def toast(self, text, actions=(), ms=8000):
        self.close_toast()
        t = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg="#222")
        tk.Label(t, text=text, fg="white", bg="#222", font=("Segoe UI", 10),
                 justify="left", padx=14, pady=10, wraplength=380).pack(side="left")

        def run(cb):
            self.close_toast()
            cb()

        for label, cb in actions:
            tk.Button(t, text=label, command=lambda cb=cb: run(cb), relief="flat",
                      bg="#444", fg="white", padx=8).pack(side="left", padx=4, pady=10)
        t.update_idletasks()
        w, h = t.winfo_width(), t.winfo_height()
        t.geometry(f"+{t.winfo_screenwidth() - w - 24}+{t.winfo_screenheight() - h - 64}")
        self._toast = t

        def expire():
            if self._toast is t:
                self.close_toast()

        t.after(ms, expire)

    def center(self, win):
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{(win.winfo_screenwidth() - w) // 2}+{(win.winfo_screenheight() - h) // 3}")

    def select_events(self, events):
        win = tk.Toplevel(self.root)
        win.title("Several events found")
        win.attributes("-topmost", True)
        tk.Label(win, text="Which ones should I add?", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        vars_ = []
        for ev in events:
            v = tk.BooleanVar(value=True)
            tk.Checkbutton(win, text=self.describe(ev), variable=v, anchor="w", justify="left").pack(fill="x", padx=14)
            vars_.append(v)
        ok = {"v": False}

        def accept():
            ok["v"] = True
            win.destroy()

        row = tk.Frame(win)
        row.pack(pady=12)
        tk.Button(row, text="Add selected", command=accept).pack(side="left", padx=6)
        tk.Button(row, text="Cancel", command=win.destroy).pack(side="left")
        self.center(win)
        win.focus_force()
        win.wait_window()
        return [e for e, v in zip(events, vars_) if v.get()] if ok["v"] else []

    def ask(self, ev, qs):
        """Show only the uncertain fields. Returns {field: value} or None if cancelled."""
        win = tk.Toplevel(self.root)
        win.title("Add to calendar")
        win.attributes("-topmost", True)
        tk.Label(win, text=self.describe(ev), font=("Segoe UI", 10, "bold"),
                 justify="left", wraplength=420).pack(anchor="w", padx=14, pady=(12, 0))
        vars_, first = {}, None
        for q in qs:
            tk.Label(win, text=q["prompt"], anchor="w", justify="left", wraplength=420).pack(fill="x", padx=14, pady=(10, 2))
            if q["field"] == "confirm":
                vars_["confirm"] = tk.StringVar(value="Add it")
                continue
            var = tk.StringVar(value=q["options"][0] if q["options"] else "")
            if q["options"]:
                w = ttk.Combobox(win, textvariable=var, values=q["options"], width=40)
            else:
                w = tk.Entry(win, textvariable=var, width=43)
            w.pack(padx=14)
            first = first or w
            vars_[q["field"]] = var
        out = {"v": None}

        def accept():
            out["v"] = {k: v.get() for k, v in vars_.items()}
            win.destroy()

        row = tk.Frame(win)
        row.pack(pady=12)
        tk.Button(row, text="Add to calendar", command=accept).pack(side="left", padx=6)
        tk.Button(row, text="Cancel", command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda _e: accept())
        win.bind("<Escape>", lambda _e: win.destroy())
        self.center(win)
        win.focus_force()
        if first:
            first.focus_set()
        win.wait_window()
        return out["v"]


_MUTEX = None


def already_running() -> bool:
    global _MUTEX
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "snap2cal_single_instance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def message_box(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, "snap2cal", 0x10)


def main():
    paths.setup_logging()
    if already_running():
        message_box("snap2cal is already running. Look for its icon in the system tray (bottom right, maybe under the ^ arrow).")
        return
    problem = extractor.key_problem()
    if problem:
        message_box(problem)
        return
    if not os.path.exists(gcal.TOKEN) and not os.path.exists(gcal.CLIENT_SECRET):
        message_box("credentials.json was not found.\n\nFollow the Google Calendar setup in the README, "
                    f"then save the downloaded file as credentials.json in:\n{paths.APP_DIR}")
        return
    try:
        if not os.path.exists(gcal.TOKEN):
            gcal.get_creds()  # first run only: opens the browser for Google sign-in
    except Exception as e:
        log.exception("google sign-in failed")
        message_box(f"Google Calendar sign-in failed:\n{e}\n\nCheck that credentials.json is in {paths.APP_DIR}")
        return
    if not os.path.exists(paths.FIRST_RUN_FLAG):  # first launch: turn on start-with-Windows once
        try:
            autostart.enable()
            open(paths.FIRST_RUN_FLAG, "w").write("1")
        except Exception:
            log.exception("could not enable autostart")
    try:  # exe only: re-point an old startup entry (e.g. from the .pyw version) at this exe
        if getattr(sys, "frozen", False) and autostart.is_enabled() and autostart.registered() != autostart.command():
            autostart.enable()
    except Exception:
        log.exception("could not update autostart entry")
    app = App()
    app.toast(f"snap2cal is running · {HOTKEY.upper()} to add an event", ms=4000)
    app.root.mainloop()


if __name__ == "__main__":
    main()
