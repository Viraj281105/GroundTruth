"""Fast checks before each commit (#21): exactly what CI would reject for formatting and lint.

Run by ``scripts/hooks/pre-commit`` once a clone has ``git config core.hooksPath scripts/hooks``
(setup: DEVELOPMENT.md, section 9). It checks only the files staged for the commit:

* Python under ``packages/`` and ``tests/``: ``ruff format --check`` and ``ruff check``, the two
  commands CI runs, with the same pinned ruff and the same configuration;
* web files under ``apps/web/``: ESLint, the rules CI applies with ``npm run lint``;
* the staged diff: ``gitleaks`` if it is installed, otherwise a one-line note.

It never runs mypy or the test suite (a slow hook gets bypassed), and it never edits a file: it
reports, and prints the command that fixes the problem. It checks the working-tree copy of each
staged file, so stage what you mean to commit.

Usage: ``python scripts/hooks/pre_commit.py [FILE ...]``. With files, those are checked instead of
the staged set (for a quick manual check, and for tests).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOTS = ("packages/", "tests/")
"""Where CI runs ``ruff check`` and ``ruff format --check``: ``.github/workflows/ci.yml``."""
WEB_ROOT = "apps/web/"
WEB_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
WEB_EXCLUDED = ("apps/web/node_modules/", "apps/web/.next/", "apps/web/src/lib/generated/")
PYPROJECT = ROOT / "packages" / "groundtruth" / "pyproject.toml"


@dataclass
class Check:
    name: str
    command: list[str]
    fix: str
    cwd: Path = ROOT
    files: list[str] = field(default_factory=list)


def pinned_ruff() -> str | None:
    """The ruff version the dev extra pins, which is the one CI installs."""
    match = re.search(r'"ruff==([0-9.]+)"', PYPROJECT.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def python_files(files: list[str], *, staged: bool) -> list[str]:
    picked = [f for f in files if f.endswith((".py", ".pyi"))]
    return (
        [f for f in picked if f.replace("\\", "/").startswith(PYTHON_ROOTS)] if staged else picked
    )


def web_files(files: list[str]) -> list[str]:
    def wanted(name: str) -> bool:
        posix = name.replace("\\", "/")
        return (
            posix.startswith(WEB_ROOT)
            and posix.endswith(WEB_SUFFIXES)
            and not posix.startswith(WEB_EXCLUDED)
        )

    return [f for f in files if wanted(f)]


def plan(files: list[str], *, staged: bool) -> list[Check]:
    """The checks to run for these files, in order. Pure: runs nothing."""
    checks: list[Check] = []
    py = python_files(files, staged=staged)
    if py:
        ruff = [sys.executable, "-m", "ruff"]
        config = ["--config", str(ROOT / "pyproject.toml"), "--force-exclude"]
        checks.append(
            Check(
                "ruff format",
                [*ruff, "format", "--check", *config, *py],
                "ruff format packages tests",
                files=py,
            )
        )
        checks.append(
            Check(
                "ruff check",
                [*ruff, "check", *config, *py],
                "ruff check --fix packages tests",
                files=py,
            )
        )
    web = web_files(files)
    if web:
        relative = [str(Path(f).as_posix())[len(WEB_ROOT) :] for f in web]
        checks.append(
            Check(
                "eslint",
                ["node", "node_modules/eslint/bin/eslint.js", *relative],
                "cd apps/web && npm run lint",
                cwd=ROOT / "apps" / "web",
                files=web,
            )
        )
    return checks


def _ruff_problem() -> str | None:
    """Why ruff here cannot give CI's answer, or None when it can."""
    try:
        installed = metadata.version("ruff")
    except metadata.PackageNotFoundError:
        return (
            'ruff is not installed in this Python. Run: pip install -e "packages/groundtruth[dev]"'
        )
    wanted = pinned_ruff()
    if wanted and installed != wanted:
        return (
            f"ruff {installed} is installed but CI uses {wanted}, so the answers could differ. "
            'Run: pip install -e "packages/groundtruth[dev]"'
        )
    return None


def main(argv: list[str]) -> int:
    staged = not argv
    files = staged_files() if staged else argv
    checks = plan(files, staged=staged)

    if any(c.name.startswith("ruff") for c in checks) and (problem := _ruff_problem()):
        print(f"pre-commit: {problem}", file=sys.stderr)
        return 1
    runnable: list[Check] = []
    for check in checks:
        if check.name == "eslint" and not (check.cwd / "node_modules" / "eslint").exists():
            print("pre-commit: ESLint skipped: run `npm ci` in apps/web to lint web files.")
            continue
        runnable.append(check)
    if staged:
        gitleaks = shutil.which("gitleaks")
        if gitleaks is None:
            print("pre-commit: gitleaks not installed, secrets not scanned (see DEVELOPMENT.md).")
        else:
            runnable.append(
                Check(
                    "gitleaks",
                    [gitleaks, "protect", "--staged", "--redact", "--no-banner"],
                    "remove the secret from the staged change, and rotate it if it is real",
                )
            )

    # The checks are independent, so they run at the same time: the hook takes as long as
    # the slowest one, not the sum. Output is printed afterwards, in a fixed order.
    running = [
        (
            check,
            subprocess.Popen(
                check.command, cwd=check.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            ),
        )
        for check in runnable
    ]
    failed: list[Check] = []
    for check, process in running:
        output, _ = process.communicate()
        if process.returncode != 0:
            failed.append(check)
            sys.stdout.write(output.decode("utf-8", errors="replace"))

    if failed:
        print("\npre-commit: commit blocked. To fix:", file=sys.stderr)
        for check in failed:
            print(f"  {check.name}: {check.fix}", file=sys.stderr)
        print("(Bypass only in an emergency: git commit --no-verify)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main(sys.argv[1:]))
