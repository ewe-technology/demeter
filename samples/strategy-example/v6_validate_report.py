"""
Turn the v6_validate.py runs into the numbers of the validation report:
sensitivity plateau, PBO / deflated Sharpe, continuous-run portfolio metrics, regime split, capacity.

usage: python v6_validate_report.py
"""
import glob
import os
import sys
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis

sys.path.insert(0, "/Users/dinohuang/.claude/plugins/cache/agiprolabs-claude-trading-skills/trading-skills/1.0.0/"
                   "skills/walk-forward-validation/scripts")
from overfit_detector import probability_of_backtest_overfitting  # noqa: E402

R = "result/v6_validate"
ETH_USD = "/Users/dinohuang/Desktop/demeter-momentum/samples/eth_usd_hourly.csv"
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)


def pct(x):
    return (x * 100).round(1)


# ---- 1. sensitivity: one parameter moved at a time, per year -------------------------------------
sens = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(f"{R}/0x88e6-sens-*.csv")))
sens["seg"] = sens["start"].str[:4]
print("errors:", sens.get("error", pd.Series(dtype=object)).notna().sum())
tab = sens.pivot(index="variant", columns="seg", values="net_return")
tab["chained"] = (1 + tab).prod(axis=1) - 1
print("\n== 1. sensitivity, net return (price impact only) ==")
print(pct(tab.sort_values("chained", ascending=False)))
diff = tab.drop(columns="chained").sub(tab.loc["base"].drop("chained"), axis=1)
engine = diff.drop(index=["base", "plain_lp"])
print("\nvariant minus base, pts: median", pct(engine.median(axis=1)).to_dict())
print("share of (variant, year) cells within ±5 pts of base:", round(float((engine.abs() <= 0.05).mean().mean()), 2))
print("v6 variants beating plain LP, per year:",
      (tab.drop(index=["plain_lp"]).drop(columns="chained") > tab.loc["plain_lp"].drop("chained")).mean().round(2).to_dict())


# ---- 2. overfitting: PBO (CSCV) over the 15 v6 variants, deflated Sharpe of base -----------------
def daily_returns(variant: str) -> pd.Series:
    parts = []
    for f in sorted(glob.glob(f"{R}/0x88e6-sens-*/equity_{variant}.csv")):
        eq = pd.read_csv(f, index_col=0, parse_dates=True)["net_value"]
        parts.append(eq.pct_change().dropna())
    return pd.concat(parts)


variants = [v for v in tab.index if v != "plain_lp"]
rets = pd.concat({v: daily_returns(v) for v in variants}, axis=1).dropna()
pbo = probability_of_backtest_overfitting(rets.values, n_groups=10, n_test_groups=5)
print(f"\n== 2. overfitting ==\nPBO over {len(variants)} v6 variants, {len(rets)} days, {pbo.n_paths} CSCV paths: "
      f"{pbo.pbo:.2f} (mean OOS rank of the IS best {pbo.mean_oos_rank:.2f})")
sr = rets.mean() / rets.std()                   # daily, not annualised
sr_var = float(sr.var())
b = rets["base"]
sr0, g3, g4, T = float(sr["base"]), float(skew(b)), float(kurtosis(b, fisher=False)), len(b)
em = 0.5772156649
print(f"base daily SR {sr0:.4f} (annualised {sr0 * np.sqrt(365):.2f}), skew {g3:.2f}, kurtosis {g4:.1f}, T {T}, "
      f"SR dispersion across variants {np.sqrt(sr_var):.4f}")
for n in [10, 50, 200, 1000]:
    e_max = np.sqrt(sr_var) * ((1 - em) * norm.ppf(1 - 1 / n) + em * norm.ppf(1 - 1 / (n * np.e)))
    se = np.sqrt((1 - g3 * sr0 + (g4 - 1) / 4 * sr0 ** 2) / (T - 1))
    print(f"  DSR with {n:>4} trials: {norm.cdf((sr0 - e_max) / se):.3f}")
print(f"  PSR (1 trial, SR > 0): {norm.cdf(sr0 / np.sqrt((1 - g3 * sr0 + (g4 - 1) / 4 * sr0 ** 2) / (T - 1))):.3f}")


# ---- 3. continuous runs: portfolio metrics against holding ---------------------------------------
def metrics(eq: pd.Series) -> dict:
    r = eq.pct_change().dropna()
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (365.25 / days) - 1
    dd = eq / eq.cummax() - 1
    under = (dd < 0).astype(int)
    longest = int(under.groupby((under == 0).cumsum()).sum().max())
    down = r[r < 0]
    return {"total": eq.iloc[-1] / eq.iloc[0] - 1, "CAGR": cagr, "vol": r.std() * np.sqrt(365),
            "maxDD": dd.min(), "sharpe": r.mean() / r.std() * np.sqrt(365),
            "sortino": r.mean() / down.std() * np.sqrt(365), "calmar": cagr / abs(dd.min()),
            "longest_underwater_d": longest}


def continuous(tag: str, price: pd.Series) -> dict:
    base = pd.read_csv(f"{R}/{tag}/equity_base.csv", index_col=0, parse_dates=True)["net_value"]
    lp = pd.read_csv(f"{R}/{tag}/equity_plain_lp.csv", index_col=0, parse_dates=True)["net_value"]
    px = price.reindex(base.index, method="ffill")
    hold = 100000 * px / px.iloc[0]
    half = 50000 + 50000 * px / px.iloc[0]
    rows = {"v6": metrics(base), "plain valley LP": metrics(lp), "hold asset": metrics(hold), "50/50 hold": metrics(half)}
    return pd.DataFrame(rows).T, base, lp, px


eth_px = pd.read_csv(ETH_USD, parse_dates=["timestamp"]).set_index("timestamp")["usd"].resample("1D").last()
eth_tag = [os.path.basename(p) for p in glob.glob(f"{R}/0x88e6-bench-*") if os.path.isdir(p)][0]
eth_tab, eth_v6, eth_lp, eth_daily = continuous(eth_tag, eth_px)
print(f"\n== 3. continuous {eth_tag} ==")
print(eth_tab.round(3))
v6r, er = eth_v6.pct_change().dropna(), eth_daily.pct_change().reindex(eth_v6.index).dropna()
beta = v6r.cov(er) / er.var()
print(f"v6 beta to ETH {beta:.2f}, corr {v6r.corr(er):.2f}, annual alpha {(v6r.mean() - beta * er.mean()) * 365:.1%}")
cont = pd.read_csv(f"{R}/{eth_tag}.csv")
print(cont[["variant", "net_return", "fees", "impact", "gas_if_mainnet", "rebuilds", "max_swap_notional"]].round(0))

btc_tags = [os.path.basename(p) for p in glob.glob(f"{R}/0x99ac-bench-*") if os.path.isdir(p)]
if btc_tags:
    btc_eq = pd.read_csv(f"{R}/{btc_tags[0]}/equity_base.csv", index_col=0, parse_dates=True)["net_value"]
    btc_px = pd.read_csv(f"{R}/btc_daily_close.csv", index_col=0, parse_dates=True)["close"]
    btc_tab, *_ = continuous(btc_tags[0], btc_px)
    print(f"\n== 3b. cross asset {btc_tags[0]} (parameters never fitted on BTC) ==")
    print(btc_tab.round(3))
    print(pd.read_csv(f"{R}/{btc_tags[0]}.csv")[["variant", "net_return", "fees", "impact", "rebuilds"]].round(0))


# ---- 4. regimes: 30 day trend x 30 day realised vol, on ETH daily closes (past data only) ---------
lr = np.log(eth_daily).diff()
trend = np.log(eth_daily).diff(30)
vol = lr.rolling(30).std() * np.sqrt(365)
regime = pd.DataFrame({"trend": np.where(trend > 0.10, "up", np.where(trend < -0.10, "down", "range")),
                       "vol": np.where(vol > vol.median(), "high vol", "low vol")}, index=eth_daily.index)
regime = regime[trend.notna() & vol.notna()]
df = pd.DataFrame({"v6": eth_v6.pct_change(), "plain_lp": eth_lp.pct_change(), "eth": eth_daily.pct_change()}).dropna()
df = df.join(regime.shift(1), how="inner")  # regime known at the start of the day
g = df.groupby(["trend", "vol"])
out = g[["v6", "plain_lp", "eth"]].apply(lambda x: (1 + x).prod() ** (365 / len(x)) - 1)
out["days"] = g.size()
print("\n== 4. regimes (annualised return within each regime) ==")
print(pct(out[["v6", "plain_lp", "eth"]]).assign(days=out["days"]))


# ---- 5. capacity: fee share (lp-math) and price impact scaling (slippage) ------------------------
def pool_fees_usd(year: int) -> float:
    total = 0.0
    for f in sorted(glob.glob(f"../real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640/*-{year}-*.minute.csv")):
        d = pd.read_csv(f, usecols=["inAmount0", "inAmount1", "closeTick"])
        eth = 1e12 / 1.0001 ** d["closeTick"]
        a0, a1 = pd.to_numeric(d["inAmount0"], errors="coerce").fillna(0), pd.to_numeric(d["inAmount1"], errors="coerce").fillna(0)
        total += float((a0 / 1e6 + a1 / 1e18 * eth).sum()) * 0.0005
    return total


s25 = sens[(sens.variant == "base") & (sens.seg == "2025")].iloc[0]
pool25 = pool_fees_usd(2025)
share = s25["fees"] / pool25
print(f"\n== 5. capacity ==\n2025 pool LP fees ${pool25:,.0f}; v6 earned ${s25['fees']:,.0f} = {share:.4%} of them")
print("demeter credits fees as L_ours / L_pool (ours not in the denominator); true share is L/(L_pool + L).")
for aum in [1e5, 1e6, 1e7, 5e7]:
    k = aum / 1e5
    naive = share * k
    true = naive / (1 + naive)
    impact_pct = s25["impact"] / 1e5 * k   # impact ~ notional^2: cost / AUM grows linearly with AUM
    print(f"  AUM ${aum:>12,.0f}: fee overstatement {naive / true - 1:6.1%}, "
          f"2025 price impact {impact_pct:6.2%} of AUM (largest single swap ${s25['max_swap_notional'] * k:,.0f})")
