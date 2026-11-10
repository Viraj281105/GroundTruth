"""The pre-commit hook (#21) blocks exactly what CI rejects for formatting, and stays fast.

Its speed is measured, not tested (it depends on the machine): see DEVELOPMENT.md, section 6.
Here: the hook checks the same paths with the same commands and the same ruff version as CI,
blocks a misformatted file and a lint error, passes a clean file, and runs nothing slow.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "hooks" / "pre_commit.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pre_commit_hook", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _ci_ruff_commands() -> list[str]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["quality"]["steps"]
    return [s["run"].strip() for s in steps if str(s.get("run", "")).strip().startswith("ruff")]


class TestSameAsCi:
    def test_ci_runs_exactly_these_two_ruff_commands(self):
        assert _ci_ruff_commands() == [
            "ruff check packages tests",
            "ruff format --check packages tests",
        ]

    def test_the_hook_checks_the_paths_ci_checks(self):
        for command in _ci_ruff_commands():
            paths = tuple(f"{p}/" for p in command.split()[-2:])
            assert paths == hook.PYTHON_ROOTS

    def test_the_hook_runs_the_same_two_ruff_commands(self):
        checks = hook.plan(["packages/a.py", "tests/b.py"], staged=True)
        commands = [c.command[3:5] for c in checks]
        assert commands == [["format", "--check"], ["check", "--config"]]
        assert all(str(ROOT / "pyproject.toml") in c.command for c in checks)

    def test_ci_installs_the_dev_extra_that_pins_ruff(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        assert 'pip install -e "packages/groundtruth[api,db,genai,dev]"' in workflow


class TestOneRuffVersion:
    def test_the_dev_extra_pins_ruff_exactly(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", hook.pinned_ruff() or "")

    def test_the_optional_framework_config_uses_the_same_ruff(self):
        config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        ruff = next(r for r in config["repos"] if r["repo"].endswith("ruff-pre-commit"))
        assert ruff["rev"] == f"v{hook.pinned_ruff()}"

    def test_this_environment_has_the_pinned_ruff(self):
        """CI installs the dev extra, so this holds there; locally it tells you to reinstall."""
        assert metadata.version("ruff") == hook.pinned_ruff()


class TestNothingSlow:
    def test_mypy_is_manual_only_in_the_framework_config(self):
        config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        hooks = {h["id"]: h for r in config["repos"] for h in r["hooks"]}
        assert hooks["mypy"]["stages"] == ["manual"]

    def test_the_hook_never_runs_mypy_or_tests(self):
        source = HOOK.read_text(encoding="utf-8")
        assert "mypy" not in re.sub(r'""".*?"""', "", source, flags=re.S)
        assert "pytest" not in source and "vitest" not in source


class TestWhatGetsChecked:
    def test_staged_python_outside_ci_paths_is_left_alone(self):
        assert hook.plan(["scripts/x.py", "apps/worker/main.py"], staged=True) == []

    def test_staged_web_files_go_to_eslint_and_generated_code_does_not(self):
        checks = hook.plan(
            [
                "apps/web/src/a.tsx",
                "apps/web/next.config.mjs",
                "apps/web/src/lib/generated/schema.d.ts",
                "apps/web/README.md",
                "docs/x.md",
            ],
            staged=True,
        )
        (eslint,) = checks
        assert eslint.name == "eslint"
        assert eslint.files == ["apps/web/src/a.tsx", "apps/web/next.config.mjs"]
        assert eslint.cwd == ROOT / "apps" / "web"

    def test_nothing_staged_means_nothing_to_run(self):
        assert hook.plan([], staged=True) == []


def _run(*files: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK), *map(str, files)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class TestItBlocks:
    def test_a_misformatted_file_is_blocked(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("x=1\n", encoding="utf-8")
        result = _run(bad)
        assert result.returncode == 1
        assert "ruff format: ruff format packages tests" in result.stderr

    def test_a_lint_error_is_blocked(self, tmp_path):
        bad = tmp_path / "unused.py"
        bad.write_text("import os\n", encoding="utf-8")
        result = _run(bad)
        assert result.returncode == 1
        assert "ruff check: ruff check --fix packages tests" in result.stderr

    def test_a_clean_file_passes_and_is_not_changed(self, tmp_path):
        good = tmp_path / "good.py"
        good.write_text('"""A clean module."""\n\nX = 1\n', encoding="utf-8")
        before = good.read_bytes()
        result = _run(good)
        assert result.returncode == 0, result.stdout + result.stderr
        assert good.read_bytes() == before  # the hook reports; it never rewrites

    def test_the_wrapper_is_a_posix_shell_script(self):
        wrapper = (ROOT / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
        assert wrapper.startswith("#!/bin/sh\n")
        assert "\r\n" not in wrapper  # a CRLF shebang does not run on macOS or Linux
        assert "pre_commit.py" in wrapper


@pytest.mark.parametrize("doc", ["DEVELOPMENT.md"])
def test_setup_is_documented(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "git config core.hooksPath scripts/hooks" in text
    assert "PowerShell" in text
