"""Offline regressions for artifact integrity and maintenance boundaries."""

from __future__ import annotations

import hashlib
import json
import unittest
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import build
import render_specimen as specimen
import validate


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


if __name__ == "__main__":
    unittest.main()
