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

State as of 2026-10-06 (end of day): EXP-001..156 recorded (`registry.csv`); read "Baseline since 2026-10-06 evening" and "Handoff 2026-10-06" below first. v6 baseline (EXP-000): ETH continuous 2022-01..2026-09 +85.4%, CAGR 14.0%,
max DD −22.8%; WBTC continuous +85.6%. The /goal of 2026-10-05 (EXP-052..081, 30 experiments) found **no improvement-level pass** on the
time-split holdout (H5 ETH 2021, H4 WBTC 2022): four dev passes each lost one window; v6.39 (idle reserve in a stablecoin LP) does not count
(ruling). v6 is a range harvester whose edge is the staged refill below the EMA; ETH and WBTC disagree about recentring (valley shape, pool
fee tier): see `experiments/FINDINGS-2026-10-05.md`. Round 2 (EXP-082..091) stopped at the first pass: **v6.75 (EXP-088, refill days count
only without a new intraday low, `REFILL_NO_NEW_LOW`) passes the improvement level on dev and the time-split holdout** (H5 ETH CAGR 21.4% vs
7.0%, H4 WBTC 3.4% vs 2.9%); the gain is ETH's, WBTC is nearly unchanged; it is a candidate until the forward window (after 2026-09-17)
confirms it: see `experiments/FINDINGS-2026-10-05-round2.md`. Round 3 (EXP-092..122, goal "10 improvement passes", reached):
11 passes, 2 clean (EXP-088 v6.75, EXP-122 v6.75 + macro restore) and 9 fee-tier rules (v6.75 on 0.05% pools, combinations of
intraday stop / volume-confirmed refill / no lower stop / account tranches on 0.3% pools). It amounts to ~4 independent findings;
both clean passes are ETH gains, WBTC within noise: `experiments/FINDINGS-2026-10-05-round3.md`. Round 4 (EXP-123..152, goal "30 more",
fee-tier rules count): 16 passes (4 clean, all v6.75 + routing variants), ~4 small new findings: routing the WBTC swap through the 0.05%
tier (+1 pt H4), cross-asset refill on ETH only (H5 +16.0% vs v6.75 +13.5%; fails on WBTC), macro restore +0.4 pt on ETH, no-new-low
on the best WBTC half (+0.5 pt H4). Rebuild-timing rules (rise, share flip) and account tranches on ETH do not hold out of time.
Candidates: clean EXP-126, fee-tier EXP-140 / EXP-150 (H5 +16.4%, H4 +10.1%). Next: forward window (after 2026-09-17) and a third
pool, no more H4 / H5 recombinations: `experiments/FINDINGS-2026-10-06-round4.md`. The best standalone strategies are lower-risk versions of v6:
`experiments/FINDINGS-2026-10-02.md`. Pure-LP scope (no perps, no lending) since 2026-10-01.
Earlier trials (momentum width, fee compounding, EMA exit band) were discarded on purpose. Background: `V6_VALIDATION.md` (PBO 0.56, DSR < 0.95,
regimes, capacity).

## Baseline since 2026-10-06 evening: spec sheet v1 (Dino: "改")

The team's baseline is the spec sheet's ETH/USDC v1 backtest (Maker's `gamma_maker_defense_ethusdc_v1.py`, branch
`maker-defense`; Google sheet "USDC/ETH gamma maker defence v1 slippage 0.1/fee 0.05": 2022-01-02..2025-12-31 +83.5%, APR 16.4%,
max DD −25.8%). Same logic as v6; four settings differ: Binance daily closes drive the EMA / F engine, spec weights cut in equal
2.5% price steps, flat 0.1% swap cost (no impact ledger), windows start on 1/2. `SPEC=v1 python v6_validate.py ...` runs every
variant on those settings and `A` is then spec v1 (reproduces the sheet's four years within 0.06 pt; USD-quoted pools only).
Run new experiments with `SPEC=v1`; EXP-000..154 keep their verdicts (EXP-155 withdrawn). This branch's old v6 (pool-price signal) is 15 pts below
spec v1 on the sheet window, mostly the signal (2023-03 USDC depeg).

EXP-156 (v6.126 = EXP-140 on spec v1, QUAN-1041): **fail**. Sheet window: +97.6% vs +84.0%, CAGR 18.6% vs 16.5%, Calmar 0.67 vs
0.64, yearly 3/4; full history 3/7 pools (wins mainnet ETH 0.05%, both BTC pools; ties on Base / Arbitrum ETH 0.05%; loses both
ETH 0.3% pools, where the WBTC-fitted 0.3% half applies). About a third of its old gain was compensating the pool-price signal;
its macro restore doubles rebuilds ($34k more mainnet gas on $100k over 2022-25, more than its $13.6k gain; gas not charged).

/goal 2026-10-07 ("找到五個打敗基準的策略"), batch 1 EXP-157..164 (v6.142..149, `SPEC=v1`, full-history 7 pools, judged with
`experiments/judge_full.py`): **5 pass** — EXP-157 v6.75 alone (5/7), 158 + cross-asset (4/7), 159 + cross-asset + macro (4/7),
160 + macro (5/7), 163 fee tier v6.75 on 0.3% / 159's rule on 0.05% (5/7); fail: 161 + intraday stop (3/7, a WBTC-only rule),
162 + two-day exit (1/7), 164 + wide top (2/7, DD > 3 pts deeper on mainnet ETH, loses BTC). Read the passes as one finding: all
five carry v6.75's no-new-low refill; the ETH gain is real on mainnet (+1.5..3.6 pts CAGR on both mainnet pools) but Base and
Arbitrum ETH 0.05% lose on Calmar for every variant, and the BTC wins are mostly within noise (+0.06 pt CAGR for v6.75 on WBTC).
157 / 158 rebuild no more than spec v1; 159 / 160 / 163 double the rebuilds (mainnet gas ~$200k vs $122k on $100k, not charged).
Batches now run one pool at a time with two workers (memory, see Gotchas).

Single-pool scan 2026-10-07 (`experiments/FINDINGS-2026-10-07-single-pool.md`, screen `experiments/single_pool_scan.py`): 19 other
strategy families (hold, 50/50, static / full-range LP, EMA / SMA200 / 84-day momentum, vol target, mean reversion) beat neither
spec v1 on ETH/USDC `0x88e6` nor v6 on WBTC/ETH `0x4585` (in BTC, where only staying in BTC wins). Dynamic ±20%: EXP-165 (DVOL
width, v6.150) and EXP-166 (ER30 width, v6.151) both **fail** (ETH CAGR 11.2% / 9.6% vs 13.55%); with EXP-030 three width
signals lose inside v6. `0x4585` runs need `BINANCE_WARM=1` (otherwise KeyError on the day before the data).

## Handoff 2026-10-06 (two sessions closed; a new session starts here)

Done since round 4, all committed, Jira and dashboard in sync:
- Rule change: no in-sample / out-of-sample split, full-history judging on every usable pool (Rules for experiments below).
- EXP-153 / 154 (v6.139 / v6.140, bull-only ladder changes above EMA100): both **fail** under the full-history rule. One-sided ETH
  ladder wins 1/7 pools (max DD ETH −40.7% vs −30.7%); +40% / −20% ladder raises CAGR on every valid ETH pool but loses both BTC
  pools (3/7). Jira QUAN-1038 / 1039 (Done).
- BTC/ETH pools (not an EXP, a comparison): three S3 pools added to `POOLS` / `INVENTORY.md` (Base `0x7aea`, Arbitrum `0x2f5e`,
  mainnet 0.3% `0xcbcd`) and `0x4585` got a Binance ETH/BTC warm-up. In BTC terms EXP-140 beats v6 on all three valid pools but the
  gain is small (best: Base 2024-09..2026-09 +14.3% vs v6 +11.0%). In USD terms every variant is close to holding BTC (Arbitrum
  2023-26 v6 +480% vs hold BTC +474%; mainnet 2021-26 max DD −77%): on a BTC/ETH pool the F engine only moves between ETH and
  BTC, never to USD, so there is no bear-market protection. `0xcbcd` is too thin for a 2 BTC book (result invalid). Raw runs:
  `result/v6_validate/0x4585-opt-ACADOEBAIAK-*`, `0x7aea-*`, `0x2f5e-*` in the main checkout.
- Research note `experiments/RESEARCH-2026-10-06-is-lp-worth-it.md`: passive LP vs holding (fees ≈ 0.8–1.0 × LVR on 5 bp pools);
  v6's edge is timing, its ETH LP leg is about zero.
- Records audit: registry, EXP files, Jira and dashboard agree for EXP-000..154. Open Jira under QUAN-834: only QUAN-842 (EXP-008)
  and QUAN-1013 (EXP-128), both waiting for the forward window. Dashboard curves now show EXP-126 / 140 / 150 (v6.39 and v6.4
  lines dropped as rulings say they do not count; v6.33 dropped on BTC). Round 4's other raw CSVs were lost with a removed
  worktree; their numbers stay in the EXP files.

Open decisions for Dino (ask before acting on them):
1. Confirm or change the full-history bar (my reading of "全歷史獲利不錯", Rules for experiments).
2. Re-judge the round-4 candidates EXP-126 / 140 / 150 under the full-history rule on all usable pools (about 1 h of runs)?
3. Add a "Running a /goal search" section here (batch size, when to stop, how to report, keep raw results)? Not written yet.
4. Build a combined strategy: v6's F from a USDC pool decides coin vs USD, the coin part LPs in a BTC/ETH pool (new code, ~half a day)?
5. EXP-008 (v6.8, ETH + BTC 50/50 portfolio) can be judged now under the full-history rule instead of waiting for Jan 2027.

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
   `level` (registry column, `improvement` / `standalone` / `validation` / `both`) separates the two success levels on the page; the strategy
   comparison lives in the `summary/standalone` and `summary/findings` documents (`experiments/dashboard_summary.py`): update them when a
   strategy passes the standalone level.
6. Tell Dino the result in Chinese: pass/fail, the numbers vs v6, the Jira key, the dashboard link.

## Rules for experiments

- Pre-register (hypothesis, fixed constants, pools, success rule) and commit **before** running.
- Structural changes only; no parameter tuning inside v6's family (PBO 0.56).
- Idle-capital yield (lending, a stablecoin LP or any other income on the (1 − F) reserve) is not a strategy change and never counts
  as an improvement (Dino, 2026-10-05): an experiment must change how the ETH/BTC liquidity itself is placed, sized, rebuilt or timed.
- Fee-tier rules count as one strategy (Dino, 2026-10-06): a variant may apply one switch set on pools with fee >= 0.3% and another
  on cheaper pools (`TIER` in `v6_validate.py`). Routing the rebuild swap through a cheaper pool also counts as a strategy change
  (Dino, ruling relayed by the EXP-117 session).
- Baseline v6 runs in the same invocation. Costs: pool fee + price impact; gas reported, not charged. From EXP-157 on, run with
  `SPEC=v1` (baseline = spec v1, flat 0.1% swap cost; see "Baseline since 2026-10-06 evening").
- **No in-sample / out-of-sample split (Dino, 2026-10-06).** Every pool in `INVENTORY.md`, local or in the team S3 bucket, may be
  used, and a pool may be downloaded from S3 (or with `fetch_uni_minute.py`) without asking; add it to `POOLS` and `INVENTORY.md`
  in the same commit. A strategy is judged on its **full-history** result: one continuous run per pool over all the data that pool
  has, v6 in the same invocation. Working bar (my reading of "全歷史獲利不錯", Dino may change it): CAGR above v6, Calmar ≥ v6,
  max DD no more than 3 pts deeper, on most of the pools run (ETH and BTC pools both represented), not on one pool alone. Report
  every pool run, including the ones it loses. Pre-register the rule and the pool list before running. EXP-001..152 were judged
  under the old dev + holdout rule; their verdicts stay as recorded (rounds 2-4 reused the H5 / H4 windows, which by the old
  rule were already in-sample).
- Anything seen out of order goes under *Deviations* in the EXP file.
- Two success levels exist, "improvement over v6" and "standalone good": see `experiments/README.md` (Success levels).

## Environment (rebuild after a new session — nothing outside git survives)

    uv venv -p 3.12 .venv-lab && uv pip install -p .venv-lab/bin/python -r samples/strategy-example/requirements-lab.txt
    # pool minute data is gitignored: samples/real-data (ETH pool) and samples/holdout-data (WBTC pools) live in the
    # main checkout /Users/dinohuang/Desktop/demeter-momentum; a worktree symlinks both from there (and samples/stable-data, the
    # USDC/USDT pools behind samples/stable_lp_daily.csv for v6.39).
    # samples/fetch_uni_minute.py downloads more (RPC); S3 pools: aws s3 cp from the bucket in INVENTORY.md section C.
    # gas and ETH/USD hourly CSVs are committed in samples/ (regenerate with samples/fetch_gas.py).
    # samples/strategy-example/experiments/INVENTORY.md lists every pool and series (downloaded, in the team S3 bucket, fit for v6): read it before
    # picking pools, and update it whenever data is added or used.
    # Write backtest results to the main checkout's samples/strategy-example/result/ (gitignored), not inside a worktree:
    # removing a worktree deletes its result/ folder (round 4's raw CSVs were lost that way).

Run (from `samples/strategy-example`, `PYTHONPATH=../..`):

    python v6_validate.py <pool> <start> <end> opt:A,B 4     # experiment variants, OPT dict in v6_validate.py
    python v6_validate.py <pool> <start> <end> sens|bench 3   # sensitivity grid / continuous v6 vs plain LP
    python v6_validate_report.py                              # validation numbers
    BINANCE_WARM=1 python v6_validate.py <pool> <start> <end> opt:A,B 4   # window before the pool's data: warm-up from Binance daily closes
    SPEC=v1 python v6_validate.py <pool> <start> <end> opt:A,B 2   # the baseline since EXP-156: A = spec sheet v1 (tag "-specv1")
    python experiments/judge.py dev|hold|holdbtc <tag> <prefix...>    # apply the pre-registered success rules to a run
    # results -> result/v6_validate/ (gitignored); daily equity CSV per variant

## Gotchas

- `demeter/uniswap/core.py:167` casts ticks to `int` before `Decimal` (numpy int64 otherwise raises). Keep it.
- Several processes loading the same data range at once can crash on demeter's `~/.demeter` cache
  (`pickle EOFError`) before any backtest runs: rerun that segment alone.
- A continuous ETH run takes ~8 min and several GB per worker; yearly segments take ~2 min. `v6_validate.py` keeps only
  timestamp + net value of demeter's per-minute AccountStatus (`LEAN_STATUS`, default on; identical results, 2022 yearly run
  4.4 → 2.7 GB parent + worker). The machine has 51 GB and other sessions share it: at most ~6 full-history workers at once
  (three invocations of two workers were OOM-killed on 2026-10-06; Dino paused a 2 x 3-worker batch on 2026-10-07).
- `git fetch` here only fetches `master` and `feat/dino-v6-opt` (narrow refspec in the local config); fetch any
  other branch by name.
- Pushing needs the `dinohuang102` GitHub account (write access to `ewe-technology/demeter`): run `gh auth switch -u dinohuang102` before pushing (a 403 means the wrong account is active) and leave it active.
