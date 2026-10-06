"""
Step 0 of reports/single_pool_lp_plan.md: where does a passive LP in ETH/USDC 0.05% or WBTC/WETH 0.05% lose,
and can those moments be named in advance?

No Demeter run. From the pool's own minute bars, for one unit of liquidity L that is always in range:

  fee  = fee_rate x (inAmount0 x p + inAmount1) / currentLiquidity      our pro-rata share of the minute's fees
  loss = (sqrt(p1) - sqrt(p0))^2 / sqrt(p0)                             loss against holding the minute-start mix (LVR)

both in token1 raw units (p = token1 raw per token0 raw = 1.0001^tick). Divided by the value of a position centred at
p0 with range [p0/k, p0 k] (V = 2 sqrt(p0) (1 - k^-1/2) per unit L) they become returns. Summed per year they are
the edge of an always-centred position that never leaves its range and re-centres for free: an upper bound on any
fixed-width LP, since real positions also pay for re-centring and sit out of range. The fee / loss ratio does not
depend on k.

Known biases: close-to-close minute moves miss intra-minute paths (loss a little low); the fee share assumes every
trade crosses our range (fee high, as in lp_capacity.py). Both favour the LP, so a negative edge here is robust.

Five checks, each split train 2022-2023 / test 2024-2025 with every cutoff fixed on train:
  year     edge per year, always in the pool
  shock    leave for N hours after an hour whose |return| is in train's top 1% / 5%
  gate     be in the pool on day d only if trailing fee / trailing loss (known at 00:00) > cutoff
  fomc     leave 17:00-24:00 UTC on FOMC statement days
  hours    leave the hours of the week whose train edge is negative
plus, for WBTC/WETH only, whether a daily ETH/BTC move beyond 2 sigma reverts over the next 1-3 days.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  python single_pool_edge.py
"""
import glob
import os

import numpy as np
import pandas as pd

RESULT_DIR = "result/single-pool-edge"
POOLS = {  # name: (address, fee rate)
    "ethusdc": ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.0005),
    "wbtcweth": ("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.0005),
}
YEARS = range(2022, 2026)
TRAIN, TEST = (2022, 2023), (2024, 2025)
K = 1.10  # reference range +/- 10%; only scales the returns, never their sign
MIN_PER_YEAR = 365 * 24 * 60

# Statement days, 14:00 US Eastern = 18:00 or 19:00 UTC (federalreserve.gov calendars).
FOMC = pd.to_datetime([
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
])


def load_minutes(address: str) -> pd.DataFrame:
    years = {str(y) for y in YEARS}
    files = sorted(f for f in glob.glob(f"../real-data/{address}/*.minute.csv")
                   if os.path.basename(f).split("-")[2] in years)
    cols = ["timestamp", "closeTick", "inAmount0", "inAmount1", "currentLiquidity"]
    df = pd.concat((pd.read_csv(f, usecols=cols) for f in files), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated()]
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1min"))
    df[["closeTick", "currentLiquidity"]] = df[["closeTick", "currentLiquidity"]].ffill()
    df[["inAmount0", "inAmount1"]] = df[["inAmount0", "inAmount1"]].fillna(0.0)
    return df.astype(float)


def edge_frame(df: pd.DataFrame, fee_rate: float) -> pd.DataFrame:
    """Per-minute fee and loss returns of the reference position, plus log pool price."""
    sp = np.power(1.0001, df["closeTick"].to_numpy() / 2)  # sqrt(p), raw units
    sp0 = np.concatenate(([sp[0]], sp[:-1]))
    value = 2 * sp0 * (1 - K ** -0.5)
    flow = df["inAmount0"].to_numpy() * sp0 ** 2 + df["inAmount1"].to_numpy()
    fee = fee_rate * flow / df["currentLiquidity"].to_numpy()
    loss = (sp - sp0) ** 2 / sp0
    return pd.DataFrame({"fee": fee / value, "loss": loss / value, "logp": 2 * np.log(sp)}, index=df.index)


def per_year(m: pd.Series, mask: pd.Series | None = None) -> pd.Series:
    """Annualised sum of a per-minute return over each year, optionally only where mask is True (zero elsewhere)."""
    x = m if mask is None else m.where(mask, 0.0)
    g = x.groupby(x.index.year)
    return g.sum() / (g.size() / MIN_PER_YEAR)


def year_table(e: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({"fee": per_year(e["fee"]), "loss": per_year(e["loss"])})
    t["edge"] = t["fee"] - t["loss"]
    t["fee/loss"] = t["fee"] / t["loss"]
    return t


def in_years(index: pd.Index, years: tuple[int, int]) -> np.ndarray:
    return (index.year >= years[0]) & (index.year <= years[1])


def rule_row(name: str, edge: pd.Series, keep: pd.Series) -> dict:
    """Edge per year when in the pool only where keep is True, next to the base edge, time in pool and exits."""
    base, kept = per_year(edge), per_year(edge, keep)
    row = {"rule": name}
    for y in YEARS:
        row[f"{y} base"] = base[y]
        row[f"{y} rule"] = kept[y]
    row["in pool"] = keep.mean()
    row["exits/yr"] = (keep.astype(int).diff() == -1).sum() / (len(keep) / MIN_PER_YEAR)
    return row


def to_minutes(mask: pd.Series, index: pd.Index) -> pd.Series:
    return mask.reindex(index, method="ffill").fillna(False).astype(bool)


def shock_rules(e: pd.DataFrame, edge: pd.Series) -> list[dict]:
    hour_ret = e["logp"].resample("1h").last().diff().abs()
    rows = []
    for pct in (0.99, 0.95):
        cut = hour_ret[in_years(hour_ret.index, TRAIN)].quantile(pct)
        hit = (hour_ret > cut).astype(int)
        for hours in (1, 4, 12, 24):
            # The bar labelled t covers t .. t+1h; known at t+1h, so it blocks the next `hours` bars.
            blocked = hit.rolling(hours, min_periods=1).max().shift(1).fillna(0) > 0
            rows.append(rule_row(f"shock top{round(100 - pct * 100)}% off {hours}h", edge,
                                 to_minutes(~blocked, e.index)))
    return rows


def gate_rules(e: pd.DataFrame, edge: pd.Series) -> list[dict]:
    daily = e[["fee", "loss"]].resample("1D").sum()
    rows = []
    for fee_days, loss_halflife in ((7, 1), (7, 3), (30, 3)):
        ratio = (daily["fee"].rolling(fee_days).mean() / daily["loss"].ewm(halflife=loss_halflife).mean()).shift(1)
        train = ratio[in_years(ratio.index, TRAIN)].dropna()
        for label, cut in (("1.0", 1.0), ("train p50", train.median()), ("train p75", train.quantile(0.75))):
            rows.append(rule_row(f"gate fee{fee_days}d/lossHL{loss_halflife}d > {label}", edge,
                                 to_minutes(ratio > cut, e.index)))
    return rows


def fomc_rule(e: pd.DataFrame, edge: pd.Series) -> list[dict]:
    keep = pd.Series(~(e.index.normalize().isin(FOMC) & (e.index.hour >= 17)), index=e.index)
    return [rule_row("fomc off 17-24 UTC", edge, keep)]


def hour_rule(e: pd.DataFrame, edge: pd.Series) -> tuple[list[dict], pd.DataFrame]:
    how = e.index.dayofweek * 24 + e.index.hour
    train = in_years(e.index, TRAIN)
    stats = pd.DataFrame({"train": edge[train].groupby(how[train]).mean(),
                          "test": edge[~train].groupby(how[~train]).mean()})
    bad = stats.index[stats["train"] < 0]
    keep = pd.Series(~np.isin(how, bad), index=e.index)
    return [rule_row(f"hours off ({len(bad)} of 168)", edge, keep)], stats


def reversal(e: pd.DataFrame) -> pd.DataFrame:
    """Daily log moves beyond 2 trailing-30d sigma: forward move, signed so that reversion is positive."""
    lp = e["logp"].resample("1D").last()
    r = lp.diff()
    z = r / r.rolling(30).std().shift(1)
    rows = []
    for span, years in (("train", TRAIN), ("test", TEST)):
        sel = in_years(z.index, years) & (z.abs() > 2).to_numpy()
        for fwd in (1, 3):
            f = ((lp.shift(-fwd) - lp) * -np.sign(r))[sel].dropna()
            rows.append({"span": span, "fwd days": fwd, "n": len(f), "mean bp": f.mean() * 1e4,
                         "t": f.mean() / f.std() * np.sqrt(len(f)), "share reverting": (f > 0).mean()})
    return pd.DataFrame(rows)


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for name, (address, fee_rate) in POOLS.items():
        e = edge_frame(load_minutes(address), fee_rate)
        edge = e["fee"] - e["loss"]
        print(f"\n===== {name}  (always-centred +/-{(K - 1) * 100:.0f}% position, returns per year)")
        yt = year_table(e)
        print(yt.round(4))
        # Sanity check against lp_capacity.py section 10.3 (+/-20%, 2025, $10k, fees only): ETH/USDC ~64%, WBTC/WETH ~54%.
        scale = (1 - K ** -0.5) / (1 - 1.2 ** -0.5)
        print(f"fee 2025 rescaled to +/-20%: {yt.loc[2025, 'fee'] * scale:.1%}")
        hours, hour_stats = hour_rule(e, edge)
        rules = pd.DataFrame(shock_rules(e, edge) + gate_rules(e, edge) + fomc_rule(e, edge) + hours)
        print(rules.round(4).to_string(index=False))
        print(f"hour-of-week edge, train vs test rank correlation: "
              f"{hour_stats.corr(method='spearman').iloc[0, 1]:.2f}")
        yt.to_csv(f"{RESULT_DIR}/{name}_years.csv")
        rules.to_csv(f"{RESULT_DIR}/{name}_rules.csv", index=False)
        hour_stats.to_csv(f"{RESULT_DIR}/{name}_hours.csv")
        if name == "wbtcweth":
            rev = reversal(e)
            print(rev.round(3).to_string(index=False))
            rev.to_csv(f"{RESULT_DIR}/{name}_reversal.csv", index=False)


if __name__ == "__main__":
    main()
