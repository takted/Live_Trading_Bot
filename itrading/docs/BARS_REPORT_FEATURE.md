# Bars Report Feature

## What is added

Each bot run now creates a dedicated per-pair bars log file:

- Path: `itrading/reports/<PAIR>/<PAIR>_bars_YYYYMMDD_HHMMSS.txt`
- Example: `itrading/reports/EURJPY/EURJPY_bars_20260415_140700.txt`

The file contains only:

- `[<PAIR>][Current Bar] ...`
- `[<PAIR>][Live Tick] ...`

## Scope

Bars report captures lines from startup onward for that bot process:

1. Historical warm-up strategy pass (`Current Bar` lines)
2. Live stream updates (`Live Tick` lines)
3. Live strategy cycles (`Current Bar` lines)

## Behavior

- Trade report behavior is unchanged.
- Bars report is auto-created at bot startup in `run_forex_live.py`.
- Bars report is closed during graceful shutdown.

## Notes

- Only bar/tick lines are written to bars report; other log tags are excluded.
- Write failures are non-fatal and do not stop trading.

