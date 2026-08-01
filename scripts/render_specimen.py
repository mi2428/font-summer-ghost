#!/usr/bin/env python3
"""Render a compact visual specimen for local quality assurance."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DIST, OUTPUT = ROOT / "dist", ROOT / "dist" / "specimen.png"


def load_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    """Load one generated font style or fail with an actionable message."""
    path = DIST / f"SummerGhost-{style}.ttf"
    if not path.is_file():
        raise SystemExit(f"{path} not found; run make build first")
    return ImageFont.truetype(path, size=size)


def main() -> None:
    """Render representative Latin, Japanese, fallback, and box glyphs."""
    image = Image.new("RGB", (1800, 1180), "#0d1117")
    draw, faces = ImageDraw.Draw(image), {style: load_font(style, 34) for style in ("Regular", "Bold", "Italic")}
    title, small = load_font("Bold", 54), load_font("Regular", 25)
    draw.text((72, 50), "Summer Ghost", font=title, fill="#f0f3f6")
    draw.text((74, 125), "Ubuntu Mono x Cyroit (Circle M+ / BIZ UD) x IBM Plex Sans JP", font=small, fill="#8b949e")
    rows: tuple[tuple[str, str], ...] = (
        ("Regular", "Regular   function ghost夏(value: number) { return value * 2; }"),
        ("Bold", "Bold      0123456789  Il1|  O0  {}[]()  => != ===  ~/io/font"),
        ("Italic", "Italic    const message = '丸く、読みやすく、幅は正確に';"),
        ("Regular", "Kana      あいうえお アイウエオ ひらがな・カタカナ、。ー ｱｲｳｴｵ"),
        ("Regular", "Kanji     日本語表示 春夏秋冬 開発環境 幽霊文字 髙﨑 侮"),
        ("Regular", "Fallback  㐅㐧㒈㔾㗞㘔 䄃䊓䐌䕺䖾䘐"),
        # Full-width numerals are intentional specimen data.
        ("Regular", "Width     |1234567890|１２３４５|abcde|日本語|かなカナ|"),  # noqa: RUF001
        ("Regular", "Boxes     ┌──────────┬──────────┐  ├──────────┼──────────┤"),
    )
    for index, (style, sample) in enumerate(rows):
        draw.text((74, 215 + index * 92), sample, font=faces[style], fill="#d8dee9")
    y = 215 + len(rows) * 92
    draw.line((72, y + 8, 1728, y + 8), fill="#30363d", width=2)
    draw.text(
        (74, y + 38),
        "Half 512 / Full 1024   Line height 1024   No PUA   No bundled Nerd Fonts",
        font=small,
        fill="#7ee787",
    )
    draw.text(
        (74, y + 85),
        "Rare glyphs use IBM Plex Sans JP only when earlier Japanese sources lack a mapping.",
        font=small,
        fill="#8b949e",
    )
    DIST.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(f"wrote    {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
