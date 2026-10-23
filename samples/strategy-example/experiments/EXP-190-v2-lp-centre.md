# EXP-190: where to centre the LP — EMA20 centre vs trailing recentre, on k100_f2low_rvol_reupE, `0x4585` IS before 2025 / OOS after

- Jira: QUAN-1192 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

Dino (2026-10-23), after asking how the AMM centre is chosen: "我找一些方法重擺中心點這方法有用嗎" -> "測": the two
centring rules not yet tried.

## Hypothesis

A position's IL depends only on how far the final price is from its centre. Moving the centre is a bet on direction:

- `emacentre` bets on reversion: centre the weak-side LP on the 20-day EMA of the pool price, where the price is
  expected to return; IS saw R mean-revert (variance ratio < 1), so it may cut IL in-sample.
- `trail10` bets on trend: recentre as soon as the price is 10% from the centre, before it reaches the ±20% edge, so a
  trend locks less IL per rebuild.

The two are opposite bets; running both shows which way this pool leans. Already tried and lost: keeping the old
range (`lpresize`, EXP-184), a mean-reversion gate on that (`mrgate`, EXP-185), off-centre placement (`weakone`,
`nscentre`).

## Change

`experiments/v2_goal.py`, base `k100_f2low_rvol_reupE` (LP version, weak-side ±20% LP):

| variant | change |
|---|---|
| `k100_reupE_emacentre` | a weak-side LP is centred on EMA20 of the pool price (BTC in ETH); if the price is more than 15% from that EMA, it is centred on the price now (the range always holds the price) |
| `k100_reupE_trail10` | an added rebuild rule: the price is 10% or more from the LP range's centre (in ticks) -> rebuild around the price now |

## Pre-registration

- Pool `0x4585`, 1 ETH start, in ETH incl. rewards; LP fees / IL / edge, swap cost and rebuild counts reported.
- IS 2021-11-02..2024-12-31; OOS 2025-01-01..2026-09-30.
- Bar (`better()` vs the base): CAGR above, Calmar >=, max DD no more than 3 pts deeper. OOS only for an IS pass; a
  rule **works** when it beats the base on IS and OOS. One batch.

## Result

(pending)

## Deviations

(none yet)
