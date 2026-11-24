#!/usr/bin/env python3
"""Run the release catalog coverage checks from the Git repository root."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "main-app"


def run(command: list[str], cwd: Path) -> None:
    print(f"[i18n-coverage] running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    run(
        [
            sys.executable,
            str(APP_ROOT / "backend" / "scripts" / "verify_i18n_coverage.py"),
        ],
        APP_ROOT,
    )
    run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "i18n" / "sync_workbench_catalog.py"),
            "--verify",
        ],
        REPO_ROOT,
    )
    print("[i18n-coverage] PASS: main catalog and workbench read-model assets are synchronized")


if __name__ == "__main__":
    main()
