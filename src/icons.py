"""Simple line icons and the window badge, drawn with Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
import customtkinter as ctk

BLUE = "#106EBE"
MINT = "#0FFCBE"
WHITE = "#FFFFFF"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _pen(hex_color: str, width: int = 2) -> dict:
    return {"outline": hex_color, "width": width}


def _canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _line(draw: ImageDraw.ImageDraw, points, color: str, width: int = 2) -> None:
    draw.line(points, fill=color, width=width, joint="curve")


def draw_icon(name: str, color: str, size: int = 20) -> Image.Image:
    image, draw = _canvas(size)
    pad = max(2, size // 10)
    x0, y0, x1, y1 = pad, pad, size - pad - 1, size - pad - 1
    mid_x, mid_y = size // 2, size // 2
    stroke = max(2, size // 12)

    if name == "camera":
        draw.rounded_rectangle((x0, y0 + 3, x1, y1), radius=4, **_pen(color, stroke))
        draw.ellipse((mid_x - 4, mid_y - 2, mid_x + 5, mid_y + 7), **_pen(color, stroke))
        draw.rectangle((x1 - 7, y0 + 5, x1 - 3, y0 + 8), fill=color)
    elif name == "folder":
        draw.polygon([(x0, y0 + 4), (x0 + 6, y0 + 4), (x0 + 8, y0 + 7), (x1, y0 + 7), (x1, y1), (x0, y1)], outline=color, width=stroke)
    elif name == "folder-out":
        draw.polygon([(x0, y0 + 4), (x0 + 5, y0 + 4), (x0 + 7, y0 + 7), (x1 - 5, y0 + 7), (x1 - 5, y1), (x0, y1)], outline=color, width=stroke)
        _line(draw, [(x1 - 6, mid_y), (x1, mid_y)], color, stroke)
        _line(draw, [(x1 - 3, mid_y - 3), (x1, mid_y), (x1 - 3, mid_y + 3)], color, stroke)
    elif name == "sort":
        _line(draw, [(x0, y0 + 2), (x1, y0 + 2)], color, stroke)
        _line(draw, [(x0, mid_y), (x1 - 3, mid_y)], color, stroke)
        _line(draw, [(x0, y1 - 2), (mid_x + 1, y1 - 2)], color, stroke)
        _line(draw, [(x1 - 2, y1 - 6), (x1 - 2, y1), (x1 + 1, y1 - 3)], color, stroke)
    elif name == "open":
        draw.rounded_rectangle((x0, y0 + 2, x1 - 4, y1 - 2), radius=3, **_pen(color, stroke))
        _line(draw, [(x1 - 6, y0 + 4), (x1, y0), (x1, y0 + 5)], color, stroke)
        _line(draw, [(x1 - 5, y0 + 1), (x1, y0)], color, stroke)
    elif name == "save":
        draw.rounded_rectangle((x0, y0, x1, y1), radius=3, **_pen(color, stroke))
        draw.polygon([(mid_x - 3, mid_y + 1), (mid_x, mid_y + 4), (mid_x + 5, mid_y - 3)], outline=color, width=stroke)
    elif name == "pause":
        draw.rounded_rectangle((x0 + 3, y0 + 1, mid_x - 2, y1 - 1), radius=2, fill=color)
        draw.rounded_rectangle((mid_x + 2, y0 + 1, x1 - 3, y1 - 1), radius=2, fill=color)
    elif name == "play":
        draw.polygon([(x0 + 4, y0 + 1), (x1 - 1, mid_y), (x0 + 4, y1 - 1)], fill=color)
    elif name == "stop":
        draw.rounded_rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), radius=3, fill=color)
    elif name == "back":
        _line(draw, [(mid_x + 3, y0 + 2), (x0 + 2, mid_y), (mid_x + 3, y1 - 2)], color, stroke)
    elif name == "photos":
        draw.rounded_rectangle((x0, y0 + 3, x1 - 3, y1), radius=3, **_pen(color, stroke))
        draw.rounded_rectangle((x0 + 3, y0, x1, y1 - 3), radius=3, **_pen(color, stroke))
    elif name == "check":
        draw.ellipse((x0, y0, x1, y1), **_pen(color, stroke))
        _line(draw, [(x0 + 3, mid_y), (mid_x - 1, y1 - 4), (x1 - 2, y0 + 4)], color, stroke)
    elif name == "stage":
        draw.polygon([(x0, y1 - 2), (x0 + 4, y0 + 6), (x1 - 4, y0 + 6), (x1, y1 - 2)], outline=color, width=stroke)
    elif name == "decoration":
        draw.ellipse((mid_x - 3, y0 + 1, mid_x + 4, y0 + 8), **_pen(color, stroke))
        draw.ellipse((x0 + 1, mid_y, x0 + 8, y1 - 1), **_pen(color, stroke))
        draw.ellipse((x1 - 8, mid_y, x1 - 1, y1 - 1), **_pen(color, stroke))
    elif name == "guests":
        draw.ellipse((x0 + 1, y0 + 1, x0 + 8, y0 + 8), **_pen(color, stroke))
        draw.ellipse((x1 - 8, y0 + 1, x1 - 1, y0 + 8), **_pen(color, stroke))
        draw.arc((x0, mid_y, x0 + 9, y1), 20, 160, fill=color, width=stroke)
        draw.arc((x1 - 9, mid_y, x1, y1), 20, 160, fill=color, width=stroke)
    elif name == "ceremony":
        draw.arc((x0, y0, x1, y1 + 4), 200, 340, fill=color, width=stroke)
        _line(draw, [(x0 + 2, mid_y + 2), (x0 + 2, y1)], color, stroke)
        _line(draw, [(x1 - 2, mid_y + 2), (x1 - 2, y1)], color, stroke)
    elif name == "food":
        draw.ellipse((x0 + 1, y0 + 3, x1 - 1, y1), **_pen(color, stroke))
        _line(draw, [(mid_x, y0), (mid_x, y0 + 5)], color, stroke)
    elif name == "venue":
        draw.polygon([(mid_x, y0), (x1, mid_y), (x1, y1), (x0, y1), (x0, mid_y)], outline=color, width=stroke)
        draw.rectangle((mid_x - 2, y1 - 6, mid_x + 3, y1), outline=color, width=stroke)
    elif name == "portrait":
        draw.rounded_rectangle((x0, y0, x1, y1), radius=3, **_pen(color, stroke))
        draw.ellipse((mid_x - 3, y0 + 3, mid_x + 4, y0 + 10), **_pen(color, stroke))
        draw.arc((x0 + 3, mid_y + 1, x1 - 3, y1 - 1), 20, 160, fill=color, width=stroke)
    elif name == "lighting":
        draw.polygon([(mid_x, y0), (x1 - 2, mid_y), (mid_x + 2, mid_y), (mid_x, y1), (mid_x - 2, mid_y), (x0 + 2, mid_y)], outline=color, width=stroke)
    elif name == "review":
        draw.ellipse((x0, y0, x1, y1), **_pen(color, stroke))
        draw.arc((x0 + 4, y0 + 3, x1 - 4, mid_y + 3), 200, 20, fill=color, width=stroke)
        draw.ellipse((mid_x - 1, y1 - 5, mid_x + 2, y1 - 2), fill=color)
    else:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=4, **_pen(color, stroke))
    return image


def ctk_icon(name: str, color: str, size: int = 18) -> ctk.CTkImage:
    image = draw_icon(name, color, size=size * 2)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


GROUP_ICONS = {
    "Stage": "stage",
    "Decoration": "decoration",
    "Guests": "guests",
    "Ceremony": "ceremony",
    "Food": "food",
    "Venue": "venue",
    "Portrait": "portrait",
    "Lighting": "lighting",
    "Needs review": "review",
}


def write_app_icon(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = (16, 32, 48, 256)
    images: list[Image.Image] = []
    for size in sizes:
        image, draw = _canvas(size)
        inset = max(1, size // 16)
        radius = max(4, size // 5)
        draw.rounded_rectangle((inset, inset, size - inset - 1, size - inset - 1), radius=radius, fill=BLUE)
        tile = max(3, size // 7)
        gap = max(2, size // 16)
        start = (size - (tile * 2 + gap)) // 2
        mint = _rgb(MINT)
        white = _rgb(WHITE)
        colors = (white, mint, mint, white)
        index = 0
        for row in range(2):
            for col in range(2):
                left = start + col * (tile + gap)
                top = start + row * (tile + gap)
                draw.rounded_rectangle((left, top, left + tile, top + tile), radius=max(2, tile // 4), fill=colors[index])
                index += 1
        images.append(image)
    images[-1].save(path, format="ICO", sizes=[(item.width, item.height) for item in images], append_images=images[:-1])
    return path
