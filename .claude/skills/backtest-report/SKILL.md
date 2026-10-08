---
name: backtest-report
description: Turn Demeter backtest results in this repo into a written backtest report (markdown in reports/, like reports/single_pool_loop.md), a backtest slide deck, or a PnL analysis page (yearly return and max drawdown against control groups, plus where each year's return and loss came from, like the single-pool and multi-pool yearly pages). Use it whenever the user asks for 回測報告, 報告, 寫進報告, 回報結果, 簡報, slides, deck, PnL 分析, 每年的 PnL, 回撤, 對照組, 報酬來源, 拆解, or wants any backtest, hypothesis (H1, H2, ...) or strategy version written up, compared year by year, or explained, even if they don't name a format.
---

# Backtest reports, decks and PnL analysis

Three outputs, made from the same backtest results. Make only the one the request asks for; when it asks for
everything, make all three in this order, because each reuses the numbers of the one before:

| Request | Output | Read |
|---|---|---|
| 報告、寫進報告、回報 Hx 的結果 | markdown in `reports/`, committed | `references/report.md` |
| PnL 分析、每年的 PnL / 回撤、報酬來源、拆解 | an HTML artifact page | `references/pnl-analysis.md` |
| 簡報、slides、deck | a claude.ai Slides artifact | `references/slides.md` |

Read the matching reference before starting; it has the structure, the tools and the checks.

## Ground rules for all three

**Language and voice.** Write in Traditional Chinese (the user's standing preference); code, identifiers and file
names stay as they are. Plain words and short sentences, the way the existing reports read. No em-dash asides,
no "not X but Y" framing, no stock phrases. Name things the way the user does (g_down, A 版, 停泊, 濾網).

**Every number traces to a file.** Take numbers from result files or a script's output, never from memory or from
an earlier summary. After writing prose, check each number in it against the data once more: hand-written text is
where the published pages had their mistakes (a +6.4 that was +3.6, a range quoted from the wrong rows). Prefer
numbers the page computes from its config over numbers typed into prose.

**Always show control groups.** A result without a yardstick reads as a claim. Use the ones that fit:
- holding the base coin (BTC, ETH) bought at the start and never touched;
- the 50/50 basket, said exactly: bought once and never rebalanced, or reset every Jan 1. They differ a lot
  (multi-pool 2022 to 2026-09: +27% vs +19%). Tables of yearly and compounded returns use buy-and-hold; a single
  year's timing effect uses the Jan-1 reset;
- the strategy's own control: same gate, same capital, the simplest holding (e.g. g_spot100 for g_down);
- the current live strategy (A 現行濾網) when the work proposes a change to it.

**Respect the pre-registration.** The repo's method: the verdict rule is committed before a run, and the result
names that commit. Keep pre-registered verdicts and after-the-fact looks apart and say which is which (事先寫死 /
只列出 / 事後追加). A yearly table or an attribution is descriptive; it never re-judges a hypothesis.

**Say what the evidence cannot show.** Every output ends with its limits: one price path (2022-01 onward),
overlapping windows, parameters picked after seeing results, approximations and which way they lean, missing data.

## Where the results are

Heavy runs live on the backtest host, not on this laptop: `aws-backtest-ssm`, work dir `~/demeter-joy`, runs from
`samples/strategy-example` with `PYTHONPATH=../.. nice -n 10 ../../.venv/bin/python <script>`. Reach it with
Windows OpenSSH from the PowerShell tool (Git Bash ssh has no key). PowerShell mangles quotes in remote commands,
so write a script locally, `scp` it over, and run it. Use at most 3 workers there: the host has 7.7 GB of RAM, and
with 4 it starts swapping and every run gets about 7 times slower.

| Study | Files (under `samples/strategy-example/result/`) |
|---|---|
| single pool, windows (H2–H4b) | `pool-lp-windows/nav_<ver>_<start>.csv` (minute: net, price), `events_<ver>_<start>.csv` (t, kind), `windows_<set>.csv` |
| single pool, batch (H5–H16) | `pool-lp-batch/nav_<pool>_<ver>_<gate>_<start>.csv`, `events_*`, `summary_<set>.csv` |
| multi pool, spot gate | `spot-gate/`, `tri-gate/` (local copies too); hourly prices in `spot-gate/prices_2026-09-30.csv` |
| multi pool, yield layer | `yield-layer/sleeve_<name>[_to2026].csv` + `events_*`, `cost-matrix/`, `holdout-extra/` |

Windows start each quarter; the Jan 1 window of year y is calendar year y (those windows restart from cash). Check a
nav file's last date before using it: test runs have overwritten real ones (w10 2022 was a 10-day test), and
`lp_attribution.py` skips such files.

## Tools in this skill

- `scripts/lp_attribution.py`: single-pool V3 runs → yearly return, maxDD and attribution (hold, impermanent loss,
  gate-on / gate-off price, fees, swap fee, impact, gas), with `fee_check()` to confirm the fee split is real.
- `scripts/sleeve_attribution.py`: sleeve_sim runs → yearly attribution by sleeve (coin price vs yield index), with
  `carve` for known artefacts and `hold_bench()` for both 50/50 definitions.
- `scripts/build_pnl_page.py` with `assets/pnl_lib.js`, `pnl_shell.html` and `pnl_content_example.html`: build the
  PnL page from a content fragment and a JSON config, then run it in a stub DOM (`scripts/check_page.js`) to catch
  script errors, NaN and empty sections before publishing.

Both attribution scripts reproduce the numbers published on 2026-10-08 exactly; if a change breaks that, the change
is wrong.
