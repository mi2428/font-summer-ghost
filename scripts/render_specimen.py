#!/usr/bin/env python3
"""Render the native-4K Summer Ghost type specimen."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

# Look-alike characters from multiple scripts are intentional in this specimen.
# ruff: noqa: RUF001

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PROVENANCE = DIST / "provenance.json"
OUTPUTS = ROOT / "specimen.png", DIST / "specimen.png"

SCALE = 2
LOGICAL_WIDTH, LOGICAL_HEIGHT = 1920, 1080
WIDTH, HEIGHT = LOGICAL_WIDTH * SCALE, LOGICAL_HEIGHT * SCALE

# Twelve-column editorial grid.
MARGIN = 56
COLUMN = 136
GUTTER = 16

# Shared layout tokens.
PANEL_HEADER = 44
PANEL_PAD = 20

# Square-edged nocturnal palette. Syntax roles use the same accents throughout.
CANVAS = "#0A0E15"
PANEL = "#111722"
INSET = "#0C111A"
INK = "#E7ECF5"
MUTED = "#96A0B2"
FAINT = "#596477"
RULE = "#2A3548"
CYAN = "#6ED4E8"
BLUE = "#78B4FF"
VIOLET = "#C39AFA"
AMBER = "#F0C86E"
CORAL = "#F08B76"
GREEN = "#8BD5A7"

Point = tuple[int, int]
Box = tuple[int, int, int, int]
Run = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Row:
    """One labeled character-atlas row."""

    label: str
    sample: str
    style: str = "Regular"
    color: str = INK


@dataclass(frozen=True, slots=True)
class Sources:
    """Source labels read from the generated provenance document."""

    ubuntu: str
    mplus1p: str
    biz: str
    ninjal: str
    ibm: str
    generated: str


LATIN_ROWS = (
    Row("UPPER", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    Row("LOWER", "abcdefghijklmnopqrstuvwxyz"),
    Row("ACCENTS I", "ÀÁÂÃÄÅ Æ Ç ÈÉÊË ÌÍÎÏ Ñ ÒÓÔÕÖ Ø Œ"),
    Row("ACCENTS II", "àáâãäå æ ç èéêë ìíîï ñ òóôõö ø œ ß"),
    Row("COMBINING", "à á â ã ä å  Ç  è é ê  ï  ñ  ö  ü"),
    Row("GREEK", "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ  αβγδεζηθ λμπσφω"),
    Row("CYRILLIC", "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩ  абвгде ёжзий я"),
    Row("FIGURES", "0123456789  00 01 02 10 42 99  1,234.56  −273.15"),
    Row("FRACTIONS", "¼ ½ ¾  ⅐ ⅑ ⅒ ⅓ ⅔ ⅕ ⅖ ⅗ ⅘ ⅙ ⅚ ⅛ ⅜ ⅝ ⅞"),
    Row("PUNCTUATION", "! ? ¡ ¿ . , : ; … ‥ ' ‘ ’ \" “ ” - – — _ / \\ |"),
    Row("FULLWIDTH", "０１２３４５６７８９  ＡＢＣＤＥ  ａｂｃｄｅ  ￥＠＃％＆＊"),
)

JAPANESE_ROWS = (
    Row("HIRAGANA A", "あいうえお かきくけこ さしすせそ たちつてと"),
    Row("HIRAGANA B", "なにぬねの はひふへほ まみむめも やゆよ らりるれろ わをん"),
    Row("VOICED HIRA", "がぎぐげご ざじずぜぞ だぢづでど ばびぶべぼ ぱぴぷぺぽ ゔ"),
    Row("SMALL HIRA", "ぁぃぅぇぉ ゃゅょ っ ゎ ゕゖ  ゐゑ"),
    Row("KATAKANA A", "アイウエオ カキクケコ サシスセソ タチツテト"),
    Row("KATAKANA B", "ナニヌネノ ハヒフヘホ マミムメモ ヤユヨ ラリルレロ ワヲン"),
    Row("VOICED KATA", "ガギグゲゴ ザジズゼゾ ダヂヅデド バビブベボ パピプペポ ヴ"),
    Row("SMALL KATA", "ァィゥェォ ャュョ ッ ヮ ヵヶ  ヰヱ"),
    Row("HALF KANA A", "ｱｲｳｴｵ ｶｷｸｹｺ ｻｼｽｾｿ ﾀﾁﾂﾃﾄ ﾅﾆﾇﾈﾉ"),
    Row("HALF KANA B", "ﾊﾋﾌﾍﾎ ﾏﾐﾑﾒﾓ ﾔﾕﾖ ﾗﾘﾙﾚﾛ ﾜｦﾝ ﾞﾟ"),
    Row("COMMON KANJI", "日本語 春夏秋冬 東京 京都 開発 環境 文字 情報 時間 駅 海 光"),
    Row("DIFFICULT", "鬱 薔薇 檸檬 躊躇 饕餮 贔屓 齷齪 魑魅魍魎"),
    Row("CJK PUNCT", "〒 々 〆 〽 「」 『』 【】 〈〉 《》 ・ 、 。 ！？ ￥ …"),
)

# These sets are provenance probes. The final build may expose a full origin index or
# only sample anchors; rendering remains useful in either case.
BIZ_ROWS = (
    Row("IPA", "ɐ ɑ ɒ ɓ ɔ ɕ ɖ ɗ ə ɚ ɜ ɞ ɟ ɠ ɡ ɤ ɥ ɦ"),
    Row("PUNCT", "‐ ‖ ‼ ‾ ‿ ⁂ ⁇ ⁈ ⁉ ⁑"),
    Row("NUMERALS", "Ⅳ Ⅴ Ⅵ Ⅶ Ⅷ Ⅸ Ⅹ Ⅺ Ⅻ ⅳ ⅴ ⅵ ⅶ ⅷ"),
)
IBM_ROWS = (
    Row("EXTENSION A", "㐅㐧㒈㔾㗞㘔㢡㢭㦤㦸"),
    Row("SUPPLEMENTARY", "𠂊𠂰𠃵𠅘𠔿𠖱𠘑𠛬"),
    Row("COMPATIBILITY", "契蘭寧旅漣煉連廉溺糖"),
    Row("UNCOMMON", "丄丅丌丟丣两丵丷乁乄"),
)

TERMINAL_ROWS = (
    Row("NEOVIM MODIFIERS A", "ʳ ʸ ˢ ˣ ᴬ ᴮ ᴰ ᴱ ᴳ ᴴ ᴵ ᴶ ᴷ ᴸ ᴹ"),
    Row("NEOVIM MODIFIERS B", "ᴺ ᴼ ᴾ ᴿ ᵀ ᵁ ᵂ ᵃ ᵇ ᵈ ᵉ ᵍ ᵏ ᵐ ᵒ"),
    Row("NEOVIM SYMBOLS", "ᵖ ᵗ ᵘ ᵛ ᶜ ᶠ ᶻ ⁱ ⁻ ⁽ ⁾ ⁿ ⱽ ✔"),
    Row("ENCLOSED 01–10", "① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩"),
    Row("ENCLOSED 11–20", "⑪ ⑫ ⑬ ⑭ ⑮ ⑯ ⑰ ⑱ ⑲ ⑳"),
    Row("GEOMETRIC I", "○ 〇 ◯ ● ◉ ◎ ◌ ◊"),
    Row("GEOMETRIC II", "□ ■ ▢ ▪ ▫ ▱ ◇ ◆ △ ▲ ▽ ▼ ☆ ★"),
    Row("DAILY / SIGNS", "☀ ☁ ☂ ☃ ☎ ☖ ☗ ☜ ☝ ☞ ☟ ♀ ♂ ♨ ⚠"),
    Row("MUSIC / SUITS", "♩ ♪ ♫ ♬ ♭ ♮ ♯ ♠ ♡ ♢ ♣ ♤ ♥ ♦ ♧"),
    Row("ARROWS I", "← ↓ ↑ → ↔ ↕ ↖ ↗ ↘ ↙  ↵ ⏎"),
    Row("ARROWS II", "⇐ ⇒ ⇔ ⇦ ⇧ ⇨ ⇩ ⇄ ⇅ ⇆ ⇋ ⇌ ⇵"),
    Row("MATH", "± × ÷ ≠ ≈ ≤ ≥ ∞ ∑ ∏ √ ∫ ∂ ∆ ∇"),
    Row("BLOCKS", "░ ▒ ▓ █ ▁ ▂ ▃ ▄ ▅ ▆ ▇ ▀ ▌ ▐"),
    Row("BOX DRAWING", "┌ ─ ┬ ┐ ├ ┼ ┤ └ ┴ ┘ ╭ ╮ ╰ ╯"),
)


def column_x(index: int) -> int:
    """Return the left edge of a zero-indexed grid column."""
    return MARGIN + index * (COLUMN + GUTTER)


def span(columns: int) -> int:
    """Return a contiguous grid span."""
    return columns * COLUMN + (columns - 1) * GUTTER


class Canvas:
    """Draw exact 2x coordinates and reject canvas or panel overflow."""

    def __init__(self, image: Image.Image) -> None:
        self.draw = ImageDraw.Draw(image)
        self._limit: Box | None = None

    @staticmethod
    def point(point: Point) -> Point:
        return point[0] * SCALE, point[1] * SCALE

    @staticmethod
    def box(box: Box) -> Box:
        left, top, right, bottom = box
        return left * SCALE, top * SCALE, right * SCALE, bottom * SCALE

    @staticmethod
    def _contains(outer: Box, inner: Sequence[float]) -> bool:
        return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]

    def _check(self, bounds: Sequence[float], name: str) -> None:
        native_canvas = (0, 0, WIDTH, HEIGHT)
        if not self._contains(native_canvas, bounds):
            raise ValueError(f"{name} exceeds canvas: {tuple(bounds)}")
        if self._limit is not None and not self._contains(self.box(self._limit), bounds):
            raise ValueError(f"{name} exceeds section {self._limit}: {tuple(bounds)}")

    @contextmanager
    def within(self, box: Box) -> Iterator[None]:
        """Apply a logical bounds assertion to enclosed draw calls."""
        previous, self._limit = self._limit, box
        try:
            yield
        finally:
            self._limit = previous

    def text(
        self,
        point: Point,
        value: str,
        *,
        face: ImageFont.FreeTypeFont,
        fill: str = INK,
        anchor: str = "la",
        name: str = "text",
    ) -> None:
        """Draw text after verifying its ink bounds."""
        native_point = self.point(point)
        bounds = self.draw.textbbox(native_point, value, font=face, anchor=anchor)
        self._check(bounds, name)
        self.draw.text(native_point, value, font=face, fill=fill, anchor=anchor)

    def textlength(self, value: str, *, face: ImageFont.FreeTypeFont) -> float:
        """Measure text in logical pixels."""
        return self.draw.textlength(value, font=face) / SCALE

    def rectangle(
        self,
        box: Box,
        *,
        fill: str | None = None,
        outline: str | None = None,
        width: int = 1,
    ) -> None:
        """Draw a square-cornered rectangle."""
        native = self.box(box)
        self._check(native, "rectangle")
        self.draw.rectangle(native, fill=fill, outline=outline, width=width * SCALE)

    def line(self, box: Box, *, fill: str = RULE, width: int = 1) -> None:
        """Draw a logical line."""
        native = self.box(box)
        self._check(native, "line")
        self.draw.line(native, fill=fill, width=width * SCALE)


@cache
def font_data(style: str) -> bytes:
    """Snapshot a generated face to avoid concurrent dist replacement."""
    path = DIST / f"SummerGhost-{style}.ttf"
    if not path.is_file():
        raise SystemExit(f"{path} not found; run make build first")
    return path.read_bytes()


@cache
def font(style: str = "Regular", size: int = 16) -> ImageFont.FreeTypeFont:
    """Load one face at a logical size."""
    return ImageFont.truetype(BytesIO(font_data(style)), size=size * SCALE)


def _asset_label(document: Mapping[str, Any], tokens: Sequence[str], fallback: str) -> str:
    """Return a compact label without depending on a particular asset filename."""
    assets = document.get("assets", ())
    for asset in assets if isinstance(assets, Sequence) else ():
        if not isinstance(asset, Mapping):
            continue
        haystack = " ".join(str(asset.get(key, "")) for key in ("name", "url")).casefold()
        if all(token.casefold() in haystack for token in tokens):
            name = str(asset.get("name", fallback)).removesuffix(".zip").removesuffix(".ttf")
            digest = str(asset.get("sha256", ""))
            suffix = f" / {digest[:8]}" if len(digest) >= 8 else ""
            return f"{name.upper()}{suffix}"
    return fallback


def _style_record(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read the first style record while accepting future provenance wrappers."""
    styles = document.get("styles", ())
    if isinstance(styles, Sequence) and styles and isinstance(styles[0], Mapping):
        return styles[0]
    raise ValueError("provenance has no readable style record")


def _parse_codepoint(raw_codepoint: object) -> int:
    """Parse integer or U+XXXX provenance keys."""
    if isinstance(raw_codepoint, int):
        return raw_codepoint
    text = str(raw_codepoint).strip()
    if text[:2].casefold() == "u+":
        text = text[2:]
    return int(text, 16)


def read_sources() -> Sources:
    """Derive visible source labels and verify provenance origin anchors."""
    document: dict[str, Any] = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    style = _style_record(document)
    origins = style.get("sample_origins", {})
    if not isinstance(origins, Mapping):
        origins = {}
    expected = {"U+0041": "ubuntu", "U+3042": "mplus1p", "U+FF11": "biz", "U+3405": "ibm"}
    mismatches = {
        codepoint: (expected_source, origins[codepoint])
        for codepoint, expected_source in expected.items()
        if codepoint in origins and origins[codepoint] != expected_source
    }
    if mismatches:
        raise ValueError(f"provenance anchors changed: {mismatches}")
    return Sources(
        ubuntu=_asset_label(document, ("ubuntu",), "UBUNTU MONO / ASCII SOURCE"),
        mplus1p=_asset_label(document, ("mplus1p", "regular"), "M PLUS 1P / JAPANESE BASE"),
        biz=_asset_label(document, ("bizudgothic",), "BIZ UDGOTHIC / JAPANESE FALLBACK"),
        ninjal=_asset_label(document, ("ninjal",), "NINJAL HENTAIGANA / DIRECT LAYER"),
        ibm=_asset_label(document, ("ibmplexsansjp", "regular"), "IBM PLEX SANS JP / FALLBACK"),
        generated="GENERATED / SEMANTIC GEOMETRY",
    )


def regular_source_origins(document: Mapping[str, Any]) -> Mapping[int, str]:
    """Read an optional provenance origin index without importing the builder."""
    style = _style_record(document)
    candidates = (style.get("codepoint_origins"), style.get("origins"), document.get("origin_index"))
    candidate = next((value for value in candidates if isinstance(value, Mapping)), {})
    parsed: dict[int, str] = {}
    for raw_codepoint, origin in candidate.items():
        try:
            codepoint = _parse_codepoint(raw_codepoint)
        except (TypeError, ValueError):
            continue
        parsed[codepoint] = str(origin)
    return parsed


def validate_fallback_samples() -> None:
    """Verify fallback labels against source precedence and final font coverage."""
    document: dict[str, Any] = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    style = _style_record(document)
    origins = dict(regular_source_origins(document))
    sample_origins = style.get("sample_origins", {})
    if isinstance(sample_origins, Mapping):
        for raw_codepoint, origin in sample_origins.items():
            try:
                origins[_parse_codepoint(raw_codepoint)] = str(origin)
            except (TypeError, ValueError):
                continue
    allowed = {"ubuntu", "mplus1p", "biz", "ninjal", "ibm", "generated"}
    unknown = sorted(set(origins.values()) - allowed)
    if unknown:
        raise ValueError(f"unsupported provenance origins: {unknown}")
    with TTFont(BytesIO(font_data("Regular")), lazy=True) as generated:
        cmap = generated.getBestCmap()
    for expected_source, sample_rows in (("biz", BIZ_ROWS), ("ibm", IBM_ROWS)):
        for row in sample_rows:
            codepoints = [ord(character) for character in row.sample if not character.isspace()]
            wrong_origins = [
                f"U+{codepoint:04X}:{origins.get(codepoint, 'missing')}"
                for codepoint in codepoints
                if codepoint in origins and origins[codepoint] != expected_source
            ]
            if wrong_origins:
                raise ValueError(f"{expected_source} {row.label} origin mismatch: {wrong_origins}")
            missing = [f"U+{codepoint:04X}" for codepoint in codepoints if codepoint not in cmap]
            if missing:
                raise ValueError(f"{expected_source} {row.label} missing from generated font: {missing}")


def validate_terminal_samples() -> None:
    """Require a covered, non-repeating symbol catalog."""
    with TTFont(BytesIO(font_data("Regular")), lazy=True) as generated:
        cmap = generated.getBestCmap()
    seen: dict[str, str] = {}
    for row in TERMINAL_ROWS:
        for character in row.sample:
            if character.isspace():
                continue
            if previous := seen.get(character):
                raise ValueError(f"terminal symbol {character!r} repeats in {previous!r} and {row.label!r}")
            if ord(character) not in cmap:
                raise ValueError(f"terminal symbol U+{ord(character):04X} is missing from Summer Ghost")
            seen[character] = row.label


def label(canvas: Canvas, point: Point, value: str, *, color: str = MUTED, size: int = 10) -> None:
    """Draw one compact uppercase label."""
    canvas.text(point, value, face=font("Bold", size), fill=color, anchor="ls", name=f"label {value}")


def panel(canvas: Canvas, box: Box, index: str, title: str, accent: str, meta: str = "") -> None:
    """Draw a square specimen panel with a shared heading baseline."""
    left, top, right, _ = box
    canvas.rectangle(box, fill=PANEL, outline=RULE)
    canvas.rectangle((left, top, right, top + 4), fill=accent)
    canvas.text((left + PANEL_PAD, top + 28), index, face=font("Bold", 10), fill=accent, anchor="lm")
    canvas.text((left + 58, top + 28), title, face=font("Bold", 14), anchor="lm")
    if meta:
        canvas.text((right - PANEL_PAD, top + 28), meta, face=font("Bold", 9), fill=FAINT, anchor="rm")
    canvas.line((left + PANEL_PAD, top + PANEL_HEADER, right - PANEL_PAD, top + PANEL_HEADER))


def rows(
    canvas: Canvas,
    point: Point,
    values: Sequence[Row],
    *,
    label_width: int,
    step: int,
    size: int,
    label_size: int = 10,
) -> None:
    """Draw consistently aligned atlas rows."""
    x, y = point
    for row_index, row in enumerate(values):
        baseline = y + row_index * step
        label(canvas, (x, baseline), row.label, size=label_size)
        canvas.text(
            (x + label_width, baseline),
            row.sample,
            face=font(row.style, size),
            fill=row.color,
            anchor="ls",
            name=f"sample {row.label}",
        )


def runs(canvas: Canvas, point: Point, segments: Sequence[Run], *, size: int = 14) -> None:
    """Draw one syntax-colored source line."""
    x_value: float = point[0]
    y = point[1]
    for value, color, style in segments:
        face = font(style, size)
        canvas.text((round(x_value), y), value, face=face, fill=color, anchor="ls", name="syntax token")
        x_value += canvas.textlength(value, face=face)


def draw_header(canvas: Canvas, sources: Sources) -> None:
    """Draw identity, scope, and source chain without technical metrics."""
    canvas.text((MARGIN, 42), "SUMMER GHOST", face=font("Bold", 40), anchor="la", name="title")
    canvas.text(
        (MARGIN + 2, 102),
        "COMPOSITE PROGRAMMING TYPE  /  CHARACTER ATLAS · READING · CODE · TERMINAL QA",
        face=font("Bold", 12),
        fill=MUTED,
        anchor="ls",
    )
    canvas.text(
        (LOGICAL_WIDTH - MARGIN, 62),
        "UBUNTU MONO  →  M PLUS 1P  →  NINJAL  →  BIZ UDGOTHIC  →  IBM PLEX SANS JP  →  GENERATED",
        face=font("Bold", 11),
        fill=CYAN,
        anchor="rs",
    )
    canvas.text(
        (LOGICAL_WIDTH - MARGIN, 94),
        "REGULAR  /  BOLD  /  ITALIC  /  BOLD ITALIC",
        face=font("Bold", 11),
        fill=FAINT,
        anchor="rs",
    )
    canvas.line((MARGIN, 126, LOGICAL_WIDTH - MARGIN, 126), fill=RULE, width=2)


def draw_reading(canvas: Canvas) -> None:
    """Draw coherent long-form English and Japanese reading text."""
    box = (column_x(0), 144, column_x(0) + span(8), 334)
    panel(canvas, box, "01", "LONGFORM READING / ENGLISH + 日本語", CYAN)
    with canvas.within(box):
        split = box[0] + span(4) + GUTTER // 2
        canvas.line((split, 204, split, 316))
        label(canvas, (box[0] + PANEL_PAD, 211), "ENGLISH / REGULAR", color=CYAN)
        label(canvas, (split + 20, 211), "日本語 / REGULAR", color=CYAN)
        english = (
            "At dusk, the platform releases the heat it kept all day.",
            "A train crosses the river, carrying the last light to sea.",
            "After the doors close, only a signal and pale reflection remain.",
            "The clock continues quietly through the summer night.",
        )
        japanese = (
            "夕暮れのホームが、一日じゅう抱えていた熱をゆっくり放していく。",
            "列車は川を渡り、最後の光を海のほうへ運んでいく。",
            "扉が閉じたあとには、信号と淡い反射だけが残る。",
            "駅の時計は、夏の夜を正確に、静かに刻みつづける。",
        )
        for line_index, value in enumerate(english):
            canvas.text(
                (box[0] + PANEL_PAD, 238 + line_index * 25),
                value,
                face=font("Regular", 16),
                anchor="ls",
                name="English longform",
            )
        for line_index, value in enumerate(japanese):
            canvas.text(
                (split + 20, 238 + line_index * 25),
                value,
                face=font("Regular", 15),
                anchor="ls",
                name="Japanese longform",
            )


def draw_styles(canvas: Canvas) -> None:
    """Draw all four generated styles at a shared size and baseline rhythm."""
    box = (column_x(8), 144, column_x(8) + span(4), 334)
    panel(canvas, box, "02", "FOUR STYLES", VIOLET, "COMPOSITE")
    style_rows = (
        Row("REGULAR", "platform / 夏のホーム", "Regular"),
        Row("BOLD", "signal / 静かな気配", "Bold"),
        Row("ITALIC", "reflection / 淡い光", "Italic"),
        Row("BOLD ITALIC", "return / 夜の列車", "BoldItalic"),
    )
    with canvas.within(box):
        rows(canvas, (box[0] + PANEL_PAD, 222), style_rows, label_width=122, step=29, size=17)


def draw_latin(canvas: Canvas, sources: Sources) -> None:
    """Draw dense Latin, combining, Greek, Cyrillic, figures, and punctuation."""
    box = (column_x(0), 350, column_x(0) + span(6), 704)
    panel(canvas, box, "03", "LATIN + EUROPEAN COVERAGE", BLUE, "PRIMARY ASCII / COMPOSITE EXTENSIONS")
    with canvas.within(box):
        canvas.text((box[0] + PANEL_PAD, 416), sources.ubuntu, face=font("Bold", 9), fill=FAINT, anchor="ls")
        rows(canvas, (box[0] + PANEL_PAD, 444), LATIN_ROWS, label_width=116, step=24, size=15)


def draw_japanese(canvas: Canvas, sources: Sources) -> None:
    """Draw dense kana, half-width forms, common kanji, and difficult kanji."""
    box = (column_x(6), 350, column_x(6) + span(6), 704)
    panel(canvas, box, "04", "JAPANESE CORE + WIDTH FORMS", CORAL, "KANA · KANJI · PUNCTUATION")
    with canvas.within(box):
        canvas.text((box[0] + PANEL_PAD, 416), sources.mplus1p, face=font("Bold", 9), fill=FAINT, anchor="ls")
        canvas.text((box[0] + PANEL_PAD, 431), sources.ninjal, face=font("Bold", 9), fill=FAINT, anchor="ls")
        rows(
            canvas,
            (box[0] + PANEL_PAD, 448),
            JAPANESE_ROWS,
            label_width=116,
            step=20,
            size=15,
            label_size=9,
        )


def draw_fallbacks(canvas: Canvas, sources: Sources) -> None:
    """Draw provenance-verified BIZ and IBM fallback-only specimens."""
    box = (column_x(0), 720, column_x(0) + span(4), 1028)
    panel(canvas, box, "05", "FALLBACK SOURCE ATLAS", GREEN, "SOURCE-SPECIFIC COVERAGE")
    with canvas.within(box):
        canvas.text((box[0] + PANEL_PAD, 791), sources.biz, face=font("Bold", 9), fill=GREEN, anchor="ls")
        rows(canvas, (box[0] + PANEL_PAD, 817), BIZ_ROWS, label_width=112, step=22, size=15, label_size=9)
        canvas.line((box[0] + PANEL_PAD, 880, box[2] - PANEL_PAD, 880))
        canvas.text((box[0] + PANEL_PAD, 897), sources.ninjal, face=font("Bold", 9), fill=CORAL, anchor="ls")
        canvas.line((box[0] + PANEL_PAD, 910, box[2] - PANEL_PAD, 910))
        canvas.text((box[0] + PANEL_PAD, 927), sources.ibm, face=font("Bold", 9), fill=AMBER, anchor="ls")
        rows(canvas, (box[0] + PANEL_PAD, 951), IBM_ROWS, label_width=112, step=21, size=15, label_size=9)


def draw_code(canvas: Canvas) -> None:
    """Draw valid TypeScript with explicit syntax roles, containers, and braces."""
    box = (column_x(4), 720, column_x(4) + span(5), 1028)
    panel(canvas, box, "06", "CODE / TYPESCRIPT", BLUE, "ARRAY · MAP · CALLBACK · COMMENT")
    code_box = (box[0] + PANEL_PAD, 780, box[2] - PANEL_PAD, 1016)
    with canvas.within(box):
        canvas.rectangle(code_box, fill=INSET, outline=RULE)
        code: tuple[tuple[Run, ...], ...] = (
            (
                ("type", VIOLET, "Bold"),
                (" Stop", CYAN, "Regular"),
                (" = ", VIOLET, "Regular"),
                ("{", AMBER, "Regular"),
                (" name", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("string", CYAN, "Regular"),
                (";", AMBER, "Regular"),
                (" minutes", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("number", CYAN, "Regular"),
                (" }", AMBER, "Regular"),
                (";", AMBER, "Regular"),
            ),
            (
                ("const", VIOLET, "Bold"),
                (" stops", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("readonly", VIOLET, "Regular"),
                (" Stop", CYAN, "Regular"),
                ("[]", AMBER, "Regular"),
                (" = ", VIOLET, "Regular"),
                ("[", AMBER, "Regular"),
            ),
            (
                ("  {", AMBER, "Regular"),
                (" name", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ('"東京"', GREEN, "Regular"),
                (",", AMBER, "Regular"),
                (" minutes", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("0", CORAL, "Regular"),
                (" },", AMBER, "Regular"),
            ),
            (
                ("  {", AMBER, "Regular"),
                (" name", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ('"海辺"', GREEN, "Regular"),
                (",", AMBER, "Regular"),
                (" minutes", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("42", CORAL, "Regular"),
                (" },", AMBER, "Regular"),
            ),
            (
                ("  {", AMBER, "Regular"),
                (" name", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ('"山麓"', GREEN, "Regular"),
                (",", AMBER, "Regular"),
                (" minutes", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("105", CORAL, "Regular"),
                (" },", AMBER, "Regular"),
            ),
            (("];", AMBER, "Regular"),),
            (
                ("function", VIOLET, "Bold"),
                (" nextTrain", BLUE, "Regular"),
                ("(", AMBER, "Regular"),
                ("stops", BLUE, "Regular"),
                (": ", INK, "Regular"),
                ("readonly Stop[]", CYAN, "Regular"),
                (")", AMBER, "Regular"),
                (": ", INK, "Regular"),
                ("string", CYAN, "Regular"),
                (" {", AMBER, "Regular"),
            ),
            (("  // Keep only stops after the origin.", MUTED, "Italic"),),
            (
                ("  const", VIOLET, "Bold"),
                (" late", BLUE, "Regular"),
                (" = ", VIOLET, "Regular"),
                ("stops", BLUE, "Regular"),
                (".filter((", AMBER, "Regular"),
                ("stop", BLUE, "Regular"),
                (") => ", VIOLET, "Regular"),
                ("stop", BLUE, "Regular"),
                (".minutes ", INK, "Regular"),
                (">", VIOLET, "Regular"),
                (" 0", CORAL, "Regular"),
                (");", AMBER, "Regular"),
            ),
            (
                ("  const", VIOLET, "Bold"),
                (" names", BLUE, "Regular"),
                (" = ", VIOLET, "Regular"),
                ("late", BLUE, "Regular"),
                (".map((", AMBER, "Regular"),
                ("stop", BLUE, "Regular"),
                (") => ", VIOLET, "Regular"),
                ("stop", BLUE, "Regular"),
                (".name);", AMBER, "Regular"),
            ),
            (
                ("  const", VIOLET, "Bold"),
                (" eta", BLUE, "Regular"),
                (" = ", VIOLET, "Regular"),
                ("late", BLUE, "Regular"),
                (".at(", AMBER, "Regular"),
                ("0", CORAL, "Regular"),
                (")?.", AMBER, "Regular"),
                ("minutes", BLUE, "Regular"),
                (" ", INK, "Regular"),
                ("??", VIOLET, "Regular"),
                (" -1", CORAL, "Regular"),
                (";", AMBER, "Regular"),
            ),
            (
                ("  return", VIOLET, "Bold"),
                (" `次の列車: ", GREEN, "Regular"),
                ("${", AMBER, "Regular"),
                ("names", BLUE, "Regular"),
                (".join(", AMBER, "Regular"),
                ('" / "', GREEN, "Regular"),
                (")}", AMBER, "Regular"),
                (" (", GREEN, "Regular"),
                ("${", AMBER, "Regular"),
                ("eta", BLUE, "Regular"),
                ("}", AMBER, "Regular"),
                ("分)`", GREEN, "Regular"),
                (";", AMBER, "Regular"),
            ),
            (("}", AMBER, "Regular"),),
            (
                ("console", BLUE, "Regular"),
                (".log(", AMBER, "Regular"),
                ("nextTrain", BLUE, "Regular"),
                ("(", AMBER, "Regular"),
                ("stops", BLUE, "Regular"),
                ("));", AMBER, "Regular"),
            ),
        )
        for line_index, syntax_line in enumerate(code, start=1):
            baseline = 800 + (line_index - 1) * 16
            canvas.text(
                (code_box[0] + 14, baseline),
                f"{line_index:02}",
                face=font("Regular", 10),
                fill=FAINT,
                anchor="ls",
            )
            runs(canvas, (code_box[0] + 44, baseline), syntax_line, size=13)


def draw_terminal(canvas: Canvas, sources: Sources) -> None:
    """Draw a dense, non-repeating atlas of terminal and everyday symbols."""
    box = (column_x(9), 720, column_x(9) + span(3), 1028)
    panel(canvas, box, "07", "TERMINAL + SYMBOLS", AMBER, f"{sources.generated} + IBM-FIT DIGITS")
    with canvas.within(box):
        rows(
            canvas,
            (box[0] + PANEL_PAD, 790),
            TERMINAL_ROWS,
            label_width=112,
            step=17,
            size=12,
            label_size=7,
        )


def draw_footer(canvas: Canvas) -> None:
    """Draw a restrained specimen footer without canvas metrics."""
    canvas.text(
        (MARGIN, 1058),
        "SUMMER GHOST  /  COMPOSITE TYPE SPECIMEN",
        face=font("Bold", 10),
        fill=FAINT,
        anchor="ls",
    )


def render() -> Image.Image:
    """Build the square-edged, high-density specimen."""
    for style in ("Regular", "Bold", "Italic", "BoldItalic"):
        font_data(style)
    sources = read_sources()
    validate_fallback_samples()
    validate_terminal_samples()
    image = Image.new("RGB", (WIDTH, HEIGHT), CANVAS)
    canvas = Canvas(image)
    draw_header(canvas, sources)
    draw_reading(canvas)
    draw_styles(canvas)
    draw_latin(canvas, sources)
    draw_japanese(canvas, sources)
    draw_fallbacks(canvas, sources)
    draw_code(canvas)
    draw_terminal(canvas, sources)
    draw_footer(canvas)
    return image


def main() -> None:
    """Atomically write byte-identical specimens to the root and dist."""
    DIST.mkdir(parents=True, exist_ok=True)
    root_temp = ROOT / ".specimen.png.tmp"
    dist_temp = DIST / ".specimen.png.tmp"
    try:
        render().save(root_temp, format="PNG", optimize=True)
        root_temp.replace(OUTPUTS[0])
        shutil.copyfile(OUTPUTS[0], dist_temp)
        dist_temp.replace(OUTPUTS[1])
    finally:
        root_temp.unlink(missing_ok=True)
        dist_temp.unlink(missing_ok=True)
    for output in OUTPUTS:
        print(f"wrote    {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
