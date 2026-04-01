#!/usr/bin/env python3
"""Compare strategy params in JSON profile files against corresponding strategy class defaults.

Prints only mismatches:
- keys present in JSON STRATEGY_PARAMS but not in strategy params
- keys present in strategy params but missing in JSON STRATEGY_PARAMS
- keys present in both but with different values

Usage:
  .venv\\Scripts\\python.exe itrading\\scripts\\compare_params_vs_strategy.py
  .venv\\Scripts\\python.exe itrading\\scripts\\compare_params_vs_strategy.py --pattern "parameters_live_*.json"
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from typing import Any

# Ensure project-root imports like `itrading.src.strategy` work regardless of launch location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _class_param_defaults(strategy_cls: Any) -> dict[str, Any]:
    """Extract Backtrader params defaults from a strategy class."""
    params_obj = getattr(strategy_cls, "params", None)
    if params_obj is None:
        return {}

    # Backtrader params implementations can expose different accessors.
    for accessor_name in ("_getitems", "_getpairs"):
        accessor = getattr(params_obj, accessor_name, None)
        if callable(accessor):
            try:
                return dict(accessor())
            except Exception:
                pass

    # Last-resort fallback: inspect public attributes on params object.
    defaults: dict[str, Any] = {}
    for name in dir(params_obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(params_obj, name)
        except Exception:
            continue
        if not callable(value):
            defaults[name] = value
    return defaults


def _load_strategy_class(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _compare_one_profile(profile_path: Path) -> list[str]:
    mismatches: list[str] = []

    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{profile_path}: ERROR reading/parsing JSON: {exc}"]

    module_name = str(raw.get("STRATEGY_MODULE", "")).strip()
    class_name = str(raw.get("STRATEGY_CLASS", "")).strip()
    json_params = raw.get("STRATEGY_PARAMS", {})

    if not module_name or not class_name:
        return [f"{profile_path}: missing STRATEGY_MODULE/STRATEGY_CLASS"]
    if not isinstance(json_params, dict):
        return [f"{profile_path}: STRATEGY_PARAMS is not an object"]

    try:
        strategy_cls = _load_strategy_class(module_name, class_name)
    except Exception as exc:
        return [f"{profile_path}: ERROR loading {module_name}.{class_name}: {exc}"]

    class_defaults = _class_param_defaults(strategy_cls)
    if not class_defaults:
        return [f"{profile_path}: could not extract params from {module_name}.{class_name}"]

    unknown_json_keys = sorted(k for k in json_params if k not in class_defaults)
    missing_json_keys = sorted(k for k in class_defaults if k not in json_params)
    value_mismatch_keys = sorted(
        k for k in json_params if k in class_defaults and json_params[k] != class_defaults[k]
    )

    if unknown_json_keys or missing_json_keys or value_mismatch_keys:
        header = f"\n=== MISMATCH: {profile_path.name} vs {module_name}.{class_name} ==="
        mismatches.append(header)

    for key in unknown_json_keys:
        mismatches.append(f"[UNKNOWN_KEY] {key} -> json={json_params[key]!r}")

    for key in missing_json_keys:
        mismatches.append(f"[MISSING_IN_JSON] {key} -> class_default={class_defaults[key]!r}")

    for key in value_mismatch_keys:
        mismatches.append(
            f"[VALUE_MISMATCH] {key} -> json={json_params[key]!r} | class_default={class_defaults[key]!r}"
        )

    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare JSON profile params to strategy class params")
    parser.add_argument(
        "--config-dir",
        default=str(Path(__file__).resolve().parent.parent / "config"),
        help="Directory containing parameter JSON files",
    )
    parser.add_argument(
        "--pattern",
        default="parameters*.json",
        help="Glob pattern inside config-dir (default: parameters*.json)",
    )
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    if not config_dir.exists() or not config_dir.is_dir():
        print(f"ERROR: config directory not found: {config_dir}")
        return 2

    profiles = sorted(config_dir.glob(args.pattern))
    if not profiles:
        print(f"No files matched pattern '{args.pattern}' in {config_dir}")
        return 0

    total_mismatch_lines = 0
    for profile_path in profiles:
        lines = _compare_one_profile(profile_path)
        if lines:
            total_mismatch_lines += len(lines)
            for line in lines:
                print(line)

    if total_mismatch_lines == 0:
        print("No mismatches found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

