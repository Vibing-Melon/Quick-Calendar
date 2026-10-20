"""Tray icon image, drawn in code so there is no asset file to ship."""
from PIL import Image, ImageDraw


def make_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 8, 60, 60), radius=9, fill="white", outline="#1a73e8", width=3)
    d.rounded_rectangle((4, 8, 60, 26), radius=9, fill="#1a73e8")
    d.rectangle((4, 18, 60, 26), fill="#1a73e8")
    for x in (18, 46):
        d.rounded_rectangle((x - 3, 2, x + 3, 14), radius=3, fill="#174ea6")
    for row in (34, 46):
        for col in (12, 27, 42):
            d.rectangle((col, row, col + 9, row + 7), fill="#9aa0a6")
    return img
