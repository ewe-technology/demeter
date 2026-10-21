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
REF = os.environ.get("REF", "5cec767")
SCRIPT = os.environ.get("SCRIPT", "gamma_maker_defense_btceth_v1.py")
# Sheet check 2026-10-21: REF=29e3dd9 SCRIPT=gamma_ig_gap_bands_defense_btceth.py OUT=<other dir> runs the remix branch's
# earlier version of the same spec (pool-price signal, no Binance files); its runs must go to their own OUT.
END = (2026, 9, 17)   # end of the EXP-178..182 out-of-sample segment (minute data then ended here)
DATA_END = (2026, 9, 30)   # both pools' minute data since 2026-10-21; the Binance files are extended to here
DATA = {"0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0": MAIN / "samples/holdout-data/0x4585fe77225b41b697c938b018e2ac67ac5a20c0",
        "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": MAIN / "samples/real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        "0x2f5e87C9312fa29aed5C179E456625D79015299c": MAIN / "samples/holdout-data/0x2f5e87c9312fa29aed5c179e456625d79015299c"}
SEGMENTS = {"is": ((2021, 11, 2), (2024, 12, 31)), "oos": ((2025, 1, 1), END), "smoke": ((2025, 3, 1), (2025, 3, 10)),
            "y2023": ((2023, 1, 2), (2023, 12, 31)), "y2025": ((2025, 1, 2), (2025, 12, 31)),  # Maker's check years
            "arb": ((2023, 1, 1), (2026, 1, 13)),   # EXP-182: Arbitrum 0x2f5e, all its minute data
            "arbsmoke": ((2024, 3, 1), (2024, 3, 10)), "mainsmoke": ((2024, 3, 1), (2024, 3, 10)),
            # the windows of Maker's sheet "BTC/ETH gamma ig gap bands defence V1 slippage 0.1/fee 0.05" (2026 ends at
            # our last minute-data day, the sheet's at 09-30)
            "y2022": ((2022, 1, 2), (2022, 12, 31)), "y2024": ((2024, 1, 2), (2024, 12, 31)),
            "c2225": ((2022, 1, 2), (2025, 12, 31)), "y2026": ((2026, 1, 2), END),
            "y2026f": ((2026, 1, 2), DATA_END),   # the sheet's 2026 window, after the data was extended to 09-30
            "oosf": ((2025, 1, 1), DATA_END)}   # EXP-183 out-of-sample: 2025 on, all minute data

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

# ---- EXP-180 batch 3 (written 2026-10-19 after an in-sample drawdown analysis of v2, before any of them ran): ADDED
# elements only, aimed at v2's ETH drawdowns, which all came while ETH rose against BTC (IS: 2022-06..11 −25.8% with
# BTC per ETH +48%, 2024-05..07 −20.5% with +19%). An "R shield" adds a flag on R = ETH/BTC; while it is on, the LP share
# of v2's target is held as plain ETH instead of an LP (`_all`: the BTC reserve too); v2's F, strength, USDC share, ranges
# and rebuild rules are unchanged (a changed target rebuilds through v2's own drift / target-LP-0 rules).
RVOL_CODE = ("    import numpy as _np\n"
             "    _v = _np.log(g).diff().rolling(30).std()\n"
             "    _vf = _v > 1.5 * _v.rolling(365, min_periods=180).median()\n"
             '    out["F"] = out["F"].where(~_vf.reindex(out.index).fillna(False).astype(bool), out["F"] * 0.5)\n')
RFLAGS = {
    # breakout: R at least 10% above its 20-day low
    "break": "    rflag = r >= 1.10 * r.rolling(20, min_periods=1).min()\n",
    # momentum: R above EMA20(R) above EMA50(R)
    "mom": ("    _r20, _r50 = r.ewm(span=20, adjust=False).mean(), r.ewm(span=50, adjust=False).mean()\n"
            "    rflag = (r > _r20) & (_r20 > _r50)\n"),
    # breakout held: on at a 10% breakout above the 20-day low, off at the first close below EMA20(R)
    "ext": ("    _lo, _r20, _on, _fl = r.rolling(20, min_periods=1).min(), r.ewm(span=20, adjust=False).mean(), False, []\n"
            "    for _x, _l, _e in zip(r, _lo, _r20):\n"
            "        _on = (_x >= 1.10 * _l) or (_on and _x >= _e)\n"
            "        _fl.append(_on)\n"
            "    rflag = pd.Series(_fl, index=r.index)\n"),
}


def RSHIELD(kind: str, btc_too: bool, rvol: bool = False) -> list:
    """While the R flag is on, v2's LP share (and with btc_too its BTC reserve) is held as ETH."""
    moved = '(shares["lp"] + shares["btc"])' if btc_too else 'shares["lp"]'
    return [(STRONG_LINE,
             '    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})  # v2_goal EXP-180\n'
             + (RVOL_CODE if rvol else "") + RFLAGS[kind] +
             '    out["rflag"] = rflag.reindex(out.index).fillna(False).astype(bool)\n'
             "    return out\n", 1),
            (ALLOC_CALL, ALLOC_CALL +
             '        if bool(row["rflag"]):  # v2_goal EXP-180 R shield: held as ETH instead\n'
             f'            shares = {{"lp": ZERO, "eth": shares["eth"] + {moved}, '
             f'"btc": {"ZERO" if btc_too else "shares[" + chr(34) + "btc" + chr(34) + "]"}, "usdc": shares["usdc"]}}\n', 1)]


VARIANTS.update({
    "rbreak_lp": ("added: R breakout shield (LP)", "while R >= 1.10 x its 20-day low, the LP share is held as ETH", RSHIELD("break", False)),
    "rbreak_all": ("added: R breakout shield (LP + BTC)", "while R >= 1.10 x its 20-day low, the LP share and the BTC reserve are held as ETH",
                   RSHIELD("break", True)),
    "rmom_lp": ("added: R momentum shield (LP)", "while R > EMA20(R) > EMA50(R), the LP share is held as ETH", RSHIELD("mom", False)),
    "rmom_all": ("added: R momentum shield (LP + BTC)", "while R > EMA20(R) > EMA50(R), the LP share and the BTC reserve are held as ETH",
                 RSHIELD("mom", True)),
    "rext_lp": ("added: held R breakout shield (LP)", "from a 10% breakout above R's 20-day low until R closes below EMA20(R), "
                "the LP share is held as ETH", RSHIELD("ext", False)),
    "rext_all": ("added: held R breakout shield (LP + BTC)", "from a 10% breakout above R's 20-day low until R closes below "
                 "EMA20(R), the LP share and the BTC reserve are held as ETH", RSHIELD("ext", True)),
    "rvol_rmom_all": ("added: rvol + R momentum shield (LP + BTC)", "EXP-179 rvol filter and rmom_all together", RSHIELD("mom", True, True)),
    "rvol_rext_all": ("added: rvol + held R breakout shield (LP + BTC)", "EXP-179 rvol filter and rext_all together", RSHIELD("ext", True, True)),
})

# ---- EXP-180 batch 4 (written 2026-10-19 after batch 3's IS runs, before any batch 4 run): ADDED "lock" layers. Batch 3
# showed that much of v2's ETH drawdown is the give-back after v2 held USDC / BTC through an ETH low (IS 2022-08-29 peak:
# 77% USDC at ETH $1427, then ETH rebounds). A lock holds a retreat asset as ETH once ETH is deeply oversold, keeping
# the ETH already won; it is released when ETH recovers above its EMA50 and v2's own target applies again.
#   capit X : ETH/USD <= X x its 90-day high close -> v2's USDC share held as ETH, until ETH/USD > EMA50(ETH/USD)
#   rlow X  : R <= X x its 90-day high -> v2's BTC share held as ETH, until R > EMA50(R)
# ETH/USD = G x sqrt(R) (Binance closes). Combinations of added layers allowed (rvol, rbreak shield).
def _lock(name: str, series: str, x: float) -> str:
    return (f"    _s = {series}\n"
            "    _hi, _m, _on, _fl = _s.rolling(90, min_periods=1).max(), _s.ewm(span=50, adjust=False).mean(), False, []\n"
            "    for _x, _h, _mm in zip(_s, _hi, _m):\n"
            f"        _on = (_x <= {x} * _h) or (_on and _x <= _mm)\n"
            "        _fl.append(_on)\n"
            f'    out["{name}"] = pd.Series(_fl, index=_s.index).reindex(out.index).fillna(False).astype(bool)\n')


def LOCKS(capit: float | None = None, rlow: float | None = None, rvol: bool = False, rbreak: bool = False) -> list:
    code = ('    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})  # v2_goal EXP-180 b4\n'
            + (RVOL_CODE if rvol else "")
            + (_lock("cflag", "g * r ** 0.5", capit) if capit else "")
            + (_lock("bflag", "r", rlow) if rlow else "")
            + (RFLAGS["break"] + '    out["rflag"] = rflag.reindex(out.index).fillna(False).astype(bool)\n' if rbreak else "")
            + "    return out\n")
    alloc = (ALLOC_CALL +
             "        _sh = dict(shares)  # v2_goal EXP-180 locks: retreat assets held as ETH\n"
             '        if bool(row.get("cflag", False)):\n'
             '            _sh["eth"], _sh["usdc"] = _sh["eth"] + _sh["usdc"], ZERO\n'
             '        if bool(row.get("bflag", False)):\n'
             '            _sh["eth"], _sh["btc"] = _sh["eth"] + _sh["btc"], ZERO\n'
             '        if bool(row.get("rflag", False)):\n'
             '            _sh["eth"], _sh["lp"], _sh["btc"] = _sh["eth"] + _sh["lp"] + _sh["btc"], ZERO, ZERO\n'
             "        shares = _sh\n")
    return [(STRONG_LINE, code, 1), (ALLOC_CALL, alloc, 1)]


VARIANTS.update({
    "capit40": ("added: capitulation lock (USDC)", "ETH/USD <= 0.60 x 90-day high -> USDC share held as ETH until ETH/USD > EMA50", LOCKS(capit=0.60)),
    "capit30": ("added: capitulation lock (USDC)", "ETH/USD <= 0.70 x 90-day high -> USDC share held as ETH until ETH/USD > EMA50", LOCKS(capit=0.70)),
    "rlow25": ("added: ETH/BTC low lock (BTC)", "R <= 0.75 x 90-day high -> BTC share held as ETH until R > EMA50(R)", LOCKS(rlow=0.75)),
    "rlow15": ("added: ETH/BTC low lock (BTC)", "R <= 0.85 x 90-day high -> BTC share held as ETH until R > EMA50(R)", LOCKS(rlow=0.85)),
    "capit40_rlow25": ("added: capit40 + rlow25", "both locks", LOCKS(capit=0.60, rlow=0.75)),
    "capit30_rlow15": ("added: capit30 + rlow15", "both locks", LOCKS(capit=0.70, rlow=0.85)),
    "capit40_rlow25_rvol": ("added: capit40 + rlow25 + rvol", "both locks and the EXP-179 rvol filter", LOCKS(capit=0.60, rlow=0.75, rvol=True)),
    "capit40_rlow25_rbreak": ("added: capit40 + rlow25 + rbreak shield", "both locks and the rbreak_all shield",
                              LOCKS(capit=0.60, rlow=0.75, rbreak=True)),
})

# ---- EXP-180 batch 5, the last (written 2026-10-19 after batch 4's IS runs, before any batch 5 run): rlow25 cut IS max
# DD by 6 pts (−20.4%) with CAGR +0.86: it won 2022 (R rebounded after the lock, x2.887 vs 2.726) and lost 2024 (R kept
# falling 0.054 -> 0.035 after the lock, x1.143 vs 1.190). Batch 5 adds a confirmation or an early release to the BTC
# lock so it stays out of trending declines, and stacks rvol (the one added layer with a return gain).
def _rlock(x: float = 0.75, conf: bool = False, newlow: bool = False, span: int = 50) -> str:
    """BTC lock on R: on at R <= x * 90-day high (with conf: and R >= 1.05 x its 10-day low), held while R <= EMA(span);
    with newlow: released at once when R closes below its previous 20-day low."""
    on = f"(_x <= {x} * _h)" + (" and (_x >= 1.05 * _l10)" if conf else "")
    rule = f"({on} or (_on and _x <= _mm))" + (" and not (_x < _l20)" if newlow else "")   # a new low blocks entry too
    return ("    _s = r\n"
            f"    _hi, _m = _s.rolling(90, min_periods=1).max(), _s.ewm(span={span}, adjust=False).mean()\n"
            "    _lo10, _lo20 = _s.rolling(10, min_periods=1).min(), _s.shift(1).rolling(20, min_periods=1).min()\n"
            "    _on, _fl = False, []\n"
            "    for _x, _h, _mm, _l10, _l20 in zip(_s, _hi, _m, _lo10, _lo20):\n"
            f"        _on = {rule}\n"
            "        _fl.append(_on)\n"
            '    out["bflag"] = pd.Series(_fl, index=_s.index).reindex(out.index).fillna(False).astype(bool)\n')


def RLOCK(rvol: bool = False, lp: bool = False, **kw) -> list:
    code = ('    out = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})  # v2_goal EXP-180 b5\n'
            + (RVOL_CODE if rvol else "") + _rlock(**kw) + "    return out\n")
    moved = '_sh["btc"] + _sh["lp"]' if lp else '_sh["btc"]'
    alloc = (ALLOC_CALL +
             "        _sh = dict(shares)  # v2_goal EXP-180 b5: BTC lock\n"
             '        if bool(row.get("bflag", False)):\n'
             f'            _sh["eth"], _sh["btc"] = _sh["eth"] + {moved}, ZERO\n'
             + ('            _sh["lp"] = ZERO\n' if lp else "") +
             "        shares = _sh\n")
    return [(STRONG_LINE, code, 1), (ALLOC_CALL, alloc, 1)]


VARIANTS.update({
    "rlow25_conf": ("added: R-low BTC lock, confirmed", "rlow25, entry also needs R >= 1.05 x its 10-day low", RLOCK(conf=True)),
    "rlow25_newlow": ("added: R-low BTC lock, new-low release", "rlow25, released when R closes below its previous 20-day low",
                      RLOCK(newlow=True)),
    "rlow20": ("added: R-low BTC lock", "R <= 0.80 x 90-day high -> BTC share held as ETH until R > EMA50(R)", RLOCK(x=0.80)),
    "rlow25_e100": ("added: R-low BTC lock, slow release", "rlow25 held until R > EMA100(R)", RLOCK(span=100)),
    "rlow25_lp": ("added: R-low lock (BTC + LP)", "rlow25, the LP share is also held as ETH while locked", RLOCK(lp=True)),
    "rlow25_rvol": ("added: rlow25 + rvol", "BTC lock and the EXP-179 rvol filter", RLOCK(rvol=True)),
    "rlow25_conf_rvol": ("added: rlow25_conf + rvol", "confirmed BTC lock and rvol", RLOCK(rvol=True, conf=True)),
    "rlow25_newlow_rvol": ("added: rlow25_newlow + rvol", "new-low-release BTC lock and rvol", RLOCK(rvol=True, newlow=True)),
})

# ---- EXP-182 (written 2026-10-19 before any of them ran; Dino chose option 1: v2's own elements may change too): stacks
# of the components that held out of sample in EXP-178 / 179 (keep50, f2low, rvol), the ETH-kept share pushed further
# (spec 6.1 tested 0 / 25 / 50%), on `0x4585` IS + OOS and on Arbitrum WBTC/WETH 0.05% `0x2f5e` (never used in this search).
def KEEP(x: str) -> list:
    return [('ETH_KEEP = Decimal("0.25")\n', f'ETH_KEEP = Decimal("{x}")\n', 1)]


F2LOW, RVOL = VARIANTS["f2low"][2], VARIANTS["rvol"][2]
VARIANTS.update({
    "k50_rvol": ("ETH kept 50% + rvol", "keep50 and the rvol filter", KEEP("0.5") + RVOL),
    "k50_f2low": ("ETH kept 50% + F second-lowest", "keep50 and f2low", KEEP("0.5") + F2LOW),
    "k50_f2low_rvol": ("ETH kept 50% + F second-lowest + rvol", "keep50, f2low and rvol", KEEP("0.5") + F2LOW + RVOL),
    "keep75": ("ETH kept outside the LP while strong", "75% of F instead of 25%", KEEP("0.75")),
    "k75_rvol": ("ETH kept 75% + rvol", "keep75 and rvol", KEEP("0.75") + RVOL),
    "k75_f2low_rvol": ("ETH kept 75% + F second-lowest + rvol", "keep75, f2low and rvol", KEEP("0.75") + F2LOW + RVOL),
    "keep100": ("ETH kept outside the LP while strong", "100% of F (no LP while ETH is strong; boundary case)", KEEP("1")),
})
# 2026-10-21 (Dino: 最單純的lp策略): the spec's own "通常LP" control, Maker's MODE_PLAIN: 100% LP, one uniform +-10% band,
# no signal, recentred when the price leaves it, same 0.1% swap cost
VARIANTS["plain"] = ("whole strategy", "spec's plain LP control (MODE_PLAIN): 100% LP, uniform +-10%, rebuilt out of range",
                     [("    modes = modes or [MODE_SIGNAL]", "    modes = [MODE_PLAIN]  # v2_goal plain", 1)])

# ---- EXP-183 (/goal 2026-10-21: IS before 2025, OOS after; only IS results may shape a variant, OOS only for IS passes).
# Base = k75_f2low_rvol (EXP-182's best); each variant adds ONE element on top of it. Batch 1 was written after an IS-only
# look at the base: its four deepest IS drawdowns (in ETH) come from holding the retreat while the market turned back
# (USDC through ETH/USD rebounds 2022-08..11 −25.2% and 2024-05..08 −21.0%; BTC through ETH/BTC rebounds 2022-06..08 and
# 2024-11), and the LP leg nets about zero over IS (+0.10 ETH of +2.96, fees included).
RVOL_LINE = '    out["F"] = out["F"].where(~flag.reindex(out.index).fillna(False).astype(bool), out["F"] * 0.5)\n'
K75 = KEEP("0.75") + F2LOW + RVOL


def REUP(level: str, strong_only: bool) -> list:
    """Re-entry after a wrong exit: when the final F falls, remember that day's close of `level`; while F < 1, a close
    >= 1.15 x that level sets F = 1 until F falls again (a new exit) or reaches 1 by itself."""
    return [(RVOL_LINE, RVOL_LINE +
             f"    _lvl, _st = ({level}).reindex(out.index).tolist(), out['strong'].tolist()  # v2_goal EXP-183 reup\n"
             "    _sell, _on, _prev, _res = None, False, None, []\n"
             "    for _x, _p, _s in zip(out['F'].tolist(), _lvl, _st):\n"
             "        if _prev is not None and _x < _prev:\n"
             "            _sell, _on = _p, False\n"
             "        if _x >= 1.0:\n"
             "            _on = False\n"
             f"        if not _on and _sell is not None and _x < 1.0 and _p >= 1.15 * _sell{' and _s' if strong_only else ''}:\n"
             "            _on = True\n"
             "        _res.append(1.0 if _on else _x)\n"
             "        _prev = _x\n"
             "    out['F'] = _res\n", 1)]


STRONG_ALLOC = '        return {"lp": f * (ONE - ETH_KEEP), "eth": f * ETH_KEEP, "btc": ZERO, "usdc": ONE - f}, RANGE_STRONG\n'
WEAK_ALLOC = '    return {"lp": f, "eth": ZERO, "btc": ONE - f, "usdc": ZERO}, RANGE_WEAK\n'
VARIANTS.update({
    "k75_f2low_rvol_reupG": ("added: re-entry after a wrong exit (G)", "F = 1 once G closes 15% above its close on the "
                             "day F last fell, until F falls again", K75 + REUP("g", False)),
    "k75_f2low_rvol_reupE": ("added: re-entry after a wrong exit (ETH/USD, strong only)", "while ETH is strong, F = 1 once "
                             "ETH/USD closes 15% above its close on the day F last fell, until F falls again",
                             K75 + REUP("g * r ** 0.5", True)),
    "k75_f2low_rvol_split50": ("retreat asset", "the (1 - F) reserve is always half BTC, half USDC (v2: USDC while strong, "
                               "BTC while weak)",
                               K75 + [(STRONG_ALLOC, STRONG_ALLOC.replace('"btc": ZERO, "usdc": ONE - f',
                                                                          '"btc": (ONE - f) / 2, "usdc": (ONE - f) / 2'), 1),
                                      (WEAK_ALLOC, WEAK_ALLOC.replace('"btc": ONE - f, "usdc": ZERO',
                                                                      '"btc": (ONE - f) / 2, "usdc": (ONE - f) / 2'), 1)]),
    "k75_f2low_rvol_ethmom": ("added: ETH momentum override (EXP-179's ethmom on the new base)", "while ETH is strong and "
                              "ETH/USD > EMA20 > EMA50, the USDC reserve is held as ETH outside the LP",
                              K75 + [(RVOL_LINE, RVOL_LINE +
                                      "    _e = g * r ** 0.5  # v2_goal EXP-183 ethmom\n"
                                      "    _e20, _e50 = _e.ewm(span=20, adjust=False).mean(), _e.ewm(span=50, adjust=False).mean()\n"
                                      '    out["ethmom"] = out["strong"] & (_e > _e20) & (_e20 > _e50)\n', 1),
                                     VARIANTS["ethmom"][2][1]]),
})
# EXP-183 batch 2 (written after batch 1's IS results and an IS-only split of the base's LP result by regime; reupE's OOS
# was identical to the base, its rule never fired): while ETH is weak (787 of 1155 IS days, LP 68% of the book) the LP
# made +0.03 ETH, a plain 50/50 ETH/BTC hold of the same money +0.14, BTC +0.28 (2022 −0.47, 2024 +0.71). Mirror of
# keep75 on the weak side: keep part of F as BTC outside the LP, or hold the weak-side LP share as 50/50 tokens.


def BKEEP(x: str) -> list:
    return K75 + [(WEAK_ALLOC, WEAK_ALLOC.replace('"lp": f, "eth": ZERO, "btc": ONE - f',
                                                  f'"lp": f * (ONE - Decimal("{x}")), "eth": ZERO, "btc": f * Decimal("{x}") + ONE - f'), 1)]


VARIANTS.update({
    "k75_f2low_rvol_bkeep25": ("added: BTC kept outside the LP while weak", "25% of F held as BTC (mirror of ETH_KEEP)", BKEEP("0.25")),
    "k75_f2low_rvol_bkeep50": ("added: BTC kept outside the LP while weak", "50% of F held as BTC (mirror of ETH_KEEP)", BKEEP("0.5")),
    "k75_f2low_rvol_weakhold": ("weak-side LP", "while weak, F is held as 50% ETH / 50% BTC tokens instead of an LP",
                                K75 + [(WEAK_ALLOC, WEAK_ALLOC.replace('"lp": f, "eth": ZERO, "btc": ONE - f',
                                                                      '"lp": ZERO, "eth": f / 2, "btc": f / 2 + ONE - f'), 1)]),
})
# EXP-183 batch 3 (after batch 2's IS results: all three weak-side changes lost IS, the LP's fees matter more than the
# regime split suggested). Collected fees (0.68 ETH over IS, 14% of the end book) sit in the wallet outside the
# strategy's capital, BTC fees stay BTC; the spec's compound mode reinvests them. Rebuild swap cost was 0.14 ETH over IS.
VARIANTS.update({
    "k75_f2low_rvol_compound": ("fee handling", "spec compound mode: collected fees count as capital and are reinvested "
                                "by the next rebuild's target (base: kept in the wallet, outside the strategy)",
                                K75 + [("        return (self.broker.get_token_balance(self.gp.base_token) - self.total_base_fee,\n"
                                        "                self.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee,\n",
                                        "        return (self.broker.get_token_balance(self.gp.base_token),  # v2_goal EXP-183 compound\n"
                                        "                self.broker.get_token_balance(self.gp.quote_token),\n", 1)]),
    "k75_f2low_rvol_follow25": ("rebuild threshold", "25% instead of 12.5% (fewer drift rebuilds, less swap cost)",
                                K75 + [('FOLLOW_THRESHOLD = Decimal("0.125")', 'FOLLOW_THRESHOLD = Decimal("0.25")', 1)]),
})
# EXP-183 batch 4 (after batch 3's IS results, both lost). While ETH is strong the book is F x 75% ETH + F x 25% ETH/BTC
# LP + (1 - F) USDC, i.e. an ETH/USD position, but F comes from G = sqrt(ETH x BTC); the base's two deepest IS drawdowns
# are USDC held through ETH/USD rebounds. Run the same four accounts (second-lowest, then rvol) on ETH/USD = G x sqrt(R).


def FE(strong_only: bool) -> list:
    return K75 + [(RVOL_LINE,
                   "    _e = g * r ** 0.5  # v2_goal EXP-183 fE: the four accounts on ETH/USD\n"
                   "    _em = {n: _e.ewm(span=n, adjust=False).mean() for n in EMA_SPANS}\n"
                   "    _pv = {n: _em[n].shift(EMA_SLOPE_DAYS) for n in EMA_SPANS}\n"
                   "    _acc, _fe = [VirtualAccount(n) for n in EMA_SPANS], []\n"
                   "    for _day, _c in _e.items():\n"
                   "        for _a in _acc:\n"
                   "            _a.step(float(_c), float(_em[_a.span][_day]), float(_pv[_a.span][_day]))\n"
                   "        _fe.append(sorted(_a.deployed for _a in _acc)[1])\n"
                   "    _fe = pd.Series(_fe, index=_e.index).reindex(out.index)\n"
                   + ('    out["F"] = _fe.where(out["strong"], out["F"])\n' if strong_only else '    out["F"] = _fe\n')
                   + RVOL_LINE, 1)]


VARIANTS.update({
    "k75_f2low_rvol_fEstrong": ("F signal while strong", "while ETH is strong, F from the four accounts on ETH/USD (base: on G)",
                                FE(True)),
    "k75_f2low_rvol_fEboth": ("F signal", "F from the four accounts on ETH/USD on every day (base: on G)", FE(False)),
})
# EXP-183 batch 5 (after batch 4's IS results, both lost; picked from the IS ranking of every v2_goal run, IS only):
# keep100 beat keep75 on IS (59.26% / −23.0% vs 58.79% / −23.3%); f2low was the largest single IS gain (+4.1 pts on v2),
# its more conservative neighbour (lowest account) was never run on v2; rlow20 had the best IS Calmar (3.076, DD −17.9%).
VARIANTS.update({
    "k100_f2low_rvol": ("ETH kept outside the LP while strong", "100% of F on the base (no LP while ETH is strong)",
                        KEEP("1") + F2LOW + RVOL),
    "k75_fmin_rvol": ("F aggregation", "lowest of the four accounts instead of the second-lowest",
                      KEEP("0.75") + [(FAPPEND, "        fractions.append(min(a.deployed for a in accounts))\n", 1)] + RVOL),
    "k75_f2low_rvol_rlow20": ("added: R-low BTC lock (EXP-180 rlow20) on the base", "R <= 0.80 x 90-day high -> the BTC "
                              "share is held as ETH until R > EMA50(R)",
                              K75 + [(RVOL_LINE, RVOL_LINE + _rlock(x=0.80), 1), RLOCK(x=0.80)[1]]),
})
# EXP-183 batch 6 (after batch 5's IS results): fmin raised IS CAGR to 67.07% and k100 to 65.10%, both with a lower
# Calmar; fmin's deepest IS drawdown is the 2022-08-29..11-05 episode (−27.0%), the one reupE cut on the base
# (−25.2% -> −24.0%). Stack reupE on them.
FMIN = [(FAPPEND, "        fractions.append(min(a.deployed for a in accounts))\n", 1)]
REUPE = REUP("g * r ** 0.5", True)
VARIANTS.update({
    "k75_fmin_rvol_reupE": ("F lowest account + re-entry", "k75_fmin_rvol + reupE", KEEP("0.75") + FMIN + RVOL + REUPE),
    "k100_f2low_rvol_reupE": ("ETH kept 100% + re-entry", "k100_f2low_rvol + reupE", KEEP("1") + F2LOW + RVOL + REUPE),
    "k100_fmin_rvol_reupE": ("ETH kept 100% + F lowest + re-entry", "k100, fmin, rvol and reupE",
                             KEEP("1") + FMIN + RVOL + REUPE),
})

# ---- EXP-184 (/goal 2026-10-21: same IS / OOS rules as EXP-183, the gain must come from the LP earning more). Base =
# EXP-183's k100_f2low_rvol_reupE (LP only while ETH is weak, +-20%). IS LP accounting of the base (LP_ACC): fees +0.610
# ETH, IL −0.287, LP edge (fees + IL) +0.323; k75 (LP also while strong) +0.296: the weak-side LP earns about 2x its IL,
# the strong-side LP does not. Batch 1: concentrate the weak-side LP (fees and IL both scale with concentration while the
# price stays in range; out-of-range rebuilds cost swaps).
BASE184 = KEEP("1") + F2LOW + RVOL + REUPE
RANGES = 'RANGE_STRONG, RANGE_WEAK = Decimal("0.10"), Decimal("0.20")'
VARIANTS.update({
    "k100_reupE_weak10": ("LP width while weak", "+-10% instead of +-20% on the EXP-183 best",
                          BASE184 + [(RANGES, RANGES.replace('Decimal("0.20")', 'Decimal("0.10")'), 1)]),
    "k100_reupE_weak5": ("LP width while weak", "+-5% instead of +-20% on the EXP-183 best",
                         BASE184 + [(RANGES, RANGES.replace('Decimal("0.20")', 'Decimal("0.05")'), 1)]),
})
# EXP-184 batch 2 (after batch 1's IS results): narrowing the weak-side LP raised fees 1.6x / 2.4x but IL 4x / 7.7x
# (edge +0.324 -> −0.145 / −0.757): recentring locks IL in, and a narrow range recentres more. Try the other way.
VARIANTS.update({
    "k100_reupE_weak30": ("LP width while weak", "+-30% instead of +-20% on the EXP-183 best",
                          BASE184 + [(RANGES, RANGES.replace('Decimal("0.20")', 'Decimal("0.30")'), 1)]),
    "k100_reupE_weak40": ("LP width while weak", "+-40% instead of +-20% on the EXP-183 best",
                          BASE184 + [(RANGES, RANGES.replace('Decimal("0.20")', 'Decimal("0.40")'), 1)]),
})
# EXP-184 batch 3 (after batch 2's IS results: +-30 / +-40 lose too, edge +0.225 / +0.171; +-20 is near the best width;
# fees / IL ratio 0.87 at +-10, 2.1 at +-20..40). All 117 IS rebuilds of the base are drift rebuilds (F or strength
# changes), none out of range; 29 of them keep an LP and still recentre it. And the strong-side LP of k75 (+-10%) did
# not pay for itself, a ratio wider ranges improve.
RANGE_LINE = "            tick_lo, tick_hi = range_ticks(current_tick, ratio, self.utils.params.tick_spacing)\n"
VARIANTS.update({
    "k100_reupE_lpresize": ("LP rebuild", "a drift rebuild keeps the old LP range (resizes the liquidity) while the price is "
                            "inside it and the width is unchanged; only a new width or an out-of-range price recentres",
                            BASE184 + [(RANGE_LINE, RANGE_LINE +
                                        "            if old and old[0] <= current_tick < old[1] and old[1] - old[0] == tick_hi - tick_lo:\n"
                                        "                tick_lo, tick_hi = old  # v2_goal EXP-184 lpresize\n", 1)]),
    "k75s20_reupE": ("strong-side LP", "25% of F as LP while strong (ETH_KEEP 0.75) at +-20% instead of +-10%",
                     KEEP("0.75") + F2LOW + RVOL + REUPE + [(RANGES, RANGES.replace('Decimal("0.10")', 'Decimal("0.20")'), 1)]),
    "k75s30_reupE": ("strong-side LP", "25% of F as LP while strong (ETH_KEEP 0.75) at +-30%",
                     KEEP("0.75") + F2LOW + RVOL + REUPE + [(RANGES, RANGES.replace('Decimal("0.10")', 'Decimal("0.30")'), 1)]),
})
# EXP-184 batch 4 (after batch 3's IS results, all lost, and an IS-only look at the base's 58 LP positions): the edge
# comes from positions that live >= 6 days (+0.374 of +0.324), and is highest while R = ETH/BTC ranges (30-day
# efficiency ratio lowest tercile +0.159); +-10% lost overall because it recentred through volatile spells. Narrow the
# weak-side LP only in calm or ranging R, judged on the day's close like F.


def WIDTH(code: str) -> list:
    """Weak-side LP half width from a daily column `wk` (code sets it from r); strong side unchanged."""
    return BASE184 + [(RVOL_LINE, RVOL_LINE +
                       "    _lr = _np.log(r).diff()  # v2_goal EXP-184 width rule\n" + code, 1),
                      (ALLOC_CALL, ALLOC_CALL +
                       '        if not strong and "wk" in row and row["wk"] == row["wk"]:  # v2_goal EXP-184 width rule\n'
                       '            ratio = Decimal(str(row["wk"]))\n', 1)]


VARIANTS.update({
    "k100_reupE_volwidth": ("LP width while weak", "+-10% while R's 30-day realized vol (annualized) < 30%, else +-20%",
                            WIDTH("    _rv = _lr.rolling(30).std() * 365 ** 0.5\n"
                                  '    out["wk"] = pd.Series(_np.where(_rv < 0.30, 0.10, 0.20), index=r.index).where(_rv.notna()).reindex(out.index)\n')),
    "k100_reupE_volwidth3": ("LP width while weak", "+-10% / +-20% / +-30% for R's 30-day vol < 30% / 30-45% / > 45%",
                             WIDTH("    _rv = _lr.rolling(30).std() * 365 ** 0.5\n"
                                   '    out["wk"] = pd.Series(_np.select([_rv < 0.30, _rv <= 0.45], [0.10, 0.20], 0.30), index=r.index).where(_rv.notna()).reindex(out.index)\n')),
    "k100_reupE_erwidth": ("LP width while weak", "+-10% while R's 30-day efficiency ratio < 0.12 (ranging), else +-20%",
                           WIDTH("    _er = (r - r.shift(30)).abs() / r.diff().abs().rolling(30).sum()\n"
                                 '    out["wk"] = pd.Series(_np.where(_er < 0.12, 0.10, 0.20), index=r.index).where(_er.notna()).reindex(out.index)\n')),
})
# EXP-184 batch 5 (after batch 4's IS results, all lost: in this pool narrowing raises IL faster than fees even in calm
# R; fees / IL is ~2 only from +-20% up). IS split of k75s30_reupE's positions: the strong-side LP (34 positions) made
# fees +0.036 / IL −0.052 with no profitable subset by R vol, R efficiency, R or G momentum or age. So the lever left is
# more LP capital where fees / IL ~2, the weak side, where the base holds only F as LP and (1 − F) as plain BTC.
# `weakone`: while weak the whole book is ONE LP of the same span, placed so its ETH share is F / 2 (the base's ETH
# exposure: F x 50% in the LP); F = 0 puts it just above the price (all BTC, out of reach of fees until BTC rises).
# A weak-side drift rebuild fires when the LP's ETH share is >= 12.5% off F / 2.
WEAKONE = [
    (WEAK_ALLOC, '    return {"lp": ONE, "eth": ZERO, "btc": ZERO, "usdc": ZERO}, RANGE_WEAK  # v2_goal EXP-184 weakone\n', 1),
    (RANGE_LINE, RANGE_LINE +
     "            if not strong:  # v2_goal EXP-184 weakone: same span, ETH share F / 2\n"
     "                _sp, _S, _best = self.utils.params.tick_spacing, tick_hi - tick_lo, None\n"
     "                for _lo in range((current_tick - _S) // _sp * _sp, current_tick + 1, _sp):\n"
     "                    if _lo <= current_tick < _lo + _S:\n"
     "                        _d = abs(lp_quote_share(current_tick, _lo, _lo + _S) - f / 2)\n"
     "                        if _best is None or _d < _best[0]:\n"
     "                            _best = (_d, _lo)\n"
     "                tick_lo, tick_hi = _best[1], _best[1] + _S\n", 1),
    ('        elif shares["lp"] == ZERO and self.positions:\n',
     "        elif not strong and self.positions and \\\n"
     "                abs(lp_quote_share(tick, self.positions[0][0], self.positions[0][1]) - f / 2) >= FOLLOW_THRESHOLD:\n"
     '            why = "drift >= 12.5%"  # v2_goal EXP-184 weakone\n'
     '        elif shares["lp"] == ZERO and self.positions:\n', 1),
]
VARIANTS.update({
    "k100_reupE_weakone": ("weak-side LP capital", "while weak the whole book is one LP (+-20% span) placed so its ETH share "
                           "is F / 2 (base: F as a centred LP + (1 - F) BTC)", BASE184 + WEAKONE),
    "k100_reupE_weakone30": ("weak-side LP capital", "weakone with a +-30% span",
                             BASE184 + WEAKONE + [(RANGES, RANGES.replace('Decimal("0.20")', 'Decimal("0.30")'), 1)]),
})
# EXP-184 batch 6 (after batch 5's IS results: weakone / weakone30 lose, the off-centre LP is run through by BTC trends,
# IL −1.016 / −0.623). Back to the base's position log on IS: positions living >= 6 days made +0.374, the 39 shorter
# ones −0.05 (19 of them 1-2 days, from F stepping .375 -> .5 -> .75 -> 1 on consecutive days, each step rebuilding
# the LP). Build the weak-side LP only once F has stopped moving; until then hold its share as 50 / 50 ETH / BTC
# tokens (the same exposure as a fresh centred LP, no LP).


def LPWAIT(n: int) -> list:
    stable = " & ".join(f"(_fs == _fs.shift({k}))" for k in range(1, n + 1))
    return BASE184 + [("    out['F'] = _res\n", "    out['F'] = _res\n"
                       "    _fs = pd.Series(out['F'], index=out.index)  # v2_goal EXP-184 lpwait\n"
                       f"    out['fstable'] = {stable}\n", 1),
                      (ALLOC_CALL, ALLOC_CALL +
                       '        if not strong and "fstable" in row and not bool(row["fstable"]) and shares["lp"] > ZERO:  # v2_goal EXP-184 lpwait\n'
                       '            shares = {"lp": ZERO, "eth": shares["lp"] / 2, "btc": shares["btc"] + shares["lp"] / 2, "usdc": shares["usdc"]}\n', 1)]


VARIANTS.update({
    "k100_reupE_lpwait2": ("weak-side LP timing", "the LP is built only after F is unchanged for 2 closes; until then its "
                           "share is held as 50 / 50 ETH / BTC tokens", LPWAIT(2)),
    "k100_reupE_lpwait3": ("weak-side LP timing", "the same after 3 unchanged closes", LPWAIT(3)),
})
ARB = "0x2f5e87C9312fa29aed5C179E456625D79015299c"
MAKER_POOL = '    contract_address, fee, chain_name = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, ChainType.ethereum.name  # wbtc/weth\n'

# Logging only (no change in behaviour): write the per-minute net value (ETH, incl. collected rewards in the wallet) as
# daily closes plus minute-level drawdowns, and the spec metrics, to <folder>/v2goal_<mode>.json
MET_LINE = '    metrics["lp_avg_share"] = strat.lp_share_sum / strat.lp_share_days if strat.lp_share_days else ZERO\n'
MET_MORE = MET_LINE + (
    "    _nv = net_value.apply(float)\n"
    "    _usd = usd_series.astype(float)\n"
    "    _nv.resample('1D').last().to_csv(f'{params.folder}/nv_daily_{mode}.csv')\n"
    "    pd.DataFrame(getattr(strat, 'lp_list', [])).to_csv(f'{params.folder}/lp_positions_{mode}.csv', index=False)\n"
    "    import json as _json\n"
    "    _json.dump({'start': str(_nv.index[0]), 'end': str(_nv.index[-1]), 'nv0': float(_nv.iloc[0]), 'nv1': float(_nv.iloc[-1]),\n"
    "                'mdd_eth': float((_nv / _nv.cummax() - 1).min()), 'mdd_usd': float((_usd / _usd.cummax() - 1).min()),\n"
    "                'usd0': float(_usd.iloc[0]), 'usd1': float(_usd.iloc[-1]),\n"
    "                **{k: float(metrics[k]) for k in ('eth_ratio_receipt', 'eth_ratio_end', 'reward_eth', 'btc_ratio', 'usd_ratio',\n"
    "                                                  'swap_cost_eth', 'lp_avg_share')},\n"
    "                'rebuilds': strat.rebuild_count, 'out_of_range': strat.out_of_range_rebuilds,\n"
    "                **{('lp_' + k): float(v) for k, v in getattr(strat, 'lp_acc', {}).items()}},\n"
    "               open(f'{params.folder}/v2goal_{mode}.json', 'w'))\n")


# Logging only (EXP-184, no change in behaviour): LP accounting per position lifetime, in ETH. When a position is removed
# (a rebuild, after its fees were collected) or at the end: fees = rewards collected since it was added, IL = its value
# minus the value of the tokens it was built from at today's price, pnl = value + fees - value when built.
LP_ACC = [
    ("    def rebuild(self, row_data: Snapshot, why: str) -> None:\n",
     "    def _lp_close(self, p) -> None:  # v2_goal EXP-184 LP accounting\n"
     "        o = getattr(self, '_lp_open', None)\n"
     "        if not hasattr(self, 'lp_acc'):\n"
     "            self.lp_acc = {'fees': ZERO, 'il': ZERO, 'pnl': ZERO, 'value_in': ZERO, 'n': ZERO}\n"
     "        if o is None:\n"
     "            return\n"
     "        out, fees = self._lp_value(), self.reward_eth - o[3]\n"
     "        self.lp_acc['fees'] += fees\n"
     "        self.lp_acc['il'] += out - (o[0] * p + o[1])\n"
     "        self.lp_acc['pnl'] += out + fees - o[2]\n"
     "        self.lp_acc['value_in'] += o[2]\n"
     "        self.lp_acc['n'] += 1\n"
     "        if not hasattr(self, 'lp_list'):\n"
     "            self.lp_list = []\n"
     "        self.lp_list.append({'open': str(o[4]), 'close': str(getattr(self, '_now', '')), 'p_open': float((o[2] - o[1]) / o[0]) if o[0] else 0.0,\n"
     "                             'p_close': float(p), 'value_in': float(o[2]), 'fees': float(fees), 'il': float(out - (o[0] * p + o[1]))})\n"
     "        self._lp_open = None\n"
     "\n"
     "    def rebuild(self, row_data: Snapshot, why: str) -> None:\n", 1),
    ("        self.collect_fees(p)\n        old = (self.positions[0][0], self.positions[0][1]) if self.positions else None\n",
     "        self.collect_fees(p)\n        self._now = row_data.timestamp\n        self._lp_close(p)\n"
     "        old = (self.positions[0][0], self.positions[0][1]) if self.positions else None\n", 1),
    ("                self.positions.append(position)\n",
     "                self.positions.append(position)\n"
     "                self._lp_open = (used_base, used_quote, used_base * p + used_quote, self.reward_eth, row_data.timestamp)\n", 1),
    ("        self.collect_fees(p)\n        lp_value = self._lp_value()\n        assets = (",
     "        self.collect_fees(p)\n        self._now = row_data.timestamp\n        self._lp_close(p)\n"
     "        lp_value = self._lp_value()\n        assets = (", 1),
]


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
    if seg.startswith("arb"):   # EXP-182: Arbitrum WBTC/WETH 0.05% (same token order and spacing as 0x4585)
        text = sub(text, MAKER_POOL, MAKER_POOL.replace("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", ARB), 1)
    for pattern, repl, n_expected in VARIANTS[variant][2] + LP_ACC:
        text = sub(text, pattern, repl, n_expected)
    return sub(text, MET_LINE, MET_MORE, 1)


def binance_files(dst: Path):
    """Maker's daily closes extended to END from samples/binance_daily_closes.csv (same date convention)."""
    long = pd.read_csv(MAIN / "samples/binance_daily_closes.csv", parse_dates=["date"]).set_index("date")
    end = pd.Timestamp(*DATA_END)
    for name, ext in (("binance_ethusdt_1d.csv", long["ETHUSDT"]), ("binance_btcusdt_1d.csv", long["BTCUSDT"]),
                      ("binance_ethbtc_1d.csv", long["ETHUSDT"] / long["BTCUSDT"])):
        s = pd.read_csv(dst / name, parse_dates=["date"]).set_index("date")["close"]
        out = pd.concat([s, ext.loc[s.index[-1] + pd.Timedelta(days=1):end]]).rename("close")
        assert out.index[0] == pd.Timestamp(2017, 8, 17) and out.index[-1] == end
        assert (out.index[1:] - out.index[:-1]).max() == pd.Timedelta(days=1)
        out.rename_axis("date").reset_index().assign(date=lambda f: f["date"].dt.strftime("%Y-%m-%d")).to_csv(dst / name, index=False)


def source() -> Path:
    src = WORK / "_src"
    ethbtc = src / "samples/strategy-example/binance_ethbtc_1d.csv"
    if ethbtc.exists() and pd.read_csv(ethbtc)["date"].iloc[-1] < "%04d-%02d-%02d" % DATA_END:
        shutil.rmtree(src)   # a cache built before DATA_END moved: rebuild it (same closes up to the old end)
    if not src.exists():
        blob = subprocess.run(["git", "-C", str(REPO), "archive", REF, "samples/strategy-example"],
                              check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(blob)).extractall(src)
        if (src / "samples/strategy-example/binance_ethbtc_1d.csv").exists():   # the remix version has no Binance files
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
    js = list((se / "result").rglob("v2goal_*.json"))   # v2goal_signal.json, or v2goal_plain.json for `plain`
    for f in list((se / "result").rglob("*.csv")):
        shutil.copy(f, dst / f.name)
    for f in js:   # one mode per run: stored under the signal name so metrics / table read every run alike
        shutil.copy(f, dst / "v2goal_signal.json")
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


def significant(m: dict, b: dict) -> bool:
    """EXP-180 bar (Dino: 報酬跟回撤要有顯著的增進): CAGR >= v2 + 2 pts and max DD at least 3 pts shallower (in ETH)."""
    return m["cagr"] >= b["cagr"] + 0.02 and m["mdd"] >= b["mdd"] + 0.03 and m["calmar"] >= b["calmar"]


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
                     "v2_calmar": b and b["calmar"], "beats_v2": bool(b) and variant != "v2" and better(m, b),
                     "significant": bool(b) and variant != "v2" and significant(m, b)})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "runs.csv", index=False)
    return df


if __name__ == "__main__":
    if sys.argv[1] == "table":
        print(table().to_string())
        sys.exit()
    if sys.argv[1] == "judge":   # EXP-183: python v2_goal.py judge <seg> <base> <variant,...> (better() vs that base)
        seg, base = sys.argv[2], metrics(sys.argv[2], sys.argv[3])
        for v in [sys.argv[3]] + sys.argv[4].split(","):
            m = metrics(seg, v)
            edge = m.get("lp_fees", math.nan) + m.get("lp_il", math.nan)   # EXP-184 LP edge = fees + IL (ETH)
            lp_up = edge > base.get("lp_fees", math.nan) + base.get("lp_il", math.nan)
            print(f"{seg:5} {v:34} cagr {m['cagr']:7.2%} dd {m['mdd']:6.1%} calmar {m['calmar']:.3f} "
                  f"usd x{m['usd_ratio']:.3f} usd-dd {m['mdd_usd']:6.1%} rebuilds {m['rebuilds']:3} "
                  f"lp fees {m.get('lp_fees', math.nan):.3f} il {m.get('lp_il', math.nan):+.3f} edge {edge:+.3f} "
                  f"{'base' if v == sys.argv[3] else ('BEATS' if better(m, base) else 'loses') + (' lp-up' if lp_up else ' lp-down')}")
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
