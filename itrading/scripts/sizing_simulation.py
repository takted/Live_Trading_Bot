"""
Effective Sizing Simulation - shows expected order sizes after optimization
for each of the 10 currency pairs at current approximate market prices.
"""

pairs = {
    'EURUSD': dict(price=1.100, pip=0.0001, quote='USD', base='EUR', jpy=False, sl_mult=4.4, atr=0.00030),
    'AUDUSD': dict(price=0.640, pip=0.0001, quote='USD', base='AUD', jpy=False, sl_mult=4.4, atr=0.00030),
    'GBPUSD': dict(price=1.270, pip=0.0001, quote='USD', base='GBP', jpy=False, sl_mult=3.5, atr=0.00040),
    'EURJPY': dict(price=165.0, pip=0.01,   quote='JPY', base='EUR', jpy=True,  sl_mult=3.0, atr=0.035,  jpy_rate=150.0),
    'USDJPY': dict(price=150.0, pip=0.01,   quote='JPY', base='USD', jpy=True,  sl_mult=3.5, atr=0.060,  jpy_rate=150.0),
    'USDCHF': dict(price=0.910, pip=0.0001, quote='CHF', base='USD', jpy=False, sl_mult=2.5, atr=0.00025),
    'EURGBP': dict(price=0.855, pip=0.0001, quote='GBP', base='EUR', jpy=False, sl_mult=4.4, atr=0.00020, gbp_rate=1.27),
    'GBPJPY': dict(price=195.0, pip=0.01,   quote='JPY', base='GBP', jpy=True,  sl_mult=3.0, atr=0.060,  jpy_rate=150.0),
    'NZDUSD': dict(price=0.600, pip=0.0001, quote='USD', base='NZD', jpy=False, sl_mult=4.4, atr=0.00030),
    'USDCAD': dict(price=1.360, pip=0.0001, quote='CAD', base='USD', jpy=False, sl_mult=2.5, atr=0.00025),
}

ALLOCATION    = 5000.0
RISK_PCT      = 0.01
MAX_FRAC      = 1.0
MIN_UNITS     = 2500
MARGIN_PCT    = 3.33 / 100  # 3.33%

risk_usd = ALLOCATION * RISK_PCT  # = $50

print("=" * 100)
print("EFFECTIVE SIZING SIMULATION — After Optimization (max_position_size_fraction = 1.0)")
print(f"Allocation per pair: ${ALLOCATION:,.0f}  |  Risk target: ${risk_usd:.0f} (1%)  |  Min units: {MIN_UNITS:,}")
print("=" * 100)
print(f"{'Pair':<8} {'Price':>8} {'Unit_Val':>9} {'Max_Units':>11} {'Risk_Units':>12} "
      f"{'Final_Units':>13} {'Lots':>7} {'Pos_Value':>11} {'Margin':>9} {'Act_Risk':>10} {'Act_Risk%':>10}")
print("-" * 100)

for symbol, d in pairs.items():
    price = d['price']
    pip   = d['pip']
    atr   = d['atr']

    # --- Unit value in USD ---
    if d['base'] == 'USD':
        unit_val = 1.0                            # USD/USD → 1.0
    elif d['jpy']:
        unit_val = price / d.get('jpy_rate', 150.0)   # price in JPY, convert to USD
    elif 'gbp_rate' in d:
        unit_val = price * d['gbp_rate']          # EUR/GBP × GBP/USD
    else:
        unit_val = price                          # base/USD pairs

    # --- Quote-to-account rate (pip value per unit in USD) ---
    if d['quote'] == 'USD':
        q2a = 1.0
    elif d['jpy']:
        q2a = 1.0 / d.get('jpy_rate', 150.0)
    elif 'gbp_rate' in d:
        q2a = d['gbp_rate']
    else:
        q2a = 1.0

    pip_val_per_unit = pip * q2a                  # USD per pip per unit

    # --- Max units by value (position cap) ---
    max_pos_value = MAX_FRAC * ALLOCATION         # = $5,000
    max_units = int(max_pos_value / unit_val) if unit_val > 0 else 0

    # --- Risk-based units ---
    sl_pips  = (d['sl_mult'] * atr) / pip        # pips at risk
    risk_per_unit = sl_pips * pip_val_per_unit    # USD risked per unit
    risk_units = int(risk_usd / risk_per_unit) if risk_per_unit > 0 else 0

    # --- Final units ---
    if max_units < MIN_UNITS:
        final = 0
        status = "BLOCKED"
    else:
        final = min(risk_units, max_units)
        if final < MIN_UNITS:
            final = MIN_UNITS

    lots = final / 100_000
    pos_value  = final * unit_val
    margin     = pos_value * MARGIN_PCT
    act_risk   = final * risk_per_unit
    act_risk_p = act_risk / ALLOCATION * 100

    if final == 0:
        print(f"{symbol:<8} {price:>8.4f} {unit_val:>9.4f} {max_units:>11,} {risk_units:>12,} "
              f"{'BLOCKED':>13} {'---':>7} {'---':>11} {'---':>9} {'---':>10} {'---':>10}")
    else:
        print(f"{symbol:<8} {price:>8.4f} {unit_val:>9.4f} {max_units:>11,} {risk_units:>12,} "
              f"{final:>13,} {lots:>7.3f} ${pos_value:>10,.2f} ${margin:>8,.2f} ${act_risk:>9,.2f} {act_risk_p:>9.2f}%")

print("=" * 100)
print(f"\nLEGEND:")
print(f"  Unit_Val   = value of 1 base-currency unit in USD")
print(f"  Max_Units  = units allowed by $5,000 cap (max_position_size_fraction=1.0)")
print(f"  Risk_Units = units required to risk exactly $50 (1% of $5,000)")
print(f"  Final      = min(Risk_Units, Max_Units), floored at {MIN_UNITS:,} min")
print(f"  Lots       = Final / 100,000 (standard forex lot)")
print(f"  Pos_Value  = actual notional USD deployed")
print(f"  Act_Risk   = actual USD at risk (typically well below $50 since cap binds)")
print(f"  Act_Risk%  = actual risk as % of $5,000 allocation")
print(f"\nNOTE: Actual risk is low because the $5,000 position cap is the binding constraint,")
print(f"not the 1% risk target. This is correct and safe — the strategy uses ATR-based SL")
print(f"which gives wide stops in pip terms, requiring small lots for 1% risk.")
print(f"By capping at the full allocation, we maximise capital efficiency while staying within limits.")

