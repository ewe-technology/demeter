"""
/goal 2026-10-19 (Dino): "在v2上新增一些因子或濾網，找到比v2好的策略" (EXP-178, `EXP-178-v2-factors.md`).

v2 = Isao's "ETH-cbBTC MGL 規格書 v2" standard mode, which has the same signals, allocation and ranges as the
"WB + ETH-strong 25%" spec that Maker implemented in `gamma_maker_defense_btceth_v1.py` (maker-defense 5cec767; matches
the spec's 2022 / 2023 ETH counts, 2024 / 2025 within 0.04). Its defaults are the v2 definitions: Binance UTC closes from
2017-08-17, ladder x1.0, 0.1% swap cost, rewards paid out (kept in the wallet, not reinvested). Mainnet WBTC/WETH 0.05%
`0x4585`, 1 ETH start, three assets (BTC / ETH / USDC), results in ETH.

Each variant is v2 with ONE element added, deleted or replaced, written as text replacements on Maker's script (each
asserted). A run gets its own copy of the maker-defense samples/strategy-example folder and runs on the main checkout's
Rust engine (.venv-rs, no PYTHONPATH). IS and OOS are separate runs from 1 ETH each; the signal engine always runs on the
Binance closes from 2017-08-17.

    python v2_goal.py is|oos <variant,variant,...|all> [workers]
    python v2_goal.py table                     # every finished run -> result/v2_goal/runs.csv (+ judged columns)

Binance files: Maker's BTCUSDT / ETHBTC (to 2025-12-31) and ETHUSDT (to 2026-08-31) extended to 2026-09-17 from
samples/binance_daily_closes.csv (BTCUSDT and ETHUSDT as is, ETHBTC = ETHUSDT / BTCUSDT).
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
OUT = Path(os.environ.get("OUT", MAIN / "samples/strategy-example/result/v2_goal"))
WORK = Path(os.environ.get("WORK", OUT / "_work"))
PY = MAIN / ".venv-rs/bin/python"
REF = "5cec767"
SCRIPT = "gamma_maker_defense_btceth_v1.py"
END = (2026, 9, 17)   # last day of minute data for both pools
DATA = {"0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0": MAIN / "samples/holdout-data/0x4585fe77225b41b697c938b018e2ac67ac5a20c0",
        "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": MAIN / "samples/real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"}
SEGMENTS = {"is": ((2021, 11, 2), (2024, 12, 31)), "oos": ((2025, 1, 1), END), "smoke": ((2025, 3, 1), (2025, 3, 10)),
            "y2023": ((2023, 1, 2), (2023, 12, 31)), "y2025": ((2025, 1, 2), (2025, 12, 31))}  # Maker's check years

# ---- variants: name -> (element of v2, what it becomes, [(pattern, replacement, expected count)]) -------------------
STRONG_LINE = '    return pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})\n'
FAPPEND = "        fractions.append(sum(a.deployed for a in accounts) / len(accounts))\n"
ALLOC_CALL = "        shares, ratio = allocation(f, strong)\n"

VARIANTS: dict[str, tuple[str, str, list]] = {
    "v2": ("-", "v2 unchanged (MGL v2 standard mode = Maker's btceth v1, Binance signal)", []),
    # ---- batch 1 (written 2026-10-19 before any variant run) ----
    "rspan20": ("ETH strength line", "R vs EMA20(R) instead of EMA100(R) (EXP-176: BTC share switch on EMA10-20 held OOS)",
                [("STRENGTH_SPAN = 100\n", "STRENGTH_SPAN = 20\n", 1)]),
    "rconfirm3": ("ETH strength filter", "added: the strong / weak flag flips only after 3 consecutive closes on the other side",
                  [(STRONG_LINE,
                    "    raw, cur, run, flags = (r >= r_ema).tolist(), None, 0, []  # v2_goal rconfirm3\n"
                    "    for x in raw:\n"
                    "        if cur is None:\n"
                    "            cur = x\n"
                    "        run = run + 1 if x != cur else 0\n"
                    "        if run >= 3:\n"
                    "            cur, run = x, 0\n"
                    "        flags.append(cur)\n"
                    '    return pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": pd.Series(flags, index=r.index), "F": fractions})\n',
                    1)]),
    "divG": ("overheat filter", "added (v3's divergence rule on G): F = 0 while G >= EMA100(G) x 1.40, released below x 1.20",
             [(STRONG_LINE,
               "    d, on, flags = (g / emas[100] - 1).tolist(), False, []  # v2_goal divG\n"
               "    for x in d:\n"
               "        on = x >= (0.20 if on else 0.40)\n"
               "        flags.append(on)\n"
               "    fractions = [0.0 if fl else fr for fl, fr in zip(flags, fractions)]\n" + STRONG_LINE, 1)]),
    "confirm5": ("refill stage-1 confirmation", "5 closes instead of 3 (EXP-176 ETH finding)",
                 [("REFILL_CONFIRM_DAYS = 3\n", "REFILL_CONFIRM_DAYS = 5\n", 1)]),
    "f2low": ("F aggregation", "second-lowest of the four accounts instead of the mean (EXP-176 ETH finding)",
              [(FAPPEND, "        fractions.append(sorted(a.deployed for a in accounts)[1])\n", 1)]),
    "btctrend": ("weak-ETH retreat destination", "added: while ETH is weak, the retreat goes to USDC instead of BTC when "
                 "BTC/USD < its EMA100 (BTC itself falling)",
                 [(STRONG_LINE,
                   "    btc_usd = g / r ** 0.5  # v2_goal btctrend: G = sqrt(B x E), R = E / B\n"
                   '    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})\n'
                   '    out["btc_down"] = btc_usd < btc_usd.ewm(span=100, adjust=False).mean()\n'
                   "    return out\n", 1),
                  (ALLOC_CALL, ALLOC_CALL +
                   '        if not strong and bool(row["btc_down"]):  # v2_goal btctrend\n'
                   '            shares = {"lp": shares["lp"], "eth": ZERO, "btc": ZERO, "usdc": shares["btc"]}\n', 1)]),
    "keep50": ("ETH kept outside the LP while strong", "50% of F instead of 25% (spec 6.1 sensitivity: 8 yr 5.35 vs 3.11)",
               [('ETH_KEEP = Decimal("0.25")\n', 'ETH_KEEP = Decimal("0.5")\n', 1)]),
    "wide20": ("LP width while strong", "+-20% always (strength no longer narrows the LP to +-10%)",
               [('RANGE_STRONG, RANGE_WEAK = Decimal("0.10"), Decimal("0.20")', 'RANGE_STRONG, RANGE_WEAK = Decimal("0.20"), Decimal("0.20")', 1)]),
    "noslope": ("EMA exit slope filter", "deleted: close < EMA_n exits without the 20-day falling-EMA test (v3 / ETH-USDC rule)",
                [("        if self.armed and close < ema and ema < ema_prev:\n", "        if self.armed and close < ema:\n", 1)]),
    "follow0625": ("rebuild threshold", "6.25% instead of 12.5% (EXP-176 ETH finding)",
                   [('FOLLOW_THRESHOLD = Decimal("0.125")', 'FOLLOW_THRESHOLD = Decimal("0.0625")', 1)]),
}

# ---- EXP-179 batch 2 (written 2026-10-19 before any of them ran): ADDED elements only (Dino: "原來的元素不動的情況下，
# 新增其他元素"). Every v2 constant and rule stays as is; each variant adds one new layer on v2's output. The filters all
# use the same action, fixed here: F' = F x 0.5 while the filter is on (the halved part follows v2's own allocation, i.e.
# to USDC while ETH is strong, to BTC while weak). A flag judged on day D's close acts on D+1 00:00, like v2's F.
SAMPLES = MAIN / "samples"


def HALVE(flag_code: str) -> list:
    """F x 0.5 on the days `flag` (a boolean Series on g's daily index, built by flag_code) is True."""
    return [(STRONG_LINE,
             '    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})  # v2_goal EXP-179\n'
             + flag_code +
             '    out["F"] = out["F"].where(~flag.reindex(out.index).fillna(False).astype(bool), out["F"] * 0.5)\n'
             "    return out\n", 1)]


VARIANTS.update({
    "fundhot": ("added: funding overheat filter", "F x 0.5 while ETHUSDT perp funding, 7-day mean of the day's prints, > 0.03% / 8h",
                HALVE(f'    _f = pd.read_csv("{SAMPLES}/binance_funding_ETHUSDT_long.csv", parse_dates=["timestamp"])\n'
                      '    _f = _f.groupby(_f["timestamp"].dt.normalize())["rate"].mean().rolling(7, min_periods=7).mean()\n'
                      "    flag = _f > 0.0003\n")),
    "dvolhi": ("added: implied-volatility filter", "F x 0.5 while Deribit ETH DVOL > its trailing 365-day 80th percentile (min 90 days)",
               HALVE(f'    _d = pd.read_csv("{SAMPLES}/deribit_dvol_daily.csv", parse_dates=["date"]).set_index("date")["ETH"]\n'
                     "    flag = _d > _d.rolling(365, min_periods=90).quantile(0.8)\n")),
    "stableflow": ("added: stablecoin liquidity factor", "F x 0.5 while the stablecoin market cap is below its value 30 days earlier",
                   HALVE(f'    _s = pd.read_csv("{SAMPLES}/flow_daily.csv", parse_dates=["date"]).set_index("date")["stable_mcap"]\n'
                         "    flag = _s < _s.shift(30)\n")),
    "rvol": ("added: realized-volatility filter", "F x 0.5 while G's 30-day realized vol > 1.5 x its trailing 365-day median",
             HALVE("    import numpy as _np\n"
                   "    _v = _np.log(g).diff().rolling(30).std()\n"
                   "    flag = _v > 1.5 * _v.rolling(365, min_periods=180).median()\n")),
    "sma200": ("added: long-trend filter", "F x 0.5 while G < SMA200(G) and SMA200 is below its value 20 days earlier",
               HALVE("    _m = g.rolling(200).mean()\n"
                     "    flag = (g < _m) & (_m < _m.shift(20))\n")),
    "weekly": ("added: weekly confirmation filter", "F x 0.5 while G's last Sunday close is below the 20-week EMA of weekly closes",
               HALVE('    _w = g.resample("W-SUN").last()\n'
                     "    _wb = _w < _w.ewm(span=20, adjust=False).mean()\n"
                     '    flag = _wb.reindex(g.index, method="ffill")\n')),
    "ethmom": ("added: ETH momentum override", "while ETH is strong and ETH/USD > EMA20 > EMA50 (ETH/USD = G x sqrt(R)), the "
               "USDC reserve is held as ETH outside the LP",
               [(STRONG_LINE,
                 '    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})  # v2_goal ethmom\n'
                 "    _e = g * r ** 0.5\n"
                 "    _e20, _e50 = _e.ewm(span=20, adjust=False).mean(), _e.ewm(span=50, adjust=False).mean()\n"
                 '    out["ethmom"] = out["strong"] & (_e > _e20) & (_e20 > _e50)\n'
                 "    return out\n", 1),
                (ALLOC_CALL, ALLOC_CALL +
                 '        if strong and bool(row["ethmom"]):  # v2_goal ethmom: USDC reserve held as ETH\n'
                 '            shares = {"lp": shares["lp"], "eth": shares["eth"] + shares["usdc"], "btc": ZERO, "usdc": ZERO}\n', 1)]),
    "cooldown7": ("added: rebuild cooldown", "a drift rebuild (>= 12.5% off target) needs 7 days since the last rebuild; "
                  "the out-of-range and target LP 0 / 100% / USDC 0 rebuilds are unchanged",
                  [("        self.rebuild_count = self.out_of_range_rebuilds = 0\n",
                    "        self.rebuild_count = self.out_of_range_rebuilds = 0\n"
                    "        self.last_rebuild = datetime(2000, 1, 1)  # v2_goal cooldown7\n", 1),
                   ("        self.rebuild_count += 1\n", "        self.rebuild_count += 1\n        self.last_rebuild = row_data.timestamp\n", 1),
                   ("        elif any(abs(cur[k] - shares[k]) >= FOLLOW_THRESHOLD for k in cur):\n",
                    "        elif any(abs(cur[k] - shares[k]) >= FOLLOW_THRESHOLD for k in cur) and \\\n"
                    "                row_data.timestamp - self.last_rebuild >= timedelta(days=7):\n", 1)]),
})

# Logging only (no change in behaviour): write the per-minute net value (ETH, incl. collected rewards in the wallet) as
# daily closes plus minute-level drawdowns, and the spec metrics, to <folder>/v2goal_<mode>.json
MET_LINE = '    metrics["lp_avg_share"] = strat.lp_share_sum / strat.lp_share_days if strat.lp_share_days else ZERO\n'
MET_MORE = MET_LINE + (
    "    _nv = net_value.apply(float)\n"
    "    _usd = usd_series.astype(float)\n"
    "    _nv.resample('1D').last().to_csv(f'{params.folder}/nv_daily_{mode}.csv')\n"
    "    import json as _json\n"
    "    _json.dump({'start': str(_nv.index[0]), 'end': str(_nv.index[-1]), 'nv0': float(_nv.iloc[0]), 'nv1': float(_nv.iloc[-1]),\n"
    "                'mdd_eth': float((_nv / _nv.cummax() - 1).min()), 'mdd_usd': float((_usd / _usd.cummax() - 1).min()),\n"
    "                'usd0': float(_usd.iloc[0]), 'usd1': float(_usd.iloc[-1]),\n"
    "                **{k: float(metrics[k]) for k in ('eth_ratio_receipt', 'eth_ratio_end', 'reward_eth', 'btc_ratio', 'usd_ratio',\n"
    "                                                  'swap_cost_eth', 'lp_avg_share')},\n"
    "                'rebuilds': strat.rebuild_count, 'out_of_range': strat.out_of_range_rebuilds},\n"
    "               open(f'{params.folder}/v2goal_{mode}.json', 'w'))\n")


def sub(text: str, pattern: str, repl: str, n_expected: int) -> str:
    n = text.count(pattern)
    assert n == n_expected, f"pattern found {n} times, expected {n_expected}: {pattern[:80]!r}"
    return text.replace(pattern, repl)


def patch(text: str, seg: str, variant: str) -> str:
    (y, mo, d), (ye, me, de) = SEGMENTS[seg]
    entry = f"\n        (datetime({y}, {mo}, {d}), date({y}, {mo}, {d}), date({ye}, {me}, {de})),"
    new, n = re.subn(r"(date_ranges: List\[tuple\[datetime, date, date\]\] = \[).*?(\n    \]\n)",
                     lambda m: m.group(1) + entry + m.group(2), text, count=1, flags=re.S)
    assert n == 1
    text = sub(new, "if __name__ == \"__main__\":\n    _self_check()\n",
               "if __name__ == \"__main__\":\n    pass  # _self_check() skipped: it asserts the default parameters\n", 1)
    for pattern, repl, n_expected in VARIANTS[variant][2]:
        text = sub(text, pattern, repl, n_expected)
    return sub(text, MET_LINE, MET_MORE, 1)


def binance_files(dst: Path):
    """Maker's daily closes extended to END from samples/binance_daily_closes.csv (same date convention)."""
    long = pd.read_csv(MAIN / "samples/binance_daily_closes.csv", parse_dates=["date"]).set_index("date")
    end = pd.Timestamp(*END)
    for name, ext in (("binance_ethusdt_1d.csv", long["ETHUSDT"]), ("binance_btcusdt_1d.csv", long["BTCUSDT"]),
                      ("binance_ethbtc_1d.csv", long["ETHUSDT"] / long["BTCUSDT"])):
        s = pd.read_csv(dst / name, parse_dates=["date"]).set_index("date")["close"]
        out = pd.concat([s, ext.loc[s.index[-1] + pd.Timedelta(days=1):end]]).rename("close")
        assert out.index[0] == pd.Timestamp(2017, 8, 17) and out.index[-1] == end
        assert (out.index[1:] - out.index[:-1]).max() == pd.Timedelta(days=1)
        out.rename_axis("date").reset_index().assign(date=lambda f: f["date"].dt.strftime("%Y-%m-%d")).to_csv(dst / name, index=False)


def source() -> Path:
    src = WORK / "_src"
    if not src.exists():
        blob = subprocess.run(["git", "-C", str(REPO), "archive", REF, "samples/strategy-example"],
                              check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(blob)).extractall(src)
        binance_files(src / "samples/strategy-example")
    return src


def tag_of(seg: str, variant: str) -> str:
    return f"{seg}-{variant}"


def run(seg: str, variant: str) -> str:
    tag = tag_of(seg, variant)
    d = WORK / tag / "samples"
    if d.parent.exists():
        shutil.rmtree(d.parent)
    se = d / "strategy-example"
    shutil.copytree(source() / "samples/strategy-example", se, ignore=shutil.ignore_patterns("result", "*.md", "*.png"))
    (d / "real-data").mkdir()
    for addr, path in DATA.items():
        os.symlink(path, d / "real-data" / addr)
    script = se / SCRIPT
    script.write_text(patch(script.read_text(), seg, variant))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ENGINE", "OUT", "WORK")}
    dst = OUT / tag
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    with open(dst / "run.log", "w") as f:
        rc = subprocess.run([str(PY), script.name], cwd=se, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    js = list((se / "result").rglob("v2goal_signal.json"))
    for f in js + list((se / "result").rglob("*.csv")):
        shutil.copy(f, dst / f.name)
    shutil.rmtree(d.parent)
    if rc != 0 or not js:
        return f"{tag} FAILED rc={rc}"
    m = metrics(seg, variant)
    return (f"{tag} eth x{m['ratio']:.4f} cagr {m['cagr']:.2%} dd {m['mdd']:.1%} calmar {m['calmar']:.3f} "
            f"usd x{m['usd_ratio']:.3f} usd-dd {m['mdd_usd']:.1%} rebuilds {m['rebuilds']}")


def metrics(seg: str, variant: str) -> dict:
    """Net value in ETH incl. collected rewards (standard mode: principal + rewards), per minute: CAGR, max DD, Calmar."""
    j = json.loads((OUT / tag_of(seg, variant) / "v2goal_signal.json").read_text())
    years = (pd.Timestamp(j["end"]) - pd.Timestamp(j["start"])).total_seconds() / (365.25 * 86400)
    ratio = j["nv1"] / j["nv0"]
    cagr = ratio ** (1 / years) - 1
    return {**j, "seg": seg, "variant": variant, "years": round(years, 3), "ratio": ratio, "cagr": cagr,
            "mdd": j["mdd_eth"], "calmar": cagr / abs(j["mdd_eth"]) if j["mdd_eth"] < 0 else math.inf}


def better(m: dict, b: dict) -> bool:
    """Pre-registered bar (EXP-176 / 177): CAGR above v2, Calmar >= v2, max DD no more than 3 pts deeper (all in ETH)."""
    return m["cagr"] > b["cagr"] and m["calmar"] >= b["calmar"] and m["mdd"] >= b["mdd"] - 0.03


def table() -> pd.DataFrame:
    rows = []
    for f in sorted(OUT.glob("*/v2goal_signal.json")):
        seg, variant = f.parent.name.split("-", 1)
        m = metrics(seg, variant)
        b = metrics(seg, "v2") if (OUT / tag_of(seg, "v2") / "v2goal_signal.json").exists() else None
        el, to, _ = VARIANTS.get(variant, ("?", "?", []))
        rows.append({k: m[k] for k in ("seg", "variant", "start", "end", "years", "ratio", "cagr", "mdd", "calmar",
                                       "eth_ratio_receipt", "reward_eth", "btc_ratio", "usd_ratio", "mdd_usd",
                                       "swap_cost_eth", "lp_avg_share", "rebuilds", "out_of_range")} |
                    {"element": el, "change": to, "v2_cagr": b and b["cagr"], "v2_mdd": b and b["mdd"],
                     "v2_calmar": b and b["calmar"], "beats_v2": bool(b) and variant != "v2" and better(m, b)})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "runs.csv", index=False)
    return df


if __name__ == "__main__":
    if sys.argv[1] == "table":
        print(table().to_string())
        sys.exit()
    seg, names = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    todo = list(VARIANTS) if names == "all" else names.split(",")
    for v in todo:   # every patch must apply before anything runs
        patch((source() / "samples/strategy-example" / SCRIPT).read_text(), seg, v)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        for msg in ex.map(lambda v: run(seg, v), todo):
            print(msg, flush=True)
