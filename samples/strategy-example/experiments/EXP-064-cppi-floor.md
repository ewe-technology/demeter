# EXP-064: CPPI floor on the strategy's own net value (v6.51)

- Jira: QUAN-946
- Status: dropped-at-dev
- Pre-registration commit: 9ea5296 · Result commit: 1fd71bb
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6's maximum drawdowns are not crashes: on ETH (−22.8%, 2024-03-11..09-06) and WBTC (−17.8%, 2024-04-08..10-23) they build up
over six months of chop in which the engine's F swings up and down (14 and 24 follow rebuilds in those windows; WBTC's price
even ended higher). The engine reads only price; it does not know the book is bleeding. Constant-proportion portfolio
insurance (Black & Perold 1992; drawdown control, Grossman & Zhou 1993) scales exposure by the cushion above a floor on the
strategy's own value: m = (W/HWM − floor) / (1 − floor). Using v6's own lower stop (0.8) as the floor, the ladder is halved at
a 10% drawdown of the book and emptied at 20%, then refilled as the book recovers. Expected: drawdowns capped near 20% and the
chop bleed cut (Calmar ↑); CAGR ↑ only if the cut periods were net losers — the main risk is a slower recovery with less capital
deployed (counter-evidence: CTA practice reports CPPI costs return in V-shaped recoveries).

## Change

`CPPI_FLOOR = 0.8` (variant `BB`): at the daily 00:00 follow check the target becomes F x m, m = clip((W / HWM − 0.8) / 0.2, 0, 1),
W = total book value (ladder + wallet, paid-out fees included), HWM = the highest W seen at the daily checks since the start.
Everything else (follow threshold, rebuilds, share) is v6's. The floor is v6's LOWER_STOP, not a new constant.

## Pre-registration

Pre-registered together with EXP-065 (same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..063); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `ABBBC`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | -0.2% | -7.8 |
| 2023 | +32.2% | +36.9% | +4.7 |
| 2024 | +36.4% | +17.5% | -18.9 |
| 2025 | +16.3% | +35.5% | +19.3 |
| 2026-01..09-17 | +18.7% | +17.0% | -1.7 |

Wins 2/5, median -1.67 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +46.0% | 8.4% | -18.2% | 0.57 | 0.46 | $49.0k | $0.08k | 432 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +13.2% | 3.3% | -21.1% | 0.28 | 0.15 | $17.4k | $0.52k | 361 |

Verdict: **dropped-at-dev** — ETH CAGR 8.4% vs 14.0%, Calmar 0.46 vs 0.61 (max DD −18.2% vs −22.8%), wins 2/5; WBTC CAGR 3.3% vs 17.3%, Calmar 0.15, max DD −21.1% vs −17.8%. Holdout not run. Reading: the classic CPPI cash lock — on WBTC the multiplier reached 0 (book 20% below its high), the ladder was emptied, and an empty LP book cannot earn its way back to the high-water mark, so it stayed mostly out (fees .4k vs .7k). An LP's return is fee income on deployed capital; de-risking on the book's own drawdown removes exactly the income that would repair it. CPPI and other own-equity overlays are closed for this strategy.

## Deviations

- The drawdown windows of v6 named in the hypothesis were measured on v6's own dev runs (baseline, already known) before this
  file. Smoke test WBTC 2024-03-01..25 (`BB,BC`, no v6 run): runs, m fell to 0.54.
