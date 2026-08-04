#!/usr/bin/env python3
"""Validate Summer Ghost names, geometry, coverage, provenance, and shaping."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from statistics import median
from typing import Any, TypeVar

import uharfbuzz as hb
import unicodedata2 as unicodedata
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.ttLib import TTFont

ROOT, STYLES = Path(__file__).resolve().parents[1], ("Regular", "Bold", "Italic", "BoldItalic")
DIST = ROOT / "dist"
IBM_COMMIT = "ceee82fa88781b8310b198fd302480efaeac609e"
MPLUS1P_COMMIT = "2796410152d4f9524b68ed46e69c1b60f8e0f7c3"
NINJAL_ARCHIVE_SHA256 = "62b01c19cb40dc4b64b1e1da776fca483e19e21c2772cc3f9db9a067bedbc84d"
NINJAL_TTF_SHA256 = "e1301406c49dffed801bc12f0bb6a148f90215d4cf7d3a7bb0831cd798f6345e"
ALLOWED_ORIGINS = frozenset({"ubuntu", "mplus1p", "biz", "ninjal", "ibm", "generated"})
APPROVED_ASSETS = {
    "ubuntu-font-family-0.83.zip": (
        "https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip",
        "61a2b342526fd552f19fef438bb9211a8212de19ad96e32a1209c039f1d68ecf",
    ),
    "MPLUS1p-Regular.ttf": (
        f"https://raw.githubusercontent.com/google/fonts/{MPLUS1P_COMMIT}/ofl/mplus1p/MPLUS1p-Regular.ttf",
        "2f294ad496432b1608f070d310e3aa2adcf1de4af429f4901df97ec4bd361ed1",
    ),
    "MPLUS1p-Bold.ttf": (
        f"https://raw.githubusercontent.com/google/fonts/{MPLUS1P_COMMIT}/ofl/mplus1p/MPLUS1p-Bold.ttf",
        "76eb077b0a31ca33ca40238e47da5a17e2786741607cec09678d7d2e5ab1afc1",
    ),
    "BIZUDGothic-1.051.zip": (
        "https://github.com/googlefonts/morisawa-biz-ud-gothic/releases/download/v1.051/BIZUDGothic.zip",
        "30692df621b92df13b88f1360aed1ab6ae50de441bce751a396c6439045cd759",
    ),
    "ninjal_hentaigana.zip": (
        "https://cid.ninjal.ac.jp/kana/ninjal_hentaigana.zip",
        NINJAL_ARCHIVE_SHA256,
    ),
    "IBMPlexSansJP-Regular.ttf": (
        f"https://raw.githubusercontent.com/IBM/plex/{IBM_COMMIT}/packages/"
        "plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Regular.ttf",
        "825b5c933c3fdb380eb84195788559103ae12710098218a1848376e35a45fcce",
    ),
    "IBMPlexSansJP-Bold.ttf": (
        f"https://raw.githubusercontent.com/IBM/plex/{IBM_COMMIT}/packages/"
        "plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Bold.ttf",
        "85645e1bc1f92778e06c100c7bc6c6720b1d3955a8eee8d38c805589f59a261e",
    ),
}
BIZ_UVS_TOTAL = 10_160
BIZ_UVS_SELECTOR_COUNTS = {
    0xFE00: 83,
    0xFE01: 3,
    0xE0100: 9_643,
    0xE0101: 404,
    0xE0102: 22,
    0xE0103: 3,
    0xE0104: 1,
    0xE0105: 1,
}
NINJAL_CODEPOINTS = frozenset(range(0x1B001, 0x1B11F)) | {0x3099, 0x309A}
ORPHAN_CODEPOINTS = frozenset(
    set(range(0x2FF0, 0x3000))
    | {0x31EF}
    | set(range(0x1B120, 0x1B129))
    | set(range(0x1B130, 0x1B169))
    | {0x2A708, 0x2CEFF, 0x2CF00, 0x2CF02}
)
EXPECTED_ORIGINS = {
    "U+0041": "ubuntu",
    "U+2190": "generated",
    "U+21B5": "generated",
    "U+23CE": "generated",
    "U+2500": "generated",
    "U+2731": "generated",
    "U+3042": "mplus1p",
    "U+65E5": "biz",
    "U+FF11": "biz",
    "U+3405": "ibm",
}
NEOVIM_GLYPHS = {
    0x02B3,
    0x02B8,
    0x02E2,
    0x02E3,
    0x1D2C,
    0x1D2E,
    0x1D30,
    0x1D31,
    0x1D33,
    0x1D34,
    0x1D35,
    0x1D36,
    0x1D37,
    0x1D38,
    0x1D39,
    0x1D3A,
    0x1D3C,
    0x1D3E,
    0x1D3F,
    0x1D40,
    0x1D41,
    0x1D42,
    0x1D43,
    0x1D47,
    0x1D48,
    0x1D49,
    0x1D4D,
    0x1D4F,
    0x1D50,
    0x1D52,
    0x1D56,
    0x1D57,
    0x1D58,
    0x1D5B,
    0x1D9C,
    0x1DA0,
    0x1DBB,
    0x2071,
    0x207B,
    0x207D,
    0x207E,
    0x207F,
    0x2C7D,
}
MODIFIER_BOUNDS_ENVELOPE = (-32, 160, 544, 780)
REQUIRED = {
    0x0041: "Ubuntu Mono Latin",
    0x21B5: "Neovim return arrow",
    0x23CE: "fish omitted-newline return symbol",
    0x2460: "circled digit one",
    0x2500: "generated box drawing",
    0x2731: "generated heavy asterisk",
    0x2580: "upper half block",
    0x2590: "right half block",
    0x2596: "quadrant lower-left block",
    0x259F: "quadrant complement block",
    0x3042: "M PLUS hiragana",
    0x30A2: "M PLUS katakana",
    0x65E5: "BIZ kanji",
    0x9AD9: "BIZ Japanese-name kanji",
    0xFA11: "BIZ compatibility ideograph",
    0x3405: "IBM Plex Sans JP fallback",
    0x3099: "NINJAL combining hentaigana mark",
    0x309A: "NINJAL combining hentaigana mark",
    0x1B001: "NINJAL hentaigana",
    0x1B11E: "NINJAL hentaigana",
    0x2985: "left white parenthesis",
    0x2986: "right white parenthesis",
}
WHITE_PARENTHESIS_PAIR = (0x2985, 0x2986)
FULL_WIDTH_OVERRIDES = frozenset(WHITE_PARENTHESIS_PAIR)
RETURN_MARKS = (0x21B5, 0x23CE)
RETURN_MARK_BOUNDS = {False: (-66, 53, 453, 623), True: (-73, 41, 471, 618)}
HEAVY_ASTERISK_CODEPOINT = 0x2731
HEAVY_ASTERISK_BOUNDS = {False: (48, 45, 464, 509), True: (40, 40, 472, 514)}
HEAVY_ASTERISK_CONTOUR_BOUNDS = {
    False: ((48, 69, 464, 485), (48, 69, 464, 485), (224, 45, 288, 509)),
    True: ((40, 61, 472, 493), (40, 61, 472, 493), (212, 40, 300, 514)),
}
HEAVY_ASTERISK_HASH = {
    False: "6aa900a082ce94f072ad081d139e7dcb4753b59b4d75a9bca959455ca561d8a3",
    True: "46132337f1fc1dfec9f99edb05c0417a566d2262d2b1c1e62432d253a998db4d",
}
CHECK_MARK_CODEPOINT = 0x2714
CHECK_MARK_BOUNDS = {False: (35, 163, 499, 717), True: (25, 158, 508, 722)}
HORIZONTAL_ARROWS = (0x2190, 0x2192)
HORIZONTAL_ARROW_Y_SHIFT = -63
VERTICAL_ARROWS = (0x2191, 0x2193)
BASIC_ARROWS = HORIZONTAL_ARROWS + VERTICAL_ARROWS
MIRRORED_HORIZONTAL_ARROW_PAIRS = ((0x21D0, 0x21D2),)
ENCLOSED_DIGITS = range(0x2460, 0x2474)
ENCLOSED_DIGIT_INK_SIZE = {False: (630, 846), True: (644, 866)}
ENCLOSED_DIGIT_BOUNDS = {False: (-59, -73, 571, 773), True: (-66, -83, 578, 783)}
ENCLOSED_DIGIT_CENTER = (256, 350)
ENCLOSED_DIGIT_ASPECT_RANGE = (0.74, 0.75)
ENCLOSED_DIGIT_INNER_BOUNDS = {False: (-37, -44, 549, 745), True: (-32, -37, 544, 737)}
ENCLOSED_DIGIT_NUMERAL_CONTOURS = (1, 1, 1, 2, 1, 2, 1, 3, 2, 3, 2, 2, 2, 3, 2, 3, 2, 4, 3, 3)
PLAIN_CIRCLE_BOUNDS = {
    False: {0x25CB: (6, 89, 506, 589), 0x25CF: (6, 89, 506, 589), 0x3007: (109, -68, 915, 739)},
    True: {0x25CB: (6, 89, 506, 589), 0x25CF: (6, 89, 506, 589), 0x3007: (100, -80, 924, 744)},
}
GEOMETRIC_CELL_FIT_SYMBOLS = frozenset(
    {
        0x25A0,
        0x25A1,
        0x25B2,
        0x25B3,
        0x25BC,
        0x25BD,
        0x25C6,
        0x25C7,
        0x25CB,
        0x25CE,
        0x25CF,
        0x25EF,
        0x2605,
        0x2606,
    }
)
EVERYDAY_CELL_FIT_SYMBOLS = frozenset({0x203B, 0x2103, 0x2109, 0x2600, 0x2601, 0x2602, 0x260E, 0x266A, 0x266F, 0x2713})
CELL_FIT_HEIGHTS = {
    False: {
        0x203B: 501,
        0x2103: 490,
        0x2109: 446,
        0x25A0: 501,
        0x25A1: 501,
        0x25B2: 480,
        0x25B3: 480,
        0x25BC: 480,
        0x25BD: 480,
        0x25C6: 501,
        0x25C7: 501,
        0x25CB: 500,
        0x25CE: 500,
        0x25CF: 500,
        0x25EF: 499,
        0x2600: 500,
        0x2601: 398,
        0x2602: 496,
        0x2605: 487,
        0x2606: 487,
        0x260E: 410,
        0x266A: 651,
        0x266F: 677,
        0x2713: 518,
    },
    True: {
        0x203B: 501,
        0x2103: 482,
        0x2109: 423,
        0x25A0: 501,
        0x25A1: 501,
        0x25B2: 480,
        0x25B3: 480,
        0x25BC: 480,
        0x25BD: 480,
        0x25C6: 501,
        0x25C7: 501,
        0x25CB: 500,
        0x25CE: 500,
        0x25CF: 500,
        0x25EF: 501,
        0x2600: 500,
        0x2601: 398,
        0x2602: 496,
        0x2605: 487,
        0x2606: 487,
        0x260E: 410,
        0x266A: 625,
        0x266F: 671,
        0x2713: 518,
    },
}
AUDITED_BOUNDS = {
    False: {
        0x2190: (6, 50, 506, 504),
        0x2191: (29, 22, 483, 695),
        0x2192: (6, 50, 506, 504),
        0x2193: (29, -15, 483, 659),
        0x25C9: (47, 129, 466, 548),
    },
    True: {
        0x2190: (6, 44, 506, 511),
        0x2191: (22, 14, 490, 701),
        0x2192: (6, 44, 506, 511),
        0x2193: (21, -20, 489, 667),
        0x25C9: (43, 126, 469, 552),
    },
}
BLOCK_RECTANGLES = {
    0x2580: ((0, 338, 512, 850),),
    **{cp: ((0, -174, 512, -174 + 128 * (cp - 0x2580)),) for cp in range(0x2581, 0x2589)},
    **{cp: ((0, -174, 64 * (0x2590 - cp), 850),) for cp in range(0x2589, 0x2590)},
    0x2590: ((256, -174, 512, 850),),
    0x2594: ((0, 722, 512, 850),),
    0x2595: ((448, -174, 512, 850),),
    0x2596: ((0, -174, 256, 338),),
    0x2597: ((256, -174, 512, 338),),
    0x2598: ((0, 338, 256, 850),),
    0x2599: ((0, -174, 256, 850), (256, -174, 512, 338)),
    0x259A: ((0, 338, 256, 850), (256, -174, 512, 338)),
    0x259B: ((0, -174, 256, 850), (256, 338, 512, 850)),
    0x259C: ((0, 338, 512, 850), (256, -174, 512, 338)),
    0x259D: ((256, 338, 512, 850),),
    0x259E: ((0, -174, 256, 338), (256, 338, 512, 850)),
    0x259F: ((0, -174, 512, 338), (256, 338, 512, 850)),
}
INK_HEIGHTS = {
    False: {0x0041: 0.638, 0x3042: 0.788, 0x65E5: 0.760, 0x8A9E: 0.791},
    True: {0x0041: 0.638, 0x3042: 0.796, 0x65E5: 0.764, 0x8A9E: 0.795},
}
EXPECTED_SCALES = {
    "Regular": {"mplus1p": 0.91, "biz": 0.87, "ninjal": 1.0, "ibm": 0.90},
    "Italic": {"mplus1p": 0.91, "biz": 0.87, "ninjal": 1.0, "ibm": 0.90},
    "Bold": {"mplus1p": 0.90, "biz": 0.87, "ninjal": 1.0, "ibm": 0.90},
    "BoldItalic": {"mplus1p": 0.90, "biz": 0.87, "ninjal": 1.0, "ibm": 0.90},
}
ORDINARY_KANA_CODEPOINTS = tuple(range(0x3041, 0x3097)) + tuple(range(0x30A1, 0x30FB))
MPLUS_AUDITED_CODEPOINTS = (0x3042, 0x3093, 0x30A2, 0x30F3, 0x3001, 0x3002)
ORDINARY_KANA_DISTRIBUTION = {
    False: {"count": 176, "width_range": (545, 899), "height_range": (480, 863), "median": (776, 761)},
    True: {"count": 176, "width_range": (555, 892), "height_range": (518, 860), "median": (786.5, 768.5)},
}
MPLUS_REPRESENTATIVE_BOUNDS = {
    False: {
        0x3042: (136, -59, 888, 748),
        0x3093: (121, -43, 913, 726),
        0x30A2: (160, -31, 896, 664),
        0x30F3: (183, -9, 903, 679),
        0x3001: (100, -55, 343, 195),
        0x3002: (103, -74, 389, 212),
    },
    True: {
        0x3042: (128, -71, 896, 744),
        0x3093: (116, -53, 918, 733),
        0x30A2: (155, -42, 902, 670),
        0x30F3: (169, -18, 908, 691),
        0x3001: (104, -69, 371, 207),
        0x3002: (98, -82, 400, 219),
    },
}
AUDITED_NON_MPLUS_ORIGINS = {
    0x65E5: "biz",
    0x3405: "ibm",
    0x1B001: "ninjal",
    0xFF76: "biz",
    0x0041: "ubuntu",
    0x2190: "generated",
    0x2500: "generated",
}
AUDITED_NON_MPLUS_BOUNDS = {
    "Regular": {
        0x65E5: (186, -67, 836, 711),
        0x3405: (154, -13, 832, 764),
        0x1B001: (135, 0, 867, 793),
        0xFF76: (55, -18, 430, 716),
        0x0041: (9, 0, 503, 653),
        0x2190: (6, 50, 506, 504),
        0x2500: (0, 295, 512, 381),
    },
    "Italic": {
        0x65E5: (186, -67, 836, 711),
        0x3405: (154, -13, 832, 764),
        0x1B001: (135, 0, 867, 793),
        0xFF76: (55, -18, 430, 716),
        0x0041: (-13, 0, 480, 653),
        0x2190: (6, 50, 506, 504),
        0x2500: (0, 295, 512, 381),
    },
    "Bold": {
        0x65E5: (176, -68, 849, 714),
        0x3405: (138, -25, 864, 780),
        0x1B001: (135, 0, 867, 793),
        0xFF76: (46, -35, 438, 724),
        0x0041: (9, 0, 503, 653),
        0x2190: (6, 44, 506, 511),
        0x2500: (0, 282, 512, 394),
    },
    "BoldItalic": {
        0x65E5: (176, -68, 849, 714),
        0x3405: (138, -25, 864, 780),
        0x1B001: (135, 0, 867, 793),
        0xFF76: (46, -35, 438, 724),
        0x0041: (-6, 0, 487, 653),
        0x2190: (6, 44, 506, 511),
        0x2500: (0, 282, 512, 394),
    },
}
T = TypeVar("T")
Contour = list[tuple[str, tuple[Any, ...]]]


def expect(actual: T, expected: T, context: str) -> None:
    """Raise a contextual assertion when two values differ."""
    if actual != expected:
        raise AssertionError(f"{context}: expected {expected!r}, got {actual!r}")


def expect_bounds_with_tolerance(
    actual: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
    tolerance: int,
    context: str,
) -> None:
    """Require each bounds coordinate to remain within an approved recipe tolerance."""
    if any(abs(value - target) > tolerance for value, target in zip(actual, expected, strict=True)):
        raise AssertionError(f"{context}: expected {expected!r} +/- {tolerance}, got {actual!r}")


def _parse_codepoint(value: object) -> int | None:
    """Parse a provenance codepoint key without accepting ambiguous labels."""
    if not isinstance(value, str) or not value.startswith("U+"):
        return None
    try:
        return int(value[2:], 16)
    except ValueError:
        return None


def ownership_map(summary: Mapping[str, object], style: str) -> dict[int, str]:
    """Read the explicit per-codepoint ownership index emitted by the builder."""
    raw = summary.get("ownership")
    if not isinstance(raw, Mapping) or not raw:
        raise AssertionError(f"{style} provenance ownership must be a non-empty object")
    parsed: dict[int, str] = {}
    for key, origin in raw.items():
        codepoint = _parse_codepoint(key)
        if codepoint is None or not isinstance(origin, str):
            raise AssertionError(f"{style} provenance has malformed ownership entry: {key!r}")
        if codepoint in parsed:
            raise AssertionError(f"{style} provenance duplicates U+{codepoint:04X} ownership")
        parsed[codepoint] = origin
    if set(parsed.values()) - ALLOWED_ORIGINS:
        unknown = sorted(set(parsed.values()) - ALLOWED_ORIGINS)
        raise AssertionError(f"{style} provenance has unknown origins: {unknown}")
    return parsed


def validate_ownership(summary: Mapping[str, object], style: str, cmap: Mapping[int, str]) -> None:
    """Validate explicit source ownership and local-generation boundaries."""
    owners = ownership_map(summary, style)
    mapped = set(cmap)
    expect(set(owners), mapped, f"{style} ownership/cmap coverage")
    expect(mapped & ORPHAN_CODEPOINTS, set(), f"{style} approved orphan removals")
    expect(
        {cp for cp in ORDINARY_KANA_CODEPOINTS if owners.get(cp) != "mplus1p"},
        set(),
        f"{style} ordinary kana M PLUS ownership",
    )
    expect(
        {cp for cp in MPLUS_AUDITED_CODEPOINTS if owners.get(cp) != "mplus1p"},
        set(),
        f"{style} audited M PLUS ownership",
    )
    expect(
        {cp for cp, origin in owners.items() if origin == "ninjal"},
        set(NINJAL_CODEPOINTS),
        f"{style} direct NINJAL coverage",
    )
    generated = (
        set(range(0x2190, 0x2194))
        | set(RETURN_MARKS)
        | set(range(0x2500, 0x2591))
        | set(range(0x2594, 0x25A0))
        | set(NEOVIM_GLYPHS)
        | {CHECK_MARK_CODEPOINT, HEAVY_ASTERISK_CODEPOINT}
    )
    expect(
        {cp for cp in generated if cp in owners and owners[cp] != "generated"},
        set(),
        f"{style} generated semantic ownership",
    )
    expect(owners.get(CHECK_MARK_CODEPOINT), "generated", f"{style} check-mark ownership")


def name(font: TTFont, name_id: int) -> str:
    """Read an English Windows name record."""
    record = font["name"].getName(name_id, 3, 1, 0x409)
    return record.toUnicode() if record else ""


def is_private_use(codepoint: int) -> bool:
    """Return whether a codepoint belongs to a Unicode private-use area."""
    return bool(unicodedata.category(chr(codepoint)) == "Co")


def cell_width(codepoint: int) -> int:
    """Mirror the builder's Unicode 17 grid rule and Japanese overrides."""
    if codepoint in FULL_WIDTH_OVERRIDES:
        return 1024
    char = chr(codepoint)
    if unicodedata.category(char) in {"Mn", "Me"}:
        return 0
    return 1024 if unicodedata.east_asian_width(char) in {"W", "F"} else 512


def _bounds(font: TTFont, glyph_name: str) -> tuple[int, int, int, int]:
    glyph = font["glyf"][glyph_name]
    glyph.recalcBounds(font["glyf"])
    return glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax


def validate_mplus_optical_balance(font: TTFont, style: str) -> None:
    """Lock the final M PLUS kana distribution and representative outline bounds."""
    cmap = font.getBestCmap()
    bold = "Bold" in style
    expected = ORDINARY_KANA_DISTRIBUTION[bold]
    missing = sorted(set(ORDINARY_KANA_CODEPOINTS) - set(cmap))
    expect(len(missing), 0, f"{style} ordinary kana coverage")
    widths, heights = [], []
    for codepoint in ORDINARY_KANA_CODEPOINTS:
        x_min, y_min, x_max, y_max = _bounds(font, cmap[codepoint])
        widths.append(x_max - x_min)
        heights.append(y_max - y_min)
    expect(len(widths), expected["count"], f"{style} ordinary kana count")
    expect((min(widths), max(widths)), expected["width_range"], f"{style} ordinary kana width distribution")
    expect((min(heights), max(heights)), expected["height_range"], f"{style} ordinary kana height distribution")
    expect((median(widths), median(heights)), expected["median"], f"{style} ordinary kana bbox median")
    for codepoint, expected_bounds in MPLUS_REPRESENTATIVE_BOUNDS[bold].items():
        expect_bounds_with_tolerance(
            _bounds(font, cmap[codepoint]),
            expected_bounds,
            1,
            f"{style} U+{codepoint:04X} M PLUS representative bounds",
        )


def validate_non_mplus_representatives(font: TTFont, style: str, owners: Mapping[int, str]) -> None:
    """Ensure non-target layers retain ownership and final outline geometry."""
    cmap = font.getBestCmap()
    for codepoint, origin in AUDITED_NON_MPLUS_ORIGINS.items():
        expect(owners.get(codepoint), origin, f"{style} U+{codepoint:04X} audited ownership")
        expect(
            _bounds(font, cmap[codepoint]),
            AUDITED_NON_MPLUS_BOUNDS[style][codepoint],
            f"{style} U+{codepoint:04X} audited non-M PLUS bounds",
        )


def _recording_contours(font: TTFont, glyph_name: str) -> list[Contour]:
    """Decompose one glyph recording into closed contours."""
    recording = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[glyph_name].draw(recording)
    contours: list[Contour] = []
    current: Contour = []
    for operation, points in recording.value:
        if operation == "moveTo" and current:
            contours.append(current)
            current = []
        current.append((operation, points))
        if operation in {"closePath", "endPath"}:
            contours.append(current)
            current = []
    if current:
        contours.append(current)
    return contours


def _recording_bounds(font: TTFont, contour: Contour) -> tuple[float, float, float, float]:
    """Measure one decomposed recording contour."""
    recording = RecordingPen()
    recording.value = contour
    bounds_pen = BoundsPen(font.getGlyphSet())
    recording.replay(bounds_pen)
    if bounds_pen.bounds is None:
        raise AssertionError("empty contour in circled digit")
    x_min, y_min, x_max, y_max = bounds_pen.bounds
    return float(x_min), float(y_min), float(x_max), float(y_max)


def _contour_bounds(font: TTFont, glyph_name: str) -> tuple[tuple[int, int, int, int], ...]:
    """Return sorted bounds for every simple contour in a glyph."""
    glyph = font["glyf"][glyph_name]
    if glyph.isComposite():
        raise AssertionError(f"{glyph_name} must be a simple generated block glyph")
    coordinates, endpoints, _ = glyph.getCoordinates(font["glyf"])
    contours, start = [], 0
    for end in endpoints:
        points = coordinates[start : end + 1]
        contours.append(
            (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            )
        )
        start = end + 1
    return tuple(sorted(contours))


_LEGACY_ARROW_POINTS = {
    False: {
        0x2190: (
            (129, 309),
            (303, 156),
            (266, 113),
            (6, 340),
            (266, 567),
            (303, 524),
            (129, 372),
            (506, 372),
            (506, 309),
        ),
        0x2191: (
            (224, 573),
            (72, 399),
            (29, 436),
            (256, 695),
            (483, 436),
            (440, 399),
            (288, 573),
            (288, 22),
            (224, 22),
        ),
        0x2192: (
            (6, 372),
            (382, 372),
            (209, 524),
            (246, 567),
            (506, 340),
            (246, 113),
            (209, 156),
            (382, 309),
            (6, 309),
        ),
        0x2193: (
            (288, 107),
            (440, 281),
            (483, 244),
            (256, -15),
            (29, 244),
            (72, 281),
            (224, 107),
            (224, 659),
            (288, 659),
        ),
        0x21D0: (
            (201, 155),
            (6, 350),
            (201, 546),
            (233, 516),
            (144, 428),
            (506, 428),
            (506, 390),
            (106, 390),
            (67, 350),
            (106, 311),
            (506, 311),
            (506, 273),
            (144, 273),
            (233, 184),
        ),
        0x21D2: (
            (311, 155),
            (506, 350),
            (311, 546),
            (279, 516),
            (368, 428),
            (6, 428),
            (6, 390),
            (406, 390),
            (445, 350),
            (406, 311),
            (6, 311),
            (6, 273),
            (368, 273),
            (279, 184),
        ),
    },
    True: {
        0x2190: (
            (181, 292),
            (326, 165),
            (276, 107),
            (6, 340),
            (276, 574),
            (326, 515),
            (181, 388),
            (506, 388),
            (506, 292),
        ),
        0x2191: (
            (208, 526),
            (81, 380),
            (22, 431),
            (256, 701),
            (490, 431),
            (431, 380),
            (304, 526),
            (304, 14),
            (208, 14),
        ),
        0x2192: (
            (6, 388),
            (331, 388),
            (186, 515),
            (236, 574),
            (506, 340),
            (236, 107),
            (186, 165),
            (331, 292),
            (6, 292),
        ),
        0x2193: (
            (303, 154),
            (430, 301),
            (489, 249),
            (255, -20),
            (21, 249),
            (80, 301),
            (207, 154),
            (207, 667),
            (303, 667),
        ),
        0x21D0: (
            (226, 130),
            (6, 350),
            (226, 570),
            (279, 523),
            (201, 446),
            (506, 446),
            (506, 387),
            (141, 387),
            (104, 350),
            (141, 313),
            (506, 313),
            (506, 254),
            (201, 254),
            (279, 177),
        ),
        0x21D2: (
            (286, 130),
            (506, 350),
            (286, 570),
            (233, 523),
            (311, 446),
            (6, 446),
            (6, 387),
            (371, 387),
            (408, 350),
            (371, 313),
            (6, 313),
            (6, 254),
            (311, 254),
            (233, 177),
        ),
    },
}
_LEGACY_ARROW_NAMES = {
    0x2190: "arrowleft",
    0x2191: "arrowup",
    0x2192: "arrowright",
    0x2193: "arrowdown",
    0x21D0: "arrowdblleft",
    0x21D2: "arrowdblright",
}
_LEGACY_ARROW_LSB = {
    False: {0x2190: 6, 0x2191: 29, 0x2192: 6, 0x2193: 29, 0x21D0: 6, 0x21D2: 6},
    True: {0x2190: 6, 0x2191: 22, 0x2192: 6, 0x2193: 21, 0x21D0: 6, 0x21D2: 6},
}
_LEGACY_ARROW_HASH = {
    False: {
        0x2190: "035b40001177a9bb02e7fc452cfd985fe1b713f88340f5c2872c2b08d485c4e0",
        0x2191: "f1f15f7efbb56277204b83e4d9c60e1903e9182b1b87dbfe2938206d2ccafcc3",
        0x2192: "add1ea21605f6b022218d77ca4579481a06232de585e727bbaafdec9c3ed6a0b",
        0x2193: "2e93e9e4bbb5900cc5ed500de92d9c619fcc38959bf2c4cabdc78d9421f8d212",
        0x21D0: "dbbfc9b3236e006e23fe6c74de08470d5e707abd89435522a08bc6b520f42dbf",
        0x21D2: "ec36bc2838a6060804c5e8535716f9781f1d528fd3e174350c61933a56353dfc",
    },
    True: {
        0x2190: "91de95f9e5b93a354d326afdc84cc70ac8466148cc98a8732dfc65570384fcf6",
        0x2191: "022172ffb68f57c79c1a3de46da978a0d3c89dcd0b2baa10bac06cec606a1c00",
        0x2192: "398f68f4702c89148164bb2bf7696c4db22fa05419b39b1e752b1b0f1a4d7b9e",
        0x2193: "117eef6c0e4ef2c44406a23d2dff83987c77e03c9b899d7c97a7ae9a25d450d2",
        0x21D0: "5a9ed0e52a5e01a96d8e1ac56f721149588d84901b0617291b11ed4440f5e2b3",
        0x21D2: "814cf022e425f0a9af5d6624b73b3a853ed8e93d055200e5e4638482d78ad757",
    },
}
_LEGACY_ARROW_BOUNDS = {
    False: {
        0x2190: (6, 50, 506, 504),
        0x2191: (29, 22, 483, 695),
        0x2192: (6, 50, 506, 504),
        0x2193: (29, -15, 483, 659),
        0x21D0: (6, 155, 506, 546),
        0x21D2: (6, 155, 506, 546),
    },
    True: {
        0x2190: (6, 44, 506, 511),
        0x2191: (22, 14, 490, 701),
        0x2192: (6, 44, 506, 511),
        0x2193: (21, -20, 489, 667),
        0x21D0: (6, 130, 506, 570),
        0x21D2: (6, 130, 506, 570),
    },
}
_LEGACY_RETURN_POINTS = {
    False: (
        (58, 248),
        (231, 96),
        (193, 53),
        (-66, 280),
        (193, 506),
        (231, 463),
        (58, 311),
        (390, 311),
        (390, 623),
        (453, 623),
        (453, 248),
    ),
    True: (
        (102, 227),
        (247, 100),
        (197, 41),
        (-73, 275),
        (197, 508),
        (247, 450),
        (102, 323),
        (374, 323),
        (374, 618),
        (471, 618),
        (471, 227),
    ),
}
_LEGACY_RETURN_HASH = {
    False: "74b2bec4d49be203850ad9e66160cea43abcaef43b595bcd896adbba6f1db600",
    True: "ef75687c21a9d8b2104bb79399d3d19541cf80ae4616795092d81fed06b10619",
}


def validate_legacy_arrows(font: TTFont, style: str) -> None:
    """Require last-good arrow contours and the local horizontal alignment."""
    bold = "Bold" in style
    cmap, glyf = font.getBestCmap(), font["glyf"]
    expect(cmap[0x21B5], cmap[0x23CE], f"{style} return cmap alias identity")
    for codepoint in (*BASIC_ARROWS, 0x21B5, 0x23CE, 0x21D0, 0x21D2):
        glyph_name = cmap[codepoint]
        points = _LEGACY_RETURN_POINTS[bold] if codepoint in RETURN_MARKS else _LEGACY_ARROW_POINTS[bold][codepoint]
        if codepoint in HORIZONTAL_ARROWS:
            points = tuple((x, y + HORIZONTAL_ARROW_Y_SHIFT) for x, y in points)
        expected_name = "carriagereturn" if codepoint in RETURN_MARKS else _LEGACY_ARROW_NAMES[codepoint]
        expected_lsb = (-66 if not bold else -73) if codepoint in RETURN_MARKS else _LEGACY_ARROW_LSB[bold][codepoint]
        expected_hash = _LEGACY_RETURN_HASH[bold] if codepoint in RETURN_MARKS else _LEGACY_ARROW_HASH[bold][codepoint]
        glyph = glyf[glyph_name]
        expect(glyph_name, expected_name, f"{style} U+{codepoint:04X} cmap glyph")
        expect(font["hmtx"].metrics[glyph_name], (512, expected_lsb), f"{style} U+{codepoint:04X} hmtx")
        expect(glyph.numberOfContours, 1, f"{style} U+{codepoint:04X} contours")
        actual, ends, flags = glyph.getCoordinates(glyf)
        expect(tuple((int(x), int(y)) for x, y in actual), points, f"{style} U+{codepoint:04X} coordinates")
        expect(tuple(int(x) for x in ends), (len(points) - 1,), f"{style} U+{codepoint:04X} endPts")
        expect(tuple(int(x) for x in flags), (1,) * len(points), f"{style} U+{codepoint:04X} flags")
        expected_bounds = (
            RETURN_MARK_BOUNDS[bold] if codepoint in RETURN_MARKS else _LEGACY_ARROW_BOUNDS[bold][codepoint]
        )
        expect(_bounds(font, glyph_name), expected_bounds, f"{style} U+{codepoint:04X} bounds")
        expect(
            hashlib.sha256(glyph.compile(glyf)).hexdigest(),
            expected_hash,
            f"{style} U+{codepoint:04X} glyf fingerprint",
        )


def validate_heavy_asterisk(font: TTFont, style: str) -> None:
    """Require the local U+2731 outline to remain centered in one terminal cell."""
    bold = "Bold" in style
    cmap, glyf = font.getBestCmap(), font["glyf"]
    glyph_name = cmap[HEAVY_ASTERISK_CODEPOINT]
    expected_bounds = HEAVY_ASTERISK_BOUNDS[bold]
    expect(glyph_name, "uni2731", f"{style} U+2731 cmap glyph")
    expect(
        font["hmtx"].metrics[glyph_name],
        (512, expected_bounds[0]),
        f"{style} U+2731 hmtx",
    )
    expect(glyf[glyph_name].numberOfContours, 3, f"{style} U+2731 contours")
    expect(_bounds(font, glyph_name), expected_bounds, f"{style} U+2731 bounds")
    expect(
        _contour_bounds(font, glyph_name),
        HEAVY_ASTERISK_CONTOUR_BOUNDS[bold],
        f"{style} U+2731 contour bounds",
    )
    expect(
        hashlib.sha256(glyf[glyph_name].compile(glyf)).hexdigest(),
        HEAVY_ASTERISK_HASH[bold],
        f"{style} U+2731 glyf fingerprint",
    )


def _computed_global_metrics(font: TTFont) -> dict[str, int]:
    """Compute head, hhea, and maxp values directly from final glyph data."""
    glyf, hmtx = font["glyf"], font["hmtx"]
    bounds: list[tuple[int, int, int, int]] = []
    widths: list[tuple[int, int, int]] = []
    max_points = max_contours = max_composite_points = max_composite_contours = 0
    max_component_elements = max_component_depth = 0
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.recalcBounds(glyf)
        if glyph.numberOfContours > 0:
            glyph_bounds = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
            bounds.append(glyph_bounds)
            points, contours = glyph.getMaxpValues()
            max_points = max(max_points, points)
            max_contours = max(max_contours, contours)
        elif glyph.numberOfContours < 0:
            glyph.recalcBounds(glyf)
            bounds.append((glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax))
            points, contours, depth = glyph.getCompositeMaxpValues(glyf)
            max_composite_points = max(max_composite_points, points)
            max_composite_contours = max(max_composite_contours, contours)
            max_component_elements = max(max_component_elements, len(glyph.components))
            max_component_depth = max(max_component_depth, depth)
        if glyph.numberOfContours:
            advance, side_bearing = hmtx.metrics[glyph_name]
            width = glyph.xMax - glyph.xMin
            widths.append((advance, side_bearing, width))

    if bounds:
        head_x_min = min(item[0] for item in bounds)
        head_y_min = min(item[1] for item in bounds)
        head_x_max = max(item[2] for item in bounds)
        head_y_max = max(item[3] for item in bounds)
    else:
        head_x_min = head_y_min = head_x_max = head_y_max = 0
    if widths:
        hhea_min_lsb = min(item[1] for item in widths)
        hhea_min_rsb = min(advance - side_bearing - width for advance, side_bearing, width in widths)
        hhea_x_max_extent = max(side_bearing + width for _, side_bearing, width in widths)
    else:
        hhea_min_lsb = hhea_min_rsb = hhea_x_max_extent = 0
    return {
        "head.xMin": head_x_min,
        "head.yMin": head_y_min,
        "head.xMax": head_x_max,
        "head.yMax": head_y_max,
        "hhea.advanceWidthMax": max(advance for advance, _ in hmtx.metrics.values()),
        "hhea.minLeftSideBearing": hhea_min_lsb,
        "hhea.minRightSideBearing": hhea_min_rsb,
        "hhea.xMaxExtent": hhea_x_max_extent,
        "maxp.numGlyphs": len(font.getGlyphOrder()),
        "maxp.maxPoints": max_points,
        "maxp.maxContours": max_contours,
        "maxp.maxCompositePoints": max_composite_points,
        "maxp.maxCompositeContours": max_composite_contours,
        "maxp.maxComponentElements": max_component_elements,
        "maxp.maxComponentDepth": max_component_depth,
    }


def _validate_lsb_consistency(font: TTFont, font_name: str) -> None:
    """Require saved head.flags bit 1 and LSBs equal to final outline xMin."""
    head = font["head"]
    if not head.flags & (1 << 1):
        raise AssertionError(f"{font_name} head.flags bit 1 is not set")

    glyf, hmtx = font["glyf"], font["hmtx"]
    outlined = mismatches = 0
    samples: list[str] = []
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        if glyph.numberOfContours == 0:
            continue
        outlined += 1
        glyph.recalcBounds(glyf)
        lsb = hmtx.metrics[glyph_name][1]
        if lsb != glyph.xMin:
            mismatches += 1
            if len(samples) < 4:
                samples.append(f"{glyph_name}({lsb}!={glyph.xMin})")
    if mismatches:
        sample_text = ", ".join(samples)
        raise AssertionError(f"{font_name} hmtx LSB/xMin mismatches: {mismatches}/{outlined}; samples: {sample_text}")


def validate_font(path: Path, style: str) -> tuple[tuple[int, int, int, int], ...]:
    """Validate one compiled TrueType font."""
    with closing(TTFont(path, recalcBBoxes=False, recalcTimestamp=False)) as font:
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

        _validate_lsb_consistency(font, path.name)
        computed = _computed_global_metrics(font)
        for field, actual in (
            ("head.xMin", head.xMin),
            ("head.yMin", head.yMin),
            ("head.xMax", head.xMax),
            ("head.yMax", head.yMax),
            ("hhea.advanceWidthMax", hhea.advanceWidthMax),
            ("hhea.minLeftSideBearing", hhea.minLeftSideBearing),
            ("hhea.minRightSideBearing", hhea.minRightSideBearing),
            ("hhea.xMaxExtent", hhea.xMaxExtent),
            ("maxp.numGlyphs", font["maxp"].numGlyphs),
            ("maxp.maxPoints", font["maxp"].maxPoints),
            ("maxp.maxContours", font["maxp"].maxContours),
            ("maxp.maxCompositePoints", font["maxp"].maxCompositePoints),
            ("maxp.maxCompositeContours", font["maxp"].maxCompositeContours),
            ("maxp.maxComponentElements", font["maxp"].maxComponentElements),
            ("maxp.maxComponentDepth", font["maxp"].maxComponentDepth),
        ):
            expect(actual, computed[field], f"{path.name} recomputed {field}")
        for field in (
            "maxZones",
            "maxTwilightPoints",
            "maxStorage",
            "maxFunctionDefs",
            "maxInstructionDefs",
            "maxStackElements",
            "maxSizeOfInstructions",
        ):
            expect(getattr(font["maxp"], field), 1 if field == "maxZones" else 0, f"{path.name} stripped maxp {field}")

        widths = {font["hmtx"][glyph][0] for glyph in set(cmap.values())}
        if unexpected := widths - {0, 512, 1024}:
            raise AssertionError(f"{path.name} has unexpected advances: {sorted(unexpected)}")
        if pua := [cp for cp in cmap if is_private_use(cp)]:
            raise AssertionError(f"{path.name} maps {len(pua)} private-use codepoints")
        expect(set(cmap) & ORPHAN_CODEPOINTS, set(), f"{path.name} approved orphan removals")
        missing = [f"{description} U+{cp:04X}" for cp, description in REQUIRED.items() if cp not in cmap]
        if missing:
            raise AssertionError(f"{path.name} lacks: {', '.join(missing)}")
        missing_ninjal = sorted(NINJAL_CODEPOINTS - set(cmap))
        if missing_ninjal:
            raise AssertionError(f"{path.name} lacks direct NINJAL coverage: {missing_ninjal}")
        validate_mplus_optical_balance(font, style)
        neovim = NEOVIM_GLYPHS | {0x2714}
        for cp in neovim:
            glyph_name = cmap[cp]
            expect(font["hmtx"].metrics[glyph_name][0], 512, f"{path.name} U+{cp:04X} Neovim advance")
            if _bounds(font, glyph_name) == (0, 0, 0, 0):
                raise AssertionError(f"{path.name} U+{cp:04X} Neovim glyph is empty")
        for cp in NEOVIM_GLYPHS:
            x_min, y_min, x_max, y_max = _bounds(font, cmap[cp])
            if not (
                x_min >= MODIFIER_BOUNDS_ENVELOPE[0]
                and y_min >= MODIFIER_BOUNDS_ENVELOPE[1]
                and x_max <= MODIFIER_BOUNDS_ENVELOPE[2]
                and y_max <= MODIFIER_BOUNDS_ENVELOPE[3]
                and x_max > x_min
                and y_max > y_min
            ):
                raise AssertionError(f"{path.name} U+{cp:04X} modifier outside generated envelope")
        expect_bounds_with_tolerance(
            _bounds(font, cmap[CHECK_MARK_CODEPOINT]),
            CHECK_MARK_BOUNDS[bold],
            8,
            f"{path.name} check-mark bounds",
        )
        if len(cmap) < 15_000:
            raise AssertionError(f"{path.name} maps only {len(cmap)} Unicode codepoints")
        return_glyphs = tuple(cmap[codepoint] for codepoint in RETURN_MARKS)
        expect(len(set(return_glyphs)), 1, f"{path.name} return marks share one glyph")
        expect_bounds_with_tolerance(
            _bounds(font, return_glyphs[0]),
            RETURN_MARK_BOUNDS[bold],
            8,
            f"{path.name} return mark bounds",
        )
        for codepoint, glyph_name in cmap.items():
            expect(
                font["hmtx"].metrics[glyph_name][0],
                cell_width(codepoint),
                f"{path.name} U+{codepoint:04X} Unicode 17 advance",
            )
        expect(
            font["hmtx"].metrics[cmap[0x0311]][0],
            0,
            f"{path.name} U+0311 combining advance",
        )

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
        box_strokes: list[int] = []
        for cp in range(0x2500, 0x2580):
            x_min, y_min, x_max, y_max = _bounds(font, cmap[cp])
            expect(font["hmtx"].metrics[cmap[cp]][0], 512, f"{path.name} U+{cp:04X} box advance")
            if x_min < 0 or x_max > 512 or y_min < -174 or y_max > 850:
                raise AssertionError(
                    f"{path.name} U+{cp:04X} box drawing exceeds its cell: ({x_min}, {y_min}, {x_max}, {y_max})"
                )
        expect(_bounds(font, cmap[0x2500])[::2], (0, 512), f"{path.name} horizontal box connection")
        expect(_bounds(font, cmap[0x2502])[1::2], (-174, 850), f"{path.name} vertical box connection")
        box_strokes.extend(
            (
                _bounds(font, cmap[0x2500])[3] - _bounds(font, cmap[0x2500])[1],
                _bounds(font, cmap[0x2502])[2] - _bounds(font, cmap[0x2502])[0],
            )
        )
        if max(box_strokes) - min(box_strokes) > 10:
            raise AssertionError(f"{path.name} box drawing stroke mismatch: {box_strokes}")
        target_width, target_height = ENCLOSED_DIGIT_INK_SIZE[bold]
        enclosed_bounds: list[tuple[int, int, int, int]] = []
        for value, cp in enumerate(ENCLOSED_DIGITS, start=1):
            glyph_name = cmap[cp]
            bounds = _bounds(font, glyph_name)
            x_min, y_min, x_max, y_max = bounds
            width, height = x_max - x_min, y_max - y_min
            expect(font["hmtx"].metrics[glyph_name][0], 512, f"{path.name} U+{cp:04X} circled digit advance")
            expect((width, height), (target_width, target_height), f"{path.name} U+{cp:04X} Plemol ellipse size")
            expect(bounds, ENCLOSED_DIGIT_BOUNDS[bold], f"{path.name} U+{cp:04X} centered ellipse bounds")
            aspect = width / height
            if not ENCLOSED_DIGIT_ASPECT_RANGE[0] <= aspect <= ENCLOSED_DIGIT_ASPECT_RANGE[1]:
                raise AssertionError(
                    f"{path.name} U+{cp:04X} outer aspect {aspect:.6f} is outside {ENCLOSED_DIGIT_ASPECT_RANGE}"
                )
            one_cell_scale = min(1.0, 512 / width)
            if not 0.79 <= one_cell_scale <= 0.82:
                raise AssertionError(
                    f"{path.name} U+{cp:04X} one-cell fit scale {one_cell_scale:.6f} does not match Plemol"
                )
            expect(min(1.0, 1024 / width), 1.0, f"{path.name} U+{cp:04X} two-cell fit scale")
            contours = _recording_contours(font, glyph_name)
            if len(contours) < 3:
                raise AssertionError(f"{path.name} U+{cp:04X} lacks digit and annulus contours")
            outer_contour, inner_contour, numeral_contours = contours[0], contours[1], contours[2:]
            expect(
                _recording_bounds(font, outer_contour),
                tuple(map(float, ENCLOSED_DIGIT_BOUNDS[bold])),
                f"{path.name} U+{cp:04X} IBM outer ring bounds",
            )
            expect(
                _recording_bounds(font, inner_contour),
                tuple(map(float, ENCLOSED_DIGIT_INNER_BOUNDS[bold])),
                f"{path.name} U+{cp:04X} IBM inner ring bounds",
            )
            numeral_bounds = [_recording_bounds(font, contour) for contour in numeral_contours]
            expect(
                len(numeral_bounds),
                ENCLOSED_DIGIT_NUMERAL_CONTOURS[value - 1],
                f"{path.name} U+{cp:04X} IBM numeral contour count for {value}",
            )
            numeral_union = (
                min(bounds[0] for bounds in numeral_bounds),
                min(bounds[1] for bounds in numeral_bounds),
                max(bounds[2] for bounds in numeral_bounds),
                max(bounds[3] for bounds in numeral_bounds),
            )
            numeral_width = numeral_union[2] - numeral_union[0]
            numeral_height = numeral_union[3] - numeral_union[1]
            numeral_center = ((numeral_union[0] + numeral_union[2]) / 2, (numeral_union[1] + numeral_union[3]) / 2)
            if not (
                ENCLOSED_DIGIT_INNER_BOUNDS[bold][0]
                < numeral_union[0]
                < numeral_union[2]
                < ENCLOSED_DIGIT_INNER_BOUNDS[bold][2]
                and ENCLOSED_DIGIT_INNER_BOUNDS[bold][1]
                < numeral_union[1]
                < numeral_union[3]
                < ENCLOSED_DIGIT_INNER_BOUNDS[bold][3]
                and 380 <= numeral_height <= 405
                and (190 <= numeral_width <= 230 if value < 10 else 420 <= numeral_width <= 475)
                and abs(numeral_center[0] - ENCLOSED_DIGIT_CENTER[0]) <= 12
                and abs(numeral_center[1] - ENCLOSED_DIGIT_CENTER[1]) <= 10
            ):
                raise AssertionError(
                    f"{path.name} U+{cp:04X} numeral {value} is not readable and centered: {numeral_union}"
                )
            enclosed_bounds.append(bounds)
        for cp, expected_bounds in PLAIN_CIRCLE_BOUNDS[bold].items():
            expect(_bounds(font, cmap[cp]), expected_bounds, f"{path.name} U+{cp:04X} plain circle bounds")
        fitted_symbols = GEOMETRIC_CELL_FIT_SYMBOLS | EVERYDAY_CELL_FIT_SYMBOLS
        expect(
            GEOMETRIC_CELL_FIT_SYMBOLS & EVERYDAY_CELL_FIT_SYMBOLS,
            frozenset(),
            f"{path.name} fitted symbol classes",
        )
        expect(fitted_symbols, frozenset(CELL_FIT_HEIGHTS[bold]), f"{path.name} fitted symbol selection")
        for class_name, codepoints in (
            ("geometric", GEOMETRIC_CELL_FIT_SYMBOLS),
            ("everyday", EVERYDAY_CELL_FIT_SYMBOLS),
        ):
            for cp in codepoints:
                x_min, y_min, x_max, y_max = _bounds(font, cmap[cp])
                width, height = x_max - x_min, y_max - y_min
                expect(font["hmtx"].metrics[cmap[cp]][0], 512, f"{path.name} U+{cp:04X} {class_name} advance")
                if abs(width - 500) > 1 or x_min < 0 or x_max > 512 or y_min < -174 or y_max > 850:
                    raise AssertionError(
                        f"{path.name} U+{cp:04X} {class_name} symbol exceeds its fitted cell: "
                        f"({x_min}, {y_min}, {x_max}, {y_max})"
                    )
                expect(height, CELL_FIT_HEIGHTS[bold][cp], f"{path.name} U+{cp:04X} {class_name} aspect ratio")
        for cp, expected_bounds in AUDITED_BOUNDS[bold].items():
            expect(_bounds(font, cmap[cp]), expected_bounds, f"{path.name} U+{cp:04X} audited bounds")

        expect(set(range(0x2580, 0x25A0)) - set(cmap), set(), f"{path.name} Block Elements coverage")
        for cp in range(0x2580, 0x25A0):
            expect(font["hmtx"].metrics[cmap[cp]][0], 512, f"{path.name} U+{cp:04X} block advance")
        for cp, rectangles in BLOCK_RECTANGLES.items():
            expect(
                _contour_bounds(font, cmap[cp]),
                tuple(sorted(rectangles)),
                f"{path.name} U+{cp:04X} solid block geometry",
            )
        for cp in range(0x2591, 0x2594):
            x_min, _, x_max, _ = _bounds(font, cmap[cp])
            if x_min < 0 or x_max > 512:
                raise AssertionError(f"{path.name} U+{cp:04X} shade exceeds its cell")
        for cp in WHITE_PARENTHESIS_PAIR:
            glyph_name = cmap[cp]
            x_min, y_min, x_max, y_max = _bounds(font, glyph_name)
            expect(font["hmtx"].metrics[glyph_name][0], 1024, f"{path.name} U+{cp:04X} white parenthesis advance")
            if x_min < 0 or x_max > 1024 or y_min < -174 or y_max > 850:
                raise AssertionError(
                    f"{path.name} U+{cp:04X} white parenthesis exceeds full-width cell: "
                    f"({x_min}, {y_min}, {x_max}, {y_max})"
                )
        left_name, right_name = (cmap[cp] for cp in WHITE_PARENTHESIS_PAIR)
        left_points, left_ends, left_flags = font["glyf"][left_name].getCoordinates(font["glyf"])
        right_points, right_ends, right_flags = font["glyf"][right_name].getCoordinates(font["glyf"])
        expect(list(left_ends), list(right_ends), f"{path.name} white parenthesis contours")
        expect(list(left_flags), list(right_flags), f"{path.name} white parenthesis point flags")
        expect(
            list(left_points),
            [(1024 - x, y) for x, y in right_points],
            f"{path.name} exact white parenthesis mirror",
        )
        validate_heavy_asterisk(font, style)
        validate_legacy_arrows(font, style)
        icon_center_sums = {cp: sum(_bounds(font, cmap[cp])[1::2]) for cp in (0x002B, HEAVY_ASTERISK_CODEPOINT, 0x2192)}
        if max(icon_center_sums.values()) - min(icon_center_sums.values()) > 1:
            raise AssertionError(f"{path.name} OpenCode icon centerlines differ: {icon_center_sums}")
        for cp in HORIZONTAL_ARROWS:
            x_min, y_min, x_max, y_max = _bounds(font, cmap[cp])
            if x_min < 0 or x_max > 512 or x_max <= x_min or y_max <= y_min:
                raise AssertionError(f"{path.name} U+{cp:04X} is not a recognizable half-width arrow")
        vertical_widths = [_bounds(font, cmap[cp])[2] - _bounds(font, cmap[cp])[0] for cp in VERTICAL_ARROWS]
        if any(width <= 0 or width > 512 for width in vertical_widths):
            raise AssertionError(f"{path.name} vertical arrows are outside their half-width cell")
        for left_codepoint, right_codepoint in MIRRORED_HORIZONTAL_ARROW_PAIRS:
            left_name, right_name = cmap[left_codepoint], cmap[right_codepoint]
            for codepoint, glyph_name in ((left_codepoint, left_name), (right_codepoint, right_name)):
                x_min, y_min, x_max, y_max = _bounds(font, glyph_name)
                if x_min < 0 or x_max > 512 or y_min < -174 or y_max > 850 or x_max <= x_min or y_max <= y_min:
                    raise AssertionError(f"{path.name} U+{codepoint:04X} double-arrow is outside its cell")
            left_points, left_ends, left_flags = font["glyf"][left_name].getCoordinates(font["glyf"])
            right_points, right_ends, right_flags = font["glyf"][right_name].getCoordinates(font["glyf"])
            expect(list(left_ends), list(right_ends), f"{path.name} mirrored double-arrow contours")
            expect(list(left_flags), list(right_flags), f"{path.name} mirrored double-arrow point flags")
            expect(
                list(left_points),
                [(512 - x, y) for x, y in right_points],
                f"{path.name} exact double-arrow mirror",
            )
            for double_codepoint, single_codepoint in (
                (left_codepoint, HORIZONTAL_ARROWS[0]),
                (right_codepoint, HORIZONTAL_ARROWS[1]),
            ):
                double_points, double_ends, double_flags = font["glyf"][cmap[double_codepoint]].getCoordinates(
                    font["glyf"]
                )
                single_points, single_ends, single_flags = font["glyf"][cmap[single_codepoint]].getCoordinates(
                    font["glyf"]
                )
                if (
                    list(double_points) == list(single_points)
                    and list(double_ends) == list(single_ends)
                    and list(double_flags) == list(single_flags)
                ):
                    raise AssertionError(
                        f"{path.name} U+{double_codepoint:04X} double-arrow outline duplicates U+{single_codepoint:04X}"
                    )
        variation_tables = [table for table in font["cmap"].tables if table.format == 14]
        if not variation_tables or not variation_tables[0].uvsDict:
            raise AssertionError(f"{path.name} lacks Japanese variation sequences")
        selectors = len(variation_tables[0].uvsDict)
        selector_counts = {selector: len(entries) for selector, entries in variation_tables[0].uvsDict.items()}
        expect(
            sum(selector_counts.values()),
            BIZ_UVS_TOTAL,
            f"{path.name} direct BIZ variation-sequence count",
        )
        expect(selector_counts, BIZ_UVS_SELECTOR_COUNTS, f"{path.name} BIZ variation selectors")
        print(
            f"ok       {path.name}: {len(cmap):,} codepoints, "
            f"{len(font.getGlyphOrder()):,} glyphs, {selectors:,} selectors"
        )
        return tuple(enclosed_bounds)


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
        ("compact arrows", "←↓↑→", [512, 512, 512, 512]),
        ("OpenCode icons", "+✱→", [512, 512, 512]),
        ("return marks", "↵⏎", [512, 512]),
        ("mirrored double arrows", "⇐⇒", [512, 512]),
        ("white parentheses", "⦅⦆", [1024, 1024]),
        ("circled digits", "①②③", [512, 512, 512]),
        ("all circled digits", "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳", [512] * 20),
        ("ASCII-adjacent circled digit", "A①Z", [512, 512, 512]),
        ("CJK-adjacent circled digit", "日①本", [1024, 512, 1024]),
        ("space-adjacent circled digit", "A① ", [512, 512, 512]),
        ("line-end circled digit", "A①", [512, 512]),
        ("complete blocks", "▀▄▌▐▖▗▘▙▚▛▜▝▞▟", [512] * 14),
    ):
        run = shape(font, text)
        expect([advance for _, advance in run], expected, f"{path.name} {label} advances")
    return_marks = shape(font, "↵⏎")
    expect(return_marks[0][0], return_marks[1][0], f"{path.name} return marks shape to one glyph")
    text = "".join(chr(cp) for cp in ENCLOSED_DIGITS)
    isolated = [shape(font, char)[0] for char in text]
    expect(shape(font, text), isolated, f"{path.name} circled digits consecutive glyphs")
    for char, expected_glyph in zip(text, isolated, strict=True):
        expect(shape(font, f"A{char}Z")[1], expected_glyph, f"{path.name} {char} ASCII-adjacent glyph")
        expect(shape(font, f"日{char}本")[1], expected_glyph, f"{path.name} {char} CJK-adjacent glyph")
        expect(shape(font, f"A{char} ")[1], expected_glyph, f"{path.name} {char} space-adjacent glyph")
        expect(shape(font, f"A{char}")[1], expected_glyph, f"{path.name} {char} line-end glyph")
    base, variant = shape(font, "侮"), shape(font, "侮\ufe00")
    if len(base) != 1 or len(variant) != 1 or base[0][0] == variant[0][0]:
        raise AssertionError(f"{path.name} IVS shaping failed: base={base}, variant={variant}")
    expect((base[0][1], variant[0][1]), (1024, 1024), f"{path.name} IVS advances")


def validate_provenance(data: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    """Validate top-level build provenance and index its style records."""
    expect(data.get("family"), "Summer Ghost", "provenance family")
    expect(data.get("version"), "0.1.0", "provenance version")
    expect(data.get("mplus1p_commit"), MPLUS1P_COMMIT, "provenance M PLUS commit")
    expect(data.get("ibm_commit"), IBM_COMMIT, "provenance IBM commit")
    expect(
        data.get("inner_hashes"),
        {"ninjal_hentaigana.ttf": NINJAL_TTF_SHA256},
        "provenance NINJAL inner hash",
    )
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
    expect(len(assets), len(APPROVED_ASSETS), "provenance approved asset count")
    actual_assets = {asset["name"]: (asset["url"], asset["sha256"]) for asset in assets}
    expect(actual_assets, APPROVED_ASSETS, "provenance approved assets")
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
    enclosed_bounds = {}
    for style in STYLES:
        path, summary = DIST / f"SummerGhost-{style}.ttf", summaries[style]
        if not path.is_file():
            raise AssertionError(f"missing {path.name}")
        expect(summary.get("scales"), EXPECTED_SCALES[style], f"{style} effective source scales")
        enclosed_bounds[style] = validate_font(path, style)
        validate_shaping(path)
        samples = summary.get("sample_origins")
        if not isinstance(samples, Mapping):
            raise AssertionError(f"{style} source precedence is not an object")
        for sample_codepoint, origin in EXPECTED_ORIGINS.items():
            expect(samples.get(sample_codepoint), origin, f"{style} source precedence {sample_codepoint}")
        with closing(TTFont(path, recalcBBoxes=False, recalcTimestamp=False)) as font:
            validate_ownership(summary, style, font.getBestCmap())
            validate_non_mplus_representatives(font, style, ownership_map(summary, style))
        counts = summary.get("codepoints")
        if not isinstance(counts, dict):
            raise AssertionError(f"{style} source counts must use approved origins")
        if set(counts) != ALLOWED_ORIGINS:
            raise AssertionError(f"{style} source counts must use only approved origins")
        if not all(isinstance(value, int) and value >= 0 for value in counts.values()):
            raise AssertionError(f"{style} source counts must be non-negative integers")
        expect(counts.get("ninjal"), len(NINJAL_CODEPOINTS), f"{style} NINJAL source coverage")
        neovim_origins = summary.get("neovim_origins", {})
        if not isinstance(neovim_origins, dict):
            raise AssertionError(f"{style} Neovim provenance is not an object")
        expect(
            set(neovim_origins),
            {f"U+{cp:04X}" for cp in NEOVIM_GLYPHS | {0x2714}},
            f"{style} Neovim provenance coverage",
        )
        expect(
            {key: neovim_origins[key] for key in neovim_origins if key != "U+2714"},
            {f"U+{cp:04X}": "generated" for cp in NEOVIM_GLYPHS},
            f"{style} generated Neovim provenance",
        )
        expect(neovim_origins.get("U+2714"), "generated", f"{style} check-mark provenance")
        expect(summary.get("uvs_mappings_from_biz"), BIZ_UVS_TOTAL, f"{style} BIZ UVS provenance")
        expect(sum(counts.values()), summary.get("total_codepoints"), f"{style} source counts")
        expect(summary.get("size_bytes"), path.stat().st_size, f"{style} artifact size")
    with (
        closing(TTFont(DIST / "SummerGhost-Regular.ttf", recalcBBoxes=False, recalcTimestamp=False)) as regular,
        closing(TTFont(DIST / "SummerGhost-Italic.ttf", recalcBBoxes=False, recalcTimestamp=False)) as italic,
        closing(TTFont(DIST / "SummerGhost-Bold.ttf", recalcBBoxes=False, recalcTimestamp=False)) as bold,
        closing(TTFont(DIST / "SummerGhost-BoldItalic.ttf", recalcBBoxes=False, recalcTimestamp=False)) as bold_italic,
    ):
        for left, right, left_style, right_style, label in (
            (regular, italic, "Regular", "Italic", "Regular/Italic"),
            (bold, bold_italic, "Bold", "BoldItalic", "Bold/BoldItalic"),
        ):
            for upright_codepoint in (0x2714, HEAVY_ASTERISK_CODEPOINT):
                left_name = left.getBestCmap()[upright_codepoint]
                right_name = right.getBestCmap()[upright_codepoint]
                left_points = list(left["glyf"][left_name].getCoordinates(left["glyf"])[0])
                right_points = list(right["glyf"][right_name].getCoordinates(right["glyf"])[0])
                expect(left_points, right_points, f"U+{upright_codepoint:04X} upright {label}")
            left_owners = ownership_map(summaries[left_style], left_style)
            right_owners = ownership_map(summaries[right_style], right_style)
            left_mplus = {cp for cp, origin in left_owners.items() if origin == "mplus1p"}
            right_mplus = {cp for cp, origin in right_owners.items() if origin == "mplus1p"}
            expect(left_mplus, right_mplus, f"{label} M PLUS ownership set")
            for audited_codepoint in sorted(left_mplus):
                left_glyph = left.getBestCmap()[audited_codepoint]
                right_glyph = right.getBestCmap()[audited_codepoint]
                left_coordinates = left["glyf"][left_glyph].getCoordinates(left["glyf"])
                right_coordinates = right["glyf"][right_glyph].getCoordinates(right["glyf"])
                expect(
                    (list(left_coordinates[0]), list(left_coordinates[1]), list(left_coordinates[2])),
                    (list(right_coordinates[0]), list(right_coordinates[1]), list(right_coordinates[2])),
                    f"U+{audited_codepoint:04X} M PLUS geometry {label}",
                )
    expect(enclosed_bounds["Regular"], enclosed_bounds["Italic"], "regular circled-digit geometry")
    expect(enclosed_bounds["Bold"], enclosed_bounds["BoldItalic"], "bold circled-digit geometry")
    if enclosed_bounds["Regular"] == enclosed_bounds["Bold"]:
        raise AssertionError("circled digits must retain the IBM regular/bold outline difference")
    print("validated Summer Ghost Regular/Bold/Italic/BoldItalic")


if __name__ == "__main__":
    main()
