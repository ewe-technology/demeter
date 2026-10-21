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

## Pre-registration

- Pool `0x4585`, 1 ETH, in ETH incl. rewards. IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-30 (`oosf`).
- A variant passes a segment when it beats the base by `better()` (CAGR above, Calmar >=, max DD no more than 3 pts
  deeper) AND its LP edge (fees + IL) is above the base's.
- IS first; OOS only for IS passes (base OOS rerun at the same time). **Goal reached** when a variant passes IS and OOS.

## Result

(pending)

## Deviations

- OOS (2025 on) was seen in EXP-178..183; the base itself is EXP-183's IS + OOS pass.
