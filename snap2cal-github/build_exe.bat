@echo off
rem Builds dist\snap2cal.exe (run this on Windows, from this folder).
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller || goto :fail
python make_ico.py || goto :fail

python -m PyInstaller --noconfirm --clean --onefile --noconsole --name snap2cal --icon snap2cal.ico ^
  --hidden-import pystray._win32 --hidden-import mss.windows ^
  --collect-data googleapiclient --collect-data tzdata ^
  --collect-submodules google.genai ^
  main.py || goto :fail

echo.
echo Done: %~dp0dist\snap2cal.exe
echo Copy it to a permanent folder together with credentials.json, token.json and config.env.
pause
exit /b 0

:fail
echo.
echo Build failed. Copy the messages above and send them over.
pause
exit /b 1
