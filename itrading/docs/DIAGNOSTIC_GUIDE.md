# Diagnostic Guide: Broker Position Display

## When You Don't See Broker Positions

Run the code and look for `[DEBUG]` messages in the output. They tell you exactly what's wrong:

### Scenario 1: `[DEBUG] ib_connection parameter not found in strategy params`
**Cause**: The `ib_connection` parameter wasn't passed to the strategy
**Fix**: Ensure strategies are created with `ib_connection=self.ib_connection`

### Scenario 2: `[DEBUG] ib_connection is None - not connected to broker`
**Cause**: `ib_connection` parameter exists but is None
**Why**: Normal in backtesting mode or when broker connection isn't initialized
**Fix**: Only relevant for live trading - provide actual broker connection

### Scenario 3: `[DEBUG] ib_connection.connected is False - broker not connected`
**Cause**: Broker connection object exists but isn't connected
**Why**: TWS/Gateway not running or connection failed
**Fix**:
1. Start TWS or Gateway
2. Enable API connections (API -> Settings -> Enable ActiveX and Socket Clients)
3. Check port is correct (default: 7497)
4. Verify firewall isn't blocking connection

### Scenario 4: `[DEBUG] No positions found in broker account`
**Cause**: Connected successfully but no open positions
**Why**: No trades opened in the account yet
**Fix**: Place a trade first, then positions will show

### Scenario 5: `[DEBUG] AttributeError fetching positions: ...`
**Cause**: Connection object missing expected methods/attributes
**Why**: Connection object is wrong type or incompletely initialized
**Fix**: Check ITradingConnection and ITradingWrapper are properly set up

### Scenario 6: `[DEBUG] Exception fetching broker positions: ...`
**Cause**: Unexpected error during position fetch
**Why**: Various - check the specific error message
**Fix**: Look at the exception details for clues

## Successful Scenarios

If you see this, everything is working:
```
=== BROKER POSITIONS (N total) ===
  SYMBOL/CURRENCY (TYPE): Qty=±value | AvgCost=price
  ...
============================================================
```

## Testing Checklist

- [ ] Is TWS/Gateway running?
- [ ] Is API enabled in TWS?
- [ ] Are there open positions in the account?
- [ ] Does the `[DEBUG]` output show which step fails?
- [ ] Can you connect to other IBKR APIs (like TWS)?
- [ ] Check firewall settings for port 7497?

## Next Steps

1. **Find the relevant `[DEBUG]` message** from the list above
2. **Apply the corresponding fix**
3. **Run again and verify** the positions now display

If no `[DEBUG]` messages appear at all:
- Check that the strategy's `stop()` method is being called
- Verify `ib_connection` parameter is actually being passed to strategy
- Look in logs for any errors during strategy initialization

