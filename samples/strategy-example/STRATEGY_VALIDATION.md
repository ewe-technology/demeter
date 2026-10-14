# Strategy validation (`strategy_validation.py`)

Five generic checks that need only a backtest's net-value series. Any strategy backtested in Demeter can be scored the
same way. First used on Maker's defense v1 / v2 / v3 (QUAN-1129): results in
`experiments/VALIDATION-2026-10-13-defense-v1-v3-demeter.md` ("Final scorecard"), method notes and references in
`experiments/RESEARCH-2026-10-13-strategy-validation.md`, slides https://claude.ai/artifact/1rmNEUAYUosctoz7sLVBwh.

## The five methods

| # | method | what it answers | how | pass bar (default) |
|---|---|---|---|---|
| 1 | real-data backtest | how much does it make | terminal, CAGR, max drawdown of the net value | terminal > initial |
| 2 | parameter plateau | is the result a lucky parameter value | profit of neighbour-parameter runs ÷ chosen run's profit − 1 | every neighbour within ±25 % |
| 3 | significance | is the mean daily return really above 0 | PSR (Bailey & López de Prado 2012) on daily log returns, plus a one-sided stationary bootstrap of the mean (Politis & Romano 1994, mean block 20 d, 5,000 draws) | PSR ≥ 0.95 |
| 4 | forward kill line | where to stop once live | 5th percentile of 90-day returns from stationary-bootstrapped daily returns (10,000 draws) | rule only |
| 5 | Monte Carlo | how bad can one year get | 10,000 one-year paths of stationary-bootstrapped daily returns (mean block 90 d): max drawdown median / 5th pct, loss probability | stress figure only |

Verdict per pool: method 1 or 2 fails → `not for deployment`; 1 and 2 pass → `pilot`; 3 also passes → `deployable`.

Formulas: r_t = ln(V_t / V_t−1) on the last net value of each day; SR = mean(r) / std(r) (annual × √365);
D = √(1 − skew·SR + (kurt − 1)/4·SR²); PSR = Φ(SR·√(T − 1) / D); bootstrap p = share(boot mean − mean ≥ mean);
kill line = exp(P5 of 90-day sums) − 1; Monte Carlo path E_t = exp(Σ r*), max DD = min(E_t / max_(s≤t) E_s − 1).

## Run it

1. Backtest the strategy in Demeter and save the net value. Demeter scripts can write it right after `actuator.run()`:

   ```python
   pd.DataFrame({"net_value": actuator.account_status_df["net_value"]}).to_csv(f"{folder}/netvalue_{name}.csv")
   ```

   One run per pool you want judged; for method 2, also run the chosen pool with each key parameter one step lower
   and one step higher.
2. Score it (from `samples/strategy-example`):

   ```bash
   python strategy_validation.py \
       --pool mainnet=result/my_strategy/mainnet/netvalue.csv \
       --pool base=result/my_strategy/base/netvalue.csv \
       --neighbour low=result/my_strategy/mainnet_low/netvalue.csv \
       --neighbour high=result/my_strategy/mainnet_high/netvalue.csv \
       --initial 100000 --out result/my_strategy/scorecard.json --md result/my_strategy/scorecard.md
   ```

   Neighbours are compared with the first `--pool`. Bars: `--psr-bar`, `--plateau-bar`; other settings in `Settings`.
   In Python: `strategy_validation.scorecard({"mainnet": path}, neighbours={...}, initial=100_000)`.

## Read it carefully

- Everything comes from the backtest as given. Gas, success fees or any cost the backtest did not charge are not in
  the figures; on mainnet a 16-band ladder rebuild costs hundreds of dollars of gas.
- PSR does not correct for how many variants were tried before this one; the more were tried, the more optimistic it is.
- Methods 3-5 resample the strategy's own history; they cannot produce regimes that never happened.
- Short histories (about 3 years or less) rarely reach PSR 0.95 even for a good strategy.
- Resampled figures move by up to about 0.01 between seeds; deterministic figures are exact.

Check: on Maker's v1 / v2 / v3 runs the module reproduces `experiments/scorecard_final_v123.py` exactly for methods 1-3
(PSR, Sharpe, CAGR, max DD, plateau; relative difference 2e-15) and within 0.007 for the resampled figures.
