# EXP-185: LP research directions 2 / 3 / 4 on k100_f2low_rvol_reupE (ETH-cbBTC MGL v2), `0x4585`, IS before 2025 / OOS after

- Jira: QUAN-1182 (subtask of QUAN-1107)
- Status: fail — none of nscentre / flip3 / flipband / mrgate beats the base on IS and OOS (mrgate: IS +0.19 pt, OOS −0.04 pt CAGR, noise)
- Pre-registration commit: 97e5e14 · Result commit: (next commit)

Dino (2026-10-21): "2,3,4都嘗試做看看，看有沒有效果" — directions 2, 3 and 4 of the LP research note (agent report of
2026-10-21, after EXP-184): swap-free recentring, keeping the weak-side LP through brief strength flips, and a
mean-reversion gate on recentring. Direction 1 (cheaper swap cost model) waits for Dino's ruling and is not run.

## Hypothesis

From the research note (IS numbers and EXP-184 logs only):

- Swap cost is about half the base's IS LP edge (0.162 ETH paid vs +0.324 edge); 0.095 of it comes from 50 rebuilds where
  F did not change (strength flips). The LP's own centred ETH / BTC split also forces a swap at each weak-side rebuild.
- The base's LP edge sits in positions that live long (16 positions over 10 days: IL 0.22 of what the path variance
  implies, edge +0.378); short ones earn about nothing. Brief weak -> strong flips cut LPs short.
- Over IS, R (ETH/BTC) mean-reverted (5-day variance ratio < 1 at 20 / 40 days), which is when keeping the old range
  pays; `lpresize` (always keep it) lost, a gate may keep only the good cases.

## Change

`experiments/v2_goal.py`; base = EXP-183's `k100_f2low_rvol_reupE` (EXP-184's `BASE184`, LP accounting logged). One
element each:

| variant | direction | change |
|---|---|---|
| `k100_reupE_nscentre` | 2 | at a weak-side LP build, the +-20% range is shifted by up to +-5% (whole tick spacings) so its ETH share uses the ETH already in the wallet, instead of swapping to the centred split |
| `k100_reupE_flip3` | 3 | the strong flag turns on only after 3 consecutive closes with R >= EMA100(R); weak still comes at once |
| `k100_reupE_flipband` | 3 | the strong flag turns on only at R >= 1.02 x EMA100(R); off at R < EMA100(R) as before |
| `k100_reupE_mrgate` | 4 | a drift rebuild keeps the old range (EXP-184 `lpresize`) only while R mean-reverts: variance ratio of 5-day log-R changes over the last 60 closes < 1; otherwise it recentres |

## Pre-registration

- Pool `0x4585`, 1 ETH start, net value in ETH incl. rewards; LP edge (fees + IL from the per-position LP log), swap
  cost, USD ratio and USD max DD reported, not judged.
- IS 2021-11-02..2024-12-31; OOS 2025-01-01..2026-09-30.
- Bar (`better()`): CAGR above the base AND Calmar >= the base AND max DD no more than 3 pts deeper.
- Only a variant that beats the base on IS runs OOS. A variant **works** when it beats the base on IS and OOS.
- One batch; every run reported. No follow-up batch unless Dino asks.

## Result

In ETH; base `k100_f2low_rvol_reupE`. LP edge = fees + IL from the per-position LP log.

IS 2021-11-02..2024-12-31:

| variant | CAGR | max DD | Calmar | LP fees / IL / edge | swap cost | rebuilds | vs base |
|---|---|---|---|---|---|---|---|
| base | 65.68% | −24.8% | 2.643 | 0.610 / −0.287 / +0.324 | 0.162 | 118 | |
| `nscentre` | 63.27% | −25.3% | 2.502 | 0.600 / −0.280 / +0.320 | 0.142 | 118 | loses |
| `flip3` | 52.78% | −26.8% | 1.967 | 0.522 / −0.404 / +0.118 | 0.111 | 106 | loses |
| `flipband` | 61.72% | −24.8% | 2.485 | 0.602 / −0.338 / +0.264 | 0.122 | 100 | loses |
| `mrgate` | 65.87% | −24.7% | 2.667 | 0.614 / −0.287 / +0.327 | 0.162 | 118 | **beats** |

OOS 2025-01-01..2026-09-30 (only `mrgate` passed IS; the base was rerun with the LP log, net value identical):

| variant | CAGR | max DD | Calmar | LP fees / IL / edge | swap cost | vs base |
|---|---|---|---|---|---|---|
| base | 25.80% | −28.7% | 0.898 | 0.114 / −0.232 / −0.118 | 0.035 | |
| `mrgate` | 25.76% | −28.1% | 0.917 | 0.113 / −0.211 / −0.099 | 0.035 | loses (CAGR −0.04 pt) |

**Verdict: fail — none of the four works.** Reading it:

- `nscentre` (direction 2) saves 0.020 ETH of swap cost but costs 2.4 pts IS CAGR: an off-centre range sits closer to
  one edge and is run through more, as `weakone` showed in EXP-184.
- `flip3` / `flipband` (direction 3) cut rebuilds and swap cost (0.111 / 0.122 vs 0.162) but lose much more: delaying the
  strong flag also delays moving the retreat from BTC to USDC and the F share from LP to ETH, which is the strategy's
  timing edge; LP IL rises (−0.404 / −0.338).
- `mrgate` (direction 4) is the base within noise on both halves (IS +0.19 pt, OOS −0.04 pt CAGR; LP edge +0.003 /
  +0.019 ETH, below EXP-184's ±0.05 noise band). The gate rarely changes a rebuild.
- The base's LP loses OOS (edge −0.118 ETH: IL −0.232 vs fees 0.114), as the research note expected from R trending
  after 2024. None of the three directions changes that.

## Deviations

- The OOS period was seen in EXP-178..184, and the research note that proposed these directions looked at OOS R
  behaviour (variance ratio 1.46 / 1.75 OOS). The variants' rules and constants were fixed from IS / literature only.
