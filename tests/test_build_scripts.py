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
import refresh_module_catalog_fixture


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


class ModuleCatalogFixtureTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.app = Path(self.temp.name)
        self.lock = self.app / "integration/repository-lock.json"
        self.catalog = self.app / "integration/out/assets/system-modules.json"
        self.fixture = self.app / "integration-core/src/test/resources/contracts/system-modules/catalog.json"
        self.core_fixture = self.app / "integration-core/src/test/resources/contracts/core/modules-installed.json"
        self.lock.parent.mkdir(parents=True)
        self.catalog.parent.mkdir(parents=True)
        self.fixture.parent.mkdir(parents=True)
        self.core_fixture.parent.mkdir(parents=True)
        self.fixture.write_text("old fixture", encoding="utf-8")
        self.core_fixture.write_text(json.dumps({"result": [{"id": "zairenkai", "version": {
            "major": 0, "minor": 3, "patch": 1}}]}), encoding="utf-8")
        self.commit = "a" * 40

    def tearDown(self):
        self.temp.cleanup()

    def write_inputs(self, catalog_commit):
        self.lock.write_text(json.dumps({"components": [{"id": "zairenkai-module", "commit": self.commit}]}), encoding="utf-8")
        self.catalog.write_text(json.dumps({"modules": [{"id": "zairenkai", "version": "v0.3.2",
            "source": {"commit": catalog_commit}}]}), encoding="utf-8")

    def test_refreshes_fixture_from_catalog_matching_locked_matrix(self):
        self.write_inputs(self.commit)
        self.assertEqual(self.commit, refresh_module_catalog_fixture.refresh(self.app))
        self.assertEqual(self.catalog.read_bytes(), self.fixture.read_bytes())
        core = json.loads(self.core_fixture.read_text(encoding="utf-8"))
        self.assertEqual({"major": 0, "minor": 3, "patch": 2}, core["result"][0]["version"])

    def test_rejects_catalog_from_different_matrix_without_changing_fixture(self):
        self.write_inputs("b" * 40)
        with self.assertRaisesRegex(ValueError, "does not match locked commit"):
            refresh_module_catalog_fixture.refresh(self.app)
        self.assertEqual("old fixture", self.fixture.read_text(encoding="utf-8"))
        core = json.loads(self.core_fixture.read_text(encoding="utf-8"))
        self.assertEqual({"major": 0, "minor": 3, "patch": 1}, core["result"][0]["version"])


class WorkflowCatalogFixtureTests(unittest.TestCase):
    def test_fixture_is_aligned_after_component_verification_and_before_app_tests(self):
        workflow = (ROOT / ".github/workflows/unified-release.yml").read_text(encoding="utf-8")
        verify = workflow.index("name: Verify the full integration lock and built components")
        align = workflow.index("name: Align module catalog test fixture with this source matrix")
        app_tests = workflow.index("name: Test, lint, and build the signed App")
        self.assertLess(verify, align)
        self.assertLess(align, app_tests)
        self.assertIn("scripts/refresh_module_catalog_fixture.py --app app", workflow)


if __name__ == "__main__":
    unittest.main()
