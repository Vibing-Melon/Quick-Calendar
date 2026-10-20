"""Start with Windows, via the per-user Run registry key (no admin needed)."""
import os
import sys
import winreg

import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "snap2cal"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")  # pythonw = no console window
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.join(paths.APP_DIR, "main.py")}"'


def registered():
    """The command currently stored in the Run key, or None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, NAME)[0]
    except FileNotFoundError:
        return None


def is_enabled() -> bool:
    return registered() is not None


def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except FileNotFoundError:
        pass


def toggle() -> None:
    disable() if is_enabled() else enable()
