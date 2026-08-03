#!/usr/bin/env python3
"""Validate Summer Ghost names, geometry, coverage, provenance, and shaping."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, TypeVar

import uharfbuzz as hb
import unicodedata2 as unicodedata
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.ttLib import TTFont

ROOT, STYLES = Path(__file__).resolve().parents[1], ("Regular", "Bold", "Italic", "BoldItalic")
DIST = ROOT / "dist"
IBM_COMMIT = "ceee82fa88781b8310b198fd302480efaeac609e"
EXPECTED_ORIGINS = {
    "U+0041": "ubuntu",
    "U+2190": "cyroit",
    "U+21B5": "cyroit",
    "U+23CE": "cyroit",
    "U+2500": "cyroit",
    "U+3042": "cyroit",
    "U+65E5": "cyroit",
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
NEOVIM_REPRESENTATIVE_BOUNDS = {
    "Regular": {0x1D36: (84, 218, 405, 700), 0x1D50: (72, 227, 444, 589), 0x207B: (111, 402, 402, 461)},
    "Bold": {0x1D36: (73, 218, 422, 700), 0x1D50: (62, 227, 450, 590), 0x207B: (106, 388, 406, 480)},
    "Italic": {0x1D36: (77, 218, 469, 700), 0x1D50: (60, 227, 477, 589), 0x207B: (127, 402, 428, 461)},
    "BoldItalic": {0x1D36: (66, 218, 486, 700), 0x1D50: (50, 227, 479, 590), 0x207B: (120, 388, 435, 480)},
}
REQUIRED = {
    0x0041: "Ubuntu Mono Latin",
    0x21B5: "Neovim return arrow",
    0x23CE: "fish omitted-newline return symbol",
    0x2460: "circled digit one",
    0x2500: "Cyroit box drawing",
    0x2580: "upper half block",
    0x2590: "right half block",
    0x2596: "quadrant lower-left block",
    0x259F: "quadrant complement block",
    0x3042: "Circle M+ hiragana",
    0x30A2: "Circle M+ katakana",
    0x65E5: "Cyroit kanji",
    0x9AD9: "Cyroit Japanese-name kanji",
    0xFA11: "Cyroit compatibility ideograph",
    0x3405: "IBM Plex Sans JP fallback",
    0x2985: "left white parenthesis",
    0x2986: "right white parenthesis",
}
UNICODE17_WIDE_CODEPOINTS = (0x2FFC, 0x2FFD, 0x2FFE, 0x2FFF, 0x31EF)
WHITE_PARENTHESIS_PAIR = (0x2985, 0x2986)
FULL_WIDTH_OVERRIDES = frozenset(WHITE_PARENTHESIS_PAIR)
RETURN_MARKS = (0x21B5, 0x23CE)
RETURN_MARK_BOUNDS = {False: (-66, 53, 453, 623), True: (-73, 41, 471, 618)}
HORIZONTAL_ARROWS = (0x2190, 0x2192)
VERTICAL_ARROWS = (0x2191, 0x2193)
MIRRORED_HORIZONTAL_ARROW_PAIRS = ((0x21D0, 0x21D2),)
MIRRORED_ARROW_BOUNDS = {False: (6, 155, 506, 546), True: (6, 130, 506, 570)}
ENCLOSED_DIGITS = range(0x2460, 0x2474)
ENCLOSED_DIGIT_INK_SIZE = {False: (630, 846), True: (644, 866)}
ENCLOSED_DIGIT_BOUNDS = {False: (-59, -73, 571, 773), True: (-66, -83, 578, 783)}
ENCLOSED_DIGIT_CENTER = (256, 350)
ENCLOSED_DIGIT_ASPECT_RANGE = (0.74, 0.75)
ENCLOSED_DIGIT_INNER_BOUNDS = {False: (-37, -44, 549, 745), True: (-32, -37, 544, 737)}
ENCLOSED_DIGIT_NUMERAL_CONTOURS = (1, 1, 1, 2, 1, 2, 1, 3, 2, 3, 2, 2, 2, 3, 2, 3, 2, 4, 3, 3)
PLAIN_CIRCLE_BOUNDS = {
    False: {0x25CB: (6, 89, 506, 589), 0x25CF: (6, 89, 506, 589), 0x3007: (121, -52, 904, 801)},
    True: {0x25CB: (6, 89, 506, 589), 0x25CF: (6, 89, 506, 589), 0x3007: (113, -61, 912, 822)},
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
UNCHANGED_AUDITED_BOUNDS = {
    False: {
        0x2190: (6, 113, 506, 567),
        0x2191: (29, 22, 483, 695),
        0x2192: (6, 113, 506, 567),
        0x2193: (29, -15, 483, 659),
        0x25C9: (47, 129, 466, 548),
    },
    True: {
        0x2190: (6, 107, 506, 574),
        0x2191: (22, 14, 490, 701),
        0x2192: (6, 107, 506, 574),
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
    False: {0x0041: 0.638, 0x3042: 0.788, 0x65E5: 0.760, 0x8A9E: 0.792},
    True: {0x0041: 0.638, 0x3042: 0.796, 0x65E5: 0.771, 0x8A9E: 0.803},
}
T = TypeVar("T")
Contour = list[tuple[str, tuple[Any, ...]]]


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
        missing = [f"{description} U+{cp:04X}" for cp, description in REQUIRED.items() if cp not in cmap]
        if missing:
            raise AssertionError(f"{path.name} lacks: {', '.join(missing)}")
        neovim = NEOVIM_GLYPHS | {0x2714}
        for cp in neovim:
            glyph_name = cmap[cp]
            expect(font["hmtx"].metrics[glyph_name][0], 512, f"{path.name} U+{cp:04X} Neovim advance")
            if _bounds(font, glyph_name) == (0, 0, 0, 0):
                raise AssertionError(f"{path.name} U+{cp:04X} Neovim glyph is empty")
        for cp, expected_bounds in NEOVIM_REPRESENTATIVE_BOUNDS[style].items():
            expect(_bounds(font, cmap[cp]), expected_bounds, f"{path.name} U+{cp:04X} representative bounds")
        if len(cmap) < 15_000:
            raise AssertionError(f"{path.name} maps only {len(cmap)} Unicode codepoints")
        return_glyphs = tuple(cmap[codepoint] for codepoint in RETURN_MARKS)
        expect(len(set(return_glyphs)), 1, f"{path.name} return marks share one glyph")
        expect(_bounds(font, return_glyphs[0]), RETURN_MARK_BOUNDS[bold], f"{path.name} return mark bounds")
        for codepoint, glyph_name in cmap.items():
            expect(
                font["hmtx"].metrics[glyph_name][0],
                cell_width(codepoint),
                f"{path.name} U+{codepoint:04X} Unicode 17 advance",
            )
        for codepoint in UNICODE17_WIDE_CODEPOINTS:
            expect(codepoint in cmap, True, f"{path.name} Unicode 17 wide coverage U+{codepoint:04X}")
            expect(
                font["hmtx"].metrics[cmap[codepoint]][0],
                1024,
                f"{path.name} U+{codepoint:04X} explicit Unicode 17 wide advance",
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
            expect(_bounds(font, cmap[cp]), expected_bounds, f"{path.name} U+{cp:04X} unchanged plain circle")
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
        for cp, expected_bounds in UNCHANGED_AUDITED_BOUNDS[bold].items():
            expect(_bounds(font, cmap[cp]), expected_bounds, f"{path.name} U+{cp:04X} audited unchanged bounds")

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
        horizontal_heights: list[int] = []
        for cp in HORIZONTAL_ARROWS:
            x_min, y_min, x_max, y_max = _bounds(font, cmap[cp])
            expect(x_max - x_min, 500, f"{path.name} U+{cp:04X} horizontal arrow ink width")
            if x_min < 0 or x_max > 512:
                raise AssertionError(f"{path.name} U+{cp:04X} exceeds its half-width cell: {x_min}..{x_max}")
            horizontal_heights.append(y_max - y_min)
        vertical_widths = [_bounds(font, cmap[cp])[2] - _bounds(font, cmap[cp])[0] for cp in VERTICAL_ARROWS]
        if max(horizontal_heights + vertical_widths) - min(horizontal_heights + vertical_widths) > 2:
            raise AssertionError(
                f"{path.name} arrow cross-axis sizes differ: "
                f"horizontal heights {horizontal_heights}, vertical widths {vertical_widths}"
            )
        for left_codepoint, right_codepoint in MIRRORED_HORIZONTAL_ARROW_PAIRS:
            left_name, right_name = cmap[left_codepoint], cmap[right_codepoint]
            expect(
                _bounds(font, left_name),
                MIRRORED_ARROW_BOUNDS[bold],
                f"{path.name} U+{left_codepoint:04X} normalized double-arrow bounds",
            )
            expect(
                _bounds(font, right_name),
                MIRRORED_ARROW_BOUNDS[bold],
                f"{path.name} U+{right_codepoint:04X} normalized double-arrow bounds",
            )
            left_points, left_ends, left_flags = font["glyf"][left_name].getCoordinates(font["glyf"])
            right_points, right_ends, right_flags = font["glyf"][right_name].getCoordinates(font["glyf"])
            expect(list(left_ends), list(right_ends), f"{path.name} mirrored double-arrow contours")
            expect(list(left_flags), list(right_flags), f"{path.name} mirrored double-arrow point flags")
            expect(
                list(left_points),
                [(512 - x, y) for x, y in right_points],
                f"{path.name} exact double-arrow mirror",
            )
        variation_tables = [table for table in font["cmap"].tables if table.format == 14]
        if not variation_tables or not variation_tables[0].uvsDict:
            raise AssertionError(f"{path.name} lacks Japanese variation sequences")
        selectors = len(variation_tables[0].uvsDict)
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
    enclosed_bounds = {}
    for style in STYLES:
        path, summary = DIST / f"SummerGhost-{style}.ttf", summaries[style]
        if not path.is_file():
            raise AssertionError(f"missing {path.name}")
        enclosed_bounds[style] = validate_font(path, style)
        validate_shaping(path)
        expect(summary.get("sample_origins"), EXPECTED_ORIGINS, f"{style} source precedence")
        counts = summary.get("codepoints")
        if not isinstance(counts, dict) or counts.get("ibm", 0) < 1_000:
            raise AssertionError(f"{style} has insufficient IBM fallback coverage")
        expect(counts.get("generated"), 74, f"{style} generated terminal geometry and Neovim glyphs")
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
        expect(neovim_origins.get("U+2714"), "cyroit", f"{style} check-mark provenance")
        expect(sum(counts.values()), summary.get("total_codepoints"), f"{style} source counts")
        expect(summary.get("size_bytes"), path.stat().st_size, f"{style} artifact size")
    with (
        closing(TTFont(DIST / "SummerGhost-Regular.ttf", recalcBBoxes=False, recalcTimestamp=False)) as regular,
        closing(TTFont(DIST / "SummerGhost-Italic.ttf", recalcBBoxes=False, recalcTimestamp=False)) as italic,
        closing(TTFont(DIST / "SummerGhost-Bold.ttf", recalcBBoxes=False, recalcTimestamp=False)) as bold,
        closing(TTFont(DIST / "SummerGhost-BoldItalic.ttf", recalcBBoxes=False, recalcTimestamp=False)) as bold_italic,
    ):
        for left, right, label in ((regular, italic, "Regular/Italic"), (bold, bold_italic, "Bold/BoldItalic")):
            left_name, right_name = left.getBestCmap()[0x2714], right.getBestCmap()[0x2714]
            left_points = list(left["glyf"][left_name].getCoordinates(left["glyf"])[0])
            right_points = list(right["glyf"][right_name].getCoordinates(right["glyf"])[0])
            expect(left_points, right_points, f"U+2714 upright {label}")
    expect(enclosed_bounds["Regular"], enclosed_bounds["Italic"], "regular circled-digit geometry")
    expect(enclosed_bounds["Bold"], enclosed_bounds["BoldItalic"], "bold circled-digit geometry")
    if enclosed_bounds["Regular"] == enclosed_bounds["Bold"]:
        raise AssertionError("circled digits must retain the IBM regular/bold outline difference")
    print("validated Summer Ghost Regular/Bold/Italic/BoldItalic")


if __name__ == "__main__":
    main()
