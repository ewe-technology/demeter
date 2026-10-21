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

Batch 4 (after batch 3's IS results, all lost). The LP log now also writes each position (`lp_positions_signal.csv`,
logging only, base rerun identical). IS look at the base's 58 positions: positions living >= 6 days made +0.374 (the
rest −0.05, mostly 1-2 day positions from stage-by-stage F changes); the edge is highest while R ranges (R's 30-day
efficiency ratio, lowest tercile +0.159 of 19 positions) and lowest in the most volatile tercile of R (+0.052). +-10%
lost overall because it recentred through volatile spells, so narrow only while R is calm or ranging (judged on the
day's close, like F; the strong side is unchanged):

| variant | weak-side half width |
|---|---|
| `k100_reupE_volwidth` | +-10% while R's 30-day realized vol (annualized) < 30%, else +-20% |
| `k100_reupE_volwidth3` | +-10% / +-20% / +-30% for R's 30-day vol < 30% / 30-45% / > 45% |
| `k100_reupE_erwidth` | +-10% while R's 30-day efficiency ratio < 0.12, else +-20% |

Batch 5 (after batch 4's IS results, all lost: in this pool narrowing raises IL faster than fees even in calm R; fees /
IL is ~2 only from +-20% up). An IS split of `k75s30_reupE`'s positions (rerun with the position log): the strong-side
LP's 34 positions made fees +0.036 / IL −0.052 with no profitable subset by R vol, R efficiency, R or G momentum or age.
The lever left is more LP capital where fees / IL ~2: the weak side, where the base holds only F as LP and (1 − F) as
plain BTC.

| variant | change |
|---|---|
| `k100_reupE_weakone` | while weak the whole book is ONE LP of the same +-20% span, placed so its ETH share is F / 2 (the base's ETH exposure); F = 0 puts it just above the price (all BTC). A weak-side drift rebuild fires when the LP's ETH share is >= 12.5% off F / 2 |
| `k100_reupE_weakone30` | the same with a +-30% span |

Smoke run (2025-03-01..10, F = 0, weak): the LP starts all BTC just above the price, out-of-range rebuilds cost ~2e-6
ETH, fees accrue daily.

Batch 6 (after batch 5's IS results: the off-centre LP is run through by BTC trends, IL −1.016 / −0.623). Back to the
base's IS position log: positions living >= 6 days made +0.374, the 39 shorter ones −0.05 (19 of them 1-2 days, from F
stepping .375 → .5 → .75 → 1 on consecutive days, each step rebuilding the LP). Build the weak-side LP only once F has
stopped moving; until then its share is held as 50 / 50 ETH / BTC tokens (the exposure of a fresh centred LP).

| variant | change |
|---|---|
| `k100_reupE_lpwait2` | the weak-side LP is built only after F is unchanged for 2 closes |
| `k100_reupE_lpwait3` | the same after 3 unchanged closes |

Batch 7 (after batch 6's IS results: lpwait2 / lpwait3 lose; a position's first days earn fees too). The base's LP
design looks like a local optimum (centred, +-20%, weak side, F high); two capital levers on the weak side remain:

| variant | change |
|---|---|
| `k100_reupE_rvolS` | rvol halves F only while ETH is strong (the base's positions opened in the most volatile R tercile still made +0.052) |
| `k100_reupE_compound` | spec compound mode: collected fees count as capital and grow the LP |

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

Batch 3, IS (none passed):

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| `lpresize` | 64.23% | −24.7% | 2.601 | 0.607 | −0.336 | +0.271 | 119 | loses, LP down |
| `k75s20_reupE` | 64.79% | −24.3% | 2.670 | 0.643 | −0.368 | +0.275 | 119 | loses (CAGR), LP down |
| `k75s30_reupE` | 65.26% | −24.2% | 2.699 | 0.633 | −0.338 | +0.295 | 118 | loses (CAGR), LP down |

Batch 4, IS (none passed): narrowing in calm or ranging R still raises IL faster than fees.

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| `volwidth` | 62.50% | −24.8% | 2.515 | 0.683 | −0.619 | +0.063 | 120 | loses, LP down |
| `volwidth3` | 62.66% | −24.9% | 2.521 | 0.655 | −0.597 | +0.058 | 120 | loses, LP down |
| `erwidth` | 62.18% | −24.8% | 2.504 | 0.733 | −0.761 | −0.028 | 121 | loses, LP down |

Batch 5, IS (none passed):

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| `weakone` | 57.16% | −24.2% | 2.358 | 0.766 | −1.016 | −0.250 | 174 | loses, LP down |
| `weakone30` | 60.08% | −24.5% | 2.452 | 0.558 | −0.623 | −0.065 | 149 | loses, LP down |

Batch 6, IS (none passed):

| variant | CAGR | max DD | Calmar | fees | IL | LP edge | rebuilds | vs base |
|---|---|---|---|---|---|---|---|---|
| `lpwait2` | 60.34% | −24.8% | 2.430 | 0.551 | −0.710 | −0.159 | 130 | loses, LP down |
| `lpwait3` | 64.64% | −24.8% | 2.601 | 0.548 | −0.298 | +0.250 | 127 | loses, LP down |

## Deviations

- OOS (2025 on) was seen in EXP-178..183; the base itself is EXP-183's IS + OOS pass.
