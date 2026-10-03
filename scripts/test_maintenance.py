"""Offline regressions for artifact integrity and maintenance boundaries."""

from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import build
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


if __name__ == "__main__":
    unittest.main()
