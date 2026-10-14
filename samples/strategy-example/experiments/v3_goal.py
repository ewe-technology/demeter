"""
/goal 2026-10-14: one-element variants of Maker's defense v3 (`gamma_maker_defense_ethusdc_v3.py`, maker-defense 5cec767)
on mainnet ETH/USDC 0.05% `0x88e6` and WBTC/WETH 0.05% `0x4585`, in-sample up to 2024-12-31, out-of-sample after
(EXP-176, `EXP-176-v3-one-element.md`).

Each variant is v3 with ONE element deleted, added or replaced, written as text replacements on Maker's script (each one
asserted). A run gets its own copy of the maker-defense samples/strategy-example folder and runs on the main checkout's
Rust engine (.venv-rs, no PYTHONPATH). IS and OOS are separate runs, each starting from the full book; the signal engine
is warmed up on Binance daily closes from 2017 either way.

    python v3_goal.py is|oos <pool:eth|btc> <variant,variant,...|all> [workers]
    python v3_goal.py table                      # every finished run -> result/v3_goal/runs.csv (+ judged columns)

WBTC/WETH: v3 runs unchanged with ETH as the base token and WBTC in USDC's place (quote, 2 WBTC book, results in BTC),
signal = Binance ETHBTC daily closes. Binance files: Maker's ETHUSDT (to 2026-08-31) and ETHBTC (to 2025-12-31), extended
to 2026-09-17 from samples/binance_daily_closes.csv (ETHUSDT as is, ETHBTC = ETHUSDT / BTCUSDT).
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
MAIN = Path("/Users/dinohuang/Desktop/demeter-momentum")
OUT = Path(os.environ.get("OUT", MAIN / "samples/strategy-example/result/v3_goal"))
WORK = Path(os.environ.get("WORK", OUT / "_work"))
PY = MAIN / ".venv-rs/bin/python"
REF = "5cec767"
SCRIPT = "gamma_maker_defense_ethusdc_v3.py"
END = (2026, 9, 17)   # last day of pool minute data for both pools
POOLS = {
    "eth": dict(address="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", data=MAIN / "samples/real-data",
                is_start=(2021, 5, 6), csv="binance_ethusdt_ext.csv"),
    "btc": dict(address="0x4585fe77225b41b697c938b018e2ac67ac5a20c0", data=MAIN / "samples/holdout-data",
                is_start=(2021, 11, 2), csv="binance_ethbtc_ext.csv"),
}
SEGMENTS = {"is": lambda p: (p["is_start"], (2024, 12, 31)), "oos": lambda p: ((2025, 1, 1), END)}

# ---- variants: name -> (element of v3, what it becomes, [(pattern, replacement, expected count)]) -------------------
# pattern is a plain string (re.escape'd) unless it starts with "re:"
A = "            if self.armed and close < ema:                      # 1 EMA exit (spec: low resets even if empty)"
STOP = "            if self.stage > 0 and close < self.centre * LOWER_STOP:        # 3 lower stop"
UPPER = "            elif self.stage > 0 and close > self.centre * UPPER_REBUILD:   # 4 upper rebuild, same size"
FIELDS = "    confirm: int = 0\n    started: bool = False\n"
STEP_CALL = "                a.step(float(c), float(emas[a.span][day]), float(emas[EMA_SPAN][day]))"
ADV = "                if advance:\n                    self.stage, lp = nxt, nxt / 4 * assets"
FMEAN = "        fractions.append(sum(a.deployed for a in accounts) / len(accounts))"
LOW_EXIT = ("                if self.signal_deploy and not self.force_rebuild:  # spec rule 2: everything to quote, follow F re-enters\n"
            "                    self.build_fraction = ZERO")
UP_EXIT = ("                    self.build_fraction = ZERO if diverged_for(self.daily_ema, row_data.timestamp) \\\n"
           "                        else self.lp_fraction(lp_market, current_price)")
SHARE = 'SHARE_ABOVE_EMA, SHARE_BELOW_EMA = Decimal("0.7"), Decimal("0.5")'
FP = 'frame["Fp"] = frame["F"].where(frame["diverged"] == 0, 0.0)'

VARIANTS: dict[str, tuple[str, str, list]] = {
    "v3": ("-", "v3 unchanged", []),
    # signal 1: EMA exit
    "exit2d": ("1 EMA exit", "needs two consecutive closes below the account's EMA",
               [(FIELDS, FIELDS + "    below: int = 0\n", 1),
                (A, "            self.below = self.below + 1 if close < ema else 0\n"
                    "            if self.armed and self.below >= 2:  # 1 EMA exit after two closes below", 1)]),
    "exitslope": ("1 EMA exit", "also needs the EMA below its value 20 days earlier (falling EMA)",
                  [(FIELDS, FIELDS + "    ema_prev: float = float(\"inf\")\n", 1),
                   (STEP_CALL, "                a.ema_prev = float(emas[a.span].iloc[max(0, i - 20)])\n" + STEP_CALL, 1),
                   (A, "            if self.armed and close < ema and ema < self.ema_prev:  # 1 EMA exit, falling EMA only", 1)]),
    "sma": ("moving-average type", "SMA instead of EMA for the four accounts and EMA100",
            [("    emas = {n: close.ewm(span=n, adjust=False).mean() for n in EMA_SPANS}",
              "    emas = {n: close.rolling(n, min_periods=1).mean() for n in EMA_SPANS}", 1)]),
    # signal 2: re-arm
    "norearm": ("2 re-arm", "deleted: any close below the EMA empties an account that holds a ladder (refill only sticks above the EMA)",
                [(A, "            if (self.armed or self.stage > 0) and close < ema:  # 1 EMA exit, no re-arm gate", 1)]),
    # signal 3: lower stop
    "nostop": ("3 lower stop", "deleted", [(STOP, "            if False:  # 3 lower stop deleted", 1)]),
    # signal 4: virtual upper rebuild
    "noupper": ("4 virtual upper rebuild", "deleted (virtual ladder keeps its centre)",
                [(UPPER, "            elif False:  # 4 upper rebuild deleted", 1)]),
    # signal 5: staged refill
    "confirm1": ("5 refill stage-1 confirmation", "1 close instead of 3",
                 [("REFILL_CONFIRM_DAYS = 3 ", "REFILL_CONFIRM_DAYS = 1 ", 1)]),
    "ladderv1": ("5 refill ladder", "v1 steps +5 / 8.33 / 11.67 / 15 % instead of +7.5 / 12.5 / 17.5 / 22.5 %",
                 [("REFILL_STAGES = ((1, 1.075), (2, 1.125), (3, 1.175), (4, 1.225))",
                   "REFILL_STAGES = ((1, 1.05), (2, 1.0833), (3, 1.1167), (4, 1.15))", 1)]),
    "multistage": ("5 refill pace", "may climb several stages in one day (no one-stage-a-day limit)",
                   [(ADV, "                if advance:\n                    while nxt < 4 and close >= self.low * REFILL_STAGES[nxt][1]:\n"
                          "                        nxt += 1\n                    self.stage, lp = nxt, nxt / 4 * assets", 1)]),
    "refillabove": ("5 refill gate", "a refill stage advances only on a close above the account's EMA",
                    [(ADV, ADV.replace("if advance:", "if advance and close > ema:"), 1)]),
    # signal 6: real ETH share
    "share50": ("6 real ETH share", "fixed 50% (no EMA100 switch)", [(SHARE, 'SHARE_ABOVE_EMA, SHARE_BELOW_EMA = Decimal("0.5"), Decimal("0.5")', 1)]),
    "share70": ("6 real ETH share", "fixed 70% (no EMA100 switch)", [(SHARE, 'SHARE_ABOVE_EMA, SHARE_BELOW_EMA = Decimal("0.7"), Decimal("0.7")', 1)]),
    "share3": ("6 real ETH share", "three levels like the virtual ladder: 25% below EMA100 x 0.95, else 70% / 50%",
               [('    share = SHARE_ABOVE_EMA if row["close"] > row["ema"] else SHARE_BELOW_EMA',
                 '    share = Decimal("0.25") if row["close"] < row["ema"] * WEAK_EMA_FACTOR else '
                 '(SHARE_ABOVE_EMA if row["close"] > row["ema"] else SHARE_BELOW_EMA)', 1)]),
    # signal 7: follow
    "follow25": ("7 follow threshold", "25% instead of 12.5%", [('FOLLOW_THRESHOLD = Decimal("0.125")', 'FOLLOW_THRESHOLD = Decimal("0.25")', 1)]),
    "followplain": ("7 follow extra conditions", "deleted (full / empty top-ups; only |F - current| >= 12.5%)",
                    [('FOLLOW_FULL_F, FOLLOW_FULL_GAP, FOLLOW_EMPTY_TOL = Decimal("0.999"), Decimal("0.01"), Decimal("0")',
                      'FOLLOW_FULL_F, FOLLOW_FULL_GAP, FOLLOW_EMPTY_TOL = Decimal("2"), Decimal("0.01"), Decimal("1")', 1)]),
    # signal 8: real range exit
    "lowrecentre": ("8 real lower range exit", "recentre at the current LP share instead of going all to USDC",
                    [(LOW_EXIT, LOW_EXIT.replace("self.build_fraction = ZERO",
                                                 "self.build_fraction = ZERO if diverged_for(self.daily_ema, row_data.timestamp) "
                                                 "else self.lp_fraction(lp_market, current_price)"), 1)]),
    "uptarget": ("8 real upper range exit", "rebuild at the target F' instead of the current LP share",
                 [(UP_EXIT, UP_EXIT.replace("self.lp_fraction(lp_market, current_price)",
                                            "target_fraction_for(self.daily_ema, row_data.timestamp)"), 1)]),
    "hourly": ("8 real range-exit check", "hourly instead of once a day",
               [("    _rescale_frequencies = [RescaleFrequency.daily]", "    _rescale_frequencies = [RescaleFrequency.hourly]", 1)]),
    "width30": ("real LP width", "+-30% instead of +-20%", [('for r in ("0.20",)]', 'for r in ("0.30",)]', 1)]),
    "width15": ("real LP width", "+-15% instead of +-20%", [('for r in ("0.20",)]', 'for r in ("0.15",)]', 1)]),
    "uniform": ("real LP shape", "uniform weights instead of the inverted gaussian valley",
                [('    _shapes: List[str] = ["inverted_gaussian_spec_price"]', '    _shapes: List[str] = ["uniform_price"]', 1)]),
    "gaussian": ("real LP shape", "gaussian (peak at the centre) instead of the inverted gaussian valley",
                 [('    _shapes: List[str] = ["inverted_gaussian_spec_price"]', '    _shapes: List[str] = ["gaussian_price"]', 1)]),
    # signal 9: virtual weak share
    "noweak": ("9 virtual weak share", "deleted (no 25% level below EMA100 x 0.95)",
               [("VIRTUAL_SHARE_WEAK, WEAK_EMA_FACTOR = 0.25, 0.95", "VIRTUAL_SHARE_WEAK, WEAK_EMA_FACTOR = 0.5, 0.95", 1)]),
    # signal 10: divergence
    "nodiv": ("10 divergence flag", "deleted (= v2)", [("\nDIVERGENCE_RULE = True\n", "\nDIVERGENCE_RULE = False\n", 1)]),
    "divhalf": ("10 divergence action", "flag ON halves F instead of F' = 0",
                [(FP, 'frame["Fp"] = frame["F"].where(frame["diverged"] == 0, frame["F"] / 2)', 1),
                 (UP_EXIT, UP_EXIT.replace("self.build_fraction = ZERO if", "self.build_fraction = target_fraction_for(self.daily_ema, row_data.timestamp) if"), 1)]),
    # F aggregation
    "fstage": ("F measure", "stage / 4 instead of virtual LP value share", [("\nF_BY_VALUE = True\n", "\nF_BY_VALUE = False\n", 1)]),
    "fmin": ("F aggregation", "minimum of the four accounts instead of the mean",
             [(FMEAN, "        fractions.append(min(a.deployed for a in accounts))", 1)]),
    "fmax": ("F aggregation", "maximum of the four accounts instead of the mean",
             [(FMEAN, "        fractions.append(max(a.deployed for a in accounts))", 1)]),
}


def sub(text: str, pattern: str, repl: str, n_expected: int) -> str:
    if pattern.startswith("re:"):
        new, n = re.subn(pattern[3:], repl, text)
    else:
        n = text.count(pattern)
        new = text.replace(pattern, repl)
    assert n == n_expected, f"pattern found {n} times, expected {n_expected}: {pattern[:80]!r}"
    return new


def patch(text: str, pool: str, seg: str, variant: str) -> str:
    p = POOLS[pool]
    (y, mo, d), (ye, me, de) = SEGMENTS[seg](p)
    entry = f"\n        (datetime({y}, {mo}, {d}, 0, 0, 0), date({y}, {mo}, {d}), date({ye}, {me}, {de}), \"\", []),"
    new, n = re.subn(r"(date_ranges: List\[.*?\] = \[).*?(\n    \]\n)", lambda m: m.group(1) + entry + m.group(2),
                     text, count=1, flags=re.S)
    assert n == 1
    text = sub(new, "\n    _self_check()\n", "\n    pass  # _self_check() skipped: it asserts the default parameters\n", 1)
    text = sub(text, 'BINANCE_CSV = Path(__file__).with_name("binance_ethusdt_1d.csv")',
               f'BINANCE_CSV = Path(__file__).with_name("{p["csv"]}")', 1)
    if pool == "btc":
        text = sub(text, "    base_token, quote_token, init_quote = eth, usdc, Decimal(100000)  #  USDC",
                   "    base_token, quote_token, init_quote = eth, btc, Decimal(2)  # v3_goal: WBTC in USDC's place", 1)
        text = sub(text, '\n    token0, token1 = usdc, eth\n    contract_address, fee, chain_name = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"',
                   f'\n    token0, token1 = btc, eth\n    contract_address, fee, chain_name = "{p["address"]}"', 1)
        text = sub(text, '    load_btc_price = quote_token.name == "btc"', "    load_btc_price = False  # v3_goal: results in BTC", 1)
    for pattern, repl, n_expected in VARIANTS[variant][2]:
        text = sub(text, pattern, repl, n_expected)
    return text


def binance_files(dst: Path):
    """Maker's daily closes extended to END from samples/binance_daily_closes.csv (same date convention)."""
    long = pd.read_csv(MAIN / "samples/binance_daily_closes.csv", parse_dates=["date"]).set_index("date")
    end = pd.Timestamp(*END)
    for name, src, ext in (("binance_ethusdt_ext.csv", "binance_ethusdt_1d.csv", long["ETHUSDT"]),
                           ("binance_ethbtc_ext.csv", "binance_ethbtc_1d.csv", long["ETHUSDT"] / long["BTCUSDT"])):
        s = pd.read_csv(dst / src, parse_dates=["date"]).set_index("date")["close"]
        add = ext.loc[s.index[-1] + pd.Timedelta(days=1):end]
        out = pd.concat([s, add]).rename("close")
        assert out.index[-1] == end and (out.index[1:] - out.index[:-1]).max() == pd.Timedelta(days=1)
        out.rename_axis("date").reset_index().assign(date=lambda f: f["date"].dt.strftime("%Y-%m-%d")).to_csv(dst / name, index=False)


def source() -> Path:
    src = WORK / "_src"
    if not src.exists():
        blob = subprocess.run(["git", "-C", str(REPO), "archive", REF, "samples/strategy-example"],
                              check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(blob)).extractall(src)
        binance_files(src / "samples/strategy-example")
    return src


def tag_of(pool: str, seg: str, variant: str) -> str:
    return f"{pool}-{seg}-{variant}"


def run(pool: str, seg: str, variant: str) -> str:
    tag = tag_of(pool, seg, variant)
    d = WORK / tag / "samples"
    if d.parent.exists():
        shutil.rmtree(d.parent)
    se = d / "strategy-example"
    shutil.copytree(source() / "samples/strategy-example", se, ignore=shutil.ignore_patterns("result", "*.md", "*.png"))
    (d / "real-data").mkdir()
    addr = POOLS[pool]["address"]
    os.symlink(POOLS[pool]["data"] / addr, d / "real-data" / addr)
    script = se / SCRIPT
    script.write_text(patch(script.read_text(), pool, seg, variant))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ENGINE", "OUT", "WORK")}
    dst = OUT / tag
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    with open(dst / "run.log", "w") as f:
        rc = subprocess.run([str(PY), script.name], cwd=se, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    nv = list((se / "result").rglob("netvalue_*.csv"))
    for f in nv + list((se / "result").rglob("apr_*.csv")):
        shutil.copy(f, dst / f.name)
    shutil.rmtree(d.parent)
    if rc != 0 or not nv:
        return f"{tag} FAILED rc={rc}"
    m = metrics(pool, seg, variant)
    return f"{tag} ret {m['ret']:+.1%} cagr {m['cagr']:.2%} dd {m['mdd']:.1%} calmar {m['calmar']:.3f}"


def metrics(pool: str, seg: str, variant: str) -> dict:
    """Net value in the quote token (USDC / WBTC), per minute: total return, CAGR, max drawdown, Calmar, rebuilds."""
    tag = tag_of(pool, seg, variant)
    f = OUT / tag / "metrics.json"
    if f.exists():
        return json.loads(f.read_text())
    nvf = next((OUT / tag).glob("netvalue_*.csv"))
    nv = pd.read_csv(nvf, index_col=0, parse_dates=True)["net_value"].astype(float)
    years = (nv.index[-1] - nv.index[0]).total_seconds() / (365.25 * 86400)
    ret = nv.iloc[-1] / nv.iloc[0] - 1
    cagr = (1 + ret) ** (1 / years) - 1
    mdd = float((nv / nv.cummax() - 1).min())
    log = (OUT / tag / "run.log").read_text()
    follow = re.search(r"follow rebuilds: (\d+)", log)
    m = dict(pool=pool, seg=seg, variant=variant, start=str(nv.index[0]), end=str(nv.index[-1]), years=round(years, 3),
             ret=ret, cagr=cagr, mdd=mdd, calmar=cagr / abs(mdd) if mdd < 0 else math.inf,
             follow_rebuilds=int(follow.group(1)) if follow else None)
    f.write_text(json.dumps(m, indent=1))
    return m


def better(m: dict, b: dict) -> bool:
    """Pre-registered bar (EXP-176): CAGR above v3, Calmar >= v3, max DD no more than 3 pts deeper."""
    return m["cagr"] > b["cagr"] and m["calmar"] >= b["calmar"] and m["mdd"] >= b["mdd"] - 0.03


def table():
    rows = []
    for f in sorted(OUT.glob("*/metrics.json")):
        m = json.loads(f.read_text())
        base = OUT / tag_of(m["pool"], m["seg"], "v3") / "metrics.json"
        b = json.loads(base.read_text()) if base.exists() else None
        el, to, _ = VARIANTS.get(m["variant"], ("?", "?", []))
        rows.append({**m, "element": el, "change": to,
                     "v3_cagr": b and b["cagr"], "v3_calmar": b and b["calmar"], "v3_mdd": b and b["mdd"],
                     "beats_v3": bool(b) and m["variant"] != "v3" and better(m, b)})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "runs.csv", index=False)
    return df


if __name__ == "__main__":
    if sys.argv[1] == "table":
        print(table().to_string())
        sys.exit()
    seg, pool, names = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    todo = list(VARIANTS) if names == "all" else names.split(",")
    for v in todo:   # every patch must apply before anything runs
        patch((source() / "samples/strategy-example" / SCRIPT).read_text(), pool, seg, v)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        for msg in ex.map(lambda v: run(pool, seg, v), todo):
            print(msg, flush=True)
