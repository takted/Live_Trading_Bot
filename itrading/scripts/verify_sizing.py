import json

pairs = ['audusd','eurusd','gbpusd','eurjpy','usdjpy','usdchf','eurgbp','gbpjpy','nzdusd','usdcad']
print(f"{'Pair':<10} {'Cash':>8} {'max_frac':>10} {'risk%':>7} {'min_units':>11} {'Max_Val_USD':>14}")
print('-'*66)
for p in pairs:
    path = f'itrading/config/parameters_live_{p}.json'
    with open(path) as f:
        cfg = json.load(f)
    sp = cfg['STRATEGY_PARAMS']
    cash = cfg.get('STARTING_CASH', 5000)
    frac = sp.get('max_position_size_fraction', 'MISSING')
    risk = sp.get('risk_percent', 0.01)
    mins = sp.get('min_exchange_units', 2500)
    if isinstance(frac, float):
        max_val = f"${frac * cash:,.0f}"
        status = "OK" if frac == 1.0 else "LOW"
    else:
        max_val = "BLOCKED"
        status = "CRITICAL"
    print(f"{p.upper():<10} {cash:>8.0f} {str(frac):>10} {risk:>7.2f} {mins:>11} {max_val:>14}  [{status}]")

