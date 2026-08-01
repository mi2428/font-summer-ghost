#!/usr/bin/env python3
"""Validate Summer Ghost names, geometry, coverage, provenance, and shaping."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import TypeVar

import uharfbuzz as hb
from fontTools.ttLib import TTFont

ROOT, STYLES = Path(__file__).resolve().parents[1], ("Regular", "Bold", "Italic", "BoldItalic")
DIST = ROOT / "dist"
IBM_COMMIT = "ceee82fa88781b8310b198fd302480efaeac609e"
EXPECTED_ORIGINS = {
    "U+0041": "ubuntu",
    "U+2500": "ubuntu",
    "U+3042": "cyroit",
    "U+65E5": "cyroit",
    "U+FF11": "biz",
    "U+3405": "ibm",
}
REQUIRED = {
    0x0041: "Ubuntu Mono Latin",
    0x2500: "Ubuntu Mono box drawing",
    0x3042: "Circle M+ hiragana",
    0x30A2: "Circle M+ katakana",
    0x65E5: "BIZ UDGothic kanji",
    0x9AD9: "BIZ UDGothic Japanese-name kanji",
    0xFA11: "BIZ UDGothic compatibility ideograph",
    0x3405: "IBM Plex Sans JP fallback",
}
INK_HEIGHTS = {
    False: {0x0041: 0.638, 0x3042: 0.788, 0x65E5: 0.760, 0x8A9E: 0.792},
    True: {0x0041: 0.638, 0x3042: 0.796, 0x65E5: 0.771, 0x8A9E: 0.803},
}
T = TypeVar("T")


def expect(actual: T, expected: T, context: str) -> None:
    """Raise a contextual assertion when two values differ."""
    if actual != expected:
        raise AssertionError(f"{context}: expected {expected!r}, got {actual!r}")


def name(font: TTFont, name_id: int) -> str:
    """Read an English Windows name record."""
    record = font["name"].getName(name_id, 3, 1, 0x409)
    return record.toUnicode() if record else ""


def is_private_use(codepoint: int) -> bool:
    """Return whether a codepoint belongs to a Unicode private-use area."""
    return unicodedata.category(chr(codepoint)) == "Co"


def _bounds(font: TTFont, glyph_name: str) -> tuple[int, int, int, int]:
    glyph = font["glyf"][glyph_name]
    glyph.recalcBounds(font["glyf"])
    return glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax


def validate_font(path: Path, style: str) -> None:
    """Validate one compiled TrueType font."""
    with closing(TTFont(path)) as font:
        cmap, os2, head, hhea = font.getBestCmap(), font["OS/2"], font["head"], font["hhea"]
        subfamily = "Bold Italic" if style == "BoldItalic" else style
        bold, italic = "Bold" in style, "Italic" in style
        for actual, expected, field in (
            (head.unitsPerEm, 1024, "UPM"),
            (hhea.ascent, 850, "ascent"),
            (hhea.descent, -174, "descent"),
            (hhea.lineGap, 0, "line gap"),
            (name(font, 16), "Summer Ghost", "typographic family"),
            (name(font, 17), subfamily, "typographic subfamily"),
            (name(font, 6), f"SummerGhost-{style}", "PostScript name"),
            (font["post"].isFixedPitch, 1, "fixed-pitch flag"),
            (font["post"].formatType, 3.0, "post format"),
            (head.macStyle, int(bold) | (int(italic) << 1), "macStyle"),
        ):
            expect(actual, expected, f"{path.name} {field}")
        if os2.version < 4 or not os2.fsSelection & (1 << 7):
            raise AssertionError(f"{path.name} does not enable USE_TYPO_METRICS")
        expect(bool(os2.fsSelection & (1 << 5)), bold, f"{path.name} OS/2 bold flag")
        expect(bool(os2.fsSelection & (1 << 0)), italic, f"{path.name} OS/2 italic flag")

        widths = {font["hmtx"][glyph][0] for glyph in set(cmap.values())}
        if unexpected := widths - {0, 512, 1024}:
            raise AssertionError(f"{path.name} has unexpected advances: {sorted(unexpected)}")
        if pua := [cp for cp in cmap if is_private_use(cp)]:
            raise AssertionError(f"{path.name} maps {len(pua)} private-use codepoints")
        missing = [f"{description} U+{cp:04X}" for cp, description in REQUIRED.items() if cp not in cmap]
        if missing:
            raise AssertionError(f"{path.name} lacks: {', '.join(missing)}")
        if len(cmap) < 15_000:
            raise AssertionError(f"{path.name} maps only {len(cmap)} Unicode codepoints")

        extents = [_bounds(font, glyph)[1::2] for glyph in set(cmap.values())]
        min_y, max_y = min(low for low, _ in extents), max(high for _, high in extents)
        if min_y < -220 or max_y > 920:
            raise AssertionError(f"{path.name} has excessive vertical overhang: {min_y}..{max_y}")
        if os2.usWinAscent < head.yMax or os2.usWinDescent < -head.yMin:
            raise AssertionError(f"{path.name} Windows metrics can clip outlines")

        for cp, expected in INK_HEIGHTS[bold].items():
            _, low, _, high = _bounds(font, cmap[cp])
            actual = (high - low) / head.unitsPerEm
            if abs(actual - expected) > 0.002:
                raise AssertionError(
                    f"{path.name} U+{cp:04X} ink height {actual:.4f}; expected {expected:.4f} +/- 0.002"
                )
        expect(_bounds(font, cmap[0x00C0])[3], 850, f"{path.name} unscaled non-ASCII accent")
        x_min, y_min, x_max, y_max = _bounds(font, cmap[0x2500])
        expect((x_max - x_min, y_max - y_min), (512, 82), f"{path.name} box drawing")
        variation_tables = [table for table in font["cmap"].tables if table.format == 14]
        if not variation_tables or not variation_tables[0].uvsDict:
            raise AssertionError(f"{path.name} lacks Japanese variation sequences")
        selectors = len(variation_tables[0].uvsDict)
        print(
            f"ok       {path.name}: {len(cmap):,} codepoints, "
            f"{len(font.getGlyphOrder()):,} glyphs, {selectors:,} selectors"
        )


def shape(font: hb.Font, text: str) -> list[tuple[int, int]]:
    """Shape text and return glyph IDs with horizontal advances."""
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    return [
        (info.codepoint, position.x_advance)
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions, strict=True)
    ]


def validate_shaping(path: Path) -> None:
    """Validate terminal advances and a representative ideographic variant."""
    face = hb.Face(path.read_bytes())
    font = hb.Font(face)
    font.scale = face.upem, face.upem
    for label, text, expected in (
        ("ASCII", "ABC", [512, 512, 512]),
        ("box drawing", "┌─┐", [512, 512, 512]),
    ):
        run = shape(font, text)
        expect([advance for _, advance in run], expected, f"{path.name} {label} advances")
    base, variant = shape(font, "侮"), shape(font, "侮\ufe00")
    if len(base) != 1 or len(variant) != 1 or base[0][0] == variant[0][0]:
        raise AssertionError(f"{path.name} IVS shaping failed: base={base}, variant={variant}")
    expect((base[0][1], variant[0][1]), (1024, 1024), f"{path.name} IVS advances")


def validate_provenance(data: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    """Validate top-level build provenance and index its style records."""
    expect(data.get("family"), "Summer Ghost", "provenance family")
    expect(data.get("version"), "0.1.0", "provenance version")
    expect(data.get("ibm_commit"), IBM_COMMIT, "provenance IBM commit")
    assets = data.get("assets")
    if (
        not isinstance(assets, list)
        or not assets
        or not all(
            isinstance(asset, dict)
            and set(asset) == {"name", "url", "sha256"}
            and isinstance(asset["sha256"], str)
            and len(asset["sha256"]) == 64
            for asset in assets
        )
    ):
        raise AssertionError("provenance assets must contain names, URLs, and SHA-256 digests")
    entries = data.get("styles")
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise AssertionError("provenance styles must be a list of objects")
    indexed = {entry["style"]: entry for entry in entries}
    expect(set(indexed), set(STYLES), "provenance styles")
    return indexed


def main() -> None:
    """Validate all four generated styles."""
    provenance_path = DIST / "provenance.json"
    if not provenance_path.is_file():
        raise SystemExit("dist/provenance.json not found; run make build first")
    summaries = validate_provenance(json.loads(provenance_path.read_text(encoding="utf-8")))
    for style in STYLES:
        path, summary = DIST / f"SummerGhost-{style}.ttf", summaries[style]
        if not path.is_file():
            raise AssertionError(f"missing {path.name}")
        validate_font(path, style)
        validate_shaping(path)
        expect(summary.get("sample_origins"), EXPECTED_ORIGINS, f"{style} source precedence")
        counts = summary.get("codepoints")
        if not isinstance(counts, dict) or counts.get("ibm", 0) < 1_000:
            raise AssertionError(f"{style} has insufficient IBM fallback coverage")
        expect(sum(counts.values()), summary.get("total_codepoints"), f"{style} source counts")
        expect(summary.get("size_bytes"), path.stat().st_size, f"{style} artifact size")
    print("validated Summer Ghost Regular/Bold/Italic/BoldItalic")


if __name__ == "__main__":
    main()
