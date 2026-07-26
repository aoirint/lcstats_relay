"""Regression tests for Flet-specific mechanical extensions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_project import Checker


class FletExtensionCheckerTests(unittest.TestCase):
    """Exercise Flet documentation and dependency-direction checks."""

    def test_requires_flet_documentation_map(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checker = Checker(Path(directory))
            checker._check_flet_extensions()
            paths = {finding.path for finding in checker.findings}
            self.assertIn("docs/README.md", paths)
            self.assertIn("docs/domain/README.md", paths)
            self.assertIn("docs/architecture/README.md", paths)
            self.assertIn("docs/operations/README.md", paths)

    def test_rejects_flet_import_in_inner_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "package" / "application" / "service.py"
            source.parent.mkdir(parents=True)
            source.write_text("import flet\n", encoding="utf-8")
            checker = Checker(root)
            checker._check_flet_extensions()
            codes = {finding.code for finding in checker.findings}
            self.assertIn("inner-flet-import", codes)

    def test_requires_flet_project_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                """
[project]
name = "example"
version = "1.0.0"
dependencies = []
""",
                encoding="utf-8",
            )
            checker = Checker(root)
            checker._check_flet_extensions()
            codes = {finding.code for finding in checker.findings}
            self.assertIn("flet-dependency", codes)
            self.assertIn("flet-app-path", codes)
            self.assertIn("flet-app-module", codes)

    def test_run_combines_shared_python_and_flet_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                """
[project]
name = "example"
version = "1.0.0"
description = "Example Flet application"
requires-python = ">=3.11"
dependencies = []
""",
                encoding="utf-8",
            )
            codes = {finding.code for finding in Checker(root).run()}
            self.assertIn("dev-dependencies", codes)
            self.assertIn("flet-dependency", codes)


if __name__ == "__main__":
    unittest.main()
