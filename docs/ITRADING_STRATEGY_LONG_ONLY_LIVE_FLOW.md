# ITradingStrategy Current LONG-Only Live Flow

This document describes the current live behavior when running LONG-only mode.

- File reference: `itrading/src/strategy.py`
- Runtime style: live signal emission (strategy emits signal, runner executes broker order)
- Typical runner message when no setup completes: `No signal generated in this analysis cycle (all conditions not met).`

## 1) Current Direction Setup

In current defaults for `ITradingStrategy.params`:

- `enable_long_trades=True`
- `enable_short_trades=False`

So only LONG path is evaluated in phase 1 and later execution checks.

## 2) LONG-Only Live Decision Path Per Bar

`next()` still runs all safety gates first:

1. Skip if pending close/order/position/cutoff gate blocks processing
2. If flat and eligible, route through state machine

State-machine path in LONG-only mode:

- `SCANNING`
  - `_phase1_scan_for_signal()` checks LONG chain
  - If fail: stay in `SCANNING`
- `ARMED_LONG`
  - `_phase2_confirm_pullback('LONG')`
  - Wait for bearish pullback candles
- `WINDOW_OPEN`
  - `_phase4_monitor_window('LONG')`
  - Needs success breakout above top boundary before timeout/failure

Only after breakout success does final entry validation run.

## 3) LONG Conditions That Must Align

For a live LONG signal to be emitted, all relevant enabled checks must pass:

- Previous candle direction filter (if enabled)
- Confirm EMA crossover above any of fast/medium/slow
- Price filter EMA (if enabled)
- EMA position filter (if enabled)
- Angle filter range (if enabled)
- ATR range filter (if enabled)
- Pullback confirmation count
- Breakout window success
- Time filter in allowed UTC range
- Risk sizing must yield positive size

If any one fails, bar ends without signal.

## 4) Why You See "No signal generated ..."

In live mode, this message means the strategy reached the end of that cycle without queueing a signal.

Common LONG-only causes:

- No fresh LONG crossover in `SCANNING`
- Pullback not completed yet in `ARMED_LONG`
- Breakout not triggered in `WINDOW_OPEN`
- Time filter rejected breakout
- Final validation blocked (angle/ATR/candle direction)
- Sizing invalid (`units <= 0` or `bt_size <= 0`)

## 5) Lifecycle Logs to Identify Exact Blocker

Set `lifecycle_logging=True` to get per-stage reasons.

Look for these `[LIFECYCLE]` signatures:

- `phase1 LONG blocked ...`
- `phase1 LONG blocked filters ...`
- `no-signal | phase1 returned None (state=SCANNING)`
- `phase2 LONG waiting ...` / `phase2 LONG pass ...`
- `phase4 LONG waiting breakout ...` / `timeout` / `failed boundary`
- `entry blocked ...`
- `signal emitted ...`

These lines tell you exactly which gate failed on each 5-minute cycle.

## 6) Practical Live Debug Workflow

1. Keep `lifecycle_logging=True` for several 5-minute bars.
2. Group logs by each `--- Analyzing new 5-minute interval ... ---` cycle.
3. Identify the deepest phase reached each cycle:
   - Stuck at phase 1 -> signal-generation filters are too strict for current tape.
   - Reaching phase 2/4 but no emit -> pullback/window timing or final filters are blocking.
4. Compare blockers against your configured LONG thresholds.

This approach avoids guessing and ties every no-signal cycle to a concrete rule gate.

