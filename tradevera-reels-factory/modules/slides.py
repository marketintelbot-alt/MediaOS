from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

from .utils import DEFAULT_PALETTE, VIDEO_H, VIDEO_W, ensure_dir, load_palette, seed_from_text

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise RuntimeError("Pillow is required. Install with: pip install -r requirements.txt") from exc


FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) != 6:
        h = "000000"
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _pick_font_paths(brand_fonts_dir: Path) -> tuple[str | None, str | None]:
    custom = sorted([p for p in brand_fonts_dir.glob("*") if p.suffix.lower() in {".ttf", ".otf", ".ttc"}])
    if custom:
        first = str(custom[0])
        second = str(custom[1]) if len(custom) > 1 else first
        return first, second
    regular = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    bold = next((p for p in FONT_BOLD_CANDIDATES if Path(p).exists()), regular)
    return regular, bold


def _font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    text = text or ""
    paragraphs = text.splitlines() or [text]
    all_lines: list[str] = []
    for p_idx, paragraph in enumerate(paragraphs):
        words = paragraph.split()
        if not words:
            all_lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            test = f"{cur} {w}"
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                cur = test
            else:
                all_lines.append(cur)
                cur = w
        all_lines.append(cur)
        if p_idx != len(paragraphs) - 1 and paragraph.strip():
            all_lines.append("")
    return all_lines or [""]


def _draw_multiline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    max_width: int,
    line_gap: int = 10,
) -> int:
    x, y = xy
    lines = _fit_lines(draw, text, font, max_width)
    cur_y = y
    for line in lines:
        if line == "":
            cur_y += int(font.size * 0.55) if hasattr(font, "size") else 18
            continue
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, cur_y), line, font=font)
        cur_y = bbox[3] + line_gap
    return cur_y


def _base_canvas(palette: dict[str, str]) -> Image.Image:
    bg = Image.new("RGBA", (VIDEO_W, VIDEO_H), _hex_to_rgba(palette["background"]))
    px = bg.load()
    top = _hex_to_rgba(palette["background"])
    surf = _hex_to_rgba(palette["surface"])
    for y in range(VIDEO_H):
        mix = y / max(1, VIDEO_H - 1)
        for x in range(VIDEO_W):
            vignette = 1.0 - 0.08 * ((x - VIDEO_W / 2) / (VIDEO_W / 2)) ** 2
            r = int((top[0] * (1 - mix) + surf[0] * mix) * vignette)
            g = int((top[1] * (1 - mix) + surf[1] * mix) * vignette)
            b = int((top[2] * (1 - mix) + surf[2] * mix) * vignette)
            px[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), 255)
    overlay = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    grid = _hex_to_rgba(palette["text_secondary"], 24)
    for x in range(60, VIDEO_W, 60):
        d.line((x, 0, x, VIDEO_H), fill=grid, width=1)
    for y in range(80, VIDEO_H, 80):
        d.line((0, y, VIDEO_W, y), fill=grid, width=1)
    glow = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((140, 180, 940, 980), fill=_hex_to_rgba(palette["accent"], 26))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.alpha_composite(Image.alpha_composite(bg, glow), overlay)


def _panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], palette: dict[str, str], radius: int = 28) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", (x1 - x0 + 40, y1 - y0 + 40), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((20, 20, x1 - x0 + 20, y1 - y0 + 20), radius=radius, fill=(0, 0, 0, 90))
    # shadow compositing is handled by caller if needed; draw subtle border directly
    draw.rounded_rectangle(box, radius=radius, fill=_hex_to_rgba(palette["surface"], 238), outline=_hex_to_rgba(palette["text_secondary"], 50), width=2)


def _add_accent_line(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, palette: dict[str, str]) -> None:
    draw.rounded_rectangle((x, y, x + w, y + 6), radius=3, fill=_hex_to_rgba(palette["accent"], 255))


def _paste_logo_or_wordmark(canvas: Image.Image, logo_path: Path, palette: dict[str, str], x: int, y: int, max_w: int, alpha: int = 255) -> None:
    try:
        logo = Image.open(logo_path).convert("RGBA")
        ratio = max_w / max(1, logo.width)
        new_w = int(logo.width * ratio)
        new_h = max(1, int(logo.height * ratio))
        logo = logo.resize((new_w, new_h), Image.LANCZOS)
        if alpha < 255:
            a = logo.getchannel("A").point(lambda p: int(p * (alpha / 255)))
            logo.putalpha(a)
        canvas.alpha_composite(logo, (x, y))
        return
    except Exception:
        pass

    d = ImageDraw.Draw(canvas)
    draw_font = _font(None, 34)
    d.text((x, y), "TRADEVERA", font=draw_font, fill=_hex_to_rgba(palette["text_primary"], alpha))


def _draw_watermark(canvas: Image.Image, logo_path: Path, palette: dict[str, str]) -> None:
    # keep watermark below caption safe area
    _paste_logo_or_wordmark(canvas, logo_path, palette, VIDEO_W - 300, VIDEO_H - 120, 220, alpha=24)


def _lower_third(
    canvas: Image.Image,
    palette: dict[str, str],
    title: str,
    subtitle: str = "TradeVera",
    reg_path: str | None = None,
    bold_path: str | None = None,
) -> None:
    d = ImageDraw.Draw(canvas)
    box = (72, 116, 760, 260)
    d.rounded_rectangle(box, radius=22, fill=_hex_to_rgba(palette["surface"], 235), outline=_hex_to_rgba(palette["text_secondary"], 56), width=2)
    _add_accent_line(d, box[0] + 24, box[1] + 22, 88, palette)
    title_font = _font(bold_path, 36)
    small_font = _font(reg_path, 22)
    d.text((box[0] + 24, box[1] + 42), title, font=title_font, fill=_hex_to_rgba(palette["text_primary"], 255))
    d.text((box[0] + 24, box[1] + 88), subtitle, font=small_font, fill=_hex_to_rgba(palette["text_secondary"], 255))


def generate_placeholder_logo(logo_path: Path, palette: dict[str, str], brand_fonts_dir: Path) -> None:
    ensure_dir(logo_path.parent)
    reg_path, bold_path = _pick_font_paths(brand_fonts_dir)
    img = Image.new("RGBA", (960, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 26, 940, 194), radius=26, fill=_hex_to_rgba(palette["surface"], 225), outline=_hex_to_rgba(palette["text_secondary"], 40), width=2)
    d.rounded_rectangle((26, 106, 180, 114), radius=4, fill=_hex_to_rgba(palette["accent"], 255))
    text_font = _font(bold_path, 84)
    d.text((24, 44), "TRADEVERA", font=text_font, fill=_hex_to_rgba(palette["text_primary"], 255))
    img.save(logo_path)


def ensure_brand_assets(project_root: Path, logger: Any = None) -> dict[str, Any]:
    brand_dir = ensure_dir(project_root / "assets" / "brand")
    fonts_dir = ensure_dir(brand_dir / "fonts")
    palette_path = brand_dir / "palette.json"
    palette_missing = not palette_path.exists()
    palette = load_palette(brand_dir)
    if palette_missing and logger:
        logger.warn("assets/brand/palette.json missing; wrote default TradeVera palette")
    logo_path = brand_dir / "logo.png"
    if not logo_path.exists():
        generate_placeholder_logo(logo_path, palette, fonts_dir)
        if logger:
            logger.warn("assets/brand/logo.png missing; generated placeholder TRADEVERA wordmark")
    return {"palette": palette, "logo_path": logo_path, "fonts_dir": fonts_dir}


def _title_card(canvas: Image.Image, script: dict[str, Any], palette: dict[str, str], logo_path: Path, reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((68, 236, 1012, 1138), radius=34, fill=_hex_to_rgba(palette["surface"], 235), outline=_hex_to_rgba(palette["text_secondary"], 44), width=2)
    _add_accent_line(d, 110, 306, 168, palette)
    small = _font(reg_path, 26)
    d.text((110, 330), "TRADEVERA // EXECUTION NOTE", font=small, fill=_hex_to_rgba(palette["text_secondary"], 255))
    hook_text = str(script.get("hook", "TradeVera execution edge"))
    hook_font = _font(bold_path, 84)
    for size in (84, 76, 68, 60):
        candidate = _font(bold_path, size)
        if len(_fit_lines(d, hook_text, candidate, 860)) <= 5:
            hook_font = candidate
            break
        hook_font = candidate
    hook_end_y = _draw_multiline(d, (110, 410), hook_text, hook_font, _hex_to_rgba(palette["text_primary"], 255), max_width=860, line_gap=12)
    med = _font(reg_path, 30)
    sub_y = min(1030, max(930, hook_end_y + 42))
    d.text((110, sub_y), "Edge is process under pressure.", font=med, fill=_hex_to_rgba(palette["text_secondary"], 255))
    _lower_third(canvas, palette, "Hook", "TradeVera", reg_path=reg_path, bold_path=bold_path)
    _paste_logo_or_wordmark(canvas, logo_path, palette, 78, 64, 320, alpha=255)


def _three_rules(canvas: Image.Image, script: dict[str, Any], palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 180, 1008, 1470), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    _add_accent_line(d, 106, 236, 120, palette)
    title = _font(bold_path, 58)
    d.text((106, 264), "3 Rules", font=title, fill=_hex_to_rgba(palette["text_primary"], 255))
    sub = _font(reg_path, 26)
    d.text((106, 334), "TradeVera process filter", font=sub, fill=_hex_to_rgba(palette["text_secondary"], 255))
    num_font = _font(bold_path, 46)
    txt_font = _font(reg_path, 36)
    y = 430
    for i, point in enumerate(script.get("points", [])[:3], start=1):
        d.rounded_rectangle((106, y - 8, 974, y + 180), radius=22, fill=_hex_to_rgba(palette["background"], 140), outline=_hex_to_rgba(palette["text_secondary"], 36), width=2)
        d.text((132, y + 28), f"{i:02d}", font=num_font, fill=_hex_to_rgba(palette["accent"], 255))
        _draw_multiline(d, (220, y + 26), point, txt_font, _hex_to_rgba(palette["text_primary"], 255), max_width=730, line_gap=8)
        y += 210
    _lower_third(canvas, palette, "Rules", "TradeVera", reg_path=reg_path, bold_path=bold_path)


def _myth_vs_fact(canvas: Image.Image, script: dict[str, Any], palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 220, 1008, 1420), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    _add_accent_line(d, 106, 270, 150, palette)
    d.text((106, 294), "Myth vs Fact", font=_font(bold_path, 54), fill=_hex_to_rgba(palette["text_primary"], 255))
    d.line((540, 400, 540, 1350), fill=_hex_to_rgba(palette["text_secondary"], 60), width=2)
    d.text((122, 408), "MYTH", font=_font(bold_path, 34), fill=_hex_to_rgba(palette["text_secondary"], 255))
    d.text((572, 408), "FACT", font=_font(bold_path, 34), fill=_hex_to_rgba(palette["accent"], 255))
    myth = "More trades means more edge."
    fact = "Selective execution protects expectancy."
    if "risk" in str(script.get("idea", "")).lower():
        myth = "Bigger size fixes weak performance."
        fact = "Risk precision creates survivability."
    _draw_multiline(d, (122, 484), myth, _font(reg_path, 36), _hex_to_rgba(palette["text_primary"], 255), 370, 8)
    _draw_multiline(d, (572, 484), fact, _font(reg_path, 36), _hex_to_rgba(palette["text_primary"], 255), 340, 8)
    _draw_multiline(d, (122, 700), "Noise feels productive.", _font(reg_path, 34), _hex_to_rgba(palette["text_secondary"], 255), 360, 8)
    _draw_multiline(d, (572, 700), "Process beats urgency under pressure.", _font(reg_path, 34), _hex_to_rgba(palette["text_secondary"], 255), 340, 8)
    _lower_third(canvas, palette, "Myth vs Fact", "TradeVera", reg_path=reg_path, bold_path=bold_path)


def _do_this_not_that(canvas: Image.Image, palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 220, 1008, 1460), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    d.text((106, 264), "Do this / Not that", font=_font(bold_path, 52), fill=_hex_to_rgba(palette["text_primary"], 255))
    d.rounded_rectangle((106, 380, 974, 840), radius=24, fill=_hex_to_rgba(palette["background"], 115), outline=_hex_to_rgba(palette["text_secondary"], 38), width=2)
    d.rounded_rectangle((106, 900, 974, 1360), radius=24, fill=_hex_to_rgba(palette["background"], 115), outline=_hex_to_rgba(palette["text_secondary"], 38), width=2)
    _add_accent_line(d, 128, 414, 90, palette)
    d.text((128, 440), "DO THIS", font=_font(bold_path, 34), fill=_hex_to_rgba(palette["accent"], 255))
    _draw_multiline(d, (128, 510), "Define entry, invalidation, and size before clicking buy or sell.", _font(reg_path, 36), _hex_to_rgba(palette["text_primary"], 255), 820, 8)
    d.text((128, 934), "NOT THAT", font=_font(bold_path, 34), fill=_hex_to_rgba(palette["text_secondary"], 255))
    _draw_multiline(d, (128, 1004), "Chase movement, then improvise the stop when pressure rises.", _font(reg_path, 36), _hex_to_rgba(palette["text_primary"], 255), 820, 8)


def _mini_chart(canvas: Image.Image, script: dict[str, Any], palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 220, 1008, 1420), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    d.text((106, 264), "Mini Chart", font=_font(bold_path, 52), fill=_hex_to_rgba(palette["text_primary"], 255))
    d.text((106, 332), "Synthetic equity curve / drawdown", font=_font(reg_path, 24), fill=_hex_to_rgba(palette["text_secondary"], 255))
    chart = (120, 420, 960, 990)
    d.rounded_rectangle(chart, radius=18, fill=_hex_to_rgba(palette["background"], 140), outline=_hex_to_rgba(palette["text_secondary"], 38), width=2)
    for i in range(1, 8):
        x = chart[0] + i * (chart[2] - chart[0]) / 8
        d.line((x, chart[1] + 20, x, chart[3] - 20), fill=_hex_to_rgba(palette["text_secondary"], 22), width=1)
    for i in range(1, 6):
        y = chart[1] + i * (chart[3] - chart[1]) / 6
        d.line((chart[0] + 20, y, chart[2] - 20, y), fill=_hex_to_rgba(palette["text_secondary"], 22), width=1)

    rnd = random.Random(seed_from_text(str(script.get("idea", ""))))
    points = []
    equity = 100.0
    max_eq = 100.0
    drawdowns = []
    for i in range(18):
        equity += rnd.uniform(-2.8, 5.5)
        equity = max(90.0, equity)
        max_eq = max(max_eq, equity)
        dd = max_eq - equity
        drawdowns.append(dd)
        x = chart[0] + 30 + i * (chart[2] - chart[0] - 60) / 17
        y = chart[3] - 30 - (equity - 90.0) / 40.0 * (chart[3] - chart[1] - 60)
        points.append((x, y))
    for i in range(len(points) - 1):
        d.line((points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]), fill=_hex_to_rgba(palette["accent"], 255), width=4)
    for x, y in points:
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=_hex_to_rgba(palette["text_primary"], 255))

    bars = (120, 1040, 960, 1330)
    d.rounded_rectangle(bars, radius=18, fill=_hex_to_rgba(palette["background"], 140), outline=_hex_to_rgba(palette["text_secondary"], 38), width=2)
    d.text((140, 1066), "Drawdown bars", font=_font(reg_path, 24), fill=_hex_to_rgba(palette["text_secondary"], 255))
    max_dd = max(drawdowns) if drawdowns else 1.0
    for i, dd in enumerate(drawdowns[:14]):
        x0 = 150 + i * 56
        height = int((dd / max_dd) * 160)
        d.rounded_rectangle((x0, 1280 - height, x0 + 30, 1280), radius=6, fill=_hex_to_rgba(palette["text_secondary"], 140))


def _checklist(canvas: Image.Image, script: dict[str, Any], palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 240, 1008, 1500), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    d.text((106, 286), "Execution Checklist", font=_font(bold_path, 52), fill=_hex_to_rgba(palette["text_primary"], 255))
    d.text((106, 354), "TradeVera close", font=_font(reg_path, 24), fill=_hex_to_rgba(palette["text_secondary"], 255))
    items = [
        "Setup quality confirmed",
        "Risk size matched to stop",
        "Invalidation level defined",
        "No impulse add-on",
        script.get("cta", "Follow TradeVera for daily edge."),
    ]
    y = 450
    for i, item in enumerate(items):
        d.rounded_rectangle((110, y - 2, 970, y + 122), radius=18, fill=_hex_to_rgba(palette["background"], 118), outline=_hex_to_rgba(palette["text_secondary"], 34), width=2)
        d.rounded_rectangle((138, y + 34, 182, y + 78), radius=10, outline=_hex_to_rgba(palette["accent"], 255), width=3)
        if i < 4:
            d.line((146, y + 57, 158, y + 69), fill=_hex_to_rgba(palette["accent"], 255), width=3)
            d.line((158, y + 69, 176, y + 43), fill=_hex_to_rgba(palette["accent"], 255), width=3)
        _draw_multiline(d, (206, y + 28), str(item), _font(reg_path, 34), _hex_to_rgba(palette["text_primary"], 255), 730, 8)
        y += 144
    _lower_third(canvas, palette, "CTA", "TradeVera", reg_path=reg_path, bold_path=bold_path)


def _setup_vs_noise(canvas: Image.Image, palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 240, 1008, 1470), radius=30, fill=_hex_to_rgba(palette["surface"], 236), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    d.text((106, 286), "Setup vs Noise", font=_font(bold_path, 52), fill=_hex_to_rgba(palette["text_primary"], 255))
    left = (106, 400, 506, 1360)
    right = (574, 400, 974, 1360)
    d.rounded_rectangle(left, radius=22, fill=_hex_to_rgba(palette["background"], 120), outline=_hex_to_rgba(palette["text_secondary"], 36), width=2)
    d.rounded_rectangle(right, radius=22, fill=_hex_to_rgba(palette["background"], 120), outline=_hex_to_rgba(palette["text_secondary"], 36), width=2)
    d.text((134, 430), "SETUP", font=_font(bold_path, 32), fill=_hex_to_rgba(palette["accent"], 255))
    d.text((602, 430), "NOISE", font=_font(bold_path, 32), fill=_hex_to_rgba(palette["text_secondary"], 255))
    _draw_multiline(d, (134, 510), "Clear invalidation\nDefined size\nRepeatable trigger\nLow decision drag", _font(reg_path, 34), _hex_to_rgba(palette["text_primary"], 255), 330, 10)
    _draw_multiline(d, (602, 510), "Impulse entries\nLate fills\nNo risk map\nOutcome chasing", _font(reg_path, 34), _hex_to_rgba(palette["text_primary"], 255), 330, 10)


def _risk_formula(canvas: Image.Image, palette: dict[str, str], reg_path: str | None, bold_path: str | None) -> None:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((72, 320, 1008, 1340), radius=32, fill=_hex_to_rgba(palette["surface"], 238), outline=_hex_to_rgba(palette["text_secondary"], 48), width=2)
    d.text((106, 382), "Risk Formula", font=_font(bold_path, 58), fill=_hex_to_rgba(palette["text_primary"], 255))
    d.text((106, 462), "Simple. Repeatable. Non-negotiable.", font=_font(reg_path, 26), fill=_hex_to_rgba(palette["text_secondary"], 255))
    d.rounded_rectangle((106, 560, 974, 850), radius=26, fill=_hex_to_rgba(palette["background"], 126), outline=_hex_to_rgba(palette["text_secondary"], 38), width=2)
    formula_font = _font(bold_path, 72)
    d.text((146, 650), "Risk = Size × Stop", font=formula_font, fill=_hex_to_rgba(palette["text_primary"], 255))
    _add_accent_line(d, 146, 742, 280, palette)
    d.text((146, 780), "Adjust size first. Keep stop logic intact.", font=_font(reg_path, 30), fill=_hex_to_rgba(palette["text_secondary"], 255))
    _lower_third(canvas, palette, "Formula", "TradeVera", reg_path=reg_path, bold_path=bold_path)


def generate_tradevera_slides(output_dir: Path, script: dict[str, Any], project_root: Path, logger: Any = None) -> dict[str, Path]:
    output_dir = ensure_dir(output_dir)
    brand = ensure_brand_assets(project_root, logger=logger)
    palette = brand["palette"]
    logo_path = brand["logo_path"]
    fonts_dir = brand["fonts_dir"]
    reg_path, bold_path = _pick_font_paths(fonts_dir)
    if logger and list(fonts_dir.glob("*")):
        logger.step("Using custom brand font from assets/brand/fonts")
    elif logger:
        logger.step("Using system font fallback for slides")

    templates: dict[str, Path] = {}

    def render(name: str, drawer) -> None:
        canvas = _base_canvas(palette)
        drawer(canvas)
        _draw_watermark(canvas, logo_path, palette)
        out_path = output_dir / f"{len(templates)+1:02d}_{name}.png"
        canvas.save(out_path)
        templates[name] = out_path

    render("title_card", lambda c: _title_card(c, script, palette, logo_path, reg_path, bold_path))
    render("three_rules_widget", lambda c: _three_rules(c, script, palette, reg_path, bold_path))
    render("myth_vs_fact", lambda c: _myth_vs_fact(c, script, palette, reg_path, bold_path))
    render("do_this_not_that", lambda c: _do_this_not_that(c, palette, reg_path, bold_path))
    render("mini_chart", lambda c: _mini_chart(c, script, palette, reg_path, bold_path))
    render("checklist", lambda c: _checklist(c, script, palette, reg_path, bold_path))
    render("setup_vs_noise", lambda c: _setup_vs_noise(c, palette, reg_path, bold_path))
    render("risk_formula", lambda c: _risk_formula(c, palette, reg_path, bold_path))

    return templates
