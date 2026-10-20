"""Builds snap2cal.ico from the in-code tray icon (used by build_exe.bat)."""
from PIL import Image

import icon

im = icon.make_icon_image().resize((256, 256), Image.LANCZOS)
im.save("snap2cal.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote snap2cal.ico")
