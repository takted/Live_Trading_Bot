#!/usr/bin/env python3
"""Cleanup utility for itrading logs and report artifacts.

Removes:
1) All *.log files under itrading/logs (recursive)
2) All files under itrading/reports/*/ subfolders (recursive)
3) All *_bars_8888.txt files under itrading/reports (recursive)

By default this runs in dry-run mode. Use --apply to actually delete files.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _collect_files(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    logs_dir = root / "logs"
    reports_dir = root / "reports"

    log_files: list[Path] = []
    report_files: list[Path] = []
    bars_files: list[Path] = []

    if logs_dir.exists():
        log_files = [p for p in logs_dir.rglob("*.log") if p.is_file()]

    if reports_dir.exists():
        for child in reports_dir.iterdir():
            if not child.is_dir():
                continue
            report_files.extend(p for p in child.rglob("*") if p.is_file())

        # Collect *_bars_8888.txt files from reports directory (recursive)
        bars_files = [p for p in reports_dir.rglob("*_bars_8888.txt") if p.is_file()]

    return log_files, report_files, bars_files


def _delete_files(files: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    deleted = 0
    errors: list[tuple[Path, str]] = []

    for file_path in files:
        try:
            file_path.unlink(missing_ok=True)
            deleted += 1
        except Exception as exc:  # pragma: no cover
            errors.append((file_path, str(exc)))

    return deleted, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove itrading log files and report files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this flag, only prints what would be deleted.",
    )
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    itrading_dir = scripts_dir.parent

    log_files, report_files, bars_files = _collect_files(itrading_dir)
    all_files = log_files + report_files + bars_files

    print("=== CLEANUP TARGETS ===")
    print(f"Logs (*.log): {len(log_files)}")
    print(f"Report files (itrading/reports/*/): {len(report_files)}")
    print(f"Bars reports (*_bars_*.txt): {len(bars_files)}")
    print(f"Total files: {len(all_files)}")

    if not args.apply:
        print("\nDry-run mode (no files deleted). Use --apply to delete.")
        for file_path in all_files:
            print(f"  WOULD DELETE: {file_path}")
        return 0

    deleted, errors = _delete_files(all_files)

    print("\n=== CLEANUP RESULT ===")
    print(f"Deleted: {deleted}")
    print(f"Errors: {len(errors)}")

    for file_path, error_msg in errors:
        print(f"  ERROR: {file_path} -> {error_msg}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

