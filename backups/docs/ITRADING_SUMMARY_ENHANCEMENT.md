# ITrading Summary Enhancement - Broker Position Integration

## Overview
Enhanced the ITrading Summary system to integrate live forex instrument position details from the broker account. The summary now displays:
1. Strategy performance metrics (trades, wins, losses, win rate, profit factor)
2. Backtrader portfolio Final Value and PnL
3. **NEW:** Live broker account positions with instrument details and market values

## Implementation Summary

### 1. New Module: `itrading/src/position_monitor.py`
A dedicated monitor class for tracking and formatting broker positions in real-time.

**Key Features:**
- `update_positions()` - Updates positions from broker connection
- `get_forex_positions()` - Filters forex-only positions
- `get_stock_positions()` - Filters stock-only positions
- `calculate_position_value()` - Computes market value of positions
- `calculate_unrealized_pnl()` - Computes unrealized P&L
- `format_position_summary()` - Formats individual position for display
- `format_all_positions_summary()` - Formats all positions with totals
- `get_total_market_value()` - Aggregates total market value
- `get_total_unrealized_pnl()` - Aggregates total unrealized P&L

### 2. Enhanced: `src/trader.py` (ITradingTrader)

**Changes:**
- Added import: `from itrading.src.position_monitor import BrokerPositionMonitor`
- Added attribute: `self.position_monitor` in `__init__`
- Updated `initialize()` to create BrokerPositionMonitor instance
- Updated `generate_signal()` to pass `ib_connection` to strategy via params
- **NEW:** `print_broker_summary()` method - Fetches and displays broker positions
- **NEW:** Enhanced `start_trading()` loop - Periodically prints broker summary (every 5 signal checks)
- **NEW:** Enhanced `stop()` - Prints final broker summary before shutdown

**Live Mode Execution:**
The broker summary is now printed automatically during live trading:
```
while self.running and not self.emergency_stop:
    # ... process symbols ...

    # Print broker summary every N signal checks
    if current_time - last_summary_time >= summary_interval:
        self.print_broker_summary()
        last_summary_time = current_time
```

### 3. Enhanced: `itrading/src/strategy.py` (ITradingStrategy)

**Changes:**
- Added `ib_connection=None` parameter to strategy params dict
- Enhanced `stop()` method to include broker position details in ITRADING SUMMARY

**New Summary Output:**
```
=== ITRADING SUMMARY ===
Trades: 5 Wins: 3 Losses: 2 WinRate: 60.00% PF: 2.50
Final Value: 5,250.00 | Total PnL: +250.00

=== BROKER POSITIONS (2 total) ===
  EURUSD/USD (FOREX): Qty=+0.05 | AvgCost=1.08500
  GBPUSD/USD (FOREX): Qty=-0.03 | AvgCost=1.27850
============================================================
```

## Usage Flow

### During Live Trading:
1. ITradingTrader initializes BrokerPositionMonitor
2. Strategy receives ib_connection as parameter
3. Trading loop runs continuously:
   - Processes signal for each symbol
   - Every N signal checks: prints live broker summary
4. On shutdown: prints final broker summary

### Summary Content:
**Backtrader Level (Strategy Stop):**
- Trade metrics from strategy execution
- Final Value and PnL from broker object
- Live broker positions (if connection available)

**Live Monitoring Level (Trader Loop):**
- Current broker positions
- Quantity and average cost per position
- Updated continuously during trading

## Access Points for Position Data

### From Strategy (in stop() method):
```python
if self.p.ib_connection and self.p.ib_connection.connected:
    positions = self.p.ib_connection.get_positions()
```

### From Trader (in start_trading loop):
```python
positions = self.ib_connection.get_positions()
```

## Configuration

The summary update interval can be controlled by modifying in `src/trader.py`:
```python
summary_interval = config.SIGNAL_CHECK_INTERVAL * 5  # Print every 5 signal checks
```

## Benefits

1. **Real-time Position Visibility** - See open positions during live trading
2. **Integrated Summary** - All important metrics in one place
3. **Risk Management** - Monitor current market exposure
4. **Performance Tracking** - Combine strategy metrics with account positions
5. **Troubleshooting** - Verify order execution at broker

## Files Modified

1. `src/trader.py` - Added position monitoring and live summary printing
2. `itrading/src/strategy.py` - Added broker position details to summary
3. `itrading/src/position_monitor.py` - NEW module for position management

## Notes

- Positions are fetched from Interactive Brokers API via ITradingConnection
- Summary handles connection errors gracefully
- Market values are calculated based on current position data
- Both forex and non-forex positions are displayed
- Summary prints only if connection is established and positions exist

