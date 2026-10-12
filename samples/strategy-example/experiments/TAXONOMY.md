# Experiment taxonomy (EXP-001..175)

Team sheet (everyone adds their own experiments there; it supersedes this file once others write to it):
[LP 策略研究總表](https://docs.google.com/spreadsheets/d/1wRgWxo6PyXtHUAEX-tObBQzKb5oZEvG_7bQDJfT-llo/edit),
seeded by `build_taxonomy_xlsx.py` (QUAN-1108).

Every experiment filed by the part of v6 it changes. One row per experiment in `TAXONOMY.csv`, built by
`python experiments/taxonomy.py` from `registry.csv` and the 2026-10-07 deck appendix (EXP-052..164 keep
the deck's category; `ladder` is renamed `width`, `idle` → `non_lp`). A combination is filed under the rule
it adds last. Columns: `passed` (status `holdout-pass` or `pass`), `rule` (`dev+holdout` for EXP-001..152,
`full-history` from EXP-153), `has_v675` (the variant contains v6.75's no-new-low refill).

| Category | 中文 | Part of v6 changed | Tried | Passed | Passed without v6.75 | What we learned |
|---|---|---|---:|---:|---:|---|
| `signal` | 訊號線 | EMA replaced by another trend line (Donchian, SMA200, Hull, Aroon, Ichimoku, Supertrend, momentum) | 17 | 1 | 1 | None beats EMA inside v6; Donchian passes only at the standalone level (EXP-032) |
| `f_engine` | F 引擎 | How the four accounts produce F: gates, floors, weekly reads, 8 accounts, fee compounding | 21 | 0 | 0 | Nothing; the four-account EMA engine is the part to leave alone |
| `exit_stop` | 撤出 / 停損 | When the ladder goes back to USDC: two-day exit, intraday stop, toxicity pause | 12 | 2 | 2 | Two-day exit passed standalone (EXP-044 / 048) but fails full-history (EXP-162, 1/7); intraday stop helps WBTC only (EXP-161, 3/7) |
| `refill` | 回補 | Conditions for the staged buy-back after an exit | 24 | 3 | 0 | **The one finding that holds**: v6.75, refill days count only without a new intraday low (EXP-088 / 157, 5/7). Cross-asset refill helps ETH only |
| `rebuild` | 重建時機 | When the range is rebuilt and where it is centred | 15 | 2 | 0 | Rise / share-flip rebuilds do not hold out of time; both passes carry v6.75 |
| `width` | 區間寬度與形狀 | ±20% width, skew, half ladder, dynamic width | 23 | 3 | 3 | Fixed ±20% stays: five dynamic-width rules lost on spec v1 (EXP-165..168); +40% top deepens DD and loses BTC (EXP-154 / 164 / 173). Standalone passes only (EXP-034 / 049 / 051) |
| `share` | ETH 比例 s | The 70% / 50% ETH share rule | 2 | 1 | 1 | Fixed 50% (ablation, EXP-046) is as good standalone: the EMA100 share rule adds little |
| `macro` | 總經事件 | Pause / restore around CPI and FOMC | 6 | 4 | 0 | +0.4 pt CAGR on ETH, but doubles rebuilds (gas not charged) |
| `fee_tier` | 費率分層組合 | One switch set on 0.3% pools, another on cheaper pools | 35 | 23 | 0 | 23 passes are ~4 findings; every one runs v6.75 on the 0.05% side |
| `routing` | 換匯路由 | Which pool the rebuild swap goes through | 3 | 1 | 0 | Routing through the 0.05% tier: about +1 pt on WBTC |
| `non_lp` | 非 LP 本體 | Spot sleeve, perp shorts, idle-cash yield | 12 | 3 | 3 | Out of scope: idle yield never counts (ruling 2026-10-05), pure-LP scope since 2026-10-01 |
| `validation` | 驗證 / 移植 | Other pools, spec v1 port, ETH + BTC portfolio | 4 | 1 | 1 | Not strategy changes |
| **Total** | | | **174** | **44** | **11** | |

## Reading

- **Every pass after EXP-052 contains v6.75.** The 11 passes without it are all from EXP-001..052 and are
  standalone-level, out-of-scope (idle yield, perp short) or validation runs. On the LP itself the only
  improvement-level finding is v6.75's no-new-low refill.
- **Maker's Q3 (2026-10-12, #scrum-quant-amm) maps onto two categories.** "Invest less after a breakdown"
  is `refill` (v6.75 holds) and `exit_stop` (nothing holds on full history). "Fewer rescales" is `rebuild`
  (15 tried, no rule passes on its own); EXP-157 / 158 keep spec v1's rebuild count, EXP-159 / 160 / 163
  double it.
- **Gap: an upside exit on price stretch was never tested.** Spec v3's rule (all USDC at close ≥ EMA100
  +40%, back below +20%) belongs in `exit_stop`. The closest tries are EXP-085 (F capped while funding is
  overheated, dropped) and the +40% top ladders (`width`, all fail).
