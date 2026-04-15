# Live Lifecycle Bridge (Backtest notify_* parity for live execution)

`run_forex_live.py` now includes a production-safe lifecycle bridge that mirrors key behavior of backtest `notify_order` / `notify_trade` when orders are executed externally via IB.

## What it does

- Registers each emitted strategy signal as a live trade intent.
- Maps parent/TP/SL IB order IDs to that trade.
- Consumes IB `orderStatusEvent` and `execDetailsEvent` callbacks.
- Marks entry filled and trade closed (TP/SL) with normalized reason.
- Computes realized PnL and pips.
- Maintains aggregate stats compatible with strategy summary fields:
  - `trades`, `wins`, `losses`, `gross_profit`, `gross_loss`, `win_rate`, `profit_factor`, `net_pnl`

## Key files

- Bridge implementation: `itrading/src/live_lifecycle_bridge.py`
- Live runner integration: `itrading/scripts/run_forex_live.py`
- Unit tests: `testing/test_live_lifecycle_bridge.py`

## Run the bridge unit test

```bash
python -m unittest testing.test_live_lifecycle_bridge
```

## Notes

- This bridge intentionally does not force Backtrader broker callbacks in live mode.
- It provides an explicit live lifecycle adapter for external broker execution, which is safer and easier to audit in production.

