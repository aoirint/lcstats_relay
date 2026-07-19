# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = []
# [tool.uv]
# exclude-newer = "P7D"
# ///
"""Check the mechanical floor of a Python Flet repository without modifying it."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "pyproject.toml",
    ".python-version",
    "uv.lock",
    "README.md",
    "docs/README.md",
    "docs/domain/README.md",
    "docs/architecture/README.md",
    "docs/operations/README.md",
)
REQUIRED_DEV_DEPENDENCIES = {"mypy", "pytest", "pytest-cov", "ruff"}
REQUIRED_RUFF_FAMILIES = {
    "ANN",
    "ASYNC",
    "B",
    "C90",
    "E",
    "F",
    "FBT",
    "I",
    "PL",
    "PT",
    "RUF",
    "S",
    "TRY",
    "UP",
    "W",
}
REQUIRED_CI_COMMANDS = (
    "uv lock --check",
    "uv sync --locked --all-groups",
    "uv run --locked ruff check",
    "uv run --locked ruff format --check",
    "uv run --locked mypy",
    "uv run --locked pytest",
)
USES_PATTERN = re.compile(r"""\buses:\s*["']?([^\s#"']+)""")


@dataclass(frozen=True, slots=True)
class Finding:
    """One mechanical baseline violation."""

    code: str
    path: str
    message: str


class Checker:
    """Collect deterministic repository findings."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(self, code: str, path: str, message: str) -> None:
        """Record a finding."""
        self.findings.append(Finding(code, path, message))

    def require(self, condition: bool, code: str, path: str, message: str) -> None:
        """Record a finding unless a condition holds."""
        if not condition:
            self.add(code, path, message)

    def run(self) -> list[Finding]:
        """Run all mechanical checks."""
        for relative in REQUIRED_FILES:
            self.require(
                (self.root / relative).is_file(),
                "required-file",
                relative,
                "required baseline file is missing",
            )

        pyproject_path = self.root / "pyproject.toml"
        if pyproject_path.is_file():
            self._check_pyproject(pyproject_path)
        self._check_python_layout()
        self._check_workflows()
        return sorted(self.findings, key=lambda item: (item.path, item.code, item.message))

    def _check_pyproject(self, path: Path) -> None:
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            self.add("invalid-pyproject", "pyproject.toml", f"cannot parse TOML: {exc}")
            return

        project = _table(document, "project")
        self.require(
            bool(project.get("name")),
            "project-name",
            "pyproject.toml",
            "project.name is required",
        )
        self.require(
            bool(project.get("description"))
            and project.get("description") != "Add your description here",
            "project-description",
            "pyproject.toml",
            "project.description must be intentional, not a generated placeholder",
        )
        self.require(
            bool(project.get("requires-python")),
            "requires-python",
            "pyproject.toml",
            "project.requires-python must define the supported range",
        )

        runtime = {_dependency_name(value) for value in _string_list(project.get("dependencies"))}
        self.require(
            "flet" in runtime,
            "flet-dependency",
            "pyproject.toml",
            "Flet must be a runtime dependency",
        )

        dev_groups = _table(document, "dependency-groups")
        dev = {_dependency_name(value) for value in _string_list(dev_groups.get("dev"))}
        missing_dev = sorted(REQUIRED_DEV_DEPENDENCIES - dev)
        self.require(
            not missing_dev,
            "dev-dependencies",
            "pyproject.toml",
            f"dependency-groups.dev is missing: {', '.join(missing_dev)}",
        )

        tool = _table(document, "tool")
        uv = _table(tool, "uv")
        self.require(
            uv.get("exclude-newer") == "P7D",
            "uv-cooldown",
            "pyproject.toml",
            'tool.uv.exclude-newer must equal "P7D"',
        )

        flet = _table(tool, "flet")
        flet_app = _table(flet, "app")
        self.require(
            isinstance(flet_app.get("path"), str) and bool(flet_app.get("path")),
            "flet-app-path",
            "pyproject.toml",
            "tool.flet.app.path is required",
        )
        self.require(
            isinstance(flet_app.get("module"), str) and bool(flet_app.get("module")),
            "flet-app-module",
            "pyproject.toml",
            "tool.flet.app.module is required",
        )

        ruff = _table(tool, "ruff")
        self.require(
            bool(ruff.get("target-version")),
            "ruff-target",
            "pyproject.toml",
            "tool.ruff.target-version is required",
        )
        ruff_lint = _table(ruff, "lint")
        selected = set(_string_list(ruff_lint.get("select")))
        missing_families = sorted(REQUIRED_RUFF_FAMILIES - selected)
        self.require(
            not missing_families,
            "ruff-families",
            "pyproject.toml",
            f"Ruff minimum families are missing: {', '.join(missing_families)}",
        )

        mypy = _table(tool, "mypy")
        self.require(
            mypy.get("strict") is True,
            "mypy-strict",
            "pyproject.toml",
            "tool.mypy.strict must be true",
        )
        self.require(
            mypy.get("warn_unreachable") is True,
            "mypy-unreachable",
            "pyproject.toml",
            "tool.mypy.warn_unreachable must be true",
        )
        mypy_files = set(_string_list(mypy.get("files")))
        self.require(
            {"src", "tests"}.issubset(mypy_files),
            "mypy-scope",
            "pyproject.toml",
            'tool.mypy.files must include "src" and "tests"',
        )

        pytest = _table(tool, "pytest")
        pytest_options = _table(pytest, "ini_options")
        addopts = " ".join(_string_list(pytest_options.get("addopts")))
        for token in (
            "--strict-config",
            "--strict-markers",
            "--cov-branch",
            "--cov-fail-under=100",
        ):
            self.require(
                token in addopts,
                "pytest-option",
                "pyproject.toml",
                f"pytest addopts must contain {token}",
            )
        self.require(
            re.search(r"(?:^|\s)--cov=[^\s]+", addopts) is not None,
            "coverage-source",
            "pyproject.toml",
            "pytest addopts must name the owned package with --cov=<package>",
        )

        coverage = _table(tool, "coverage")
        coverage_run = _table(coverage, "run")
        self.require(
            coverage_run.get("branch") is True,
            "coverage-branch",
            "pyproject.toml",
            "tool.coverage.run.branch must be true",
        )
        source_scope = _string_list(coverage_run.get("source")) + _string_list(
            coverage_run.get("source_pkgs")
        )
        self.require(
            bool(source_scope),
            "coverage-scope",
            "pyproject.toml",
            "coverage must name owned source/package scope",
        )
        coverage_report = _table(coverage, "report")
        self.require(
            coverage_report.get("fail_under") == 100,
            "coverage-threshold",
            "pyproject.toml",
            "tool.coverage.report.fail_under must equal 100",
        )
        self.require(
            coverage_report.get("show_missing") is True,
            "coverage-missing",
            "pyproject.toml",
            "tool.coverage.report.show_missing must be true",
        )

    def _check_python_layout(self) -> None:
        src = self.root / "src"
        tests = self.root / "tests"
        self.require(
            any(src.rglob("*.py")) if src.is_dir() else False,
            "src-layout",
            "src",
            "src must contain Python source",
        )
        self.require(
            any(tests.rglob("test_*.py")) if tests.is_dir() else False,
            "test-layout",
            "tests",
            "tests must contain pytest modules",
        )

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

        for file in src.rglob("*.py") if src.is_dir() else ():
            self._check_keyword_only_definitions(file)

    def _check_keyword_only_definitions(self, file: Path) -> None:
        relative = file.relative_to(self.root).as_posix()
        try:
            text = file.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=relative)
        except OSError, UnicodeError, SyntaxError:
            return
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = [*node.args.posonlyargs, *node.args.args]
            if positional and positional[0].arg in {"self", "cls"}:
                positional = positional[1:]
            if len(positional) <= 1 or (node.name.startswith("__") and node.name.endswith("__")):
                continue
            decorator_names = {_decorator_name(decorator) for decorator in node.decorator_list}
            if "override" in decorator_names:
                continue
            first_line = min(
                [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
            )
            preceding = lines[max(0, first_line - 4) : first_line - 1]
            if any("# keyword-only-exception:" in line for line in preceding):
                continue
            self.add(
                "keyword-only-definition",
                f"{relative}:{node.lineno}",
                "keep at most one project-owned input positional; add '*' before the rest or "
                "document an external-signature exception",
            )

    def _check_workflows(self) -> None:
        workflow_root = self.root / ".github" / "workflows"
        workflows = (
            sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
            if workflow_root.is_dir()
            else []
        )
        self.require(
            bool(workflows),
            "ci-workflow",
            ".github/workflows",
            "at least one GitHub Actions workflow is required",
        )
        if not workflows:
            return
        workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        ci_files = self._collect_ci_files(workflows)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in ci_files)
        for command in REQUIRED_CI_COMMANDS:
            self.require(
                command in combined,
                "ci-command",
                ".github/workflows",
                f"workflow must run: {command}",
            )
        self.require(
            re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", workflow_text) is not None,
            "ci-permissions",
            ".github/workflows",
            "workflow permissions must include contents: read",
        )
        self.require(
            "persist-credentials: false" in workflow_text,
            "checkout-credentials",
            ".github/workflows",
            "checkout must disable persisted credentials",
        )
        self.require(
            "timeout-minutes:" in workflow_text,
            "ci-timeout",
            ".github/workflows",
            "jobs must have an explicit timeout",
        )
        for path in ci_files:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = USES_PATTERN.search(line)
                if match is None or match.group(1).startswith("./"):
                    continue
                value = match.group(1)
                if re.fullmatch(r"[^@]+@[0-9a-fA-F]{40}", value) is None:
                    self.add(
                        "action-pin",
                        f"{path.relative_to(self.root).as_posix()}:{line_number}",
                        "external action/reusable workflow must use a full commit SHA",
                    )

    def _collect_ci_files(self, workflows: list[Path]) -> list[Path]:
        """Follow repository-local actions and reusable workflows from CI roots."""
        repository_root = self.root.resolve()
        pending = list(reversed(workflows))
        collected: list[Path] = []
        seen: set[Path] = set()
        while pending:
            path = pending.pop().resolve()
            if path in seen:
                continue
            seen.add(path)
            collected.append(path)
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = USES_PATTERN.search(line)
                if match is None or not match.group(1).startswith("./"):
                    continue
                referenced = (repository_root / match.group(1)[2:]).resolve()
                relative_source = path.relative_to(repository_root).as_posix()
                if not referenced.is_relative_to(repository_root):
                    self.add(
                        "local-action-path",
                        f"{relative_source}:{line_number}",
                        "repository-local action/workflow reference escapes the repository",
                    )
                    continue
                target = _resolve_local_ci_file(referenced)
                if target is None:
                    self.add(
                        "local-action-missing",
                        f"{relative_source}:{line_number}",
                        f"repository-local action/workflow does not resolve: {match.group(1)}",
                    )
                    continue
                target = target.resolve()
                if not target.is_relative_to(repository_root):
                    self.add(
                        "local-action-path",
                        f"{relative_source}:{line_number}",
                        "repository-local action/workflow resolves outside the repository",
                    )
                    continue
                if target not in seen:
                    pending.append(target)
        return collected


def _table(value: dict[str, Any], key: str) -> dict[str, Any]:
    child = value.get(key)
    return child if isinstance(child, dict) else {}


def _resolve_local_ci_file(path: Path) -> Path | None:
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        return path
    if not path.is_dir():
        return None
    for name in ("action.yml", "action.yaml"):
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _dependency_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement.strip())
    return match.group(0).lower().replace("_", "-") if match else ""


def _decorator_name(decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return ""


def main() -> int:
    """Run the command-line checker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Python Flet repository root")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
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
        print("PASS: mechanical Flet project baseline satisfied")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
