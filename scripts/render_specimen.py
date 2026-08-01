#!/usr/bin/env python3
"""Render the Summer Ghost programming-font specimen."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUTPUTS = ROOT / "specimen.png", DIST / "specimen.png"
WIDTH, HEIGHT = 2048, 1152

# Catppuccin Mocha: https://github.com/catppuccin/palette
BASE, MANTLE, CRUST = "#1e1e2e", "#181825", "#11111b"
SURFACE_0, SURFACE_1, OVERLAY_0 = "#313244", "#45475a", "#6c7086"
SUBTEXT_0, TEXT = "#a6adc8", "#cdd6f4"
BLUE, MAUVE, PEACH, GREEN = "#89b4fa", "#cba6f7", "#fab387", "#a6e3a1"

DISPLAY_SIZE, QUOTE_SIZE, JP_QUOTE_SIZE = 56, 34, 30
PANEL_TITLE_SIZE, BODY_SIZE, JP_BODY_SIZE = 18, 19, 17
LABEL_SIZE, SMALL_SIZE, METRIC_SIZE = 12, 14, 32

Point = tuple[int, int]
Box = tuple[int, int, int, int]
Segment = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Sample:
    """One labeled row in a specimen panel."""

    label: str
    value: str
    style: str = "Regular"
    color: str = TEXT


BADGES = (
    ("UPM", "1024", BLUE),
    ("HALF", "512", MAUVE),
    ("FULL", "1024", PEACH),
    ("LINE", "1.0 EM", GREEN),
    ("GRID", "16 PX", BLUE),
    ("PUA", "NONE", MAUVE),
)
LATIN_SAMPLES = (
    Sample("UPPER", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    Sample("LOWER", "abcdefghijklmnopqrstuvwxyz"),
    Sample("ACCENTS", "ÀÁÂÃÄÅ Æ Ç ÈÉÊË Ñ Ø Œ ß àáâãäå"),
    Sample("GREEK / CYR", "ΑΒΓΔΩ αβγδε λμπσφω  ДЖЯ дёжя"),
    Sample("FIGURES", "0123456789  ０１２３４５６７８９"),  # noqa: RUF001
    Sample("AMBIGUOUS", "0O○〇  1Il|  2Z  5S  8B  rn m  vv w"),  # noqa: RUF001
    Sample("OPERATORS", "{} [] () <> /\\ :;,.  => -> == != <= >= && ||"),
)
STYLE_SAMPLES = tuple(
    Sample(label, "function ghost夏() { return 42; }", style)
    for label, style in (("REGULAR", "Regular"), ("BOLD", "Bold"), ("ITALIC", "Italic"), ("BOLD ITALIC", "BoldItalic"))
)
JAPANESE_SAMPLES = (
    Sample("HIRAGANA 1", "あいうえお かきくけこ さしすせそ たちつてと"),
    Sample("HIRAGANA 2", "なにぬねの はひふへほ まみむめも やゆよ らりるれろ わをん"),
    Sample("KATAKANA 1", "アイウエオ カキクケコ サシスセソ タチツテト"),
    Sample("KATAKANA 2", "ナニヌネノ ハヒフヘホ マミムメモ ヤユヨ ラリルレロ ワヲン"),
    Sample("HALF KANA", "ｱｲｳｴｵ ｶｷｸｹｺ ｻｼｽｾｿ ﾀﾁﾂﾃﾄ ﾊﾋﾌﾍﾎ ﾔﾕﾖ ﾜｦﾝﾞﾟ"),
    Sample("KANJI", "日本語 春夏秋冬 開発環境 幽霊文字 東京大阪 京都"),
    Sample("COMPLEX", "鬱 薔薇 檸檬 躊躇 饕餮 贔屓"),
    Sample("VARIANTS", "邊 邉 齋 齊 髙 﨑 侮 侮"),
    Sample("IBM FALLBACK", "㐅㐧㒈㔾㗞㘔  䄃䊓䐌䕺䖾䘐"),
    Sample("FULL FORMS", "０１２３４５６７８９ ＡＢＣ ａｂｃ ￥＠＃％"),  # noqa: RUF001
    Sample("CJK PUNCT", "〒々〆〇「」『』【】〈〉・、。！？￥…"),  # noqa: RUF001
)
TERMINAL = (
    "┌──────────┬──────────┐  ┏━━━━┓  ╔════╗",
    "│  code    │  日本語  │  ┃ UI ┃  ║ 42 ║",
    "├──────────┼──────────┤  ┣━━━━┫  ╠════╣",
    "└──────────┴──────────┘  ┗━━━━┛  ╚════╝",
)
SYMBOL_SAMPLES = (
    Sample("BOX JOINS", "┌┬┐ ├┼┤ └┴┘  ┏┳┓ ┣╋┫ ┗┻┛"),
    Sample("ARROW / MATH", "←↓↑→  ← ↑ → ↓ ↔  ⇐ ⇒ ⇔   ± × ÷ ≠ ≈ ≤ ≥ ∞"),  # noqa: RUF001
    Sample("BLOCKS", "░▒▓█  ▏▎▍▌▋▊▉  ▁▂▃▄▅▆▇█"),
    Sample("PUNCT", "() [] {} <> /\\ |  「」『』【】〈〉  $ € ¥"),
)


@cache
def _font(style: str = "Regular", size: int = BODY_SIZE) -> ImageFont.FreeTypeFont:
    """Load and cache one generated face at a specific size."""
    path = DIST / f"SummerGhost-{style}.ttf"
    if not path.is_file():
        raise SystemExit(f"{path} not found; run make build first")
    return ImageFont.truetype(path, size=size)


def _panel(draw: ImageDraw.ImageDraw, box: Box, title: str, accent: str) -> None:
    """Draw a labeled panel on the plain specimen field."""
    draw.rounded_rectangle(box, radius=14, fill=MANTLE, outline=SURFACE_1, width=2)
    x, y, _, _ = box
    draw.rectangle((x, y, x + 8, y + 40), fill=accent)
    draw.text((x + 28, y + 26), title, font=_font("Bold", PANEL_TITLE_SIZE), fill=accent, anchor="lm")


def _badge(draw: ImageDraw.ImageDraw, xy: Point, label: str, value: str, color: str) -> None:
    """Draw a compact metric badge."""
    x, y = xy
    draw.rounded_rectangle((x, y, x + 216, y + 40), radius=10, fill=CRUST, outline=SURFACE_0, width=2)
    draw.text((x + 12, y + 20), label, font=_font("Bold", 13), fill=SUBTEXT_0, anchor="lm")
    draw.text((x + 202, y + 20), value, font=_font("Bold", 15), fill=color, anchor="rm")


def _samples(
    draw: ImageDraw.ImageDraw,
    xy: Point,
    rows: Sequence[Sample],
    *,
    step: int,
    label_width: int,
    size: int,
) -> None:
    """Render compact labeled specimen rows."""
    x, y = xy
    label_face = _font("Bold", LABEL_SIZE)
    for index, sample in enumerate(rows):
        baseline = y + index * step
        draw.text((x, baseline), sample.label, font=label_face, fill=OVERLAY_0, anchor="ls")
        draw.text(
            (x + label_width, baseline), sample.value, font=_font(sample.style, size), fill=sample.color, anchor="ls"
        )


def _runs(draw: ImageDraw.ImageDraw, xy: Point, face: ImageFont.FreeTypeFont, segments: Sequence[Segment]) -> None:
    """Render syntax-colored segments on one baseline."""
    x, y = xy
    for value, color in segments:
        draw.text((x, y), value, font=face, fill=color, anchor="ls")
        x += round(draw.textlength(value, font=face))


def _metric_grid(draw: ImageDraw.ImageDraw, box: Box, step: int = 16) -> None:
    """Draw the only grid in the specimen: one measured half-width per cell."""
    left, top, right, bottom = box
    draw.rectangle(box, fill=CRUST, outline=SURFACE_1, width=2)
    for index, x in enumerate(range(left + step, right, step), start=1):
        draw.line((x, top, x, bottom), fill=SURFACE_1 if index % 2 == 0 else SURFACE_0, width=1)
    for y in range(top + step, bottom, step):
        draw.line((left, y, right, y), fill=SURFACE_0, width=1)
    for index in range(0, (right - left) // step, 4):
        draw.text((left + index * step + 2, top + 2), f"{index:02}", font=_font(size=11), fill=OVERLAY_0)


def _draw_header(draw: ImageDraw.ImageDraw) -> None:
    """Draw the title and primary metrics."""
    draw.text((48, 36), "SUMMER GHOST", font=_font("Bold", DISPLAY_SIZE), fill=TEXT)
    draw.text(
        (52, 112),
        "PROGRAMMING FONT SPECIMEN  /  GHOSTTY JP COMPOSITE  /  NERD ICONS VIA FALLBACK",
        font=_font(size=18),
        fill=SUBTEXT_0,
    )
    for index, (label, value, color) in enumerate(BADGES):
        _badge(draw, (1256 + index % 3 * 232, 40 + index // 3 * 48), label, value, color)


def _draw_quote(draw: ImageDraw.ImageDraw) -> None:
    """Draw the bilingual Red Queen quotation."""
    _panel(draw, (48, 160, 2000, 384), "MIXED SCRIPT / THE RED QUEEN'S RACE", BLUE)
    draw.text(
        (80, 240),
        "“Now, here, you see, it takes all the running you can do, to keep in the same place.”",
        font=_font(size=QUOTE_SIZE),
        fill=TEXT,
        anchor="ls",
    )
    draw.text(
        (80, 296),
        "「ここではだね、同じ場所にとどまるだけで、もう必死で走らなきゃいけないんだよ。」",
        font=_font(size=JP_QUOTE_SIZE),
        fill=TEXT,
        anchor="ls",
    )
    _runs(
        draw,
        (80, 344),
        _font(size=18),
        (
            ("while", MAUVE),
            (" (", TEXT),
            ("alice.position", BLUE),
            (" ", TEXT),
            ("===", MAUVE),
            (" ", TEXT),
            ("origin", BLUE),
            (") { ", TEXT),
            ("run", GREEN),
            ("(", TEXT),
            ("2", PEACH),
            (" ", TEXT),
            ("*", MAUVE),
            (" ", TEXT),
            ("speed", BLUE),
            ("); }  ", TEXT),
            ("// 赤の女王仮説 / Red Queen hypothesis", OVERLAY_0),
        ),
    )
    draw.text(
        (1968, 372),
        "Lewis Carroll, Through the Looking-Glass (1871) / JP © 2000 Hiroo Yamagata, CC BY-SA 2.1 JP",
        font=_font(size=12),
        fill=OVERLAY_0,
        anchor="rs",
    )


def _draw_latin(draw: ImageDraw.ImageDraw) -> None:
    """Draw Latin coverage, ambiguity, and style samples."""
    _panel(draw, (48, 400, 1008, 808), "LATIN / AMBIGUITY / STYLES", MAUVE)
    _samples(draw, (80, 464), LATIN_SAMPLES, step=38, label_width=128, size=BODY_SIZE)
    draw.line((80, 712, 976, 712), fill=SURFACE_0, width=2)
    _samples(draw, (80, 728), STYLE_SAMPLES, step=24, label_width=128, size=17)


def _draw_japanese(draw: ImageDraw.ImageDraw) -> None:
    """Draw Japanese coverage and width-form samples."""
    _panel(draw, (1024, 400, 2000, 808), "JAPANESE COVERAGE / WIDTH FORMS", PEACH)
    _samples(draw, (1056, 464), JAPANESE_SAMPLES, step=30, label_width=128, size=JP_BODY_SIZE)


def _draw_metrics(draw: ImageDraw.ImageDraw) -> None:
    """Draw measured advances, baselines, and source scales."""
    _panel(draw, (48, 824, 1008, 1096), "ADVANCE / BASELINE / SOURCE SCALE", GREEN)
    _metric_grid(draw, (176, 872, 976, 1008))
    metric_face = _font(size=METRIC_SIZE)
    for baseline in (920, 960, 1000):
        draw.line((176, baseline, 976, baseline), fill=BLUE, width=1)
    for label, baseline in (("CELLS", 920), ("WIDTH", 960), ("MIXED", 1000)):
        draw.text((80, baseline), label, font=_font("Bold", LABEL_SIZE), fill=OVERLAY_0, anchor="ls")
    draw.text((176, 920), "ABCD日本12かな[]{}", font=metric_face, fill=TEXT, anchor="ls")
    draw.text(
        (176, 960),
        "|12345|１２３４５|abcde|日本語|",  # noqa: RUF001
        font=metric_face,
        fill=PEACH,
        anchor="ls",
    )
    _runs(
        draw,
        (176, 1000),
        metric_face,
        (
            ("let", MAUVE),
            (" ", TEXT),
            ("夏", BLUE),
            (" ", TEXT),
            ("=", MAUVE),
            (" ", TEXT),
            ("42", PEACH),
            (";  ", TEXT),
            ("// 赤の女王", OVERLAY_0),
        ),
    )
    _runs(
        draw,
        (80, 1038),
        _font(size=SMALL_SIZE),
        (
            ("LATIN  ", BLUE),
            ("Ubuntu Mono X100/Y103; box unscaled", TEXT),
            ("     JP CORE  ", MAUVE),
            ("Cyroit X100/Y100", TEXT),
        ),
    )
    _runs(
        draw,
        (80, 1070),
        _font(size=SMALL_SIZE),
        (
            ("JP EXT  ", PEACH),
            ("BIZ 87 / IBM Plex JP 90", TEXT),
            ("     GRID  ", GREEN),
            ("16 px @ 32 px = 512 units", TEXT),
        ),
    )


def _draw_terminal(draw: ImageDraw.ImageDraw) -> None:
    """Draw connected terminal geometry and symbol coverage."""
    _panel(draw, (1024, 824, 2000, 1096), "TERMINAL GEOMETRY / SYMBOL INVENTORY", BLUE)
    terminal_face = _font(size=24)
    for index, value in enumerate(TERMINAL):
        draw.text((1056, 896 + index * 24), value, font=terminal_face, fill=GREEN, anchor="ls")
    draw.line((1056, 984, 1968, 984), fill=SURFACE_0, width=2)
    _samples(draw, (1056, 1012), SYMBOL_SAMPLES, step=24, label_width=120, size=17)


def render() -> Image.Image:
    """Build the complete 16:9 technical specimen."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BASE)
    draw = ImageDraw.Draw(image)
    for section in (_draw_header, _draw_quote, _draw_latin, _draw_japanese, _draw_metrics, _draw_terminal):
        section(draw)
    draw.text((48, 1120), "SUMMER GHOST  /  TECHNICAL SPECIMEN", font=_font("Bold", 12), fill=OVERLAY_0)
    draw.text((2000, 1120), "16:9  /  CATPPUCCIN MOCHA", font=_font("Bold", 12), fill=OVERLAY_0, anchor="ra")
    return image


def main() -> None:
    """Write byte-identical specimens to the repository root and dist/."""
    DIST.mkdir(parents=True, exist_ok=True)
    render().save(OUTPUTS[0], optimize=True)
    shutil.copyfile(OUTPUTS[0], OUTPUTS[1])
    for output in OUTPUTS:
        print(f"wrote    {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
