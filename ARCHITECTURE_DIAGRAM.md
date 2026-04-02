# ITrading Summary - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LIVE TRADING BOT                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐         ┌──────────────────────┐     │
│  │   ITradingTrader     │         │  ITradingConnection  │     │
│  │  (Main Entry Point)  │◄────────┤   (Broker Link)      │     │
│  │                      │         │                      │     │
│  │ - initialize()       │         │ - connect()          │     │
│  │ - start_trading()    │         │ - get_positions()    │     │
│  │ - generate_signal()  │         │ - account_info       │     │
│  │ - process_symbol()   │         │ - client (wrapper)   │     │
│  │ - print_broker_      │         │                      │     │
│  │   summary()          │         └──────────────────────┘     │
│  │ - stop()             │                   ▲                   │
│  └──────────────────────┘                   │                   │
│         │                                   │                   │
│         │ creates & uses                    │ communicates      │
│         ▼                                   ▼                   │
│  ┌──────────────────────┐         ┌──────────────────────┐     │
│  │ BrokerPosition       │         │  Interactive Brokers │     │
│  │   Monitor            │         │     TWS/Gateway      │     │
│  │                      │         │                      │     │
│  │ - positions[]        │         │ - Account data       │     │
│  │ - update_positions() │         │ - Position data      │     │
│  │ - format_summary()   │         │ - Market data        │     │
│  │ - calc_market_value()│         │ - Order data         │     │
│  │ - calc_unrealized_   │         │                      │     │
│  │   pnl()              │         └──────────────────────┘     │
│  └──────────────────────┘                                       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              BACKTRADER STRATEGIES                        │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────┐  │  │
│  │  │ ITTrading      │  │ ITTrading      │  │ ITTrading  │  │  │
│  │  │ StrategyAUD    │  │ StrategyEUR    │  │ StrategyGBP│  │  │
│  │  │                │  │                │  │            │  │  │
│  │  │ - params with  │  │ - params with  │  │ - params   │  │  │
│  │  │   ib_conn      │  │   ib_conn      │  │   with     │  │  │
│  │  │ - stop()       │  │ - stop()       │  │   ib_conn  │  │  │
│  │  │   prints       │  │   prints       │  │ - stop()   │  │  │
│  │  │   summary      │  │   summary      │  │   prints   │  │  │
│  │  └────────────────┘  └────────────────┘  └────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow - Live Trading Loop

```
START TRADING LOOP
       │
       ├─► Process Symbol 1
       │    └─► generate_signal()
       │         └─► Strategy.stop() prints ITRADING SUMMARY + positions
       │
       ├─► Process Symbol 2
       │    └─► generate_signal()
       │         └─► Strategy.stop() prints ITRADING SUMMARY + positions
       │
       ├─► Process Symbol N
       │    └─► generate_signal()
       │         └─► Strategy.stop() prints ITRADING SUMMARY + positions
       │
       ├─► Check Time Elapsed
       │    └─ If summary_interval exceeded:
       │         └─► print_broker_summary()
       │             └─► get_positions() from broker
       │                 └─► display live positions
       │
       ├─► Sleep SIGNAL_CHECK_INTERVAL
       │
       └─► Loop Back to START
```

## Summary Output Structure

```
┌─────────────────────────────────────────────────────────────┐
│  STRATEGY STOP() - Printed when strategy finishes          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  === ITRADING SUMMARY ===                                  │
│  Trades: 5 Wins: 3 Losses: 2 WinRate: 60.00% PF: 2.50    │
│  Final Value: 5,250.00 | Total PnL: +250.00              │
│                                                             │
│  === BROKER POSITIONS (2 total) ===                        │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ - EURUSD/USD (FOREX)                               │  │
│  │   Qty=+0.05 | AvgCost=1.08500                      │  │
│  │ - GBPUSD/USD (FOREX)                               │  │
│  │   Qty=-0.03 | AvgCost=1.27850                      │  │
│  └─────────────────────────────────────────────────────┘  │
│  ============================================================
│                                                             │
│  === ENTRY SIGNAL DEBUG STATS ===                          │
│  Total Entry Signals: 10                                   │
│  Block Rate: 60.0%                                         │
│  Success Rate: 40.0%                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  TRADER LOOP - Printed periodically during trading        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ================================================================================
│  === LIVE BROKER SUMMARY ===                              │
│  ================================================================================
│  Timestamp: 2026-04-02 14:30:45                           │
│                                                             │
│  Open Positions: 2                                          │
│                                                             │
│    EURUSD/USD (FOREX)                                      │
│      Quantity: +0.05 units                                 │
│      Average Cost: 1.08500                                 │
│                                                             │
│    GBPUSD/USD (FOREX)                                      │
│      Quantity: -0.03 units                                 │
│      Average Cost: 1.27850                                 │
│                                                             │
│  ================================================================================
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Component Interaction - Sequence Diagram

```
ITradingTrader        BrokerPosition    ITradingConnection    Strategy
      │                  Monitor               │                │
      │                    │                   │                │
      ├─initialize()────────┼───────────────────┼────────────────┤
      │   │create            │                   │                │
      │   └───────────────────┘                   │                │
      │                        create ib_conn     │                │
      │                              │            │                │
      │                              └────────────┤                │
      │                                           │                │
      ├─start_trading()───────────────────────────┼────────────────┤
      │                                           │                │
      ├─generate_signal()─────────────────────────┼────────────────┤
      │   pass ib_connection as param             │                │
      │                                           │                │
      │                                           │                │
      │                                           ├─Strategy()     │
      │                                           │  params with   │
      │                                           │  ib_connection │
      │                                           │                │
      │                                           │ ... trading... │
      │                                           │                │
      │                                           ├─stop()         │
      │                                           │  get_positions()
      │                                           ├────────────────┤
      │                                           │ get_positions() │
      │                                           ├─ API call ────►│ IBKR
      │                                           │◄─ positions ───│
      │                                           │                │
      │                                           ├─ print summary with positions
      │                                           │
      │
      ├─ Check time elapsed
      │  │
      │  ├─print_broker_summary()─────────────────┼────────────────┤
      │  │  get_positions()                        │                │
      │  │  ├─────────────────────────────────────►│                │
      │  │  │ get_positions()                      │                │
      │  │  │ ├──────────────────────────────────►│ IBKR          │
      │  │  │ │◄─────────────────────────────────│◄──────────────┤
      │  │  │◄─────────────────────────────────────│                │
      │  │  │                                      │                │
      │  │  update_positions()                    │                │
      │  │  └──────────┐                          │                │
      │  │  │positions │                          │                │
      │  │  └──────────►│                          │                │
      │  │              │                          │                │
      │  └─ print formatted summary with positions│                │
      │                                           │                │
      └─ Loop ────────────────────────────────────┴────────────────┘
```

## Data Model - Position Object

```
Position (from IBKR)
├── account: str                    (e.g., "DU123456")
├── symbol: str                     (e.g., "EUR" for EURUSD)
├── secType: str                    (e.g., "FOREX" or "STK")
├── currency: str                   (e.g., "USD" for quote currency)
├── position: float                 (e.g., 0.05 or -0.03)
└── avgCost: float                  (e.g., 1.08500)

Position Summary (computed)
├── market_value: float            (computed from position * current_price)
├── unrealized_pnl: float          (computed from market_value - entry_value)
└── pnl_percent: float             (computed as unrealized_pnl / entry_value)
```

## Integration Points

```
╔═══════════════════════════════════════════════════════════╗
║           INTEGRATION POINTS FOR EXTENSIONS               ║
╚═══════════════════════════════════════════════════════════╝

1. Market Value Display
   ├─ Fetch current prices from ITradingWrapper
   └─ Calculate market_value in position_monitor

2. Margin Monitoring
   ├─ Use account_info from ITradingConnection
   └─ Display margin utilization in summary

3. Export Functionality
   ├─ Serialize summary to CSV/JSON/HTML
   └─ Store in reports directory

4. Real-time Charts
   ├─ Cache position history
   └─ Plot using matplotlib or Plotly

5. Alert System
   ├─ Monitor for position changes
   └─ Send notifications (email/webhook)

6. Multi-Account Support
   ├─ Create multiple connections
   └─ Display combined summary
```

## Call Stack - Summary Generation

```
trader.print_broker_summary()
│
├─ self.ib_connection.get_positions()
│  │
│  └─ self.client.positions[]  ◄─── from IBKR API
│
├─ self.position_monitor.update_positions(positions)
│
├─ loop through positions:
│  │
│  └─ format position data
│     ├─ symbol/currency pair
│     ├─ security type
│     ├─ quantity
│     └─ average cost
│
└─ print formatted summary

strategy.stop()
│
├─ self.p.ib_connection.get_positions()
│  │
│  └─ self.client.positions[]  ◄─── from IBKR API
│
├─ loop through positions:
│  │
│  └─ format position data
│
└─ print in ITRADING SUMMARY section
```

## Key Data Flows

### Flow 1: Initial Connection
```
main()
  └─► ITradingTrader()
      └─► initialize()
          ├─► ITradingConnection.connect()
          │   └─► ITradingWrapper (connection established)
          └─► BrokerPositionMonitor() (ready to use)
```

### Flow 2: Strategy with Connection
```
generate_signal()
  └─► cerebro.addstrategy(
        strategy_class,
        instrument_name=symbol,
        ib_connection=self.ib_connection  ◄─── PASSED HERE
      )
  └─► strategy instantiated with ib_connection in params
      └─► strategy.stop() can access self.p.ib_connection
```

### Flow 3: Live Summary During Trading
```
start_trading()
  └─► while running:
      ├─► process_symbol()
      │   └─► generate_signal()
      │       └─► strategy with positions printed
      │
      ├─► if time_elapsed > summary_interval:
      │   └─► print_broker_summary()
      │       └─► positions from broker
      │
      └─► sleep(SIGNAL_CHECK_INTERVAL)
```

