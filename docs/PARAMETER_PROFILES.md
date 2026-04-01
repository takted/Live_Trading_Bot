# Parameter Profiles (Live vs Paper)

The live runner now supports profile-based parameter files:

- `itrading/config/parameters_live.json` -> current production-style values
- `itrading/config/parameters_paper.json` -> permissive values for integration-cycle testing

Runner file: `itrading/scripts/run_forex_live.py`

## Selection Order

`load_params()` resolves config in this order:

1. `ITRADING_PARAMS_FILE` (explicit path)
2. `ITRADING_PARAMS_PROFILE` (`live` or `paper`)
3. Fallback to legacy `itrading/config/parameters.json`

## Example Usage (Windows cmd)

```bat
set ITRADING_PARAMS_PROFILE=paper
python itrading\scripts\run_forex_live.py
```

```bat
set ITRADING_PARAMS_PROFILE=live
python itrading\scripts\run_forex_live.py
```

```bat
set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live.json
python itrading\scripts\run_forex_live.py
```

## Notes

- `parameters_paper.json` is intentionally permissive to trigger trades and validate end-to-end lifecycle integration.
- Use paper profile only for testing lifecycle and order plumbing.
- Switch back to `live` profile for your normal strategy behavior.

