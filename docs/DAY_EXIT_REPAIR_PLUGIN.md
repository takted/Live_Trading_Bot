# Restart DAY Exit Repair Plugin

This plugin is integrated into `itrading/scripts/run_forex_live.py` and is designed for this workflow:

- IB cancels DAY child exits around 5 PM ET (`Expired (5)`)
- You restart bot(s) around 6 PM ET
- Bot detects open net position with missing exits and recreates protective `LMT` + `STP`

## What it does

At startup (after IB connect + reconciliation), per instrument:

1. Detects current net position for the pair.
2. Reads active open orders for that pair.
3. If protective exit orders are missing (LMT and/or STP), it recalculates prices from **current market context**:
   - latest close from recent historical bars
   - ATR from recent bars (`atr_length` from strategy params)
   - uses long/short ATR stop/take multipliers from strategy params
4. Places replacement exit orders as OCA siblings (`LMT` and `STP`) for the open position size.

> Note: For already-filled parent entries, IB cannot reattach true child orders to a filled parent. The plugin creates equivalent protective OCA exits.

## Config keys (top-level JSON, not inside `STRATEGY_PARAMS`)

```json
{
  "ENABLE_RESTART_DAY_EXIT_REPAIR": false,
  "ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH": false,
  "RESTART_DAY_EXIT_REPAIR_DRY_RUN": false,
  "RESTART_DAY_EXIT_REPAIR_PRICE_MODE": "ATR_MARKET",
  "RESTART_DAY_EXIT_REPAIR_DURATION": "2 D",
  "RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW": "MIDPOINT",
  "RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF": true,
  "RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS": 1.0,
  "RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS": 12.0,
  "RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY": true
}
```

### Key behavior

- `ENABLE_RESTART_DAY_EXIT_REPAIR`
  - `true`: plugin runs at startup
  - `false`: plugin disabled

- `RESTART_DAY_EXIT_REPAIR_DRY_RUN`
  - `true`: logs intended replacement orders, places nothing
  - `false`: places real orders

- `RESTART_DAY_EXIT_REPAIR_PRICE_MODE`
  - `ATR_MARKET` (default): recalc from latest close + ATR
  - `SNAPSHOT`: uses fallback price context if ATR fetch unavailable

- `RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF`
  - `true`: plugin only runs if `IB_BRACKET_EXIT_TIF=DAY`
  - `false`: plugin can run with non-DAY exit TIF too

- `ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH`
  - `true`: when broker position is flat, plugin can reconstruct exposure from FX cash balances
  - `false`: plugin repairs only from broker position

- `RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY`
  - `true` (recommended): only allow cash fallback when recent completed child exits show `Expired (5)`
  - `false`: relax this guard

## Environment overrides (for bulk restart of many symbols)

You can toggle without editing every pair file:

- `ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR`
- `ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH`
- `ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN`
- `ITRADING_RESTART_DAY_EXIT_REPAIR_PRICE_MODE`

Accepted bool values: `1/0`, `true/false`, `yes/no`, `on/off`.

## Recommended 6 PM ET restart flow

1. First run in dry-run:

```cmd
set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR=true
set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=true
```

2. Start bot(s), review logs for `[EXIT-REPAIR]` computed LMT/STP.
3. If values look good, run real placement:

```cmd
set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=false
```

4. Restart bot(s) again and verify new open orders appear (`LMT` + `STP`).

## One-shot utility script (repair-only)

If you prefer to run repair once before normal bot startup, use:

- `itrading/scripts/repair_day_exits_once.py`

This script:

1. Connects to IB
2. Forces the restart repair plugin ON for this run
3. Repairs missing DAY exits for the target instrument
4. Logs resulting open orders
5. Disconnects and exits

### Dry-run first (recommended)

```cmd
cd /d C:\PyCharmProjects\Live_Trading_Bot
.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --instrument AUDUSD --dry-run
```

### Real placement

```cmd
cd /d C:\PyCharmProjects\Live_Trading_Bot
.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --instrument AUDUSD

.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --instrument AUDUSD --from-cash
```

### Useful options

```cmd
.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --instrument EURJPY --mode ATR_MARKET
.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --profile paper --instrument GBPJPY --dry-run
.venv\Scripts\python.exe itrading\scripts\repair_day_exits_once.py --params-file itrading\config\parameters_live_usdcad.json --dry-run
```

## Logging

Look for these messages:

- Startup settings:
  - `Restart DAY exit repair: enabled=... dry_run=... mode=...`
- Repair decision:
  - `[EXIT-REPAIR] ... missing(LMT=..., STP=...) ...`
- Placement:
  - `[EXIT-REPAIR] Placed replacement LMT ...`
  - `[EXIT-REPAIR] Placed replacement STP ...`

## Why normal bot startup may skip repair

`repair_day_exits_once.py` forces repair ON for that one run.

Normal `run_forex_live.py` startup only runs repair when:

- `ENABLE_RESTART_DAY_EXIT_REPAIR=true` (config or env), and
- (by default) `IB_BRACKET_EXIT_TIF=DAY` when `RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF=true`.

If disabled, startup logs now include an explicit warning when an open position has missing exits.

## Enable repair for normal bot start (6 PM ET)

Use env vars in the shell before launching your normal bot script(s):

```cmd
set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR=true
set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=false
set ITRADING_RESTART_DAY_EXIT_REPAIR_PRICE_MODE=ATR_MARKET
```

Then start as usual (`run_bot_forex.bat` / `start_10_forex.bat`).

For a safe first pass:

```cmd
set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=true
```

## Safety

- No action when flat.
- No action when both protective exits are already active.
- Non-fatal on errors (bot continues running).
- Snapshot updated after replacement orders are placed.

