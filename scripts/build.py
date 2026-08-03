#!/usr/bin/env python3
"""Build Summer Ghost deterministically from pinned upstream font binaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from contextlib import ExitStack, closing
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

import unicodedata2 as unicodedata
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables.O_S_2f_2 import calcCodePageRanges, intersectUnicodeRanges

ROOT = Path(__file__).resolve().parents[1]
CACHE, DIST = ROOT / ".cache", ROOT / "dist"
DOWNLOADS, SOURCES = CACHE / "downloads", CACHE / "sources"
FAMILY, PS_FAMILY, VERSION = "Summer Ghost", "SummerGhost", "0.1.0"
UPM, HALF_WIDTH, FULL_WIDTH = 1024, 512, 1024
ASCENT, DESCENT, UBUNTU_VERTICAL_SCALE = 850, 174, 1.03
HORIZONTAL_ARROW_INK_WIDTH = 500
CELL_FIT_INK_WIDTH = 500
ARROW_HEAD_DEPTH_RATIO = 0.80
BASIC_ARROWS = frozenset(range(0x2190, 0x2194))
RETURN_ARROW_CODEPOINT = 0x21B5
RETURN_SYMBOL_CODEPOINT = 0x23CE
CYROIT_TERMINAL_SYMBOLS = BASIC_ARROWS | {RETURN_ARROW_CODEPOINT}
HORIZONTAL_ARROWS = {0x2190: True, 0x2192: False}
MIRRORED_HORIZONTAL_ARROW_PAIRS = ((0x21D0, 0x21D2),)
ENCLOSED_DIGITS = range(0x2460, 0x2474)
PLEMOL_REFERENCE_UPM = 1000
PLEMOL_ENCLOSED_X_SCALE = 0.67
PLEMOL_ENCLOSED_Y_SCALE = 0.90
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
CYROIT_BOX_BOUNDS = (-89, -420, 601, 1014)
IBM_COMMIT = "ceee82fa88781b8310b198fd302480efaeac609e"
SOURCE_ORDER = ("ubuntu", "cyroit", "biz", "ibm")
PROVENANCE_ORIGINS = (*SOURCE_ORDER, "generated")
SOURCE_SCALES = {"cyroit": 1.0, "biz": 0.87, "ibm": 0.90}
SOURCE_PREFIXES = {"cyroit": "j", "biz": "b", "ibm": "i"}
JAPANESE_RANGES = (
    (0x2E80, 0x2FFF),
    (0x3000, 0x30FF),
    (0x3190, 0x319F),
    (0x31C0, 0x31FF),
    (0x3200, 0x33FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x1AFF0, 0x1AFFF),
    (0x1B000, 0x1B16F),
    (0x1F200, 0x1F2FF),
    (0x20000, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x323AF),
)
UNICODE17_WIDE_CODEPOINTS = (0x2FFC, 0x2FFD, 0x2FFE, 0x2FFF, 0x31EF)
WHITE_PARENTHESIS_SOURCE = 0xFF5F
FULL_WIDTH_OVERRIDES = frozenset({0x2985, 0x2986})


@dataclass(frozen=True, slots=True)
class Asset:
    """A content-addressed upstream asset."""

    name: str
    url: str
    sha256: str


ASSETS: tuple[Asset, ...] = (
    Asset(
        "ubuntu-font-family-0.83.zip",
        "https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip",
        "61a2b342526fd552f19fef438bb9211a8212de19ad96e32a1209c039f1d68ecf",
    ),
    Asset(
        "Cyroit-Regular.nopatch.ttf",
        "https://raw.githubusercontent.com/omonomo/Ubroit/v1.8.0/sourceFonts/Cyroit.nopatch/Cyroit-Regular.nopatch.ttf",
        "cdd13dff9df6785860d22fe5f8ec71d1bc9ebe1913d18b68c529d19404090974",
    ),
    Asset(
        "Cyroit-Bold.nopatch.ttf",
        "https://raw.githubusercontent.com/omonomo/Ubroit/v1.8.0/sourceFonts/Cyroit.nopatch/Cyroit-Bold.nopatch.ttf",
        "4feff623bc4d4fc1e09f9cdc7bfcbc8b320c732a3ce76b27ef9a9279c6532e08",
    ),
    Asset(
        "BIZUDGothic-1.051.zip",
        "https://github.com/googlefonts/morisawa-biz-ud-gothic/releases/download/v1.051/BIZUDGothic.zip",
        "30692df621b92df13b88f1360aed1ab6ae50de441bce751a396c6439045cd759",
    ),
    Asset(
        "IBMPlexSansJP-Regular.ttf",
        f"https://raw.githubusercontent.com/IBM/plex/{IBM_COMMIT}/packages/"
        "plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Regular.ttf",
        "825b5c933c3fdb380eb84195788559103ae12710098218a1848376e35a45fcce",
    ),
    Asset(
        "IBMPlexSansJP-Bold.ttf",
        f"https://raw.githubusercontent.com/IBM/plex/{IBM_COMMIT}/packages/"
        "plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Bold.ttf",
        "85645e1bc1f92778e06c100c7bc6c6720b1d3955a8eee8d38c805589f59a261e",
    ),
)
STYLE_PARTS = {
    "Regular": ("R", "Regular"),
    "Bold": ("B", "Bold"),
    "Italic": ("RI", "Regular"),
    "BoldItalic": ("BI", "Bold"),
}
STYLES: Mapping[str, tuple[str, str, str, str]] = {
    style: (
        f"UbuntuMono-{ubuntu}.ttf",
        f"Cyroit-{weight}.nopatch.ttf",
        f"BIZUDGothic-{weight}.ttf",
        f"IBMPlexSansJP-{weight}.ttf",
    )
    for style, (ubuntu, weight) in STYLE_PARTS.items()
}
UVSMap = dict[int, list[tuple[int, str | None]]]


def file_sha256(path: Path) -> str:
    """Return a file's lowercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(asset: Asset) -> None:
    destination, temporary = DOWNLOADS / asset.name, DOWNLOADS / f"{asset.name}.part"
    if destination.is_file() and file_sha256(destination) == asset.sha256:
        print(f"cached   {asset.name}")
        return
    destination.unlink(missing_ok=True)
    temporary.unlink(missing_ok=True)
    print(f"download {asset.url}")
    request = urllib.request.Request(asset.url, headers={"User-Agent": "SummerGhost/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out)
        actual = file_sha256(temporary)
        if actual != asset.sha256:
            raise RuntimeError(f"SHA-256 mismatch for {asset.name}: {actual} != {asset.sha256}")
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def fetch_sources() -> Mapping[str, Path]:
    """Fetch, verify, and extract every pinned source."""
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    SOURCES.mkdir(parents=True, exist_ok=True)
    for asset in ASSETS:
        _download(asset)

    archive_key = hashlib.sha256(
        "".join(asset.sha256 for asset in ASSETS if asset.name.endswith(".zip")).encode()
    ).hexdigest()[:12]
    extracted = SOURCES / f"extracted-{archive_key}"
    if not (extracted / ".complete").is_file():
        shutil.rmtree(extracted, ignore_errors=True)
        extracted.mkdir(parents=True)
        for archive, directory in (
            ("ubuntu-font-family-0.83.zip", "ubuntu"),
            ("BIZUDGothic-1.051.zip", "biz"),
        ):
            with zipfile.ZipFile(DOWNLOADS / archive) as bundle:
                bundle.extractall(extracted / directory)
        (extracted / ".complete").touch()
    return {
        "ubuntu": extracted / "ubuntu" / "ubuntu-font-family-0.83",
        "cyroit": DOWNLOADS,
        "biz": extracted / "biz",
        "ibm": DOWNLOADS,
    }


def is_private_use(codepoint: int) -> bool:
    """Return whether a codepoint belongs to a Unicode private-use area."""
    return bool(unicodedata.category(chr(codepoint)) == "Co")


def cell_width(codepoint: int) -> int:
    """Map Unicode display properties to the 0/half/full-width grid."""
    if codepoint in FULL_WIDTH_OVERRIDES:
        return FULL_WIDTH
    char = chr(codepoint)
    if unicodedata.category(char) in {"Mn", "Me"}:
        return 0
    return FULL_WIDTH if unicodedata.east_asian_width(char) in {"W", "F"} else HALF_WIDTH


def is_adjusted_japanese(codepoint: int) -> bool:
    """Select Cyroit's adjusted Japanese repertoire and terminal symbols."""
    excluded = codepoint in {0x309B, 0x309C} or 0xFF65 <= codepoint <= 0xFF9F
    return codepoint in CYROIT_TERMINAL_SYMBOLS or (
        not excluded and any(start <= codepoint <= end for start, end in JAPANESE_RANGES)
    )


def scale_ubuntu_ascii(font: TTFont) -> None:
    """Apply Ubroit's 103% vertical scale to printable ASCII only."""
    glyph_set, order = font.getGlyphSet(), font.getGlyphOrder()
    scaled = {name for cp, name in font.getBestCmap().items() if 0x20 <= cp <= 0x7E}
    transformed: dict[str, Any] = {}
    # Decompose first so non-ASCII composites cannot inherit scaled Latin components.
    for name in order:
        recording, pen = DecomposingRecordingPen(glyph_set), TTGlyphPen(None)
        glyph_set[name].draw(recording)
        scale_y = UBUNTU_VERTICAL_SCALE if name in scaled else 1.0
        recording.replay(TransformPen(pen, (1, 0, 0, scale_y, 0, 0)))
        transformed[name] = pen.glyph()
    font["glyf"].glyphs = transformed
    for name, glyph in transformed.items():
        glyph.recalcBounds(font["glyf"])
        font["hmtx"].metrics[name] = (font["hmtx"].metrics[name][0], getattr(glyph, "xMin", 0))


def _replace_glyph(font: TTFont, name: str, glyph: Any) -> None:
    """Replace one outline while preserving its advance width."""
    glyph.recalcBounds(font["glyf"])
    font["glyf"].glyphs[name] = glyph
    font["hmtx"].metrics[name] = (font["hmtx"].metrics[name][0], getattr(glyph, "xMin", 0))


def _replay_transformed(
    recording: DecomposingRecordingPen,
    pen: TTGlyphPen,
    transform_point: Callable[[tuple[float, float]], tuple[float, float]],
) -> None:
    """Replay an outline through a point transform that may be nonlinear."""
    for operation, points in recording.value:
        if operation == "moveTo":
            pen.moveTo(transform_point(points[0]))
        elif operation == "lineTo":
            pen.lineTo(transform_point(points[0]))
        elif operation == "curveTo":
            pen.curveTo(*(transform_point(point) for point in points))
        elif operation == "qCurveTo":
            pen.qCurveTo(*(None if point is None else transform_point(point) for point in points))
        elif operation == "closePath":
            pen.closePath()
        elif operation == "endPath":
            pen.endPath()
        else:
            raise ValueError(f"Unsupported outline operation {operation}")


def _shorten_left_arrow_point(
    point: tuple[float, float],
    *,
    x_min: float,
    head_depth: float,
    shaft_factor: float,
    target_left: float,
) -> tuple[float, float]:
    """Shorten a left-facing arrow shaft while preserving its head."""
    x, y = point
    distance = x - x_min
    if distance > head_depth:
        distance = head_depth + (distance - head_depth) * shaft_factor
    return target_left + distance, y


def _mirror_transformed_point(
    point: tuple[float, float],
    *,
    transform_point: Callable[[tuple[float, float]], tuple[float, float]],
) -> tuple[float, float]:
    """Mirror a transformed point around the half-width cell center."""
    x, y = transform_point(point)
    return HALF_WIDTH - x, y


def _set_mapped_glyph(
    font: TTFont,
    cmap: MutableMapping[int, str],
    codepoint: int,
    glyph: Any,
    prefix: str,
    width: int = HALF_WIDTH,
) -> bool:
    """Replace or add one mapped glyph; return whether it was added."""
    if glyph_name := cmap.get(codepoint):
        _replace_glyph(font, glyph_name, glyph)
        return False

    glyph_name = f"sg.{prefix}.{codepoint:04X}"
    if glyph_name in font["glyf"].glyphs:
        raise ValueError(f"Duplicate generated glyph name {glyph_name}")
    glyph.recalcBounds(font["glyf"])
    font["glyf"].glyphs[glyph_name] = glyph
    order = font.getGlyphOrder()
    order.append(glyph_name)
    font.setGlyphOrder(order)
    font["hmtx"].metrics[glyph_name] = (width, getattr(glyph, "xMin", 0))
    cmap[codepoint] = glyph_name
    return True


def replace_box_drawing(
    font: TTFont,
    source: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
) -> None:
    """Map Cyroit's complete box-drawing grid exactly onto terminal cells."""
    source_cmap, glyph_set = source.getBestCmap(), source.getGlyphSet()
    source_x_min, source_y_min, source_x_max, source_y_max = CYROIT_BOX_BOUNDS
    scale_x = HALF_WIDTH / (source_x_max - source_x_min)
    scale_y = (ASCENT + DESCENT) / (source_y_max - source_y_min)
    transform = (
        scale_x,
        0,
        0,
        scale_y,
        -source_x_min * scale_x,
        -DESCENT - source_y_min * scale_y,
    )
    for codepoint in range(0x2500, 0x2580):
        recording, pen = DecomposingRecordingPen(glyph_set), TTGlyphPen(None)
        glyph_set[source_cmap[codepoint]].draw(recording)
        recording.replay(TransformPen(pen, transform))
        _set_mapped_glyph(font, cmap, codepoint, pen.glyph(), "box")
        origins[codepoint] = "cyroit"


def _rectangles_glyph(rectangles: Iterable[tuple[int, int, int, int]]) -> Any:
    """Build a TrueType glyph from exact, non-overlapping rectangles."""
    pen = TTGlyphPen(None)
    for x_min, y_min, x_max, y_max in rectangles:
        pen.moveTo((x_min, y_min))
        pen.lineTo((x_max, y_min))
        pen.lineTo((x_max, y_max))
        pen.lineTo((x_min, y_max))
        pen.closePath()
    return pen.glyph()


def _fit_enclosed_digits(font: TTFont, enclosed_source: TTFont, cmap: Mapping[int, str]) -> None:
    """Apply PlemolJP Console's enclosed-number proportions at Summer Ghost's UPM."""
    source_cmap, source_glyphs = enclosed_source.getBestCmap(), enclosed_source.getGlyphSet()
    upm_scale = UPM / PLEMOL_REFERENCE_UPM
    x_scale = PLEMOL_ENCLOSED_X_SCALE * upm_scale
    y_scale = PLEMOL_ENCLOSED_Y_SCALE * upm_scale
    for codepoint in ENCLOSED_DIGITS:
        glyph_name = cmap[codepoint]
        if font["hmtx"].metrics[glyph_name][0] != HALF_WIDTH:
            raise ValueError(f"U+{codepoint:04X} must have a half-width advance")
        source_name = source_cmap[codepoint]
        bounds_pen = BoundsPen(source_glyphs)
        source_glyphs[source_name].draw(bounds_pen)
        if bounds_pen.bounds is None:
            raise ValueError(f"Cannot fit empty IBM U+{codepoint:04X} outline")
        x_min, _, x_max, _ = bounds_pen.bounds
        x_offset = HALF_WIDTH / 2 - (x_min + x_max) * x_scale / 2
        recording, pen = DecomposingRecordingPen(source_glyphs), TTGlyphPen(None)
        source_glyphs[source_name].draw(recording)
        recording.replay(TransformPen(pen, (x_scale, 0, 0, y_scale, x_offset, 0)))
        _replace_glyph(font, glyph_name, pen.glyph())


def _normalize_mirrored_horizontal_arrows(font: TTFont, cmap: Mapping[int, str]) -> None:
    """Shorten each left arrow's shaft and derive an exact right-facing mirror."""
    glyph_set = font.getGlyphSet()
    for left_codepoint, right_codepoint in MIRRORED_HORIZONTAL_ARROW_PAIRS:
        source_name = cmap[left_codepoint]
        bounds_pen = BoundsPen(glyph_set)
        glyph_set[source_name].draw(bounds_pen)
        if bounds_pen.bounds is None:
            raise ValueError(f"Cannot normalize empty U+{left_codepoint:04X} arrow")
        x_min, y_min, x_max, y_max = bounds_pen.bounds
        natural_width = x_max - x_min
        head_depth = (y_max - y_min) * ARROW_HEAD_DEPTH_RATIO
        if natural_width <= HORIZONTAL_ARROW_INK_WIDTH or head_depth >= HORIZONTAL_ARROW_INK_WIDTH:
            raise ValueError(f"Cannot shorten U+{left_codepoint:04X} horizontal arrow")
        target_left = (HALF_WIDTH - HORIZONTAL_ARROW_INK_WIDTH) / 2
        shaft_factor = (HORIZONTAL_ARROW_INK_WIDTH - head_depth) / (natural_width - head_depth)

        fit_left = partial(
            _shorten_left_arrow_point,
            x_min=x_min,
            head_depth=head_depth,
            shaft_factor=shaft_factor,
            target_left=target_left,
        )
        fit_right = partial(_mirror_transformed_point, transform_point=fit_left)

        recording = DecomposingRecordingPen(glyph_set)
        glyph_set[source_name].draw(recording)
        left_pen, right_pen = TTGlyphPen(None), TTGlyphPen(None)
        _replay_transformed(recording, left_pen, fit_left)
        _replay_transformed(recording, right_pen, fit_right)
        _replace_glyph(font, cmap[left_codepoint], left_pen.glyph())
        _replace_glyph(font, cmap[right_codepoint], right_pen.glyph())


def _fit_proportional_cell_symbols(font: TTFont, cmap: Mapping[int, str], codepoints: frozenset[int]) -> None:
    """Fit one audited symbol class to 500-unit ink width without changing its aspect ratio."""
    glyph_set, fitted = font.getGlyphSet(), set()
    for codepoint in sorted(codepoints):
        glyph_name = cmap[codepoint]
        if glyph_name in fitted:
            continue
        if font["hmtx"].metrics[glyph_name][0] != HALF_WIDTH:
            raise ValueError(f"U+{codepoint:04X} must have a half-width advance")
        bounds_pen = BoundsPen(glyph_set)
        glyph_set[glyph_name].draw(bounds_pen)
        if bounds_pen.bounds is None:
            raise ValueError(f"Cannot fit empty U+{codepoint:04X} outline")
        x_min, y_min, x_max, y_max = bounds_pen.bounds
        width, height = x_max - x_min, y_max - y_min
        if width <= 0 or height <= 0:
            raise ValueError(f"Cannot fit degenerate U+{codepoint:04X} outline")
        scale = CELL_FIT_INK_WIDTH / width
        x_offset = HALF_WIDTH / 2 - (x_min + x_max) * scale / 2
        y_offset = (y_min + y_max) * (1 - scale) / 2
        recording, pen = DecomposingRecordingPen(glyph_set), TTGlyphPen(None)
        glyph_set[glyph_name].draw(recording)
        recording.replay(TransformPen(pen, (scale, 0, 0, scale, x_offset, y_offset)))
        _replace_glyph(font, glyph_name, pen.glyph())
        fitted.add(glyph_name)


def _set_block_glyph(
    font: TTFont,
    cmap: MutableMapping[int, str],
    codepoint: int,
    rectangles: Iterable[tuple[int, int, int, int]],
) -> bool:
    """Replace or add one exact solid block glyph; return whether it was added."""
    return _set_mapped_glyph(font, cmap, codepoint, _rectangles_glyph(rectangles), "block")


def _normalize_block_elements(
    font: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
) -> None:
    """Generate the complete solid Block Elements set on the terminal cell grid."""
    bottom, middle, top = -DESCENT, (ASCENT - DESCENT) // 2, ASCENT
    left, center, right = 0, HALF_WIDTH // 2, HALF_WIDTH
    lower_blocks = {cp: ((left, bottom, right, bottom + 128 * (cp - 0x2580)),) for cp in range(0x2581, 0x2589)}
    left_blocks = {cp: ((left, bottom, 64 * (0x2590 - cp), top),) for cp in range(0x2589, 0x2590)}
    block_rectangles = {
        0x2580: ((left, middle, right, top),),
        **lower_blocks,
        **left_blocks,
        0x2590: ((center, bottom, right, top),),
        0x2594: ((left, top - 128, right, top),),
        0x2595: ((right - 64, bottom, right, top),),
        0x2596: ((left, bottom, center, middle),),
        0x2597: ((center, bottom, right, middle),),
        0x2598: ((left, middle, center, top),),
        0x2599: ((left, bottom, center, top), (center, bottom, right, middle)),
        0x259A: ((left, middle, center, top), (center, bottom, right, middle)),
        0x259B: ((left, bottom, center, top), (center, middle, right, top)),
        0x259C: ((left, middle, right, top), (center, bottom, right, middle)),
        0x259D: ((center, middle, right, top),),
        0x259E: ((left, bottom, center, middle), (center, middle, right, top)),
        0x259F: ((left, bottom, right, middle), (center, middle, right, top)),
    }
    for codepoint, rectangles in block_rectangles.items():
        _set_block_glyph(font, cmap, codepoint, rectangles)
        origins[codepoint] = "generated"


def _add_white_parentheses(
    font: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
) -> None:
    """Derive U+2985/U+2986 from full-width U+FF5F and its exact mirror.

    The pinned sources do not map either white-parenthesis codepoint.  U+FF5F
    is the closest existing Japanese full-width opening shape, so its final
    target outline supplies the style-specific stroke.  U+2986 is generated
    by reflecting that decomposed outline around the 1024-unit cell centre.
    """
    source_name = cmap.get(WHITE_PARENTHESIS_SOURCE)
    if source_name is None:
        raise ValueError(f"U+{WHITE_PARENTHESIS_SOURCE:04X} is required to derive white parentheses")
    glyph_set = font.getGlyphSet()
    recording = DecomposingRecordingPen(glyph_set)
    glyph_set[source_name].draw(recording)

    def identity(point: tuple[float, float]) -> tuple[float, float]:
        return point

    def mirror(point: tuple[float, float]) -> tuple[float, float]:
        return FULL_WIDTH - point[0], point[1]

    left_pen, right_pen = TTGlyphPen(None), TTGlyphPen(None)
    _replay_transformed(recording, left_pen, identity)
    _replay_transformed(recording, right_pen, mirror)
    _set_mapped_glyph(font, cmap, 0x2985, left_pen.glyph(), "whiteparen", width=FULL_WIDTH)
    _set_mapped_glyph(font, cmap, 0x2986, right_pen.glyph(), "whiteparen", width=FULL_WIDTH)
    origins[0x2985] = origins[0x2986] = "generated"


def normalize_terminal_glyphs(
    font: TTFont,
    enclosed_source: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
) -> None:
    """Stabilize audited symbols and exact terminal block graphics."""
    _normalize_mirrored_horizontal_arrows(font, cmap)
    _fit_enclosed_digits(font, enclosed_source, cmap)
    for codepoint in ENCLOSED_DIGITS:
        origins[codepoint] = "ibm"
    _fit_proportional_cell_symbols(font, cmap, GEOMETRIC_CELL_FIT_SYMBOLS)
    _fit_proportional_cell_symbols(font, cmap, EVERYDAY_CELL_FIT_SYMBOLS)
    _normalize_block_elements(font, cmap, origins)
    _add_white_parentheses(font, cmap, origins)


class GlyphCopier:
    """Copy decomposed outlines into a target font at a fixed cell width."""

    def __init__(self, target: TTFont, source: TTFont, prefix: str, scale: float) -> None:
        self.target, self.scale, self.prefix = target, scale, prefix
        self.cmap, self.glyphs = source.getBestCmap(), source.getGlyphSet()
        self.metrics, self.source_upm = source["hmtx"].metrics, source["head"].unitsPerEm
        self.order, self.counter = target.getGlyphOrder(), 0
        self.cache: dict[tuple[str, int, bool | None], str] = {}

    def copy_codepoint(self, codepoint: int) -> str:
        """Copy the glyph mapped from a Unicode codepoint."""
        return self.copy_glyph(
            self.cmap[codepoint],
            cell_width(codepoint),
            arrow_points_left=HORIZONTAL_ARROWS.get(codepoint),
        )

    def copy_glyph(self, source_name: str, width: int, arrow_points_left: bool | None = None) -> str:
        """Copy one source glyph, centered and scaled in the requested cell."""
        key = source_name, width, arrow_points_left
        if cached := self.cache.get(key):
            return cached
        factor = UPM / self.source_upm * self.scale
        recording, pen = DecomposingRecordingPen(self.glyphs), TTGlyphPen(None)
        self.glyphs[source_name].draw(recording)
        if arrow_points_left is None:
            offset = 0.0 if width == 0 else (width - self.metrics[source_name][0] * factor) / 2
            recording.replay(TransformPen(pen, (factor, 0, 0, factor, offset, 0)))
        else:
            bounds_pen = BoundsPen(self.glyphs)
            self.glyphs[source_name].draw(bounds_pen)
            if bounds_pen.bounds is None:
                raise ValueError(f"Cannot fit empty glyph {source_name}")
            x_min, y_min, x_max, y_max = bounds_pen.bounds
            natural_width = (x_max - x_min) * factor
            head_depth = (y_max - y_min) * factor * ARROW_HEAD_DEPTH_RATIO
            if natural_width <= HORIZONTAL_ARROW_INK_WIDTH or head_depth >= HORIZONTAL_ARROW_INK_WIDTH:
                raise ValueError(f"Cannot shorten horizontal arrow {source_name}")
            target_left = (width - HORIZONTAL_ARROW_INK_WIDTH) / 2
            target_right = target_left + HORIZONTAL_ARROW_INK_WIDTH
            shaft_factor = (HORIZONTAL_ARROW_INK_WIDTH - head_depth) / (natural_width - head_depth)

            def transform_point(point: tuple[float, float]) -> tuple[float, float]:
                x, y = point
                distance = (x - x_min) * factor if arrow_points_left else (x_max - x) * factor
                if distance > head_depth:
                    distance = head_depth + (distance - head_depth) * shaft_factor
                target_x = target_left + distance if arrow_points_left else target_right - distance
                return target_x, y * factor

            _replay_transformed(recording, pen, transform_point)
        glyph, name = pen.glyph(), f"sg.{self.prefix}.{self.counter:05d}"
        self.counter += 1
        self.target["glyf"].glyphs[name] = glyph
        self.order.append(name)
        glyph.recalcBounds(self.target["glyf"])
        self.target["hmtx"].metrics[name] = (width, getattr(glyph, "xMin", 0))
        self.cache[key] = name
        return name


def add_codepoints(
    target: TTFont,
    source: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
    origin: str,
    accepts: Callable[[int], bool],
) -> GlyphCopier:
    """Append eligible, previously unmapped source glyphs."""
    copier = GlyphCopier(target, source, SOURCE_PREFIXES[origin], SOURCE_SCALES[origin])
    for codepoint in sorted(source.getBestCmap()):
        if codepoint not in cmap and not is_private_use(codepoint) and accepts(codepoint):
            cmap[codepoint], origins[codepoint] = copier.copy_codepoint(codepoint), origin
    return copier


def remap_uvs(source: TTFont, copier: GlyphCopier, origins: Mapping[int, str]) -> UVSMap:
    """Copy Cyroit variation sequences whose base glyphs won source precedence."""
    remapped: UVSMap = {}
    for table in source["cmap"].tables:
        if table.format != 14:
            continue
        for selector, entries in table.uvsDict.items():
            selected = [
                (base, None if name is None else copier.copy_glyph(name, cell_width(base)))
                for base, name in entries
                if origins.get(base) == "cyroit"
            ]
            if selected:
                remapped[selector] = selected
    return remapped


def rebuild_cmap(font: TTFont, mapping: Mapping[int, str], uvs: UVSMap) -> None:
    """Install canonical BMP, full-Unicode, and variation-selector cmaps."""
    cmap, bmp = newTable("cmap"), {cp: name for cp, name in mapping.items() if cp <= 0xFFFF}
    cmap.tableVersion, cmap.tables = 0, []
    for format_, encodings, values in (
        (4, ((0, 3), (3, 1)), bmp),
        (12, ((0, 4), (3, 10)), mapping),
    ):
        for platform, encoding in encodings:
            table = CmapSubtable.newSubtable(format_)
            table.platformID, table.platEncID, table.language = platform, encoding, 0
            table.cmap = dict(values)
            if format_ == 12:
                table.nGroups = 0
            cmap.tables.append(table)
    if uvs:
        table = CmapSubtable.newSubtable(14)
        table.platformID, table.platEncID, table.language = 0, 5, 0
        table.cmap, table.uvsDict = (
            {},
            {selector: list(entries) for selector, entries in uvs.items()},
        )
        cmap.tables.append(table)
    font["cmap"] = cmap


def normalize_mapped_advances(font: TTFont, mapping: Mapping[int, str]) -> None:
    """Apply the Unicode 17.0 0/512/1024 advance rule to every mapping."""
    expected_by_glyph: dict[str, int] = {}
    for codepoint, glyph_name in sorted(mapping.items()):
        expected = cell_width(codepoint)
        previous = expected_by_glyph.setdefault(glyph_name, expected)
        if previous != expected:
            raise ValueError(f"Glyph {glyph_name} is shared by widths {previous} and {expected}")
    for glyph_name, width in expected_by_glyph.items():
        _, side_bearing = font["hmtx"].metrics[glyph_name]
        font["hmtx"].metrics[glyph_name] = width, side_bearing


def _bit_fields(bits: Iterable[int], count: int) -> list[int]:
    values = [0] * count
    for bit in bits:
        if bit < count * 32:
            values[bit // 32] |= 1 << (bit % 32)
    return values


def set_range_bits(font: TTFont, codepoints: Iterable[int]) -> None:
    """Recompute OS/2 Unicode and code-page coverage bits."""
    points, os2 = tuple(codepoints), font["OS/2"]
    os2.ulUnicodeRange1, os2.ulUnicodeRange2, os2.ulUnicodeRange3, os2.ulUnicodeRange4 = _bit_fields(
        intersectUnicodeRanges(points), 4
    )
    if os2.version >= 1:
        os2.ulCodePageRange1, os2.ulCodePageRange2 = _bit_fields(calcCodePageRanges(points), 2)


def set_names(font: TTFont, style: str) -> None:
    """Replace inherited names with a coherent cross-platform family model."""
    subfamily = "Bold Italic" if style == "BoldItalic" else style
    postscript = f"{PS_FAMILY}-{style}"
    values = {
        0: "Contains Ubuntu Mono, Circle M+ 1m, BIZ UDGothic, and IBM Plex Sans JP.",
        1: FAMILY,
        2: subfamily,
        3: f"{VERSION};SGST;{postscript}",
        4: f"{FAMILY} {subfamily}",
        5: f"Version {VERSION}",
        6: postscript,
        8: "Summer Ghost project",
        9: "Summer Ghost project",
        13: "Source font licenses differ; see THIRD_PARTY_LICENSES.md.",
        16: FAMILY,
        17: subfamily,
    }
    font["name"].names = []
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def strip_hinting(font: TTFont) -> None:
    """Remove invalidated TrueType hints and device-specific hint tables."""
    for glyph in font["glyf"].glyphs.values():
        glyph.removeHinting()
    for tag in ("cvt ", "fpgm", "prep", "hdmx", "LTSH", "VDMX", "DSIG"):
        if tag in font:
            del font[tag]


def recompute_global_metrics(font: TTFont) -> None:
    """Recompute final-outline bounds and all applicable TrueType maxima."""
    glyf = font["glyf"]
    bounds: list[tuple[int, int, int, int]] = []
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.recalcBounds(glyf)
        if glyph.numberOfContours:
            bounds.append((glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax))
    maxp = font["maxp"]
    maxp.recalc(font)
    head = font["head"]
    if bounds:
        head.xMin = min(item[0] for item in bounds)
        head.yMin = min(item[1] for item in bounds)
        head.xMax = max(item[2] for item in bounds)
        head.yMax = max(item[3] for item in bounds)
    else:
        head.xMin = head.yMin = head.xMax = head.yMax = 0
    # Hint programs and their storage are removed by strip_hinting().
    maxp.maxZones = 1
    maxp.maxTwilightPoints = 0
    maxp.maxStorage = 0
    maxp.maxFunctionDefs = 0
    maxp.maxInstructionDefs = 0
    maxp.maxStackElements = 0
    maxp.maxSizeOfInstructions = 0
    font["hhea"].recalc(font)


def set_metadata(font: TTFont, style: str, mapping: Mapping[int, str]) -> None:
    """Set reproducible names, style flags, and compact non-clipping metrics."""
    bold, italic = "Bold" in style, "Italic" in style
    hhea, os2, head = font["hhea"], font["OS/2"], font["head"]
    recompute_global_metrics(font)
    hhea.ascent, hhea.descent, hhea.lineGap = ASCENT, -DESCENT, 0
    os2.version = max(os2.version, 4)
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ASCENT, -DESCENT, 0
    extents: list[tuple[int, int]] = []
    for glyph in font["glyf"].glyphs.values():
        glyph.recalcBounds(font["glyf"])
        if hasattr(glyph, "yMax"):
            extents.append((glyph.yMin, glyph.yMax))
    os2.usWinAscent = max(ASCENT, max(y_max for _, y_max in extents))
    os2.usWinDescent = max(DESCENT, -min(y_min for y_min, _ in extents))
    os2.xAvgCharWidth, os2.usWeightClass, os2.achVendID = HALF_WIDTH, 700 if bold else 400, "SGST"
    os2.fsSelection &= ~((1 << 0) | (1 << 5) | (1 << 6))
    os2.fsSelection |= (1 << 7) | (int(italic) << 0) | (int(bold) << 5)
    if not bold and not italic:
        os2.fsSelection |= 1 << 6
    os2.panose.bProportion = 9
    font["post"].isFixedPitch, font["post"].formatType = 1, 3.0
    head.macStyle = int(bold) | (int(italic) << 1)
    head.fontRevision = 0.1
    head.created = head.modified = 2082844800
    set_names(font, style)
    set_range_bits(font, mapping)


def build_style(style: str, roots: Mapping[str, Path]) -> Mapping[str, object]:
    """Build one style and return its machine-readable provenance."""
    files = {source: roots[source] / name for source, name in zip(SOURCE_ORDER, STYLES[style], strict=True)}
    missing = [f"{source}: {path}" for source, path in files.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing source files: " + ", ".join(missing))
    print(f"\n=== {style} ===")
    with ExitStack() as stack:
        fonts = {
            source: stack.enter_context(closing(TTFont(path, recalcBBoxes=False, recalcTimestamp=False)))
            for source, path in files.items()
        }
        target = fonts["ubuntu"]
        if target["head"].unitsPerEm != UPM:
            scale_upem(target, UPM)
        scale_ubuntu_ascii(target)
        mapping = {cp: name for cp, name in target.getBestCmap().items() if not is_private_use(cp)}
        origins = dict.fromkeys(mapping, "ubuntu")
        copier = add_codepoints(target, fonts["cyroit"], mapping, origins, "cyroit", is_adjusted_japanese)
        # Fish hard-codes U+23CE for output without a trailing newline. Reuse
        # Cyroit's U+21B5 outline so fish and Neovim show the same return mark.
        mapping[RETURN_SYMBOL_CODEPOINT] = mapping[RETURN_ARROW_CODEPOINT]
        origins[RETURN_SYMBOL_CODEPOINT] = "cyroit"
        uvs = remap_uvs(fonts["cyroit"], copier, origins)
        add_codepoints(target, fonts["biz"], mapping, origins, "biz", lambda _: True)
        add_codepoints(target, fonts["ibm"], mapping, origins, "ibm", lambda _: True)
        replace_box_drawing(target, fonts["cyroit"], mapping, origins)
        normalize_terminal_glyphs(target, fonts["ibm"], mapping, origins)
        target.setGlyphOrder(target.getGlyphOrder())
        target["maxp"].numGlyphs = len(target.getGlyphOrder())
        rebuild_cmap(target, mapping, uvs)
        normalize_mapped_advances(target, mapping)
        strip_hinting(target)
        set_metadata(target, style, mapping)

        DIST.mkdir(parents=True, exist_ok=True)
        output, temporary = DIST / f"{PS_FAMILY}-{style}.ttf", DIST / f".{PS_FAMILY}-{style}.tmp"
        try:
            target.save(temporary, reorderTables=False)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        glyph_count, counts = len(target.getGlyphOrder()), Counter(origins.values())

    uvs_count = sum(map(len, uvs.values()))
    summary: dict[str, object] = {
        "style": style,
        "output": str(output.relative_to(ROOT)),
        "codepoints": {origin: counts[origin] for origin in PROVENANCE_ORIGINS},
        "total_codepoints": len(mapping),
        "uvs_mappings_from_cyroit": uvs_count,
        "glyphs": glyph_count,
        "size_bytes": output.stat().st_size,
        "scales": SOURCE_SCALES,
        "sample_origins": {
            f"U+{cp:04X}": origins.get(cp)
            for cp in (0x0041, 0x2190, 0x21B5, 0x23CE, 0x2500, 0x3042, 0x65E5, 0xFF11, 0x3405)
        },
    }
    print(f"wrote    {output.name}: {len(mapping):,} codepoints, IBM fallback {counts['ibm']:,}, UVS {uvs_count:,}")
    return summary


def clean() -> None:
    """Remove only repository-local caches and generated artifacts."""
    for path in (CACHE, DIST):
        if path.exists():
            shutil.rmtree(path)
            print(f"removed  {path.relative_to(ROOT)}")


def main() -> None:
    """Parse CLI arguments and build the requested styles."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="remove downloads and build output")
    parser.add_argument("--style", action="append", choices=tuple(STYLES), help="build only this style")
    args = parser.parse_args()
    if args.clean:
        clean()
        return
    roots = fetch_sources()
    summaries = [build_style(style, roots) for style in args.style or STYLES]
    provenance = DIST / "provenance.json"
    document = {
        "family": FAMILY,
        "version": VERSION,
        "ibm_commit": IBM_COMMIT,
        "assets": [asdict(asset) for asset in ASSETS],
        "styles": summaries,
    }
    provenance.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote    {provenance.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
