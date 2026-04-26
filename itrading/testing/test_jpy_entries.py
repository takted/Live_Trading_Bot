#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Script: JPY Pairs Entry Test
=================================
Simple script to test opening LONG positions on EURJPY and USDJPY
with Stop Loss and Take Profit, using coherent lot sizes.

Broker Specifications (from attached images):
---------------------------------------------
USDJPY:
  - Contract Size: 100,000 USD
  - Precision: 3 decimals
  - Spread: Floating
  - Min Volume: 0.01
  - Max Volume: 50
  - Volume Step: 0.01
  - Margin Currency: USD
  - Profit Currency: JPY

EURJPY:
  - Contract Size: 100,000 EUR
  - Precision: 3 decimals
  - Spread: Floating
  - Min Volume: 0.01
  - Max Volume: 50
  - Volume Step: 0.01
  - Margin Currency: EUR
  - Profit Currency: JPY

USAGE:
------
1. Ensure MT5 terminal is running and logged in
2. Run this script: python test_jpy_entries.py
3. Follow the prompts to test entries

DISCLAIMER: This is for DEMO TESTING ONLY!
"""

# This file previously tested JPY entries using MetaTrader5 (MT5).
# MT5 is no longer supported in this project. Please use IBKR test scripts instead.
print("This test is deprecated. Use IBKR-based test scripts.")
