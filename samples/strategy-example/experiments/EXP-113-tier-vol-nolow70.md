# EXP-113: fee tier: volume refill on 0.3%, v6.75 + ETH share 70% on 0.05% (v6.100)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

On the 0.05% pool two rules won H5 separately: v6.75's refill filter and the fixed 70% ETH share (EXP-073, which lost only on WBTC). Combined on the cheap pool; the expensive pool keeps the volume refill. New evidence: the ETH combination on H5.

## Change

Variant `CZ`: fee >= 0.3%: `REFILL_VOL_CONFIRM = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`, `SHARE_BELOW_EMA = 0.7`. Constant: the 0.3% boundary (70% is v6's own value).

## Pre-registration

Pre-registered together with EXP-112..116 (same commit), run with `A` (v6) in `A,CY,CZ,DA,DB,DC` per window.

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

- Dino, 2026-10-05: 'keep searching until 10 passes'. Fee-tier passes are counted toward the 10 and labelled as such (his ruling on them is still open). Rule applied to every fee-tier pair from here on: at least one half must be new on its holdout window (a pair assembled from halves that already won their windows would pass by construction and is not registered). Which halves are known: on H4 WBTC 2022, EXP-063 (account tranches) +2.9%, EXP-066 (no lower stop) +3.7%, EXP-101 (intraday stop, inside EXP-103) +7.1%, EXP-087 (volume refill, inside EXP-104) +6.9% vs v6 +2.4%; on H5 ETH 2021, EXP-088 (v6.75) and EXP-073 (share 70%) won. The combinations registered here have not been run on any window. Smoke test WBTC 2023-09-01..10-31 (`A,CY,CZ,DA,DB,DC`): all execute; no stop fires there, so CY / CZ / DA equal the volume-refill result and DC equals v6.
