# EXP-053: downside volatility targeting of F (v6.40)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino).

## Hypothesis

An LP's loss-versus-rebalancing grows with variance (σ²/8 per unit of time, Milionis et al. 2022) while its fees grow
roughly with volume, which tracks σ: fee / LVR worsens in volatility spikes, and in crypto those cluster in sell-offs.
Volatility targeting of exposure cuts the left tail in every asset class studied (Harvey et al. 2018, "The impact of
volatility targeting"; Moreira & Muir 2017). v6 sizes F from trend only. Scaling F down by realised volatility, only
while the close is below EMA100 (so uptrends are never trimmed), should cut the deepest drawdowns (v6 max DD −22.8% ETH,
−17.8% WBTC) at a small fee cost. Honest counter-evidence: v6 earns +9.4% a year in the down / high-vol regime
(`V6_VALIDATION.md` §5) and vol-managed gains often vanish out of sample (Cederburg et al. 2020): CAGR may fall.
This is a size rule, not a width rule (EXP-030 vol-scaled width is a different mechanism).

## Change

`VOL_TARGET = "pool"` (variant `AP`): on every day whose close is ≤ EMA100, the engine's F is multiplied by
min(1, σ* / σ14), σ14 = standard deviation of the last 14 daily log returns of the pool's daily closes, σ* = the asset's
median σ14 over 2019-01-01..2021-04-30 from Binance daily closes (before any pool data and before every window used
here): ETH 0.04179, BTC 0.03219. Days above EMA100: F unchanged. The scaled F feeds v6's follow rule (rebuild when
|F − current| ≥ 12.5%) unchanged. Constants fixed here: 14 days, the two σ*, the EMA100 condition. Everything else
identical to v6.

## Pre-registration

Pre-registered together with EXP-052 and EXP-054 and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev
  windows, warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC
  0.3% 2022-01-01..2022-10-31. v6's own numbers on both are known (EXP-040..051); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and
    max DD no more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- σ* was computed from Binance closes 2019-01..2021-04 while writing this file (an input, no strategy run).
- A 3.5-week smoke test (ETH 2023-06-01..06-25, variants `A,AO,AP,AQ`) checked that the code runs; its numbers are not used.
