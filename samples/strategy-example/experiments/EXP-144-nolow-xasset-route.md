# EXP-144: v6.75 + cross-asset refill + routing (one rule for both pools) (v6.130)

- Jira: QUAN-1029
- Status: pre-registered
- Pre-registration commit: f35df2e · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-130's ETH half applied to both pools, with routing on the 0.3% pool: if the cross-asset filter removes false refills on ETH, it should also remove them on WBTC (where each refill swap costs ~6x more).

## Change

Variant `EF`: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`, `SWAP_ROUTE = pool` on every pool.

## Pre-registration

Pre-registered together with EXP-144..148 (same commit), run with `A` (v6) in `A,EF,EG,EH,EI,EJ` per window.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- Designed after EXP-139..143's dev results and before their holdout results were read. EXP-130's cross-asset refill (a refill stage also needs the other asset >= 1.05 x its low since the exit) is the only ETH-side rule besides v6.75 with its own out-of-time gain; it has never run on the 0.3% WBTC pool together with v6.75 (EXP-086 ran it alone and was dropped at dev, H4 never run). EXP-144 / 145 / 148 apply it to both pools as one rule; EXP-146 adds it to EXP-124's WBTC half (new on H4); EXP-147 merges EXP-139's and EXP-140's ETH halves (new on H5).
