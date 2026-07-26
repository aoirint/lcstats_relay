# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = []
# [tool.uv]
# exclude-newer = "P7D"
# ///
"""Check the shared Python floor and Flet-specific mechanical extensions."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_python_checker() -> ModuleType:
    script = (
        Path(__file__).resolve().parents[2]
        / "python-quality-check"
        / "scripts"
        / "check_project.py"
    )
    if not script.is_file():
        raise RuntimeError(
            "python-quality-check is required beside flet-project-quality-check"
        )
    spec = importlib.util.spec_from_file_location("_python_quality_check", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load shared Python checker: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PYTHON_CHECKER = _load_python_checker()
Finding = _PYTHON_CHECKER.Finding


class Checker(_PYTHON_CHECKER.Checker):  # type: ignore[misc]
    """Add Flet-specific checks to the shared Python checker."""

    def run(self) -> list[Any]:
        """Run shared Python checks followed by Flet extensions."""
        super().run()
        self._check_flet_extensions()
        return sorted(
            self.findings, key=lambda item: (item.path, item.code, item.message)
        )

    def _check_flet_extensions(self) -> None:
        for relative in (
            "docs/README.md",
            "docs/domain/README.md",
            "docs/architecture/README.md",
            "docs/operations/README.md",
        ):
            self.require(
                (self.root / relative).is_file(),
                "required-file",
                relative,
                "required Flet documentation baseline file is missing",
            )

        src = self.root / "src"
        for layer in ("domain", "application", "presentation"):
            for file in src.rglob("*.py") if src.is_dir() else ():
                if layer not in file.relative_to(src).parts:
                    continue
                text = file.read_text(encoding="utf-8")
                if re.search(r"(?m)^\s*(?:from\s+flet\b|import\s+flet\b)", text):
                    self.add(
                        "inner-flet-import",
                        file.relative_to(self.root).as_posix(),
                        f"{layer} layer must not import Flet",
                    )

        pyproject = self.root / "pyproject.toml"
        if pyproject.is_file():
            try:
                document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, tomllib.TOMLDecodeError):
                return
            project = document.get("project")
            runtime = (
                {
                    _PYTHON_CHECKER._dependency_name(item)
                    for item in project.get("dependencies", [])
                    if isinstance(item, str)
                }
                if isinstance(project, dict)
                else set()
            )
            self.require(
                "flet" in runtime,
                "flet-dependency",
                "pyproject.toml",
                "Flet must be a runtime dependency",
            )
            tool = document.get("tool")
            flet = tool.get("flet") if isinstance(tool, dict) else None
            app = flet.get("app") if isinstance(flet, dict) else None
            app = app if isinstance(app, dict) else {}
            self.require(
                isinstance(app.get("path"), str) and bool(app.get("path")),
                "flet-app-path",
                "pyproject.toml",
                "tool.flet.app.path is required",
            )
            self.require(
                isinstance(app.get("module"), str) and bool(app.get("module")),
                "flet-app-module",
                "pyproject.toml",
                "tool.flet.app.module is required",
            )


def main() -> int:
    """Run the command-line checker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Python Flet repository root")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    findings = Checker(root).run()
    if args.json:
        print(
            json.dumps(
                {
                    "status": "PASS" if not findings else "FAIL",
                    "findings": [asdict(item) for item in findings],
                },
                indent=2,
            )
        )
    elif findings:
        for finding in findings:
            print(f"{finding.path}: [{finding.code}] {finding.message}")
        print(f"FAIL: {len(findings)} finding(s)")
    else:
        print("PASS: mechanical Python and Flet project baseline satisfied")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
