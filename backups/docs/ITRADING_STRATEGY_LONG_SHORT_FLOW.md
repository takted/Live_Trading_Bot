# ITradingStrategy Flow (LONG + SHORT)

This document describes how `ITradingStrategy.next()` processes bars when both directions are enabled.

- File reference: `itrading/src/strategy.py`
- Core method: `ITradingStrategy.next()`
- Entry engine: 4-phase state machine (`SCANNING -> ARMED_* -> WINDOW_OPEN -> ENTRY`)

## 1) High-Level Pipeline Per Bar

`next()` runs on every bar and follows this sequence:

1. Lifecycle/housekeeping gates
2. Position/order safety gates
3. Global invalidation checks
4. State-machine routing
5. Entry execution checks
6. Live signal emission (live mode) or Backtrader order placement (backtest mode)

If any gate fails, the method returns early and no new entry is produced for that bar.

## 2) Early-Return Safety Gates

Before entry logic, `next()` can return for these reasons:

- Live warmup position skip (live mode + position + not final processing bar)
- Pending close is still active
- Live cutoff replay skip (`live_cutoff_dt`)
- Pending entry order exists (`self.order`)
- Already in position (`self.position`)
- Exit already happened this bar (`exit_this_bar`)

With `lifecycle_logging=True`, these are emitted as `[LIFECYCLE] next skip ...` lines.

## 3) Global Invalidation Rule

When state is `ARMED_LONG` or `ARMED_SHORT`, an opposing crossover setup can reset state back to `SCANNING`:

- `ARMED_LONG` invalidated by bearish opposing setup
- `ARMED_SHORT` invalidated by bullish opposing setup

This prevents stale setups from surviving regime flips.

## 4) 4-Phase Entry State Machine

## Phase 1: `SCANNING`

Method: `_phase1_scan_for_signal()`

Checks LONG and SHORT independently (if each direction is enabled):

- Candle direction gate (optional)
- EMA crossover gate (confirm EMA crosses any fast/medium/slow)
- Optional EMA order gate
- Optional price filter gate
- Optional EMA position gate
- Optional angle gate
- Optional ATR range gate

On pass:

- Return `LONG` or `SHORT`
- Transition to `ARMED_LONG` / `ARMED_SHORT`
- Store trigger candle + ATR snapshot

On fail:

- Remain in `SCANNING`
- Live diagnostics show exact phase-1 blockers

## Phase 2: `ARMED_LONG` / `ARMED_SHORT`

Method: `_phase2_confirm_pullback(armed_direction)`

Pullback confirmation:

- `LONG`: waits for bearish pullback candles
- `SHORT`: waits for bullish pullback candles
- Requires configured candle count by direction

On pass:

- Transition to `WINDOW_OPEN`
- Call `_phase3_open_breakout_window(...)`

On fail/invalidation:

- Wait (count not reached) or reset to `SCANNING`

## Phase 3: Open Breakout Window

Method: `_phase3_open_breakout_window(armed_direction)`

Builds two-sided channel:

- Computes window start (optionally delayed by `window_offset_multiplier`)
- Sets expiry bar
- Calculates top/bottom breakout boundaries using pullback candle range and `window_price_offset_multiplier`

State becomes `WINDOW_OPEN`.

## Phase 4: `WINDOW_OPEN` Monitor

Method: `_phase4_monitor_window(armed_direction)`

Evaluates:

- Not active yet -> wait
- Timeout -> revert to `ARMED_*`
- Success boundary break -> returns `SUCCESS`
- Failure boundary break -> revert to `ARMED_*`

## 5) Post-Breakout Entry Execution

If phase 4 returns `SUCCESS`, execution still requires final checks:

- Time-window validation (`_is_in_trading_time_range`)
- Trigger-candle direction validation
- Direction-specific full filter validation
  - LONG: `_validate_all_entry_filters()`
  - SHORT: `_validate_all_short_entry_filters()`
- ATR sanity (`atr_now > 0`)
- Risk sizing validity (`units > 0`, `bt_size > 0`)

Any failure resets entry state and exits current bar with no trade.

## 6) Live vs Backtest Action

After all checks pass:

- Live mode (`live_trading=True`): emit signal to queue
  - payload: `direction`, `size`, `stop_loss`, `take_profit`
- Backtest mode: place Backtrader order (`buy` / `sell`)

Then:

- Record entry metadata
- Update entry tracking fields
- Reset state machine for next setup

## 7) Lifecycle Diagnostics You Can Watch

With `lifecycle_logging=True`, key lines include:

- `phase1 LONG/SHORT blocked ...`
- `phase1 LONG/SHORT blocked filters ...`
- `phase2 ... waiting` / `phase2 ... pass` / `phase2 ... invalidated`
- `phase4 ... waiting start` / `waiting breakout` / `timeout` / `failed boundary`
- `entry blocked ...` (time/candle/filter/sizing)
- `signal emitted ...`

These logs map directly to the no-signal decision path on each bar.

