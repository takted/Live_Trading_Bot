from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

# This pulls the actual cash held in each currency
account_values = ib.accountSummary()

for entry in account_values:
    if entry.tag == 'CashBalance':
        print(f"Currency: {entry.currency}, Amount: {entry.value}")