"""
Demeter runs of Maker's defense v1 / v2 / v3 scripts (branch maker-defense 5cec767) for
VALIDATION-2026-10-13-defense-v1-v3-demeter.md: decision hours, a second pool and parameter neighbours.

Each run gets its own copy of the maker-defense samples/strategy-example folder with text replacements only (each one
asserted), and runs with this branch's `demeter` on PYTHONPATH.

    python demeter_runs_v123.py <work_dir> [workers] [tag,tag,...]

Results are copied to the main checkout's result/validate_v123/demeter/<tag>/.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
MAIN = Path("/Users/dinohuang/Desktop/demeter-momentum")
OUT = MAIN / "samples/strategy-example/result/validate_v123/demeter"
PY = MAIN / ".venv-lab/bin/python"
REF = "5cec767"
SCRIPTS = {"v1": "gamma_maker_defense_ethusdc_v1.py", "v2": "gamma_maker_defense_ethusdc_v2.py",
           "v3": "gamma_maker_defense_ethusdc_v3.py"}
MAINNET = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
BASE = "0xd0b53d9277642d899df5c87a3966a349a798f224"
DATA = {MAINNET: MAIN / "samples/real-data" / MAINNET, BASE: MAIN / "samples/base-data" / BASE}
V1_STEPS = (0.05, 0.0833, 0.1167, 0.15)


def runs() -> dict:
    r = {"R0-v1-h0": dict(v="v1")}
    for v in SCRIPTS:
        for h in (4, 8, 12, 16, 20):
            r[f"R1-{v}-h{h}"] = dict(v=v, hour=h)
        r[f"R2-{v}-base"] = dict(v=v, pool=BASE, start=(2023, 12, 2))
    for m in (0.9, 1.1):
        r[f"R3-v1-x{m}"] = dict(v="v1", ladder=m)
    for m in (1.4, 1.6):
        r[f"R3-v2-x{m}"] = dict(v="v2", ladder=m)
    for on in (0.35, 0.45):
        r[f"R3-v3-div{on}"] = dict(v="v3", div_on=on)
    return r


def sub(text: str, pattern: str, repl: str, count: int = 0, min_n: int = 1, flags=0) -> str:
    new, n = re.subn(pattern, repl, text, count=count, flags=flags)
    assert n >= min_n, f"pattern not found: {pattern!r}"
    return new


def patch(text: str, v: str, hour: int = 0, pool: str = MAINNET, start=(2021, 5, 6), ladder: float | None = None,
          div_on: float | None = None) -> str:
    y, mo, d = start
    entry = f"\n        (datetime({y}, {mo}, {d}, {hour}, 0, 0), date({y}, {mo}, {d}), date(2026, 8, 31), \"\", []),"
    text = sub(text, r"(date_ranges: List\[.*?\] = \[).*?(\n    \]\n)", lambda m: m.group(1) + entry + m.group(2),
               count=1, flags=re.S)
    text = sub(text, r"\n    _compound = True\n", "\n    _compound = False\n", min_n=0)
    if hour:
        text = sub(text, r'BINANCE_CSV = Path\(__file__\)\.with_name\("binance_ethusdt_1d\.csv"\)',
                   f'BINANCE_CSV = Path(__file__).with_name("binance_ethusdt_1d_h{hour}.csv")')
        text = sub(text, r"PeriodTrigger\(time_delta=([^\n]*?), do=self\.(rescale_work|follow_work|compound_work|log_fees)\)",
                   lambda m: f"PeriodTrigger(time_delta={m.group(1)}, do=self.{m.group(2)}, pending=timedelta(hours={hour}))",
                   min_n=3)
    if pool != MAINNET:
        text = sub(text, r"\n    token0, token1 = usdc, eth\n    contract_address, fee, chain_name = \"" + MAINNET + "\"",
                   "\n    token0, token1 = eth, usdc\n    contract_address, fee, chain_name = \"" + pool + "\"")
    if ladder is not None:
        steps = V1_STEPS if v == "v1" else tuple(s * 1.5 for s in V1_STEPS)
        base = 1.0 if v == "v1" else 1.5
        st = ", ".join(f"({i + 1}, {1 + s * ladder / base:.5f})" for i, s in enumerate(steps))
        text = sub(text, r"\nREFILL_STAGES = \(\(1, [^\n]*", f"\nREFILL_STAGES = ({st})  # neighbour run x{ladder}", count=1)
    if div_on is not None:
        text = sub(text, r"\nDIVERGENCE_ON, DIVERGENCE_OFF = 0\.40, 0\.20", f"\nDIVERGENCE_ON, DIVERGENCE_OFF = {div_on}, 0.20")
    if ladder is not None or div_on is not None:  # Maker's self-check asserts the default constants
        text = sub(text, r"\n    _self_check\(\)\n", "\n    pass  # _self_check() skipped: it asserts the default parameters\n")
    if "netvalue_" not in text:  # v1: same minute net-value export as v2 / v3
        text = sub(text, r'(\n        benchmark_series = actuator\.account_status_df\["price"\]\[price_name\]\n)',
                   lambda m: m.group(1) + '        pd.DataFrame({"net_value": actuator.account_status_df["net_value"], '
                   '"price": benchmark_series}).to_csv(\n            f"{params.folder}/netvalue_{params.report_name}.csv")\n',
                   count=1)
    return text


def hour_csv(hour: int, dst: Path):
    """Binance closes at hour:00, row date D = close at D+1 hour:00 (the convention of binance_ethusdt_1d.csv for 00:00)."""
    s = pd.read_csv(MAIN / "samples/binance_ethusdt_1h.csv", parse_dates=["open_time"]).set_index("open_time")["close"]
    s.index = s.index + pd.Timedelta(hours=1)
    s = s[s.index.hour == hour]
    out = pd.DataFrame({"date": (s.index - pd.Timedelta(days=1)).normalize(), "close": s.to_numpy()})
    out = out.drop_duplicates("date").set_index("date").asfreq("1D").ffill().reset_index()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(dst, index=False)


def prepare(work: Path, tag: str, spec: dict) -> Path:
    src = work / "_src"
    if not src.exists():
        blob = subprocess.run(["git", "-C", str(REPO), "archive", REF, "samples/strategy-example"],
                              check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(blob)).extractall(src)
    d = work / tag / "samples"
    if d.exists():
        shutil.rmtree(d)
    se = d / "strategy-example"
    shutil.copytree(src / "samples/strategy-example", se, ignore=shutil.ignore_patterns("result", "*.md", "*.png"))
    (d / "real-data").mkdir()
    pool = spec.get("pool", MAINNET)
    os.symlink(DATA[pool], d / "real-data" / pool)
    if spec.get("hour"):
        hour_csv(spec["hour"], se / f"binance_ethusdt_1d_h{spec['hour']}.csv")
    script = se / SCRIPTS[spec["v"]]
    script.write_text(patch(script.read_text(), **spec))
    return script


def run(work: Path, tag: str, spec: dict) -> str:
    script = prepare(work, tag, spec)
    log = work / f"{tag}.log"
    env = dict(os.environ, PYTHONPATH=str(MAIN))  # main checkout: same demeter as this branch, survives worktree removal
    with open(log, "w") as f:
        rc = subprocess.run([str(PY), script.name], cwd=script.parent, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    res = script.parent / "result"
    dst = OUT / tag
    if dst.exists():
        shutil.rmtree(dst)
    if res.exists():
        shutil.copytree(res, dst)
    shutil.copy(log, OUT / f"{tag}.log")
    return f"{tag} rc={rc}"


if __name__ == "__main__":
    work = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    todo = runs()
    if len(sys.argv) > 3:
        todo = {t: todo[t] for t in sys.argv[3].split(",")}
    work.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        for msg in ex.map(lambda kv: run(work, *kv), todo.items()):
            print(msg, flush=True)
