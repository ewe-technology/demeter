# PnL analysis page

A published HTML artifact that answers, for each strategy: how much it made or lost each calendar year, how deep
the drawdown went, against which yardsticks; and where each year's return and loss came from. The two pages of
2026-10-08 are the models:
- single pool: https://claude.ai/artifact/FbAxNNbBUjhoxv9xAfLYmA (Uniswap V3 LPs, windows restarting yearly)
- multi pool: https://claude.ai/artifact/9gEVYtmKSnfpmZ83vpNaa8 (spot gate with sleeves, one continuous run)

The user prints these to PDF, so nothing may hide behind a control: no tabs, chips or selects. Show every view
(one table per control, one card per strategy). Hover tooltips are fine as an extra, never as the only place a
number appears; `pnl_lib.js` already puts every charted value in a table under its chart.

## 1. Decide how years are cut

- **Windows that restart from cash** (single-pool `pool_lp_windows.py`): year y = the window starting y-01-01. A
  partial last year comes from slicing the latest window that covers it (2026 = from 2026-01-01 in the 2025-10
  window). Each year pays its own entry cost; say so on the page.
- **One continuous run** (sleeve_sim strategies): run once from the first day and cut the NAV into years; a year's
  return is its last NAV over the NAV just before it. Years then compound into the run's total. Check that they do
  against the study's report (A 版 2022–2025 = +217.1%).
- Don't mix the two in one table without saying which rows are which.

## 2. Compute yearly returns and the attribution

Run the scripts on the backtest host (access in SKILL.md).

**Single pool, V3 positions**: `scripts/lp_attribution.py spec.json out.json` (spec format in its docstring).
Components: `hold` and `il` for plain LPs; `on` and `off` for gated ones; then `fees`, `swap`, `impact`, `gas` (or
one `costs` when no windows CSV has the split) and `other`. Run `fee_check()` on two or three representative
files and report the result on the page: in 2026-10 the slope part was at most 3 pt a year against fees of 4–90 pt,
which is what made the fee numbers usable. If the slope part is large, the position sizing is off (leftover
tokens, tick rounding, a wrong mode) and the fee / price split must not be published.

**Multi pool, sleeves**: write a small driver in `samples/strategy-example` that builds the weights and values
exactly like the study's own script (`cost_matrix.py`, `holdout_extra.py`, `yield_layer.py`) and calls
`sleeve_attribution.attribute` for each version, plus `hold_bench()` for the controls. Reproduce one published
total first, then trust the rest. Known gaps: the wstETH ratio is NaN before 2022-08-26 (`.bfill()` holds it flat,
which is plain WETH); the parking index starts 2022-08-27; carve the 2023-03-10..04-01 USDC depeg out of the
parking yield.

**Older runs with only paired NAVs** (an LP version and the same rule in spot, like `tri-gate/nav_decompose.csv`):
show the yearly LP − spot gap and the whole-period fees vs IL + costs from the summary. If the study's own yearly
numbers don't compound to its total, they were restarts; recompute from the NAV and say on the page why it differs.

Every component set must add up to the year's return; keep `other` visible and explain anything over about 1 pt.

## 3. Choose what to show

- Yearly tables: one absolute, then one per control (minus that control, in pt). Rows grouped: 對照組 first, then
  the families in the order the research went, each with its pre-registered verdict as a tag (✓ / ✗ / △ and the
  H number). Columns: each year, compounded spans (all years, and the span every row has data for), worst yearly
  drawdown.
- NAV chart: the controls, the current strategy, the best candidate, one clear loser for contrast. Six lines at most.
- Attribution cards: one per strategy that has components. Same component order on every card: market exposure
  (hold / BTC / ETH / gate-on), the strategy's own move (IL / ladder price / timing), yield (fees, staking,
  parking), artefacts, costs (swap, impact, gas), other.
- Difference cards: candidate − its control, split into the same components. Usually the most useful view; it is
  where "g_down's edge is the ladder's fees, not buying low" was found.
- A takeaways row of four tiles: the headline compounded result, the drawdown truth, the main source, the main drag.

Color slots (`--s1` .. `--s8` in the shell, a validated categorical order): 1 base coin or gate-on exposure, 2 the
strategy's move (IL, ladder, ETH), 3 fees / staking, 4 swap or parking, 5 impact or an artefact, 6 gas or a second
LP, 7 other, 8 a second cost. Keep one meaning per slot within a page.

## 4. Build, check, publish

1. Copy `assets/pnl_content_example.html` and write the prose: the header (eyebrow with the source report and date,
   h1, lede, meta chips), a note under every section heading saying how to read it, an explanation per card
   (`explain` in the config), and a methods and limits section.
2. Write the config JSON (schema at the top of `assets/pnl_lib.js`); series keys and component keys are free-form.
3. `python .claude/skills/backtest-report/scripts/build_pnl_page.py --title "<2-4 word name>" --content c.html --config cfg.json --out page.html`
   It writes the page and runs `check_page.js`; fix anything it flags.
4. Re-read every number written into prose against the config. On 2026-10-08 this pass caught six wrong figures
   and one mislabelled control (a 50/50 reset every year shown as buy-and-hold).
5. Publish with the Artifact tool, `icon: "chart"`, and a one-sentence description. To change a published page,
   publish the same file path again (same URL) and tell the user what changed and why.

Build files go in the session scratchpad, not in the repo. The scripts that produced the numbers are worth
keeping: say where they are and offer to commit them.
