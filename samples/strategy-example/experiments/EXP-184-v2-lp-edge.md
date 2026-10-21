# EXP-184: make the LP earn more on top of k100_f2low_rvol_reupE (ETH-cbBTC MGL v2), `0x4585`, IS before 2025 / OOS after

- Jira: (pending)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

Dino (/goal 2026-10-21): "一樣is oos的方式優化策略，優化方式請以lp賺錢為主" — same IS / OOS rules as EXP-183, and the
gain must come from the LP itself earning more, not from timing or holding more ETH.

## Hypothesis

`v2_goal.py` now logs LP accounting per position (logging only; the base's IS and k75's IS rerun byte-identical in net
value and max DD): for each position, from build to removal, fees collected, IL (its value minus the tokens it was
built from, at the removal price) and LP edge = fees + IL. IS, in ETH:

| run | fees | IL | LP edge | avg LP share |
|---|---|---|---|---|
| base `k100_f2low_rvol_reupE` (LP only while weak, +-20%) | +0.610 | −0.287 | +0.323 | 0.47 |
| `k75_f2low_rvol` (also 25% of F as LP while strong, +-10%) | +0.683 | −0.387 | +0.296 | 0.53 |

The weak-side LP earns about twice its IL; the strong-side LP does not pay for itself. Concentrating the weak-side LP
scales fees and IL together while the price stays in range, so with a 2:1 ratio the LP edge should grow, minus more
out-of-range rebuilds and swap cost.

## Change

`experiments/v2_goal.py`; base = `k100_f2low_rvol_reupE`, each variant changes one LP element. Batch 1:

| variant | change |
|---|---|
| `k100_reupE_weak10` | LP half width while weak +-10% (base +-20%) |
| `k100_reupE_weak5` | LP half width while weak +-5% |

Later batches, if needed, are added here and committed before they run, shaped from IS results only.

Batch 2 (after batch 1's IS results): narrowing raised fees 1.6x / 2.4x but IL 4x / 7.7x; recentring locks IL in, and a
narrow range recentres more. The other way:

| variant | change |
|---|---|
| `k100_reupE_weak30` | LP half width while weak +-30% |
| `k100_reupE_weak40` | LP half width while weak +-40% |

Batch 3 (after batch 2's IS results: +-30 / +-40 lose too; +-20 is near the best width, fees / IL 0.87 at +-10 and
2.1 at +-20..40). All 117 IS rebuilds of the base are drift rebuilds (F or strength changes), none out of range; 29 of
them keep an LP and still recentre it. The strong-side LP of k75 (+-10%) did not pay for itself.

| variant | change |
|---|---|
| `k100_reupE_lpresize` | a drift rebuild keeps the old LP range (resizes it) while the price is inside and the width is unchanged |
| `k75s20_reupE` | 25% of F as LP while strong (ETH_KEEP 0.75) at +-20% (k75: +-10%) |
| `k75s30_reupE` | the same at +-30% |

## Pre-registration

- Pool `0x4585`, 1 ETH, in ETH incl. rewards. IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-30 (`oosf`).
- A variant passes a segment when it beats the base by `better()` (CAGR above, Calmar >=, max DD no more than 3 pts
  deeper) AND its LP edge (fees + IL) is above the base's.
- IS first; OOS only for IS passes (base OOS rerun at the same time). **Goal reached** when a variant passes IS and OOS.

## Result

In ETH; base `k100_f2low_rvol_reupE`. LP edge = fees + IL over all LP positions.

Batch 1, IS (none passed):

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| base (+-20%) | 65.68% | −24.8% | 2.643 | 0.610 | −0.287 | +0.324 | 118 | |
| `weak10` | 58.64% | −24.6% | 2.388 | 0.994 | −1.139 | −0.145 | 125 | loses, LP down |
| `weak5` | 50.33% | −26.2% | 1.922 | 1.447 | −2.204 | −0.757 | 156 | loses, LP down |

Batch 2, IS (none passed):

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| `weak30` | 64.57% | −24.9% | 2.591 | 0.421 | −0.196 | +0.225 | 118 | loses, LP down |
| `weak40` | 64.01% | −25.0% | 2.565 | 0.321 | −0.149 | +0.171 | 118 | loses, LP down |

## Deviations

- OOS (2025 on) was seen in EXP-178..183; the base itself is EXP-183's IS + OOS pass.
