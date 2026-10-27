# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import resolve_sources
import select_versions
import create_build_manifest


class SourceMatrixTests(unittest.TestCase):
    def test_matrix_has_unique_dev_sources_and_explicit_exclusion(self):
        config = resolve_sources.load_config(ROOT / "build/repositories.json")
        rows = config["repositories"]
        names = [row["name"] for row in rows]
        self.assertEqual("dev", config["ref"])
        self.assertEqual(15, len(names))
        self.assertEqual(len(names), len(set(names)))
        excluded = {entry["repository"].split("/", 1)[-1] for entry in config["excluded"]}
        self.assertNotIn("anime-extensions", names)
        self.assertIn("anime-extensions", excluded)

    def test_resolved_commit_must_belong_to_expected_repository(self):
        from unittest.mock import patch
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self):
                return json.dumps({"sha": "a" * 40,
                                   "html_url": "https://github.com/wrong/repo/commit/" + "a" * 40}).encode()
        with patch.object(resolve_sources.urllib.request, "urlopen", return_value=Response()):
            with self.assertRaises(RuntimeError):
                resolve_sources.resolve("owner", "repo", "dev")


class VersionSelectionTests(unittest.TestCase):
    def test_versions_advance_monotonically_and_ignore_other_tag_families(self):
        tags = ["v1.2.8", "module-v0.4.1", "other-v9.9.9", "v2.0.0-beta.2"]
        self.assertEqual("1.2.9", select_versions.choose("1.0.0", tags))
        self.assertEqual("0.4.2", select_versions.choose("0.1.0", tags, prefix="module-v"))

    def test_source_version_ahead_of_release_is_preserved(self):
        self.assertEqual("1.3.0", select_versions.choose("1.3.0-beta.2", ["v1.2.9"]))


class BuildManifestTests(unittest.TestCase):
    def test_manifest_binds_matrix_builder_and_artifact_hashes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_sha, modules_sha, builder_sha = "a" * 40, "b" * 40, "c" * 40
            matrix = root / "matrix.json"
            matrix.write_text(json.dumps({"ref": "dev", "repositories": [
                {"name": "Zairenkai-App", "sha": app_sha, "repository": "ZairenkaiPrjctX/Zairenkai-App", "ref": "dev", "role": "app"},
                {"name": "Zairenkai-Modules", "sha": modules_sha, "repository": "ZairenkaiPrjctX/Zairenkai-Modules", "ref": "dev", "role": "module"},
            ]}), encoding="utf-8")
            app, module, components = root / "app.apk", root / "module.zip", root / "components.json"
            app.write_bytes(b"signed apk")
            module.write_bytes(b"module zip")
            components.write_text("{}", encoding="utf-8")
            output = root / "release"
            manifest = create_build_manifest.create(matrix, output, "1.0.0", "0.1.0",
                                                     app_sha, modules_sha, builder_sha,
                                                     app, module, components)
            self.assertEqual(builder_sha, manifest["builder"]["commit"])
            self.assertEqual(app_sha, manifest["source_repositories"]["Zairenkai-App"]["commit"])
            self.assertEqual(2, len(manifest["artifacts"]))
            self.assertTrue((output / "build-manifest.json.sha256").is_file())
            self.assertTrue((output / "SHA256SUMS").is_file())

    def test_manifest_rejects_product_commit_outside_matrix(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix = root / "matrix.json"
            matrix.write_text(json.dumps({"repositories": [
                {"name": "Zairenkai-App", "sha": "a" * 40, "repository": "owner/app", "ref": "dev", "role": "app"},
                {"name": "Zairenkai-Modules", "sha": "b" * 40, "repository": "owner/modules", "ref": "dev", "role": "module"},
            ]}), encoding="utf-8")
            artifacts = [root / "app.apk", root / "module.zip", root / "components.json"]
            artifacts[0].write_bytes(b"a")
            artifacts[1].write_bytes(b"m")
            artifacts[2].write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                create_build_manifest.create(matrix, root / "out", "1.0.0", "0.1.0",
                                             "d" * 40, "b" * 40, "c" * 40, *artifacts)


if __name__ == "__main__":
    unittest.main()
