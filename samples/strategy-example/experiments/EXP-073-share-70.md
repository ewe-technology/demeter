# EXP-073: ETH share 70% in both trend states (ablation of the EMA100 share switch) (v6.60)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6 builds its ladder with 70% of the value in ETH while the close is above EMA100 and 50% below. EXP-046 removed the upper state (50% always): shallower drawdowns on every window, lower CAGR. The mirror ablation removes the lower state (70% always): more ETH in the ladder below EMA100, where the engine harvests ranges with staged refills on rebounds (EXP-067/068). If the refills below the EMA are where v6 earns, holding more of the asset in those rebounds should add return; the cost is deeper drawdowns in sell-offs. Completes the share-rule ablation pair.

## Change

`SHARE_BELOW_EMA = 0.7` (variant `BL`): the ladder's ETH value share is 70% in both trend states. Everything else is v6's. No new constant (70% is v6's own upper-state value).

## Pre-registration

Pre-registered together with the other two ablations of the same commit (EXP-073..075) and run in the same invocations as
`A` (v6). EXP-074 and EXP-075 are near-copies of each other.

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

(pending)

## Deviations

- Ablations chosen after EXP-052..072 (this goal's results: every rebuild-rule change moved ETH and WBTC in opposite directions; the engine ablations showed which rules carry v6's edge). Smoke test ETH 2022-05-01..06-30 (`BL,BM,BN`, inside the dev data; v6's total there, −7.9%, was seen in EXP-055's smoke test): share 70% −10.5%, the two exit ablations −7.9% with one skipped exit each. The ablations have no constant to adjust.
