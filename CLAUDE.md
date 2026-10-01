# demeter — defense v6 LP strategy research

Talk to the user (Dino) in Traditional Chinese. Code, commit messages and Jira bodies stay English.

## What this branch is

`feat/dino-v6-opt` is Dino's only development branch; it starts from Maker's `defense_v6` and iterates on defense v6 (`samples/strategy-example/gamma_ig_gap_bands_defense_v6.py`, Maker's
`defense_v6` branch): a ±20% inverted-gaussian valley LP on Uniswap v3 whose deployed fraction F comes from an
EMA 90–120 four-account engine. Every change is an experiment, recorded in three places that must stay in sync:

- `samples/strategy-example/experiments/` — source of truth: `README.md` (workflow), `registry.csv`, one
  `EXP-NNN-*.md` each. Read the README before starting an experiment.
- Jira story QUAN-834 (site `ewetechnology`, project QUAN) — one subtask per experiment.
- Team dashboard https://claude.ai/artifact/ATZR3s2SqybzjQvMMsAZg5 — write with the `ArtifactData` tool:
  `experiments/<EXP-id>` (registry fields + `hypothesis`, `verdict`, `order`), `curves/eth`, `curves/btc`
  (weekly net value per series key). Only editors write; the page never needs republishing for new rows.

State as of 2026-09-30: only EXP-000 (v6 baseline): ETH continuous 2022-01..2026-09 +85.4%, CAGR 14.0%,
max DD −22.8%; WBTC continuous +85.6%. Earlier trials (momentum width, fee compounding, EMA exit band) were
discarded on purpose — numbering restarts at EXP-001. Background: `V6_VALIDATION.md` (PBO 0.56, DSR < 0.95,
regimes, capacity).

## Git workflow (Dino's standing instruction)

- `feat/dino-v6-opt` is the only branch Dino uses in this repo. Commit to it and push it directly — no pull
  requests, no feature branches, no need to ask before committing or pushing to it.
- Never create, modify, rebase or delete any other branch (`defense_v6`, `remix`, `master`, `feat/*`, ...).
- The main checkout `/Users/dinohuang/Desktop/demeter-momentum` stays on `feat/dino-v6-opt`. When a session has
  to work in a worktree, use a detached one (`git worktree add --detach <path> origin/feat/dino-v6-opt`), push
  with `git push origin HEAD:feat/dino-v6-opt`, then fast-forward the main checkout (`git merge --ff-only`) and
  remove the worktree — never leave a second branch behind.

## A strategy version is done only when all of this is done

Dino names versions `v6.1`, `v6.2`, ...; each is one experiment `EXP-NNN` (next free number in `registry.csv`,
`version` field = his name). When asked to "make v6.x", carry it through every step without being reminded:

1. Pre-register: copy `experiments/TEMPLATE.md` to `EXP-NNN-<slug>.md`, fill hypothesis, change and rule, add a
   `pre-registered` row to `registry.csv`, commit and push.
2. Implement the variant (add it to `OPT` in `v6_validate.py`), run dev, then the holdout once.
3. Record: fill *Result* / *Deviations*, update the registry row (status, numbers, commits), commit and push.
4. Jira: open a Subtask under QUAN-834 with the `jira-ticket` skill (summary `[Uniswap] v6.x: <change>`,
   research template). **Create it right away — Dino pre-approved these subtasks**: skip the skill's
   confirmation step, assign Dino (`712020:61c91efb-686a-4919-bb27-377f27b88318`), and report the key in step 6
   (he edits or reassigns afterwards if needed). Never defer ticket creation to "batch it later" or to a reply —
   an experiment is not done while its `jira` column is empty. Put the key in the registry `jira` column and the
   EXP file. When the registry status is final (`dropped-at-dev`, `holdout-pass`, `holdout-fail`, `fail`), also
   transition the subtask to Done (transition id `31`); leave it open for `dev-done` or a pending holdout.
5. Dashboard (https://claude.ai/artifact/ATZR3s2SqybzjQvMMsAZg5): build the documents with
   `python experiments/dashboard_rows.py row ...` (and `curve ...` when a continuous ETH/WBTC run exists), then
   `ArtifactData set experiments/<EXP-id>` and `ArtifactData update curves/eth|btc` (get first, pass `if_version`).
   New curves take slot 2, 5, 6, 7, 8 in that order; at most five experiment lines, drop the oldest failed one
   (`{"__delete__": true}` on its series/labels/slots keys) before adding a sixth. The page itself never needs
   republishing; its source is `experiments/dashboard/index.html` (republish with `url` only for layout changes).
6. Tell Dino the result in Chinese: pass/fail, the numbers vs v6, the Jira key, the dashboard link.

## Rules for experiments

- Pre-register (hypothesis, fixed constants, dev data, holdout, success rule) and commit **before** running.
- Structural changes only; no parameter tuning inside v6's family (PBO 0.56).
- Baseline v6 runs in the same invocation. Costs: pool fee + price impact; gas reported, not charged.
- ETH/USDC 0.05% (2021-05..2026-09-17) and WBTC/USDC 0.3% (2021-11..2026-09-17) are in-sample now: every new
  pre-registration names a fresh holdout (another pool or chain, or data after 2026-09-17).
- Anything seen out of order goes under *Deviations* in the EXP file.

## Environment (rebuild after a new session — nothing outside git survives)

    uv venv -p 3.12 .venv-lab && uv pip install -p .venv-lab/bin/python -r samples/strategy-example/requirements-lab.txt
    # pool minute data is gitignored: samples/real-data (ETH pool) and samples/holdout-data (WBTC pools) live in the
    # main checkout /Users/dinohuang/Desktop/demeter-momentum; a worktree symlinks both from there.
    # samples/fetch_uni_minute.py downloads more (e.g. data after 2026-09-17 for a fresh holdout).
    # gas and ETH/USD hourly CSVs are committed in samples/ (regenerate with samples/fetch_gas.py).
    # samples/strategy-example/experiments/INVENTORY.md lists every pool and series (downloaded, in the team S3 bucket, fit for v6): read it before
    # picking a holdout, and update it whenever data is added or used.

Run (from `samples/strategy-example`, `PYTHONPATH=../..`):

    python v6_validate.py <pool> <start> <end> opt:A,B 4     # experiment variants, OPT dict in v6_validate.py
    python v6_validate.py <pool> <start> <end> sens|bench 3   # sensitivity grid / continuous v6 vs plain LP
    python v6_validate_report.py                              # validation numbers
    # results -> result/v6_validate/ (gitignored); daily equity CSV per variant

## Gotchas

- `demeter/uniswap/core.py:167` casts ticks to `int` before `Decimal` (numpy int64 otherwise raises). Keep it.
- Several processes loading the same data range at once can crash on demeter's `~/.demeter` cache
  (`pickle EOFError`) before any backtest runs: rerun that segment alone.
- A continuous ETH run takes ~8 min and several GB per worker; yearly segments take ~2 min.
- `git fetch` here only fetches `master` and `feat/dino-v6-opt` (narrow refspec in the local config); fetch any
  other branch by name.
- Pushing needs the `dinohuang102` GitHub account (write access to `ewe-technology/demeter`): run `gh auth switch -u dinohuang102` before pushing (a 403 means the wrong account is active) and leave it active.
