"""
Fixed on 2026-10-06, before the backfilled pool data (to 2026-09-30) arrives and before any of it is looked at.
Nothing here may change after the first run on that data: a change made later is a new, separate test and is
reported as one, next to these.

What gets backfilled (the colleague's list): on Ethereum the tails of USDC/USDT 0.01%, wstETH/WETH 0.01% and
WBTC/cbBTC 0.01%; on Arbitrum the tails of WETH/USDC and WBTC/WETH 0.05% and new USDC/USDT, wstETH/WETH and
WBTC/cbBTC 0.01% pools; optionally the BTC/stablecoin pools of both chains.

Five tests, each with its candidates and its verdict rule:
  1. yield layer holdout  A / C x 1 / 3 / 6 tranches on Ethereum, 2026-01-01 ~ 2026-09-30 (cost_matrix.py)
  2. gate price source    derived BTC (ETH/USDC x WBTC/WETH) or a direct BTC/stablecoin pool
  3. BTC/stablecoin LP    a diagnostic like vol_lp_check.py; no strategy is designed unless it passes
  4. Arbitrum             the same rules and parameters as Ethereum, never re-picked on Arbitrum data
  5. depeg stress         fixed synthetic shocks to the wstETH and cbBTC sleeves

The verdict functions read the per-offset rows that cost_matrix.py writes (runs*.csv): period, tranches, offset,
version, capital, total, maxDD. A holdout of nine months is short: "consistent" only means the data did not
contradict the in-sample result, not that it proved it.

Run from samples/strategy-example to print the plan:
  python preregistration.py
"""
from dataclasses import dataclass

import pandas as pd

# ---- 1. yield layer holdout (Ethereum) --------------------------------------------------------------------------

HOLDOUT = ("2026-01-01", "2026-10-01")  # end exclusive: the last day is 2026-09-30
EMA_SPAN = 100
VERSIONS = ("A exchange", "A on-chain", "C on-chain")
TRANCHES = (1, 3, 6)  # every offset of each, as in cost_matrix.py
CAPITALS = (None, 10_000, 100_000, 1_000_000)  # None = no gas
HOLDOUT_GWEI = 3  # 2026 has no entry in tri_btc_eth_gate.GAS_GWEI; 2025's value, the one cost_matrix falls back to
HOLDOUT_GWEI_STRESS = (10, 20)  # reported beside it, not used for the verdict
MAX_DD_SLACK = 2.0  # pt: C's median max drawdown may be at most this much deeper than A on-chain's


@dataclass(frozen=True)
class Claim:
    """One in-sample claim from spot_yield_and_basket.md section 14, checked on the holdout."""
    name: str
    capital: str  # as cost_matrix writes it: "$100,000"
    tranches: int
    source: str


CLAIMS = (
    Claim("C beats A on-chain, $100k, 3 tranches", "$100,000", 3, "14.2: +3.1 pt, the recommended live version"),
    Claim("C beats A on-chain, $1M, 3 tranches", "$1,000,000", 3, "14.2: +5.0 pt"),
    Claim("C beats A on-chain, $1M, 6 tranches", "$1,000,000", 6, "14.2: +4.7 pt"),
)
NOT_CLAIMED = "$10k: no on-chain version was recommended, its holdout is shown only"


def one_period(runs: pd.DataFrame) -> pd.DataFrame:
    """The verdicts compare rows paired by offset, so a table must hold one period only."""
    if "period" in runs and runs["period"].nunique() != 1:
        raise ValueError(f"filter runs to one period first, got {sorted(runs['period'].unique())}")
    return runs


def paired_gap(runs: pd.DataFrame, capital: str, tranches: int, column: str) -> pd.Series:
    """C on-chain minus A on-chain in pt, paired by offset."""
    part = runs[(runs["capital"] == capital) & (runs["tranches"] == tranches)].set_index(["version", "offset"])
    return 100 * (part.loc["C on-chain", column] - part.loc["A on-chain", column])


def holdout_verdict(runs: pd.DataFrame) -> pd.DataFrame:
    """Per claim: consistent if the median return gap > 0 and the median drawdown is no more than MAX_DD_SLACK
    deeper; contradicted if the median return gap < 0; otherwise inconclusive."""
    runs = one_period(runs)
    rows = []
    for claim in CLAIMS:
        ret = paired_gap(runs, claim.capital, claim.tranches, "total")
        dd = paired_gap(runs, claim.capital, claim.tranches, "maxDD")  # negative = C's drawdown is deeper
        if ret.median() > 0 and dd.median() >= -MAX_DD_SLACK:
            verdict = "consistent"
        elif ret.median() < 0:
            verdict = "contradicted"
        else:
            verdict = "inconclusive"
        rows.append({"claim": claim.name, "in-sample": claim.source, "pt med": ret.median(), "pt min": ret.min(),
                     "pt max": ret.max(), "maxDD pt med": dd.median(), "verdict": verdict})
    return pd.DataFrame(rows)


def spread_verdict(runs: pd.DataFrame, capital: str = "$100,000") -> bool:
    """Section 11's other claim: 3 tranches give a narrower range of outcomes over offsets than 1 tranche."""
    runs = one_period(runs)
    c = runs[(runs["version"] == "C on-chain") & (runs["capital"] == capital)]
    width = c.groupby("tranches")["total"].agg(lambda s: s.max() - s.min())
    return bool(width[3] < width[1])


# If the wstETH/WETH gap of 2022-11-15 ~ 2023-06-11 comes back with trades, the FULL period of cost_matrix.py and
# yield_layer.py is rerun and the new numbers are reported next to the old ones. Nothing is re-picked from them.

# ---- 2. gate price source ----------------------------------------------------------------------------------------

# Chosen on data quality, never on backtest return: the return difference is reported but does not decide.
BTC_STABLE_POOLS = {  # Ethereum; per year the one with the highest median daily volume is the direct price
    "WBTC/USDT 0.05%": "0x56534741CD8B152df6d48AdF7ac51f75169A83b2",
    "WBTC/USDC 0.30%": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",
    "WBTC/USDT 0.30%": "0x9db9e0e53058c89e5b94e29621a205198648425b",
}
CLOSE_GAP = 0.005  # a daily close differs when |derived / direct - 1| exceeds this
MAX_GAP_DAYS = 0.01  # switch to the direct price only if more than this share of days differ


def price_source_verdict(derived_close: pd.Series, direct_close: pd.Series) -> str:
    """Daily UTC closes of the derived and the direct BTC price, on the same days."""
    both = pd.concat([derived_close, direct_close], axis=1, join="inner").dropna()
    gap_days = ((both.iloc[:, 0] / both.iloc[:, 1] - 1).abs() > CLOSE_GAP).mean()
    return "switch to direct" if gap_days > MAX_GAP_DAYS else "keep derived"


# ---- 3. BTC/stablecoin LP diagnostic -----------------------------------------------------------------------------

@dataclass(frozen=True)
class LpTest:
    chain: str
    pool: str
    pair: str
    start: str  # first day counted; the 30 days before it only warm up the volatility
    end: str = "2026-09-30"


LP_TESTS = (
    LpTest("ethereum", "0x56534741CD8B152df6d48AdF7ac51f75169A83b2", "WBTC/USDT 0.05%", "2025-01-01"),  # dead before
    LpTest("arbitrum", "0x0e4831319a50228b9e450861297ab92dee15b44f", "WBTC/USDC 0.05%", "2023-07-01"),
)
LP_WIDTHS = (0.10, 0.20)  # +/- around the price, re-centred at 00:00 when out of range; both must pass
LP_CAPITAL = 50_000  # USDC: the BTC half of $100k when the gate is open
LP_MIN_DAYS = 60  # gate-open days a calendar year needs to count


def lp_verdict(daily: pd.DataFrame) -> bool:
    """daily: one row per day with columns width, gate_open (bool) and excess (LP return minus the return of
    holding, as spot, the token mix the position had at 00:00, i.e. an exposure-matched spot).
    Passes only if, at every width, the mean excess on gate-open days is above 0 in every calendar year that has
    LP_MIN_DAYS of them, and there are at least two such years. Otherwise the idea stops, as in vol_lp_check.py."""
    open_days = daily[daily["gate_open"]]
    for _, part in open_days.groupby("width"):
        by_year = part.groupby(part.index.year)["excess"].agg(["mean", "size"])
        counted = by_year[by_year["size"] >= LP_MIN_DAYS]
        if len(counted) < 2 or not (counted["mean"] > 0).all():
            return False
    return True


# ---- 4. Arbitrum -------------------------------------------------------------------------------------------------

ARBITRUM_POOLS = {
    "eth": "0xC6962004f452bE9203591991D15f6b388e09E8D0",  # WETH/USDC 0.05%
    "ratio": "0x2f5e87C9312fa29aed5c179E456625D79015299c",  # WBTC/WETH 0.05%
    "park": "0xbe3ad6a5669dc0b8b12febc03608860c31e2eef6",  # USDC/USDT 0.01%
    "wsteth": "0x35218a1cbac5bbc3e57fd9bd38219d37571b3537",  # wstETH/WETH 0.01%
    "cbbtc": "0x9b42809aaae8d088ee01fe637e948784730f0386",  # WBTC/cbBTC 0.01%
}
ARBITRUM_PERIOD = ("2024-11-22", "2026-10-01")  # from the day after the WBTC/cbBTC pool opened
# Same EMA_SPAN, gate, VERSIONS, TRANCHES and CAPITALS as Ethereum. Swaps are priced from the pool's own
# liquidity at the trade (no flat 10 bps), plus one bridge in and one out at the start and the end.
ARBITRUM_CLAIM = "C on Arbitrum beats A exchange at $10k, 3 tranches"  # the size Ethereum could not serve


def arbitrum_verdict(runs: pd.DataFrame) -> str:
    """runs: Arbitrum per-offset rows at $10k, plus the "A exchange" rows of the same period."""
    runs = one_period(runs)
    part = runs[runs["tranches"] == 3]
    c = part[(part["version"] == "C on-chain") & (part["capital"] == "$10,000")].set_index("offset")["total"]
    a = part[part["version"] == "A exchange"].set_index("offset")["total"]
    gap = 100 * (c - a.reindex(c.index))
    return "consistent" if gap.median() > 0 else "contradicted"


# ---- 5. depeg stress ---------------------------------------------------------------------------------------------

DEPEG_SHOCKS = (  # (sleeve, discount to the peg, days held at that discount before recovering linearly)
    ("wsteth", 0.05, 7), ("wsteth", 0.05, 30),
    ("cbbtc", 0.03, 7), ("cbbtc", 0.03, 30),
)
# Applied at the worst moment for the sleeve (the day the gate is open with the most capital in it) and the
# position exits at the shocked pool price. Reported as pt lost against one year of the sleeve's in-sample gain;
# no pass or fail, it sizes the risk.


if __name__ == "__main__":
    print(__doc__)
    print("holdout", HOLDOUT, f"EMA{EMA_SPAN}", VERSIONS, TRANCHES, CAPITALS, f"{HOLDOUT_GWEI} gwei")
    for claim in CLAIMS:
        print("  claim:", claim.name, "|", claim.source)
    print("  ", NOT_CLAIMED)
    print("gate price pools", BTC_STABLE_POOLS)
    for test in LP_TESTS:
        print("LP test", test, "widths", LP_WIDTHS, "capital", LP_CAPITAL)
    print("arbitrum", ARBITRUM_PERIOD, ARBITRUM_POOLS, "|", ARBITRUM_CLAIM)
    print("depeg shocks", DEPEG_SHOCKS)
