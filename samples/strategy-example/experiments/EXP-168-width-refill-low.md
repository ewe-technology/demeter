# EXP-168: while refilling, the ladder's lower edge sits at the refill low (v6.153)

- Jira: QUAN-1074
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: 4621cb7 · Result commit: ______
- Scope: as EXP-167 (Dino, 2026-10-07: width that follows the refill stage or F).

## Hypothesis

After an EMA exit each account tracks the lowest close since the exit (its refill low) and refills in four stages at 5..15%
above it. That low is v6's own support level: if the price goes back below it, the refill was wrong. A ±20% ladder built during
a refill reaches far below that low and buys the coin all the way down; ending the lower reach at the refill low keeps the
refilled liquidity between support and the price, where v6 expects the base to form, and concentrates it (more fees).

## Change

Variant `GL`: `WIDTH_SIGNAL = "refill_low"`. At a build whose judged day has 0 < F < 1, the lower ratio is
`1 - low / close`, with `low` the lowest refill low among accounts not fully deployed and `close` the judged close, clamped to
[10%, 30%] and rounded to 5% (EXP-030's clamp and grid); the upper reach stays v6's +20%. At F = 0 or F = 1 the ladder is v6's
±20%. Everything else is the baseline's. No new constant.

## Pre-registration

- Same pools, windows, invocation and success rule as EXP-167 (`opt:A,GK,GL` on `0x88e6` with `SPEC=v1`, on `0x4585` with
  `BINANCE_WARM=1`).
- Gas is reported, not charged.

## Result

Run `opt-AGKGL` on `0x88e6` with `SPEC=v1` and on `0x4585` with `BINANCE_WARM=1` (values in BTC), 2 workers (2026-10-07; raw
runs in the main checkout's `result/v6_validate/0x88e6-opt-AGKGL-specv1-*`, `0x4585-opt-AGKGL-*`). `A` reproduces spec v1
(+97.7%) and v6 on `0x4585` (-1.40%).

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | LP fees | win |
|---|---|---|---|---|---|
| ETH/USDC `0x88e6` 2021-05-06..2026-09-17 (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +92.0% / 12.93% / -21.8% / 0.592 | 179 → 186 | $101.5k → $104.9k | lose |
| WBTC/ETH `0x4585` 2021-11-02..2026-09-17 (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | -3.34% / -0.69% / -33.6% / <0 | 100 → 107 | 0.262 → 0.337 BTC | lose |

Lower reach built on `0x88e6`: v6's ±20% x67, 10% x78, 15% x27, 20% x11, 25% x3 (the 10% floor binds on most refill builds).

Verdict: **fail** — loses both pools (ETH/USDC CAGR -0.62 pt with Calmar equal (0.592 vs 0.591) and max DD 1.1 pts shallower;
WBTC/ETH -0.40 pt).

Reading: the narrow lower reach does what the hypothesis said on fees (+3% on ETH, +29% on WBTC/ETH) and trims drawdown on ETH,
but (a likely mechanism, not tested) the price breaks below the refill low often enough that the ladder exits and rebuilds 7 more times on each pool; the
rebuild costs and the coin bought just above the low outweigh the extra fees. Closest of the four width rules (EXP-165..168)
to the baseline on ETH.

## Deviations

- Smoke test as EXP-167 (lower reach 10..20% built during the 2022-06 refill); not evidence. Refill stages sit 5..15% above the
  low, so the 10% floor binds on most refill builds: in practice the rule is "lower reach 10-15% while refilling".
