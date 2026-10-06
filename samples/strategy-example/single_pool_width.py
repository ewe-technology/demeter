"""
Step 0b of reports/single_pool_lp_plan.md: does scaling the position's concentration inversely to recent volatility
help, against a fixed width with the same average concentration?

Same idealised position as single_pool_edge.py. A width k scales the per-capital edge by 1 / (1 - k^-1/2), so a
dynamic width is a time-varying multiplier m_t on the +/-10% edge:

  m_t = clip((sigma_ref / sigma_t) ^ a, 0.25, 4)

with sigma_t the realised volatility of the last W hours, known at the start of hour t, and sigma_ref set so that
m averages 1 over train 2022-2023. The multiplier stays fixed when applied to 2024-2025.

The fair benchmark is a fixed width with the same average multiplier, year by year:

  dynamic - matched = sum(m_t edge_t) - mean(m) sum(edge_t)

which is positive only when m is high at the times the edge is high (exposure_check.py made the same point for the
volatility cap). Each variant also runs on top of the shock breaker (top 1%, off 1h), against the breaker alone at
the same average multiplier.

Run from samples/strategy-example:
  python single_pool_width.py
"""
import os

import numpy as np
import pandas as pd

import single_pool_edge as spe

RESULT_DIR = spe.RESULT_DIR
VARIANTS = [(w, a) for w in (24, 168) for a in (1, 2)]  # (W hours, exponent)
CLIP = (0.25, 4.0)


def multiplier(e: pd.DataFrame, hours: int, power: int) -> pd.Series:
    r = e["logp"].resample("1h").last().diff()
    sigma = r.rolling(hours).std().shift(1)  # hour t uses returns up to the end of hour t-1
    train = sigma[spe.in_years(sigma.index, spe.TRAIN)].dropna()
    # sigma_ref such that the clipped multiplier averages 1 over train, by bisection on log sigma_ref.
    lo, hi = np.log(train.min()), np.log(train.max())
    for _ in range(60):
        mid = (lo + hi) / 2
        mean = np.clip((np.exp(mid) / train) ** power, *CLIP).mean()
        lo, hi = (lo, mid) if mean > 1 else (mid, hi)
    m = np.clip((np.exp(lo) / sigma) ** power, *CLIP).fillna(1.0)
    return m.reindex(e.index, method="ffill").fillna(1.0)


def breaker(e: pd.DataFrame) -> pd.Series:
    hour_ret = e["logp"].resample("1h").last().diff().abs()
    cut = hour_ret[spe.in_years(hour_ret.index, spe.TRAIN)].quantile(0.99)
    blocked = (hour_ret > cut).astype(int).shift(1).fillna(0) > 0
    return spe.to_minutes(~blocked, e.index)


def row(name: str, edge: pd.Series, m: pd.Series) -> dict:
    out = {"rule": name}
    for y in spe.YEARS:
        sel = edge.index.year == y
        scale = sel.sum() / spe.MIN_PER_YEAR
        out[f"{y} dyn"] = (edge[sel] * m[sel]).sum() / scale
        out[f"{y} matched"] = m[sel].mean() * edge[sel].sum() / scale
        out[f"{y} mean m"] = m[sel].mean()
    return out


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for name, (address, fee_rate) in spe.POOLS.items():
        e = spe.edge_frame(spe.load_minutes(address), fee_rate)
        edge = e["fee"] - e["loss"]
        gated = edge.where(breaker(e), 0.0)
        rows = []
        for hours, power in VARIANTS:
            m = multiplier(e, hours, power)
            rows.append(row(f"width W{hours}h a{power}", edge, m))
            rows.append(row(f"width W{hours}h a{power} + breaker", gated, m))
        t = pd.DataFrame(rows)
        print(f"\n===== {name}  (per-year edge of the +/-10% reference, dynamic vs fixed at the same mean multiplier)")
        print(t.round(4).to_string(index=False))
        t.to_csv(f"{RESULT_DIR}/{name}_width.csv", index=False)


if __name__ == "__main__":
    main()
