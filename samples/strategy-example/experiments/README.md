# v6 optimization experiments

One file per experiment, one row per experiment in `registry.csv`. The repo is the source of truth; the other
two layers mirror it:

- Jira story [QUAN-834](https://ewetechnology.atlassian.net/browse/QUAN-834): one subtask per experiment (who, when).
- Team dashboard https://claude.ai/artifact/ATZR3s2SqybzjQvMMsAZg5: leaderboard, log and equity curves. Its
  database holds `experiments/<EXP-id>` (same fields as a registry row plus `hypothesis`, `verdict`, `order`)
  and `curves/eth`, `curves/btc` (`series`, `labels`, `slots` per key: weekly net value, legend name, palette slot).
  `dashboard_rows.py` builds both documents; the page draws any new key without being republished. Page source:
  `dashboard/index.html`. Only editors can write.

Versions: Dino's `v6.1`, `v6.2`, ... map one-to-one to `EXP-NNN` (the `version` field on the dashboard). The full
definition of done is in the repo's `CLAUDE.md`.

## Workflow

1. Copy `TEMPLATE.md` to `EXP-NNN-<slug>.md` (next free number), fill *Hypothesis* and *Pre-registration*,
   add a `pre-registered` row to `registry.csv`, commit. The commit hash is the proof the rule came first.
2. Run it with `v6_validate.py` (add the variant to `OPT` there). Development data first; holdout only for the
   single pick, once.
3. Fill *Result*, update the registry row (status, numbers, result commit), commit.
4. Anything seen out of order (a holdout number before the pick, a crash rerun) goes under *Deviations*.

## Rules that carry over between experiments

- Baseline is always EXP-000 (v6 as is) run in the same invocation, so costs and data match.
- Costs: pool fee + price impact always; gas reported, not charged (deployment chain not fixed yet).
- No parameter tuning inside v6's family: its PBO is 0.56 (`../V6_VALIDATION.md`). Structural changes only,
  constants fixed in the pre-registration.
- Data seen so far: ETH/USDC 0.05% 2021-05..2026-09 and WBTC/USDC 0.3% 2021-11..2026-09 are both in-sample now.
  A new clean holdout must be named in the pre-registration (another pool, chain, or data after 2026-09-17).

## Registry status values

`pre-registered` → `dev-done` → `holdout-pass` | `holdout-fail` | `dropped-at-dev`; `fail` = a single-stage test failed

## Run

    cd samples/strategy-example
    PYTHONPATH=../.. python v6_validate.py <pool> <start> <end> opt:A,<id> 4
    # results: result/v6_validate/<pool>-opt-...csv (+ daily equity per variant)

## Success levels (added 2026-10-02, /goal "find five well-performing Uniswap strategies")

Two different questions, never mixed in a verdict:

- **Improvement** (the original rule in each EXP file): the variant beats v6 on both assets (CAGR above, Calmar ≥,
  max DD ≤ 3 pts deeper) and on a fresh holdout. Status `holdout-pass`.
- **Standalone** (a re-judged experiment, `r` suffix like v6.1r, own EXP number, own fresh holdout run once): absolute bar,
  no comparison to v6 needed. Dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%, ETH positive in
  at least 4 of 5 yearly segments. Holdout (three pools, one continuous run each): total return > 0 on all three,
  Calmar ≥ 0.50 on at least 2 of the 3, max DD no deeper than −35% on all three. Status `holdout-pass` with
  "standalone" in the EXP file's first line. v6 itself is the reference level (Base WETH 0.63, Base cbBTC 0.79).
  A standalone pass says the strategy is good by itself, not that it is better than v6.

A re-judged experiment reuses the dev numbers of the original (already seen: say so under *Deviations*) and runs its
holdout once. Variants that are near-copies of each other (signal correlation, same price path) are reported with their
correlation to v6 and to each other; they do not count as independent evidence.
