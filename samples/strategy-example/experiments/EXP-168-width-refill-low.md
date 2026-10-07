# EXP-168: while refilling, the ladder's lower edge sits at the refill low (v6.153)

- Jira: QUAN-___
- Status: pre-registered
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: ______ · Result commit: ______
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

## Deviations

- Smoke test as EXP-167 (lower reach 10..20% built during the 2022-06 refill); not evidence. Refill stages sit 5..15% above the
  low, so the 10% floor binds on most refill builds: in practice the rule is "lower reach 10-15% while refilling".
