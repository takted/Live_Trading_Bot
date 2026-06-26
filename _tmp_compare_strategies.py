import ast
import pathlib

base = pathlib.Path(r"C:\PyCharmProjects\Live_Trading_Bot\strategies")
files = {
    "AUDUSD": base / "itrading_strategy_audusd.py",
    "EURUSD": base / "itrading_strategy_eurusd.py",
}


def analyze(path: pathlib.Path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    target = None
    for cls in classes:
        if cls.name.startswith("ITradingStrategy"):
            target = cls
            break
    if target is None:
        raise RuntimeError(f"No strategy class found in {path}")

    info = {
        "class": target.name,
        "class_lineno": target.lineno,
        "methods": {},
        "params": {},
        "sell_calls": 0,
        "buy_calls": 0,
    }

    for node in target.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == "params"
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "dict"
                ):
                    for kw in node.value.keywords:
                        if kw.arg is None:
                            continue
                        try:
                            val = ast.literal_eval(kw.value)
                        except Exception:
                            val = ast.unparse(kw.value)
                        info["params"][kw.arg] = val

        if isinstance(node, ast.FunctionDef):
            info["methods"][node.name] = node.lineno
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr == "sell":
                        info["sell_calls"] += 1
                    if sub.func.attr == "buy":
                        info["buy_calls"] += 1

    return info


res = {name: analyze(path) for name, path in files.items()}
aud = res["AUDUSD"]
eur = res["EURUSD"]

print("AUD class", aud["class"], "line", aud["class_lineno"])
print("EUR class", eur["class"], "line", eur["class_lineno"])

ak = set(aud["params"])
ek = set(eur["params"])
print("PARAM_COUNT", len(ak), len(ek))
print("ONLY_AUD", sorted(ak - ek))
print("ONLY_EUR", sorted(ek - ak))

common = sorted(ak & ek)
changed = []
for key in common:
    if aud["params"][key] != eur["params"][key]:
        changed.append((key, aud["params"][key], eur["params"][key]))
print("CHANGED_COMMON_COUNT", len(changed))
for key, av, ev in changed:
    print(f"PARAM_DIFF {key}: AUD={av!r} EUR={ev!r}")

am = set(aud["methods"])
em = set(eur["methods"])
print("METHOD_COUNT", len(am), len(em))
print("ONLY_METHOD_AUD", sorted(am - em))
print("ONLY_METHOD_EUR", sorted(em - am))

print("BUY_SELL_CALLS AUD", aud["buy_calls"], aud["sell_calls"])
print("BUY_SELL_CALLS EUR", eur["buy_calls"], eur["sell_calls"])

