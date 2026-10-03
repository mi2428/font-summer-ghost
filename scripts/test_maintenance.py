"""Offline regressions for artifact integrity and maintenance boundaries."""

from __future__ import annotations

import hashlib
import json
import stat
import unittest
import urllib.request
import warnings
import zipfile
from contextlib import nullcontext
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import build
import render_specimen as specimen
import validate
from fontTools.ttLib import TTFont, newTable


def provenance() -> dict[str, Any]:
    """Provide the current recipe without building or downloading fonts."""
    return {
        "family": "Summer Ghost",
        "version": "0.1.0",
        "mplus1p_commit": validate.MPLUS1P_COMMIT,
        "ibm_commit": validate.IBM_COMMIT,
        "inner_hashes": {"ninjal_hentaigana.ttf": validate.NINJAL_TTF_SHA256},
        "assets": [
            {"name": name, "url": url, "sha256": digest} for name, (url, digest) in validate.APPROVED_ASSETS.items()
        ],
        "styles": [{"style": style} for style in validate.STYLES],
    }


class ProvenanceTests(unittest.TestCase):
    def test_style_records_are_unique_and_complete(self) -> None:
        document = provenance()
        self.assertEqual(set(validate.validate_provenance(document)), set(validate.STYLES))
        for records in (
            document["styles"] + [deepcopy(document["styles"][0])],
            document["styles"][:-1],
            [*document["styles"][:-1], {"style": "Unknown"}],
            [*document["styles"][:-1], {}],
        ):
            with self.subTest(records=records), self.assertRaises(AssertionError):
                validate.validate_provenance({**document, "styles": records})

    def test_coverage_counts_match_the_compiled_font(self) -> None:
        summary: dict[str, Any] = {
            "ownership": {"U+0041": "ubuntu"},
            "codepoints": {origin: int(origin == "ubuntu") for origin in validate.ALLOWED_ORIGINS},
            "total_codepoints": 1,
            "glyphs": 2,
        }
        font = Mock()
        font.getBestCmap.return_value = {0x41: "A"}
        font.getGlyphOrder.return_value = [".notdef", "A"]
        validate.validate_coverage_summary(summary, "Regular", font)
        for field, value in (("total_codepoints", 2), ("glyphs", 3), ("ownership", {"U+0042": "ubuntu"})):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate.validate_coverage_summary({**summary, field: value}, "Regular", font)
        changed = deepcopy(summary)
        changed["codepoints"]["ubuntu"], changed["codepoints"]["biz"] = 0, 1
        with self.assertRaises(AssertionError):
            validate.validate_coverage_summary(changed, "Regular", font)

    def test_artifact_path_size_and_digest(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "SummerGhost-Regular.ttf"
            path.write_bytes(b"font")
            summary = {
                "output": "dist/SummerGhost-Regular.ttf",
                "size_bytes": 4,
                "sha256": hashlib.sha256(b"font").hexdigest(),
            }
            validate.validate_artifact(summary, "Regular", path)
            for field, value in (("output", "dist/wrong.ttf"), ("size_bytes", 5), ("sha256", "0" * 64)):
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    validate.validate_artifact({**summary, field: value}, "Regular", path)
            path.write_bytes(b"fake")
            with self.assertRaisesRegex(AssertionError, "SHA-256"):
                validate.validate_artifact(summary, "Regular", path)

    def test_failed_manifest_replace_keeps_previous_json(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "provenance.json"
            manifest.write_text('{"previous": true}\n')
            with (
                patch.object(build, "DIST", root),
                patch.object(build, "ROOT", root),
                patch.object(build, "fetch_sources", return_value={}),
                patch.object(build, "build_style", side_effect=lambda style, _: {"style": style}),
                patch("sys.argv", ["build.py"]),
                patch.object(Path, "replace", side_effect=OSError("publication failed")),
                self.assertRaisesRegex(OSError, "publication failed"),
            ):
                build.main()
            self.assertEqual(json.loads(manifest.read_text()), {"previous": True})
            self.assertFalse((root / ".provenance.json.tmp").exists())


class SpecimenTests(unittest.TestCase):
    def test_source_labels_require_canonical_anchors(self) -> None:
        document = provenance()
        owners = {"U+0041": "ubuntu", "U+3042": "mplus1p", "U+FF11": "biz", "U+3405": "ibm"}
        document["styles"][0]["ownership"] = owners
        with patch.object(Path, "read_text", side_effect=lambda **_: json.dumps(document)):
            self.assertIn("MPLUS1P-REGULAR", specimen.read_sources().mplus1p)
            for replacement in (None, "biz"):
                if replacement is None:
                    del owners["U+3042"]
                else:
                    owners["U+3042"] = replacement
                with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "anchors changed"):
                    specimen.read_sources()

    def test_regular_ownership_is_required_and_selected_by_name(self) -> None:
        document = provenance()
        document["styles"][0]["ownership"] = {"U+0041": "ubuntu"}
        document["styles"].reverse()
        self.assertEqual(specimen.regular_source_origins(document), {0x41: "ubuntu"})
        regular = next(record for record in document["styles"] if record["style"] == "Regular")
        for ownership in (None, {}, {"bad key": "ubuntu"}, {"U+0041": "unknown"}):
            regular["ownership"] = ownership
            with self.subTest(ownership=ownership), self.assertRaises(AssertionError):
                specimen.regular_source_origins(document)

    def test_fallback_samples_reject_missing_or_wrong_owners(self) -> None:
        document = provenance()
        owners = {
            f"U+{ord(character):04X}": origin
            for origin, rows in (
                ("biz", specimen.BIZ_ROWS),
                ("ninjal", specimen.NINJAL_ROWS),
                ("ibm", specimen.IBM_ROWS),
            )
            for row in rows
            for character in row.sample
            if not character.isspace()
        }
        document["styles"][0]["ownership"] = owners
        font = Mock()
        font.getBestCmap.return_value = {int(key[2:], 16): key for key in owners}
        with (
            patch.object(Path, "read_text", side_effect=lambda **_: json.dumps(document)),
            patch.object(specimen, "font_data", return_value=b""),
            patch.object(specimen, "TTFont", return_value=nullcontext(font)),
        ):
            specimen.validate_fallback_samples()
            for origin, row in (
                ("biz", specimen.BIZ_ROWS[0]),
                ("ninjal", specimen.NINJAL_ROWS[0]),
                ("ibm", specimen.IBM_ROWS[0]),
            ):
                codepoint = f"U+{ord(row.sample[0]):04X}"
                for replacement in (None, "generated"):
                    if replacement is None:
                        del owners[codepoint]
                    else:
                        owners[codepoint] = replacement
                    with (
                        self.subTest(origin=origin, replacement=replacement),
                        self.assertRaisesRegex(ValueError, "origin mismatch"),
                    ):
                        specimen.validate_fallback_samples()
                    owners[codepoint] = origin


class IncrementalBuildTests(unittest.TestCase):
    def test_incremental_builds_accumulate_and_deduplicate_styles(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            font = Mock()
            font.getBestCmap.return_value = {0x41: "A"}
            font.getGlyphOrder.return_value = [".notdef", "A"]

            def fake_build(style: str, _: object) -> dict[str, Any]:
                path = root / f"SummerGhost-{style}.ttf"
                path.write_bytes(style.encode())
                return {
                    "style": style,
                    "output": f"dist/{path.name}",
                    "size_bytes": path.stat().st_size,
                    "sha256": build.file_sha256(path),
                    "scales": validate.EXPECTED_SCALES[style],
                    "ownership": {"U+0041": "ubuntu"},
                    "codepoints": {origin: int(origin == "ubuntu") for origin in validate.ALLOWED_ORIGINS},
                    "total_codepoints": 1,
                    "glyphs": 2,
                }

            with (
                patch.object(build, "DIST", root),
                patch.object(build, "ROOT", root),
                patch.object(build, "fetch_sources", return_value={}),
                patch.object(build, "TTFont", return_value=font),
                patch.object(build, "build_style", side_effect=fake_build) as builder,
            ):
                for style in validate.STYLES:
                    with patch("sys.argv", ["build.py", "--style", style, "--style", style]):
                        build.main()
                self.assertEqual(builder.call_count, 4)
                manifest = root / "provenance.json"
                before = json.loads(manifest.read_text())
                validate.validate_provenance(before)
                with patch("sys.argv", ["build.py", "--style", "Regular"]):
                    build.main()
                self.assertEqual(json.loads(manifest.read_text()), before)
                for mutation in ("bytes", "scales", "recipe"):
                    changed = deepcopy(before)
                    if mutation == "bytes":
                        (root / "SummerGhost-Bold.ttf").write_bytes(b"fake")
                    elif mutation == "scales":
                        changed["styles"][1]["scales"] = {}
                    else:
                        changed["version"] = "unknown"
                    manifest.write_text(json.dumps(changed))
                    count = builder.call_count
                    with (
                        patch("sys.argv", ["build.py", "--style", "Regular"]),
                        self.subTest(mutation=mutation),
                        self.assertRaisesRegex(RuntimeError, "full build"),
                    ):
                        build.main()
                    self.assertEqual(builder.call_count, count)
                    (root / "SummerGhost-Bold.ttf").write_bytes(b"Bold")
                manifest.write_text("corrupted JSON")
                with patch("sys.argv", ["build.py"]):
                    build.main()
                validate.validate_provenance(json.loads(manifest.read_text()))


class SourceFileTests(unittest.TestCase):
    def test_verified_download_cache_and_failure_cleanup(self) -> None:
        asset = build.Asset("font.ttf", "https://example.invalid/font.ttf", hashlib.sha256(b"font").hexdigest())
        with TemporaryDirectory() as directory, patch.object(build, "DOWNLOADS", Path(directory)):
            destination = Path(directory) / asset.name
            temporary = Path(directory) / f"{asset.name}.part"
            with patch.object(urllib.request, "urlopen", return_value=BytesIO(b"font")) as request:
                build._download(asset)
                build._download(asset)
                request.assert_called_once()
                self.assertEqual(destination.read_bytes(), b"font")
            destination.write_bytes(b"bad cache")
            with (
                patch.object(urllib.request, "urlopen", return_value=BytesIO(b"wrong")),
                self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"),
            ):
                build._download(asset)
            self.assertFalse(destination.exists())
            self.assertFalse(temporary.exists())

            response = Mock()
            response.read.side_effect = [b"partial", OSError("interrupted download")]
            with (
                patch.object(urllib.request, "urlopen", return_value=nullcontext(response)),
                self.assertRaisesRegex(OSError, "interrupted download"),
            ):
                build._download(asset)
            self.assertFalse(destination.exists())
            self.assertFalse(temporary.exists())

    def test_archive_paths_types_duplicates_and_size_limit(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, destination = root / "archive.zip", root / "sources"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("fonts/font.ttf", b"font")
            build._safe_extract_zip(archive, destination)
            self.assertEqual((destination / "fonts/font.ttf").read_bytes(), b"font")
            for name in ("../escape.ttf", "/escape.ttf", "C:/escape.ttf", "C:\\escape.ttf", "fonts\\escape.ttf"):
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name, b"bad")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    build._safe_extract_zip(archive, destination)
            self.assertFalse((root / "escape.ttf").exists())
            symlink = zipfile.ZipInfo("link")
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(symlink, b"../escape.ttf")
            with self.assertRaisesRegex(ValueError, "member type"):
                build._safe_extract_zip(archive, destination)
            with zipfile.ZipFile(archive, "w") as bundle, warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                bundle.writestr("duplicate", b"first")
                bundle.writestr("duplicate", b"second")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                build._safe_extract_zip(archive, destination)
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("too_large", b"three")
            with patch.object(build, "MAX_ARCHIVE_UNCOMPRESSED_SIZE", 2), self.assertRaisesRegex(ValueError, "exceeds"):
                build._safe_extract_zip(archive, destination)


class BoxDrawingTests(unittest.TestCase):
    @staticmethod
    def boxes(bold: bool) -> tuple[TTFont, dict[int, str]]:
        font = TTFont()
        font["glyf"] = newTable("glyf")
        font["glyf"].glyphs = {}
        font["hmtx"] = newTable("hmtx")
        font["hmtx"].metrics = {}
        font.setGlyphOrder([])
        cmap: dict[int, str] = {}
        build.replace_box_drawing(font, cmap, {}, bold)
        return font, cmap

    @staticmethod
    def rectangles(glyph: Any) -> list[tuple[int, int, int, int]]:
        rectangles = []
        start = 0
        for end in glyph.endPtsOfContours:
            points = glyph.coordinates[start : end + 1]
            rectangles.append(
                (
                    min(x for x, _ in points),
                    min(y for _, y in points),
                    max(x for x, _ in points),
                    max(y for _, y in points),
                )
            )
            start = end + 1
        return rectangles

    def test_directional_weights_and_rail_counts_at_cell_edges(self) -> None:
        cases = {
            0x250D: {"down": "light", "right": "heavy"},
            0x250E: {"down": "heavy", "right": "light"},
            0x251E: {"up": "heavy", "right": "light", "down": "light"},
            0x253F: {"up": "light", "down": "light", "left": "heavy", "right": "heavy"},
            0x2543: {"left": "heavy", "up": "heavy", "right": "light", "down": "light"},
            0x2552: {"down": "light", "right": "double"},
            0x2553: {"down": "double", "right": "light"},
            0x255E: {"down": "light", "up": "light", "right": "double"},
            0x256C: {direction: "double" for direction in ("up", "down", "left", "right")},
            0x257C: {"left": "light", "right": "heavy"},
        }
        for bold in (False, True):
            font, cmap = self.boxes(bold)
            light = round(512 * (0.22 if bold else 0.17))
            rail_half = max(32, light // 2) // 2
            offset = rail_half + max(24, light // 3) // 2
            for cp, arms in cases.items():
                rectangles = self.rectangles(font["glyf"][cmap[cp]])
                for direction in ("left", "right", "down", "up"):
                    horizontal = direction in ("left", "right")
                    edge = {"left": 0, "right": 512, "down": -174, "up": 850}[direction]
                    center = 338 if horizontal else 256
                    intervals = sorted(
                        {
                            (y0, y1) if horizontal else (x0, x1)
                            for x0, y0, x1, y1 in rectangles
                            if (x0 <= edge <= x1 if horizontal else y0 <= edge <= y1)
                        }
                    )
                    arm = arms.get(direction)
                    expected = []
                    if arm == "double":
                        expected = [
                            (center - offset - rail_half, center - offset + rail_half),
                            (center + offset - rail_half, center + offset + rail_half),
                        ]
                    elif arm:
                        half = light if arm == "heavy" else light // 2
                        expected = [(center - half, center + half)]
                    with self.subTest(bold=bold, cp=f"U+{cp:04X}", direction=direction):
                        self.assertEqual(intervals, expected)

    def test_double_junctions_connect_without_filling_rail_gaps(self) -> None:
        for bold in (False, True):
            font, cmap = self.boxes(bold)
            light = round(512 * (0.22 if bold else 0.17))
            offset = max(32, light // 2) // 2 + max(24, light // 3) // 2

            def ink(cp: int, x: float, y: float, font: TTFont = font, cmap: dict[int, str] = cmap) -> bool:
                return any(
                    x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in self.rectangles(font["glyf"][cmap[cp]])
                )

            with self.subTest(bold=bold):
                self.assertTrue(ink(0x2552, 256, 338 + offset))
                self.assertTrue(ink(0x2553, 256 - offset, 338))
                self.assertTrue(ink(0x2554, 256 - offset / 2, 338 + offset))
                self.assertTrue(ink(0x2554, 256 - offset, 338 + offset / 2))
                self.assertFalse(ink(0x2560, 256 + offset, 338))
                for sign in (-1, 1):
                    self.assertFalse(ink(0x256C, 256 + sign * offset, 338))
                    self.assertFalse(ink(0x256C, 256, 338 + sign * offset))
                    for other_sign in (-1, 1):
                        self.assertTrue(ink(0x256C, 256 + sign * offset, 338 + other_sign * offset))

    def test_arcs_are_curved_mirrored_and_every_box_fits_its_cell(self) -> None:
        for bold in (False, True):
            font, cmap = self.boxes(bold)
            self.assertEqual(set(cmap), set(range(0x2500, 0x2580)))
            base = font["glyf"][cmap[0x256D]]
            for cp, sx, sy in ((0x256D, 1, 1), (0x256E, -1, 1), (0x256F, -1, -1), (0x2570, 1, -1)):
                glyph = font["glyf"][cmap[cp]]
                with self.subTest(bold=bold, cp=f"U+{cp:04X}"):
                    self.assertEqual(list(glyph.flags), list(base.flags))
                    self.assertEqual(
                        list(glyph.coordinates),
                        [(256 + sx * (x - 256), 338 + sy * (y - 338)) for x, y in base.coordinates],
                    )
                    self.assertEqual(sum(not flag & 1 for flag in glyph.flags), 4)
            for cp, name in cmap.items():
                glyph = font["glyf"][name]
                with self.subTest(bold=bold, cp=f"U+{cp:04X}"):
                    self.assertEqual(font["hmtx"][name][0], 512)
                    self.assertTrue(0 <= glyph.xMin <= glyph.xMax <= 512)
                    self.assertTrue(-174 <= glyph.yMin <= glyph.yMax <= 850)


if __name__ == "__main__":
    unittest.main()
