# v6 optimization experiments

One file per experiment, one row per experiment in `registry.csv`. The repo is the source of truth; the other
two layers mirror it:

- Jira story [QUAN-834](https://ewetechnology.atlassian.net/browse/QUAN-834): one subtask per experiment (who, when).
- Team dashboard https://claude.ai/artifact/ATZR3s2SqybzjQvMMsAZg5: leaderboard, log and equity curves. Its
  database holds `experiments/<EXP-id>` (same fields as a registry row plus `hypothesis`, `verdict`, `order`)
  and `curves/eth`, `curves/btc` (weekly net value per variant). Ask Claude to "sync EXP-NNN to the dashboard";
  only editors can write.

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
