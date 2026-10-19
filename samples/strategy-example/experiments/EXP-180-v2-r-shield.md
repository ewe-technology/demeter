# EXP-180: ETH/BTC shield added to ETH-cbBTC MGL v2 (v2 untouched), significant-gain bar, `0x4585`

- Jira: QUAN-1174 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

Goal (Dino, 2026-10-19): "我要你繼續找因子新增到v2優化v2，報酬跟回撤要有顯著的增進" — keep adding elements to v2 (v2's
own elements untouched, EXP-179 rule) until return and drawdown both improve significantly.

## Hypothesis

In-sample drawdown analysis of v2 (`result/v2_goal/is-v2/daily_1ETH_signal.csv`, done before this file; OOS not looked
at): every ETH drawdown deeper than 8% came while ETH rose against BTC — 2021-11..12 −12.3% (BTC per ETH +15%),
2022-01..04 −11.1% (+17%), 2022-06..11 −25.8% (+48%), 2022-11..2023-01 −10.0% (+10%), 2024-01 −8.9% (+21%), 2024-05..07
−20.5% (+19%), 2024-11 −9.3% (+17%). In those spells v2 holds BTC (the LP's BTC side, the BTC reserve while ETH is weak)
and its LP sells ETH into the rise, so its ETH count falls. v2's strength line (R vs EMA100) is slow to see these
rallies. An added "R shield" that holds the LP share (and the BTC reserve) as plain ETH while R breaks out or trends up
should cut those drawdowns; if it also keeps the BTC-carry and USD-retreat gains, CAGR rises too.

## Change

Base `v2` and runner as in EXP-178 / 179 (`experiments/v2_goal.py`, Maker's btceth v1 = MGL v2 standard mode, Rust engine).
Added layer only: a flag on R = ETH/BTC (Binance closes) judged at D close, acting at D+1 00:00. While it is on, v2's
target is changed after v2 computes it: LP share -> ETH (variants `_lp`), or LP share and BTC reserve -> ETH (`_all`).
v2's F, strength flag, USDC share, ranges and rebuild rules are not edited; the changed target rebuilds through v2's own
drift (12.5%) and target-LP-0 rules.

| flag | rule (constants fixed here) |
|---|---|
| `rbreak` | R >= 1.10 x its 20-day low |
| `rmom` | R > EMA20(R) > EMA50(R) |
| `rext` | on at a `rbreak` breakout, held until R closes below EMA20(R) |

Variants: `rbreak_lp`, `rbreak_all`, `rmom_lp`, `rmom_all`, `rext_lp`, `rext_all`, and two combinations of added
elements with EXP-179's `rvol` filter: `rvol_rmom_all`, `rvol_rext_all`.

## Pre-registration

- Pool `0x4585`; IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-17; separate runs from 1 ETH; net value in ETH incl.
  rewards; v2 rerun in the same batch.
- **Significant (the goal's bar)**: on a segment, CAGR >= v2 + 2.0 pts AND max DD at least 3.0 pts shallower AND Calmar
  >= v2. A variant **counts** when it is significant on IS and on OOS. (The EXP-178 / 179 "beats v2" bar is also
  reported.)
- Procedure: only IS-significant variants get an OOS run. If none counts, a further batch of at most 8 added elements
  (combinations of added elements allowed) is written from IS results only, committed before it runs; at most three
  batches in this experiment.

## Result

(pending)

## Deviations

- The flags were chosen after looking at v2's in-sample drawdowns (stated in the hypothesis); IS results are therefore
  partly in-sample by design, and OOS decides.
