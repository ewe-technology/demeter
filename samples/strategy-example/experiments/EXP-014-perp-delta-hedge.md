# EXP-014: partial perp delta hedge — short 60% of the ladder's ETH delta on Binance USDT-M (v6.11)

- Version: v6.11
- Jira: [QUAN-860](https://ewetechnology.atlassian.net/browse/QUAN-860)
- Status: pre-registered
- Pre-registration commit: 599f492 (implementation e81b196, 9e66e97) · Result commit: ______
- Literature: `RESEARCH-2026-09-30-lp-literature.md` §2.

## Hypothesis

v6's variance is market exposure: beta to ETH 0.22, and the three drawdowns past −20% are ETH falls the ladder
was deployed into (`V6_VALIDATION.md` §4). An LP position's delta is exactly the ETH it holds in the bands
(dV/dP = x for a Uniswap v3 position), so the exposure can be removed with a short perpetual of the same size.
Milionis et al. (arXiv 2208.06046) show that a hedged LP is left with fees − LVR; Lipton, Lucic and Sepp (arXiv
2407.05146) give the dynamic hedge with perps and note that short perps have on average *earned* funding; arXiv
2603.19716 finds that with collateralised hedging the optimal hedge ratio is 50–70%, not 100%, because of
liquidation risk. Hedging is the one direction in the literature pass that removes exposure instead of adding it
(the dropped EXP-001 sleeve added delta), and it is the diagnostic for how much of v6's +85% is fee alpha rather than
the F engine's ETH beta.

Expected: max drawdown and Calmar improve materially; total return falls in the bull years (2023, 2024) and rises
in 2022; funding is a tailwind when positive (2023–25 mostly) and a cost in 2022. The test is risk-adjusted, so the
rule below is Calmar / Sharpe / drawdown, with the yearly return table reported but not deciding.

## Change

`HEDGE = 0.6` (v6: 0), `HEDGE_FEE = 0.0005` (Binance USDT-M taker), `HEDGE_FUNDING` = the symbol's 8h funding
history (`samples/fetch_binance_funding.py`, committed CSV; ETHUSDT for the ETH pools, BTCUSDT for WBTC/USDC).

- Target short = `HEDGE` × (base tokens held inside the bands), i.e. 60% of the ladder's delta. The reserve (USDC)
  and collected fees are not hedged. Free base outside the bands is zero in v6.
- The short is set to target right after every build / rebuild and once a day at 00:00 UTC (the follow check's
  time), trading the difference at the pool price (perp basis ignored) and paying `HEDGE_FEE` on the traded
  notional. No band constant: daily to target.
- Settled daily: the short's price PnL (mark vs current pool price on the open size) and each 8h funding payment
  (`rate × notional`, positive rate = the short receives) go to the USDC balance. The margin account is part of the
  book: hedge losses reduce the deployable capital F × equity and gains add to it (unlike EXP-004's interest, which
  was kept out of the ladder — a hedge loss cannot be, it is paid from the reserve).
- Margin: `HEDGE_LEVERAGE = 5`: at every build the short's initial margin (notional / 5 ≈ 0.6 × s × F / 5 of equity,
  at most 8.4%) is held back in USDC outside the ladder, so the ladder deploys F × (1 − 0.6 s / 5) of equity. The
  follow check still targets the raw F (the ~8% gap is inside its 12.5% threshold, so no extra rebuilds).
  Settlements are paid from the USDC balance; if a loss between two builds exceeds it the balance goes negative
  (margin call territory) and the lowest balance is reported. Liquidation is not modelled; max notional / equity is
  reported.
- Not modelled: perp-pool basis, funding on intraday size changes between settlements (the settlement-time size is
  used), exchange counterparty risk, slippage (a $100k book is negligible on ETHUSDT).
- Everything else identical to v6.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC), ETHUSDT funding; continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3%
  2022-11-01..2026-09-17 (BTCUSDT funding) reported. v6 (A) and this (K) in the same invocation.
- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), yearly
  segments 2024, 2025, 2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17 run, ETHUSDT funding. v6's
  numbers on this pool are known from EXP-004; no run of this variant has touched it.
- Success rule (risk-reduction variant: the return table is reported, not deciding):
  - Dev: continuous ETH Calmar ≥ v6's 0.61 **and** Sharpe ≥ v6's 0.73 **and** max DD shallower than v6's −22.8%
    **and** continuous total return ≥ +40% (at least half of v6's gain kept, so "hold cash" cannot pass).
    Otherwise `dropped-at-dev`.
  - Holdout: continuous Base Calmar ≥ v6's **and** max DD shallower **and** total return ≥ half of v6's →
    `holdout-pass`, else `holdout-fail`.

## Result

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|

Continuous run: total / CAGR / max DD / Sharpe / Calmar / funding received / hedge fees.

Verdict:

## Deviations

- Accounting refinement after the pre-registration commit and before any pre-registered window ran: the first text
  said hedge flows are booked "like the fees" (outside the deployable capital, as EXP-004's interest). That cannot
  hold for losses — a short that loses in a rally is paid from the reserve, and booking it outside the book would let
  the fee bucket go negative and the ladder overdraw. Hedge flows now go to the USDC balance (deployable), and the
  first smoke run (ETH 2021-11..12, outside every pre-registered window) showed why margin must be explicit: with
  F = 1 the whole reserve is in the bands and a $21 settlement found 0 USDC. `HEDGE_LEVERAGE = 5` (initial margin
  held back at each build) was added before any pre-registered window ran. The second smoke run then showed 44
  rebuilds in two months (v6: 5): with the margin outside the ladder the book sits at 0.916 F and the follow
  check's "not fully deployed" branch fired daily; the follow target is now scaled by the same margin factor
  (third smoke run: 3 rebuilds, −1.6% vs v6 −4.8%, hedge PnL +$2.2k, funding +$116, fees $82). Same hedge ratio,
  same rule.
