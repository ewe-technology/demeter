"""
QUAN-1214 look-ahead audit of ETH-USDC MGL v3.2 and ETH-cbBTC MGL v2.2: truncation test.

For each test date D both strategies run twice from the same start S = D - LEAD_DAYS:
* short: only what a live bot has at D 00:00 UTC, Binance daily closes up to D-1 and pool minutes up to the D 00:00 row;
* long: the scripts' own inputs to D+30 (Binance closes up to D+30, pool minutes to D+30 23:59).
Every logged action with execution time <= D 00:00, the per-minute net value up to D 00:00 and the signal rows up to D-1
must be identical. Any rule that reads a later close, a later minute or a whole-window statistic breaks that.
`--leak` is the positive control: the signal is shifted one day early (D's decision sees D's close), which must FAIL.

Both runs call the scripts' own run_test with the settings of their process_for_date (v3.2: fee-in-range engine fix on,
the validation setting; v2.2: auto reinvest on, the spec default). Two patches, test only: the strategy class records
its instance, and performance_metrics_for_dca records the minute net value and stops run_test there (the short run has
no end-of-run settlement, so the metrics after it would divide by zero).

Usage, from samples/strategy-example with the Rust engine (no PYTHONPATH):
    $PY experiments/lookahead_audit.py v32|v22 [--leak] [YYYY-MM-DD[:pool] ...]   # default: the 5 dates below
Results: RESULT_DIR/<strategy>[-leak]/<D>-short|long/ and summary_<strategy>[-leak].csv.
"""
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

LEAD_DAYS = 120            # S = D - 120: every test window has rebuilds, claims and month-starts before D
TAIL_DAYS = 30             # the long run sees 30 more days of every input
# raw runs go to the main checkout (gitignored, survives removing a worktree)
RESULT_DIR = Path("/Users/dinohuang/Desktop/demeter-momentum/samples/strategy-example/result/quan1214_lookahead")
# test dates: days with a rebuild in the full runs (v3.2 2021-05..2026-08 on 0x88e6; v2.2 mainnet 2022-25 / Base
# 2024-09..2026-08), across years, with month-starts (reinvest day) and both v2.2 token orders
DATES = {
    "v32": [("2022-08-01", "mainnet"), ("2023-03-16", "mainnet"), ("2024-05-01", "mainnet"),
            ("2025-10-07", "mainnet"), ("2026-07-15", "mainnet")],
    "v22": [("2022-07-28", "mainnet"), ("2023-10-02", "mainnet"), ("2024-10-01", "mainnet"),
            ("2025-05-11", "mainnet"), ("2026-04-02", "base")],
}


def _same(a, b) -> bool:
    """Equal, with NaN == NaN (float or Decimal): unset log fields must not count as a difference."""
    nan = lambda x: (isinstance(x, float) and x != x) or (isinstance(x, Decimal) and x.is_nan())
    return (nan(a) and nan(b)) or (not nan(a) and not nan(b) and a == b)


def prefix_diff(short: list, long: list, cutoff: datetime, key: str) -> list:
    """Rows (dicts) of the two runs with `key` time <= cutoff, compared in order: one line per differing row."""
    upto = lambda rows: [r for r in rows if pd.Timestamp(r[key]) <= pd.Timestamp(cutoff)]
    a, b = upto(short), upto(long)
    out = []
    for i in range(max(len(a), len(b))):
        ra, rb = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if ra is None or rb is None:
            r = ra or rb
            out.append(f"{pd.Timestamp(r[key]):%Y-%m-%d %H:%M} row only in the {'short' if rb is None else 'long'} run")
            continue
        fields = [k for k in sorted(set(ra) | set(rb)) if not _same(ra.get(k), rb.get(k))]
        if fields:
            out.append(f"{pd.Timestamp(ra[key]):%Y-%m-%d %H:%M} differs in "
                       + ", ".join(f"{k} ({ra.get(k)!r} vs {rb.get(k)!r})" for k in fields))
    return out


def series_diff(short: pd.Series, long: pd.Series, cutoff: datetime) -> list:
    """Minute values up to the cutoff: empty when identical, else the first differing (or missing) minute."""
    a, b = short.loc[:pd.Timestamp(cutoff)], long.loc[:pd.Timestamp(cutoff)]
    if not a.index.equals(b.index):
        return [f"minutes differ: short {len(a)} up to {a.index[-1]}, long {len(b)} up to {b.index[-1]}"]
    bad = [t for t, x, y in zip(a.index, a, b) if not _same(x, y)]
    return [f"net value first differs at {bad[0]:%Y-%m-%d %H:%M}: {a[bad[0]]} vs {b[bad[0]]} ({len(bad)} minutes)"] if bad else []


class _BacktestDone(Exception):
    """Raised by the patched performance_metrics_for_dca: the backtest is over, its outputs are captured."""


def _capture(module, class_name: str) -> dict:
    """Patch `module` so its run_test leaves the strategy instance and the minute net value in the returned dict."""
    got = {}
    base = getattr(module, class_name)
    if hasattr(base, "_audit_base"):
        base = base._audit_base

    class Recording(base):
        _audit_base = base

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            got["strategy"] = self

    def stop(net_value, *args, **kwargs):
        got["net_value"] = net_value.apply(float)
        raise _BacktestDone

    setattr(module, class_name, Recording)
    module.performance_metrics_for_dca = stop
    return got


def _run(module, class_name: str, call) -> dict:
    got = _capture(module, class_name)
    try:
        call()
    except _BacktestDone:
        pass
    return got


def _cut(market_cls, pool, frame: pd.DataFrame, end: datetime):
    """Minute data up to and including the `end` row, as engine data (MarketData) for run_test."""
    from demeter import MarketInfo
    m = market_cls(MarketInfo("cut"), pool)
    m.data = frame.loc[:pd.Timestamp(end)]
    return m.data


def _load(market_cls, pool, address: str, chain: str, start: date, end: date) -> pd.DataFrame:
    from demeter import MarketInfo
    m = market_cls(MarketInfo("data"), pool)
    m.data_path = f"../real-data/{address}"
    m.load_data(chain, address, start, end)
    return m.data.to_pandas()


def _records(frame: pd.DataFrame) -> list:
    return frame.rename_axis("date").reset_index().to_dict("records")


def _leaky(frame: pd.DataFrame) -> pd.DataFrame:
    """Positive control: the row of day D carries day D+1's signal (the last row repeats its predecessor)."""
    return frame.shift(-1).ffill()


def run_v22(d: date, pool_name: str, leak: bool, folder: Path) -> dict:
    """Short and long run of ETH-cbBTC v2.2 (auto reinvest on) around D, settings of its process_for_date."""
    import gamma_ig_gap_bands_defense_btceth_v2_2 as m
    from demeter import ChainType, TokenInfo
    from demeter.uniswap import UniV3Pool
    from market_v2 import UniLpMarketV2
    from remix_dao_utils import RemixDAOParams
    from rm_types import GlobalParams, RangeStrategy, RescaleFrequency, TestParams

    eth, btc = TokenInfo(name="eth", decimal=18), TokenInfo(name="btc", decimal=8)
    btc_token0, address, chain = m.POOLS[pool_name]
    token0, token1 = (btc, eth) if btc_token0 else (eth, btc)
    fee, start, last = 0.05, d - timedelta(days=LEAD_DAYS), d + timedelta(days=TAIL_DAYS)
    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=Decimal(1), quote_token=eth, base_token=btc,
                      chain_name=chain, contract_address=address, swap_fee=False, init_quote_usdc=Decimal(0))
    bull = RemixDAOParams(tick_spread_upper=60, tick_spread_lower=60, tick_upper_boundary_offset=0,
                          tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                          rescale_tick_lower_boundary_offset=0, init_tick_spread=120, tick_spacing=10,
                          tick_gap_lower=1, tick_gap_upper=1)
    pool = UniV3Pool(token0, token1, fee, eth)
    usdc_pool = UniV3Pool(m.USDC, eth, fee, m.USDC)
    minutes = _load(UniLpMarketV2, pool, address, chain, start, last)
    usdc = _load(UniLpMarketV2, usdc_pool, "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", ChainType.ethereum.name,
                 start, last)
    out = {}
    for run, end, closes_to in (("short", datetime.combine(d, datetime.min.time()), d - timedelta(days=1)),
                                ("long", datetime.combine(last, datetime.max.time()), last)):
        signal = m.binance_signal_frame(closes_to)
        if leak:
            signal = _leaky(signal)
        sub = folder / f"{d}-{run}"
        sub.mkdir(parents=True, exist_ok=True)
        tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1, report_name=f"1eth_{m.MODE_REINVEST}",
                        cal_start_datetime=datetime.combine(start, datetime.min.time()), data_start_date=start,
                        data_end_date=end.date(), folder=str(sub), rescale_frequency=RescaleFrequency.daily)
        data, usdc_data = _cut(UniLpMarketV2, pool, minutes, end), usdc.loc[:pd.Timestamp(end)]
        got = _run(m, "EthBtcMglStrategy",
                   lambda: m.run_test(bull, tp, gp, data, usdc_data, signal, m.MODE_REINVEST))
        s = got["strategy"]
        out[run] = {"logs": {"daily": (s.daily_log, "exec"), "rebuild": (s.rebuild_log, "time"),
                             "reinvest": (s.reinvest_log, "exec")},
                    "signal": signal, "net_value": got["net_value"]}
    return out


def run_v32(d: date, pool_name: str, leak: bool, folder: Path) -> dict:
    """Short and long run of ETH-USDC v3.2 (auto reinvest on, fee-in-range fix on) around D on mainnet 0x88e6,
    settings of its process_for_date."""
    if pool_name != "mainnet":
        raise ValueError("v3.2 runs on mainnet 0x88e6 only here")
    import gamma_maker_defense_ethusdc_v3_2 as m
    m.FEE_IN_RANGE_LIQUIDITY = True   # the validation setting (QUAN-1213); run_test reads it per run
    from demeter import ChainType, TokenInfo
    from demeter.uniswap import UniV3Pool
    from market_v2 import UniLpMarketV2
    from remix_dao_utils import RemixDAOParams
    from rm_types import DcaAddition, DcaTiming, GlobalParams, RangeStrategy, RescaleFrequency, TestParams

    usdc, eth = TokenInfo(name="usdc", decimal=6), TokenInfo(name="eth", decimal=18)
    address, fee, chain = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.05, ChainType.ethereum.name
    start, last = d - timedelta(days=LEAD_DAYS), d + timedelta(days=TAIL_DAYS)
    init_quote = Decimal(100000)
    gp = GlobalParams(token0=usdc, token1=eth, fee=fee, init_quote=init_quote, quote_token=usdc, base_token=eth,
                      chain_name=chain, contract_address=address, swap_fee=False, dca_usdc_amount=Decimal(10000),
                      dca_add_if_non_empty=False, dca_add_timing=DcaTiming.none,
                      init_quote_usdc=init_quote * m.INIT_PRICE, dca_addon_price_percent=Decimal(0),
                      dca_addon_amount_percent=Decimal(0), dca_addition=DcaAddition.none)
    params = RemixDAOParams(tick_spread_upper=410, tick_spread_lower=410, tick_upper_boundary_offset=0,
                            tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                            rescale_tick_lower_boundary_offset=0, init_tick_spread=410, tick_spacing=10,
                            tick_gap_lower=1, tick_gap_upper=1)
    pool = UniV3Pool(usdc, eth, fee, usdc)
    minutes = _load(UniLpMarketV2, pool, address, chain, start, last)
    ratio = Decimal("0.20")
    out = {}
    for run, end, closes_to in (("short", datetime.combine(d, datetime.min.time()), d - timedelta(days=1)),
                                ("long", datetime.combine(last, datetime.max.time()), last)):
        signal = m.binance_daily_frame(start, closes_to)
        if leak:
            signal = _leaky(signal)
        sub = folder / f"{d}-{run}"
        sub.mkdir(parents=True, exist_ok=True)
        tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1, report_name="100000USDC_v32_reinvest",
                        indicator_length_hr=1, to_swap=False, aggressive=True, compound=True,
                        rescale_frequency=RescaleFrequency.daily,
                        cal_start_datetime=datetime.combine(start, datetime.min.time()), data_start_date=start,
                        data_end_date=end.date(), folder=str(sub), initial_swap=True, flip_param_dates=[],
                        start_with_bull_param=True, initial_type=1, starting_mark_price=Decimal(20))
        data = _cut(UniLpMarketV2, pool, minutes, end)
        usd = pd.DataFrame(index=pd.date_range(start=start, end=end, freq="min"), data={"price": Decimal(1)})
        got = _run(m, "RemixDaoDcaWeekStratStrategy",
                   lambda: m.run_test(params, params, tp, gp, data, usd, shape="inverted_gaussian_spec_price",
                                      upper_ratio=ratio, lower_ratio=ratio, half_gap=0, eth_share=m.EMA_SHARE,
                                      daily_ema=signal, deploy=m.DEPLOY_SIGNAL))
        s = got["strategy"]
        out[run] = {"logs": {"rebuild": ([vars(e) for e in s.export_actions], "time"),
                             "reinvest": (s.reinvest_log, "date"), "daily": (s.fee_log, "date")},
                    "signal": signal, "net_value": got["net_value"]}
    return out


RUNNERS = {"v32": run_v32, "v22": run_v22}


def truncation_test(strategy: str, d: date, pool_name: str, leak: bool) -> dict:
    """One date: run short and long, compare everything up to D 00:00. Returns one summary row."""
    folder = RESULT_DIR / f"{strategy}{'-leak' if leak else ''}"
    runs = RUNNERS[strategy](d, pool_name, leak, folder)
    short, long = runs["short"], runs["long"]
    cut = datetime.combine(d, datetime.min.time())
    row = {"strategy": strategy, "pool": pool_name, "D": d, "start": d - timedelta(days=LEAD_DAYS), "leak": leak}
    problems = []
    for name, (rows, key) in short["logs"].items():
        long_rows = long["logs"][name][0]
        problems += [f"{name}: {p}" for p in prefix_diff(rows, long_rows, cut, key)]
        upto = [r for r in long_rows if pd.Timestamp(r[key]) <= pd.Timestamp(cut)]
        row[f"{name}_rows"] = len(upto)
        row[f"{name}_on_D"] = sum(pd.Timestamp(r[key]) == pd.Timestamp(cut) for r in upto)
    problems += [f"signal: {p}" for p in prefix_diff(_records(short["signal"]), _records(long["signal"]),
                                                      cut - timedelta(days=1), "date")]
    problems += series_diff(short["net_value"], long["net_value"], cut)
    row["signal_rows"] = len(short["signal"])
    row["minutes"] = len(short["net_value"].loc[:pd.Timestamp(cut)])
    row["mismatches"] = len(problems)
    row["verdict"] = "PASS" if not problems else "FAIL"
    row["first_mismatch"] = problems[0] if problems else ""
    for p in problems[:20]:
        print(f"  {strategy} {d}: {p}")
    print(f"{strategy} {d} ({pool_name}{', leak' if leak else ''}): {row['verdict']}, {row['mismatches']} mismatches")
    return row


# v3.2 spec section 6: a daily claim also needs the estimated gas <= $0.2 (not modelled in the backtest). Gas units are
# assumptions: one Uniswap v3 collect ~75k; the full ladder = 16 collects + one ETH -> USDC swap ~120k
CLAIM_GAS_UNITS = {"one collect": 75_000, "16 collects + swap": 16 * 75_000 + 120_000}
CLAIM_GAS_MAX_USD = 0.2


def gas_claim_share(gwei: pd.Series, eth_usd: pd.Series, units: int, max_usd: float = CLAIM_GAS_MAX_USD) -> pd.Series:
    """Per calendar year, the share of 00:00 UTC judgements whose claim (`units` gas at the last gas price and ETH/USD
    sample at or before 00:00) costs at most `max_usd` on Ethereum mainnet."""
    days = pd.date_range(gwei.index[0].normalize() + pd.Timedelta(days=1), gwei.index[-1].normalize(), freq="D")
    g = gwei.sort_index().reindex(days, method="ffill")
    p = eth_usd.sort_index().reindex(days, method="ffill")
    cost = units * g * 1e-9 * p
    return (cost <= max_usd).groupby(days.year).mean()


def gas_report() -> pd.DataFrame:
    gwei = pd.read_csv("../gas_ethereum_hourly.csv", parse_dates=["timestamp"]).set_index("timestamp")["gwei"]
    usd = pd.read_csv("../eth_usd_hourly.csv", parse_dates=["timestamp"]).set_index("timestamp")["usd"]
    table = pd.DataFrame({k: gas_claim_share(gwei, usd, u) for k, u in CLAIM_GAS_UNITS.items()})
    print(f"share of days a mainnet claim costs <= ${CLAIM_GAS_MAX_USD} at 00:00 UTC:")
    print(table.round(3).to_string())
    return table


def main(argv: list) -> None:
    if argv[0] == "gas":
        gas_report()
        return
    strategy, leak = argv[0], "--leak" in argv
    picks = [a for a in argv[1:] if a != "--leak"]
    dates = [(p.split(":") + ["mainnet"])[:2] for p in picks] if picks else DATES[strategy]
    rows = [truncation_test(strategy, date.fromisoformat(day), pool, leak) for day, pool in dates]
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows)
    path = RESULT_DIR / f"summary_{strategy}{'-leak' if leak else ''}.csv"
    summary.to_csv(path, index=False)
    print(summary.to_string(index=False))
    print(path)


def _self_check():
    t = lambda s: datetime.fromisoformat(s)
    cut = t("2024-05-01 00:00")
    long = [{"time": t("2024-04-30 00:00"), "F": 0.5}, {"time": t("2024-05-01 00:00"), "F": 0.25},
            {"time": t("2024-05-02 00:00"), "F": 0.0}]
    # rows after the cutoff do not count; equal prefixes give no mismatch
    assert prefix_diff(long[:2], long, cut, "time") == []
    # a changed value at the cutoff minute is reported with its time and field
    short = [long[0], {"time": t("2024-05-01 00:00"), "F": 0.3}]
    diff = prefix_diff(short, long, cut, "time")
    assert len(diff) == 1 and "2024-05-01 00:00" in diff[0] and "F" in diff[0], diff
    # a row only one run has (an action skipped or added) is reported
    diff = prefix_diff(long[:1], long, cut, "time")
    assert len(diff) == 1 and "2024-05-01 00:00" in diff[0], diff
    # NaN equals NaN (unset log fields); the time key may be a string date
    nan = [{"date": "2024-04-30 00:00", "x": float("nan")}]
    assert prefix_diff(nan, nan, cut, "date") == []
    # minute net value: equal up to the cutoff, the first differing minute is named
    idx = pd.date_range("2024-04-30 23:58", periods=4, freq="min")
    a = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    assert series_diff(a.iloc[:3], a, cut) == []
    b = a.copy()
    b.iloc[2] = 3.5
    assert "2024-05-01 00:00" in series_diff(a.iloc[:3], b, cut)[0]
    assert series_diff(a.iloc[:2], a, cut)   # a missing minute is a mismatch
    # gas: 75k gas x 1 gwei x $2,000 = $0.15 (passes $0.2); 2 gwei = $0.30 (fails). The 00:00 judgement uses the last
    # sample before it: 01-02 sees 01-01 23:00's 2 gwei (fails, not 00:30's 1 gwei), 01-03 and 01-04 see 1 gwei (pass)
    ts = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 23:00", "2024-01-02 00:30", "2024-01-03 01:00",
                         "2024-01-04 01:00"])
    gwei = pd.Series([1.0, 2.0, 1.0, 1.0, 1.0], index=ts)
    usd = pd.Series(2000.0, index=ts)
    assert gas_claim_share(gwei, usd, 75_000).tolist() == [2 / 3], gas_claim_share(gwei, usd, 75_000)


if __name__ == "__main__":
    _self_check()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # the strategy scripts
    if len(sys.argv) > 1 and sys.argv[1] != "gas":
        import engine_guard
        engine_guard.require_rust("lookahead_audit.py")
    if len(sys.argv) > 1:
        main(sys.argv[1:])
