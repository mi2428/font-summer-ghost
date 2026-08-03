#!/usr/bin/env python3
"""Build Summer Ghost deterministically from pinned upstream font binaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from contextlib import ExitStack, closing
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
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
ASCENT, DESCENT, ASCII_VERTICAL_SCALE = 850, 174, 1.03
CELL_FIT_INK_WIDTH = 500
BASIC_ARROWS = frozenset(range(0x2190, 0x2194))
RETURN_ARROW_CODEPOINT = 0x21B5
RETURN_SYMBOL_CODEPOINT = 0x23CE
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
IBM_COMMIT = "ceee82fa88781b8310b198fd302480efaeac609e"
MPLUS1P_COMMIT = "2796410152d4f9524b68ed46e69c1b60f8e0f7c3"
NINJAL_TTF_SHA256 = "e1301406c49dffed801bc12f0bb6a148f90215d4cf7d3a7bb0831cd798f6345e"
NINJAL_CODEPOINTS = frozenset({0x3099, 0x309A, *range(0x1B001, 0x1B11F)})
CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x323AF),
)
ORPHAN_CODEPOINTS = frozenset(
    {
        *range(0x2FF0, 0x3000),
        0x31EF,
        *range(0x1B120, 0x1B129),
        *range(0x1B130, 0x1B169),
        0x2A708,
        0x2CEFF,
        0x2CF00,
        0x2CF02,
    }
)
if len(ORPHAN_CODEPOINTS) != 87:
    raise AssertionError("ORPHAN_CODEPOINTS must contain exactly 87 codepoints")
SOURCE_ORDER = ("ubuntu", "mplus1p", "ninjal", "biz", "ibm")
PROVENANCE_ORIGINS = (*SOURCE_ORDER, "generated")
SOURCE_SCALES = {"mplus1p": 1.0, "biz": 0.87, "ninjal": 1.0, "ibm": 0.90}
MPLUS1P_STYLE_SCALES = {
    "Regular": 0.91,
    "Italic": 0.91,
    "Bold": 0.90,
    "BoldItalic": 0.90,
}
SOURCE_PREFIXES = {"mplus1p": "m", "biz": "b", "ninjal": "n", "ibm": "i"}
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
WHITE_PARENTHESIS_SOURCE = 0xFF5F
FULL_WIDTH_OVERRIDES = frozenset({0x2985, 0x2986})

NEOVIM_GLYPHS: Mapping[int, int] = {
    0x02B3: 0x72,
    0x02B8: 0x79,
    0x02E2: 0x73,
    0x02E3: 0x78,
    0x1D2C: 0x41,
    0x1D2E: 0x42,
    0x1D30: 0x44,
    0x1D31: 0x45,
    0x1D33: 0x47,
    0x1D34: 0x48,
    0x1D35: 0x49,
    0x1D36: 0x4A,
    0x1D37: 0x4B,
    0x1D38: 0x4C,
    0x1D39: 0x4D,
    0x1D3A: 0x4E,
    0x1D3C: 0x4F,
    0x1D3E: 0x50,
    0x1D3F: 0x52,
    0x1D40: 0x54,
    0x1D41: 0x55,
    0x1D42: 0x57,
    0x1D43: 0x61,
    0x1D47: 0x62,
    0x1D48: 0x64,
    0x1D49: 0x65,
    0x1D4D: 0x67,
    0x1D4F: 0x6B,
    0x1D50: 0x6D,
    0x1D52: 0x6F,
    0x1D56: 0x70,
    0x1D57: 0x74,
    0x1D58: 0x75,
    0x1D5B: 0x76,
    0x1D9C: 0x63,
    0x1DA0: 0x66,
    0x1DBB: 0x7A,
    0x2071: 0x69,
    0x207B: 0x2D,
    0x207D: 0x28,
    0x207E: 0x29,
    0x207F: 0x6E,
    0x2C7D: 0x56,
}
NEOVIM_CHECK = 0x2714


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
        "MPLUS1p-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/{MPLUS1P_COMMIT}/ofl/mplus1p/MPLUS1p-Regular.ttf",
        "2f294ad496432b1608f070d310e3aa2adcf1de4af429f4901df97ec4bd361ed1",
    ),
    Asset(
        "MPLUS1p-Bold.ttf",
        f"https://raw.githubusercontent.com/google/fonts/{MPLUS1P_COMMIT}/ofl/mplus1p/MPLUS1p-Bold.ttf",
        "76eb077b0a31ca33ca40238e47da5a17e2786741607cec09678d7d2e5ab1afc1",
    ),
    Asset(
        "ninjal_hentaigana.zip",
        "https://cid.ninjal.ac.jp/kana/ninjal_hentaigana.zip",
        "62b01c19cb40dc4b64b1e1da776fca483e19e21c2772cc3f9db9a067bedbc84d",
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
STYLES: Mapping[str, tuple[str, str, str, str, str]] = {
    style: (
        f"UbuntuMono-{ubuntu}.ttf",
        f"MPLUS1p-{weight}.ttf",
        "ninjal_hentaigana.ttf",
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


MAX_ARCHIVE_UNCOMPRESSED_SIZE = 512 * 1024 * 1024


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    """Extract a verified archive through controlled, regular-file paths only."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    seen: set[Path] = set()
    total_size = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in sorted(bundle.infolist(), key=lambda item: item.filename):
            name = info.filename
            posix_name = PurePosixPath(name)
            windows_name = PureWindowsPath(name)
            if (
                not name
                or "\x00" in name
                or "\\" in name
                or posix_name.is_absolute()
                or windows_name.is_absolute()
                or windows_name.drive
                or any(part in {"", ".", ".."} for part in posix_name.parts)
            ):
                raise ValueError(f"Unsafe archive member path: {name!r}")
            relative = Path(*posix_name.parts)
            target = destination.joinpath(relative)
            try:
                target.resolve().relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Archive member escapes destination: {name!r}") from exc
            if relative in seen:
                raise ValueError(f"Duplicate archive member path: {name!r}")
            seen.add(relative)

            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported archive member type: {name!r}")
            if info.is_dir():
                if mode not in (0, stat.S_IFDIR):
                    raise ValueError(f"Unsupported archive directory type: {name!r}")
                target.mkdir(parents=True, exist_ok=True)
                continue
            if mode == stat.S_IFDIR:
                raise ValueError(f"Directory member lacks directory marker: {name!r}")
            if info.file_size < 0 or total_size + info.file_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                raise ValueError(f"Archive exceeds {MAX_ARCHIVE_UNCOMPRESSED_SIZE} uncompressed bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with bundle.open(info) as source, target.open("wb") as output:
                while chunk := source.read(1 << 20):
                    written += len(chunk)
                    if written > info.file_size or total_size + written > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                        raise ValueError(f"Archive member exceeds declared size: {name!r}")
                    output.write(chunk)
            if written != info.file_size:
                raise ValueError(f"Archive member size mismatch: {name!r}")
            total_size += written


def fetch_sources() -> Mapping[str, Path]:
    """Fetch, verify, and extract every pinned source."""
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    SOURCES.mkdir(parents=True, exist_ok=True)
    for asset in ASSETS:
        _download(asset)

    archive_key = hashlib.sha256("".join(f"{asset.name}:{asset.sha256}" for asset in ASSETS).encode()).hexdigest()[:12]
    extracted = SOURCES / f"extracted-{archive_key}"
    shutil.rmtree(extracted, ignore_errors=True)
    extracted.mkdir(parents=True)
    for archive, directory in (
        ("ubuntu-font-family-0.83.zip", "ubuntu"),
        ("ninjal_hentaigana.zip", "ninjal"),
        ("BIZUDGothic-1.051.zip", "biz"),
    ):
        _safe_extract_zip(DOWNLOADS / archive, extracted / directory)

    ninjal_matches = sorted((extracted / "ninjal").rglob("ninjal_hentaigana.ttf"))
    if len(ninjal_matches) != 1 or file_sha256(ninjal_matches[0]) != NINJAL_TTF_SHA256:
        raise RuntimeError("NINJAL TTF is missing or has an unexpected SHA-256")
    return {
        "ubuntu": extracted / "ubuntu" / "ubuntu-font-family-0.83",
        "mplus1p": DOWNLOADS,
        "ninjal": ninjal_matches[0].parent,
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


def is_mplus1p_japanese(codepoint: int) -> bool:
    """Select non-Han Japanese glyphs from the pinned M PLUS base."""
    excluded = codepoint in {0x309B, 0x309C} or 0xFF65 <= codepoint <= 0xFF9F
    is_han = any(start <= codepoint <= end for start, end in CJK_RANGES)
    return (
        not excluded
        and codepoint not in NINJAL_CODEPOINTS
        and not is_han
        and any(start <= codepoint <= end for start, end in JAPANESE_RANGES)
    )


def is_ninjal_hentaigana(codepoint: int) -> bool:
    """Select the complete 288-codepoint hentaigana layer."""
    return codepoint in NINJAL_CODEPOINTS


def remove_orphans(mapping: MutableMapping[int, str], origins: MutableMapping[int, str]) -> None:
    """Drop the explicitly unowned 87 codepoints from every source and final cmap."""
    for codepoint in ORPHAN_CODEPOINTS:
        mapping.pop(codepoint, None)
        origins.pop(codepoint, None)


def scale_ascii(font: TTFont) -> None:
    """Apply the established 103% vertical fit to printable ASCII only."""
    glyph_set, order = font.getGlyphSet(), font.getGlyphOrder()
    scaled = {name for cp, name in font.getBestCmap().items() if 0x20 <= cp <= 0x7E}
    transformed: dict[str, Any] = {}
    # Decompose first so non-ASCII composites cannot inherit scaled Latin components.
    for name in order:
        recording, pen = DecomposingRecordingPen(glyph_set), TTGlyphPen(None)
        glyph_set[name].draw(recording)
        scale_y = ASCII_VERTICAL_SCALE if name in scaled else 1.0
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


def _scratch_glyph(font: TTFont, codepoint: int) -> Any:
    """Decompose one Ubuntu ASCII glyph into an independent scratch outline."""
    name = font.getBestCmap()[codepoint]
    recording, pen = DecomposingRecordingPen(font.getGlyphSet()), TTGlyphPen(None)
    font.getGlyphSet()[name].draw(recording)
    recording.replay(TransformPen(pen, (1, 0, 0, 1, 0, 0)))
    return pen.glyph()


def _modifier_fit_glyph(glyph: Any) -> Any:
    """Fit one Ubuntu outline into the documented modifier envelope."""
    bounds_pen = BoundsPen({"scratch": glyph})
    glyph.draw(bounds_pen, None)
    if bounds_pen.bounds is None:
        return glyph
    x_min, y_min, x_max, y_max = bounds_pen.bounds
    target_x_min, target_y_min, target_x_max, target_y_max = (56, 320, 456, 760)
    scale = min(
        (target_x_max - target_x_min) / max(x_max - x_min, 1),
        (target_y_max - target_y_min) / max(y_max - y_min, 1),
    )
    x_offset = target_x_min + (target_x_max - target_x_min - (x_max - x_min) * scale) / 2 - x_min * scale
    y_offset = target_y_min + (target_y_max - target_y_min - (y_max - y_min) * scale) / 2 - y_min * scale
    recording = DecomposingRecordingPen({"scratch": glyph})
    glyph.draw(recording, None)
    pen = TTGlyphPen(None)
    _replay_transformed(
        recording,
        pen,
        lambda point: (round(point[0] * scale + x_offset), round(point[1] * scale + y_offset)),
    )
    return pen.glyph()


def _transform_glyph(glyph: Any, transform: tuple[float, float, float, float, float, float]) -> Any:
    recording, pen = DecomposingRecordingPen({"scratch": glyph}), TTGlyphPen(None)
    glyph.draw(recording, None)
    recording.replay(TransformPen(pen, transform))
    return pen.glyph()


def _make_polygon_glyph(points: Iterable[tuple[int, int]]) -> Any:
    """Build one closed polygon outline."""
    pen = TTGlyphPen(None)
    points = tuple(points)
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return pen.glyph()


def _draw_rectangle(pen: TTGlyphPen, rectangle: tuple[int, int, int, int]) -> None:
    x_min, y_min, x_max, y_max = rectangle
    pen.moveTo((x_min, y_min))
    pen.lineTo((x_max, y_min))
    pen.lineTo((x_max, y_max))
    pen.lineTo((x_min, y_max))
    pen.closePath()


def _draw_polygon(pen: TTGlyphPen, points: Iterable[tuple[int, int]]) -> None:
    points = tuple(points)
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()


def _make_check_mark_glyph(bold: bool) -> Any:
    """Build a conventional, source-independent check mark."""
    half = 42 if bold else 32
    left_normal = (round(half * 0.92), round(half * 0.39))
    right_normal = (-round(half * 0.85), round(half * 0.53))
    left = (64, 480)
    valley = (180, 180)
    right = (472, 700)
    ln_x, ln_y = left_normal
    rn_x, rn_y = right_normal
    return _make_polygon_glyph(
        (
            (left[0] + ln_x, left[1] + ln_y),
            (valley[0] + ln_x, valley[1] + ln_y),
            (right[0] + rn_x, right[1] + rn_y),
            (right[0] - rn_x, right[1] - rn_y),
            (valley[0] - rn_x, valley[1] - rn_y),
            (valley[0] - ln_x, valley[1] - ln_y),
            (left[0] - ln_x, left[1] - ln_y),
        )
    )


def _make_neovim_glyphs(
    target: TTFont,
    scratch_font: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
    italic: bool,
    bold: bool,
) -> None:
    """Install the 43 Ubuntu-derived Neovim modifier symbols and check mark."""
    scratch: dict[int, Any] = {}
    for cp in sorted(set(NEOVIM_GLYPHS.values())):
        scratch[cp] = _scratch_glyph(scratch_font, cp)
    for target_cp, base_cp in NEOVIM_GLYPHS.items():
        if italic:
            scratch[base_cp] = _transform_glyph(scratch[base_cp], (1, 0, 0.16, 1, -48, 0))
        glyph = _modifier_fit_glyph(scratch[base_cp])
        cmap.pop(target_cp, None)
        _set_mapped_glyph(target, cmap, target_cp, glyph, "generated")
        origins[target_cp] = "generated"

    cmap.pop(NEOVIM_CHECK, None)
    _set_mapped_glyph(target, cmap, NEOVIM_CHECK, _make_check_mark_glyph(bold), "generated")
    origins[NEOVIM_CHECK] = "generated"


def _set_mapped_glyph(
    font: TTFont,
    cmap: MutableMapping[int, str],
    codepoint: int,
    glyph: Any,
    prefix: str,
    width: int = HALF_WIDTH,
) -> bool:
    """Replace or add one mapped glyph; return whether it was added."""
    existing_name = cmap.get(codepoint)
    if existing_name is not None:
        shared = any(other_cp != codepoint and other_name == existing_name for other_cp, other_name in cmap.items())
        if not shared:
            _replace_glyph(font, existing_name, glyph)
            return False

    glyph_name = f"sg.{prefix}.{codepoint:04X}"
    suffix = 1
    while glyph_name in font["glyf"].glyphs:
        glyph_name = f"sg.{prefix}.{codepoint:04X}.{suffix}"
        suffix += 1
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
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
    bold: bool,
) -> None:
    """Generate box drawings with style-aware, cell-proportional strokes."""
    center_x, center_y = HALF_WIDTH // 2, (ASCENT - DESCENT) // 2
    bottom, top = -DESCENT, ASCENT
    light_thickness = round(HALF_WIDTH * (0.22 if bold else 0.17))
    heavy_thickness = light_thickness * 2
    double_rail_thickness = max(32, light_thickness // 2)
    double_rail_gap = max(24, light_thickness // 3)
    double_rail_offset = double_rail_thickness // 2 + double_rail_gap // 2

    def line_polygon(start: tuple[int, int], end: tuple[int, int], thickness: int) -> tuple[tuple[int, int], ...]:
        x0, y0 = start
        x1, y1 = end
        if x0 == x1:
            half = thickness // 2
            return ((x0 - half, y0), (x1 - half, y1), (x1 + half, y1), (x0 + half, y0))
        if y0 == y1:
            half = thickness // 2
            return ((x0, y0 - half), (x1, y1 - half), (x1, y1 + half), (x0, y0 + half))
        half = max(1, thickness // 2)
        # Box diagonals are 45-degree strokes; offset in both axes and clamp
        # each endpoint to the terminal cell so corner ink never overflows.
        normal = max(1, (half * 181 + 128) // 256)
        if y1 > y0:
            nx, ny = -normal, normal
        else:
            nx, ny = normal, normal
        raw_points: tuple[tuple[int, int], ...] = (
            (x0 + nx, y0 + ny),
            (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny),
            (x0 - nx, y0 - ny),
        )
        return tuple((max(0, min(HALF_WIDTH, x)), max(bottom, min(top, y))) for x, y in raw_points)

    def draw_horizontal(pen: TTGlyphPen, x_min: int, x_max: int, y: int, thickness: int, dash_count: int) -> None:
        spans: tuple[tuple[int, int], ...] = ((x_min, x_max),)
        if dash_count:
            span_length = x_max - x_min
            denominator = 2 * dash_count - 1
            dashed_spans: list[tuple[int, int]] = []
            for i in range(dash_count):
                span_min = x_min + span_length * (2 * i) // denominator
                span_max = x_min + span_length * (2 * i + 1) // denominator
                if span_max > span_min:
                    dashed_spans.append((span_min, span_max))
            spans = tuple(dashed_spans)
        for span_min, span_max in spans:
            _draw_rectangle(pen, (span_min, y - thickness // 2, span_max, y + thickness // 2))

    def draw_vertical(pen: TTGlyphPen, y_min: int, y_max: int, x: int, thickness: int, dash_count: int) -> None:
        spans: tuple[tuple[int, int], ...] = ((y_min, y_max),)
        if dash_count:
            span_length = y_max - y_min
            denominator = 2 * dash_count - 1
            dashed_spans: list[tuple[int, int]] = []
            for i in range(dash_count):
                span_min = y_min + span_length * (2 * i) // denominator
                span_max = y_min + span_length * (2 * i + 1) // denominator
                if span_max > span_min:
                    dashed_spans.append((span_min, span_max))
            spans = tuple(dashed_spans)
        for span_min, span_max in spans:
            _draw_rectangle(pen, (x - thickness // 2, span_min, x + thickness // 2, span_max))

    for codepoint in range(0x2500, 0x2580):
        name = unicodedata.name(chr(codepoint), "")
        name_tokens = set(name.split())
        pen = TTGlyphPen(None)
        diagonal = "DIAGONAL" in name
        cross = "CROSS" in name
        dash_count = 0
        if "DASH" in name_tokens:
            dash_count = next(
                (count for token, count in (("QUADRUPLE", 4), ("TRIPLE", 3), ("DOUBLE", 2)) if token in name_tokens),
                1,
            )
        double_line = "DOUBLE" in name_tokens and dash_count == 0
        heavy = "HEAVY" in name and "LIGHT" not in name
        thickness = heavy_thickness if heavy else light_thickness
        if diagonal:
            diagonals: tuple[tuple[int, int, int, int], ...] = ((0, bottom, HALF_WIDTH, top),)
            if "UPPER LEFT TO LOWER RIGHT" in name:
                diagonals = ((0, top, HALF_WIDTH, bottom),)
            if cross:
                diagonals = ((0, bottom, HALF_WIDTH, top), (0, top, HALF_WIDTH, bottom))
            for x0, y0, x1, y1 in diagonals:
                _draw_polygon(pen, line_polygon((x0, y0), (x1, y1), thickness))
            if double_line:
                _draw_polygon(pen, line_polygon((8, top), (HALF_WIDTH - 8, bottom), max(thickness // 2, 20)))
        else:
            directions = set()
            for token, direction in (("LEFT", "left"), ("RIGHT", "right"), ("UP", "up"), ("DOWN", "down")):
                if token in name_tokens:
                    directions.add(direction)
            if "HORIZONTAL" in name:
                directions.update(("left", "right"))
            if "VERTICAL" in name:
                directions.update(("up", "down"))
            if cross:
                directions.update(("left", "right", "up", "down"))
            if not directions:
                directions.update(("left", "right"))

            def arm_thickness(direction: str, box_name: str = name, base_thickness: int = thickness) -> int:
                token = direction.upper()
                if f"HEAVY {token}" in box_name:
                    return heavy_thickness
                if f"LIGHT {token}" in box_name:
                    return light_thickness
                return base_thickness

            if dash_count and directions == {"left", "right"}:
                draw_horizontal(pen, 0, HALF_WIDTH, center_y, arm_thickness("left"), dash_count)
            elif dash_count and directions == {"up", "down"}:
                draw_vertical(pen, bottom, top, center_x, arm_thickness("up"), dash_count)
            else:
                horizontal_rails = (
                    (center_y - double_rail_offset, center_y + double_rail_offset) if double_line else (center_y,)
                )
                vertical_rails = (
                    (center_x - double_rail_offset, center_x + double_rail_offset) if double_line else (center_x,)
                )
                for y in horizontal_rails:
                    if "left" in directions:
                        draw_horizontal(
                            pen,
                            0,
                            center_x,
                            y,
                            double_rail_thickness if double_line else arm_thickness("left"),
                            dash_count,
                        )
                    if "right" in directions:
                        draw_horizontal(
                            pen,
                            center_x,
                            HALF_WIDTH,
                            y,
                            double_rail_thickness if double_line else arm_thickness("right"),
                            dash_count,
                        )
                for x in vertical_rails:
                    if "down" in directions:
                        draw_vertical(
                            pen,
                            bottom,
                            center_y,
                            x,
                            double_rail_thickness if double_line else arm_thickness("down"),
                            dash_count,
                        )
                    if "up" in directions:
                        draw_vertical(
                            pen,
                            center_y,
                            top,
                            x,
                            double_rail_thickness if double_line else arm_thickness("up"),
                            dash_count,
                        )
        glyph = pen.glyph()
        _set_mapped_glyph(font, cmap, codepoint, glyph, "box")
        origins[codepoint] = "generated"


_LEGACY_ARROW_POINTS: Mapping[bool, Mapping[int, tuple[tuple[int, int], ...]]] = {
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
_LEGACY_ARROW_LSB = {
    False: {0x2190: 6, 0x2191: 29, 0x2192: 6, 0x2193: 29, 0x21D0: 6, 0x21D2: 6},
    True: {0x2190: 6, 0x2191: 22, 0x2192: 6, 0x2193: 21, 0x21D0: 6, 0x21D2: 6},
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
_LEGACY_RETURN_LSB = {False: -66, True: -73}


def _legacy_arrow_glyph(codepoint: int, bold: bool) -> Any:
    """Construct one exact last-good arrow from embedded on-curve points."""
    pen = TTGlyphPen(None)
    points = _LEGACY_ARROW_POINTS[bold][codepoint]
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return pen.glyph()


def _legacy_return_glyph(bold: bool) -> Any:
    """Construct the exact last-good shared return glyph from local points."""
    pen = TTGlyphPen(None)
    points = _LEGACY_RETURN_POINTS[bold]
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return pen.glyph()


def install_terminal_semantics(
    font: TTFont,
    cmap: MutableMapping[int, str],
    origins: MutableMapping[int, str],
    bold: bool,
) -> None:
    """Install embedded last-good arrows and preserve return-mark semantics."""
    for codepoint in sorted(BASIC_ARROWS):
        _replace_glyph(font, cmap[codepoint], _legacy_arrow_glyph(codepoint, bold))
        font["hmtx"].metrics[cmap[codepoint]] = (HALF_WIDTH, _LEGACY_ARROW_LSB[bold][codepoint])
        origins[codepoint] = "generated"
    for codepoint in (0x21D0, 0x21D2):
        _replace_glyph(font, cmap[codepoint], _legacy_arrow_glyph(codepoint, bold))
        font["hmtx"].metrics[cmap[codepoint]] = (HALF_WIDTH, _LEGACY_ARROW_LSB[bold][codepoint])
        origins[codepoint] = "generated"
    return_glyph = _legacy_return_glyph(bold)
    _set_mapped_glyph(font, cmap, RETURN_ARROW_CODEPOINT, return_glyph, "return")
    font["hmtx"].metrics[cmap[RETURN_ARROW_CODEPOINT]] = (HALF_WIDTH, _LEGACY_RETURN_LSB[bold])
    cmap[RETURN_SYMBOL_CODEPOINT] = cmap[RETURN_ARROW_CODEPOINT]
    origins[RETURN_ARROW_CODEPOINT] = origins[RETURN_SYMBOL_CODEPOINT] = "generated"


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
        self.cache: dict[tuple[str, int], str] = {}

    def copy_codepoint(self, codepoint: int) -> str:
        """Copy the glyph mapped from a Unicode codepoint."""
        return self.copy_glyph(self.cmap[codepoint], cell_width(codepoint))

    def copy_glyph(self, source_name: str, width: int) -> str:
        """Copy one source glyph, centered and scaled in the requested cell."""
        key = source_name, width
        if cached := self.cache.get(key):
            return cached
        factor = UPM / self.source_upm * self.scale
        recording, pen = DecomposingRecordingPen(self.glyphs), TTGlyphPen(None)
        self.glyphs[source_name].draw(recording)
        source_advance = self.metrics[source_name][0]
        offset = 0.0 if width == 0 else (width - source_advance * factor) / 2
        recording.replay(TransformPen(pen, (factor, 0, 0, factor, offset, 0)))
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
    scale: float,
) -> GlyphCopier:
    """Append eligible, previously unmapped source glyphs."""
    copier = GlyphCopier(target, source, SOURCE_PREFIXES[origin], scale)
    for codepoint in sorted(source.getBestCmap()):
        if (
            codepoint not in cmap
            and codepoint not in ORPHAN_CODEPOINTS
            and not is_private_use(codepoint)
            and accepts(codepoint)
        ):
            cmap[codepoint], origins[codepoint] = copier.copy_codepoint(codepoint), origin
    return copier


def remap_biz_uvs(source: TTFont, copier: GlyphCopier) -> UVSMap:
    """Copy every approved BIZ variation sequence into the target."""
    remapped: UVSMap = {}
    for table in source["cmap"].tables:
        if table.format != 14:
            continue
        for selector, entries in table.uvsDict.items():
            selected = [
                (base, None if name is None else copier.copy_glyph(name, cell_width(base)))
                for base, name in entries
                if base not in ORPHAN_CODEPOINTS
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
        0: "Contains Ubuntu Mono, M PLUS 1p, BIZ UDGothic, NINJAL Hentaigana, and IBM Plex Sans JP.",
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
    scales = {**SOURCE_SCALES, "mplus1p": MPLUS1P_STYLE_SCALES[style]}
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
        scratch_path = roots["ubuntu"] / f"UbuntuMono-{'B' if 'Bold' in style else 'R'}.ttf"
        scratch_font = stack.enter_context(closing(TTFont(scratch_path, recalcBBoxes=False, recalcTimestamp=False)))
        if scratch_font["head"].unitsPerEm != UPM:
            scale_upem(scratch_font, UPM)
        target = fonts["ubuntu"]
        if target["head"].unitsPerEm != UPM:
            scale_upem(target, UPM)
        scale_ascii(target)
        mapping = {
            cp: name
            for cp, name in target.getBestCmap().items()
            if not is_private_use(cp) and cp not in ORPHAN_CODEPOINTS
        }
        origins = dict.fromkeys(mapping, "ubuntu")
        add_codepoints(
            target,
            fonts["mplus1p"],
            mapping,
            origins,
            "mplus1p",
            is_mplus1p_japanese,
            scales["mplus1p"],
        )
        add_codepoints(
            target,
            fonts["ninjal"],
            mapping,
            origins,
            "ninjal",
            is_ninjal_hentaigana,
            scales["ninjal"],
        )
        biz_copier = add_codepoints(target, fonts["biz"], mapping, origins, "biz", lambda _: True, scales["biz"])
        uvs = remap_biz_uvs(fonts["biz"], biz_copier)
        add_codepoints(target, fonts["ibm"], mapping, origins, "ibm", lambda _: True, scales["ibm"])
        _make_neovim_glyphs(
            target,
            scratch_font,
            mapping,
            origins,
            "Italic" in style,
            "Bold" in style,
        )
        install_terminal_semantics(target, mapping, origins, "Bold" in style)
        replace_box_drawing(target, mapping, origins, "Bold" in style)
        normalize_terminal_glyphs(target, fonts["ibm"], mapping, origins)
        remove_orphans(mapping, origins)
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
    if set(origins) != set(mapping):
        raise RuntimeError("Per-codepoint ownership does not match the final cmap")
    summary: dict[str, object] = {
        "style": style,
        "output": str(output.relative_to(ROOT)),
        "codepoints": {origin: counts[origin] for origin in PROVENANCE_ORIGINS},
        "total_codepoints": len(mapping),
        "orphan_count": len(ORPHAN_CODEPOINTS),
        "orphan_codepoints_absent": sorted(f"U+{cp:04X}" for cp in ORPHAN_CODEPOINTS if cp not in mapping),
        "uvs_mappings_from_biz": uvs_count,
        "glyphs": glyph_count,
        "size_bytes": output.stat().st_size,
        "scales": scales,
        "sample_origins": {
            f"U+{cp:04X}": origins.get(cp)
            for cp in (0x0041, 0x2190, 0x21B5, 0x23CE, 0x2500, 0x3042, 0x65E5, 0xFF11, 0x3405)
        },
        "ownership": {f"U+{cp:04X}": origins[cp] for cp in sorted(mapping)},
        "neovim_origins": {f"U+{cp:04X}": origins[cp] for cp in (*NEOVIM_GLYPHS, NEOVIM_CHECK)},
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
        "mplus1p_commit": MPLUS1P_COMMIT,
        "ibm_commit": IBM_COMMIT,
        "inner_hashes": {"ninjal_hentaigana.ttf": NINJAL_TTF_SHA256},
        "assets": [asdict(asset) for asset in ASSETS],
        "styles": summaries,
    }
    provenance.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote    {provenance.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
