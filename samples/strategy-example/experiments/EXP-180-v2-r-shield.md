# EXP-180: ETH/BTC shield added to ETH-cbBTC MGL v2 (v2 untouched), significant-gain bar, `0x4585`

- Jira: QUAN-1174 (subtask of QUAN-1107)
- Status: fail (0 of 24 added layers significant in-sample; best `rlow25_rvol` CAGR +1.66 pts, max DD 6.0 pts shallower)
- Pre-registration commit: 3e7f8fa (batch 4 deecb78, batch 5 f7d361c) · Result commit: 50457b9

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

### Batch 3 (R shields), IS only

| variant | IS ETH x / CAGR / max DD / Calmar | significant |
|---|---|---|
| v2 | 4.197 / 57.33% / −26.4% / 2.170 | – |
| `rbreak_lp` | 4.150 / 56.77% / −24.6% / 2.310 | no |
| `rbreak_all` | 4.153 / 56.81% / −24.6% / 2.312 | no |
| `rmom_lp` | 3.970 / 54.59% / −24.6% / 2.220 | no |
| `rmom_all` | 3.970 / 54.59% / −24.6% / 2.220 | no |
| `rext_lp` | 3.933 / 54.14% / −24.7% / 2.191 | no |
| `rext_all` | 3.937 / 54.19% / −24.7% / 2.193 | no |
| `rvol_rmom_all` | 4.036 / 55.41% / −24.6% / 2.252 | no |
| `rvol_rext_all` | 3.970 / 54.60% / −24.7% / 2.210 | no |

None is significant (DD at most 1.8 pts shallower, CAGR lower); no OOS run. The shields fix the rally they target
(`rbreak_all` IS 2022-06-17..08-12 −12.2% instead of the −25.8% v2 episode) but a new deepest episode remains,
2022-08-29..11-05 −25.0%: v2 sat 77% in USDC at the ETH low of 2022-08-29 ($1427), so its ETH count peaked there, and the
rebound, refills and the late-October ETH/BTC jump gave it back. `_all` = `_lp`: the BTC reserve is rarely held when
the flag is on.

### Batch 4 (locks; written after batch 3's IS results, before any batch 4 run)

A lock holds a retreat asset as ETH once ETH is deeply oversold, keeping the ETH v2 has already won, and releases it
when ETH recovers above its EMA50:

| variant | added layer(s) |
|---|---|
| `capit40` | ETH/USD <= 0.60 x its 90-day high close -> USDC share held as ETH until ETH/USD > EMA50(ETH/USD) |
| `capit30` | same at 0.70 |
| `rlow25` | R <= 0.75 x its 90-day high -> BTC share held as ETH until R > EMA50(R) |
| `rlow15` | same at 0.85 |
| `capit40_rlow25`, `capit30_rlow15` | both locks |
| `capit40_rlow25_rvol` | both locks + EXP-179 `rvol` |
| `capit40_rlow25_rbreak` | both locks + `rbreak_all` shield |

Same bar and procedure; ETH/USD = G x sqrt(R).

Batch 4 IS (v2 from the batch 3 run, same code and data):

| variant | IS ETH x / CAGR / max DD / Calmar | significant |
|---|---|---|
| `rlow25` | 4.269 / 58.19% / −20.4% / 2.854 | no (CAGR +0.86 < +2; DD 6.0 pts shallower) |
| `rlow15` | 3.935 / 54.17% / −17.9% / 3.019 | no |
| `capit40_rlow25_rvol` | 4.174 / 57.07% / −20.4% / 2.798 | no |
| `capit40_rlow25` | 4.109 / 56.28% / −20.4% / 2.760 | no |
| `capit40_rlow25_rbreak` | 4.050 / 55.57% / −24.6% / 2.261 | no |
| `capit40` | 4.038 / 55.43% / −26.4% / 2.098 | no |
| `capit30_rlow15` | 2.746 / 37.59% / −17.9% / 2.094 | no |
| `capit30` | 2.902 / 40.03% / −26.4% / 1.516 | no |

The BTC lock (`rlow`) is the first added layer that cuts the ETH drawdown a lot (−20.4% / −17.9%); the USDC lock
(`capit`) only costs return. `rlow25` by year vs v2: 2022 x2.887 vs 2.726 (R rebounded after the lock), 2024 x1.143 vs
1.190 (R kept falling, 0.054 -> 0.035, after the lock), 2021 / 2023 equal.

### Batch 5, the last (written after batch 4's IS results, before any batch 5 run)

The BTC lock with a guard against trending declines, and stacked with `rvol`:

| variant | added layer(s) |
|---|---|
| `rlow25_conf` | rlow25, entry also needs R >= 1.05 x its 10-day low |
| `rlow25_newlow` | rlow25, released (and entry blocked) on a close below R's previous 20-day low |
| `rlow20` | lock at R <= 0.80 x 90-day high |
| `rlow25_e100` | rlow25 held until R > EMA100(R) |
| `rlow25_lp` | rlow25, the LP share is also held as ETH while locked |
| `rlow25_rvol`, `rlow25_conf_rvol`, `rlow25_newlow_rvol` | with the EXP-179 `rvol` filter |

Batch 5 IS:

| variant | IS ETH x / CAGR / max DD / Calmar | significant |
|---|---|---|
| `rlow25_rvol` | 4.338 / 58.99% / −20.4% / 2.892 | no (CAGR +1.66 < +2; DD 6.0 pts shallower) |
| `rlow25_lp` | 4.301 / 58.56% / −20.7% / 2.828 | no |
| `rlow25_e100` | 4.269 / 58.19% / −20.4% / 2.854 | no (identical to `rlow25`) |
| `rlow20` | 4.017 / 55.17% / −17.9% / 3.076 | no |
| `rlow25_conf_rvol` | 4.093 / 56.09% / −26.1% / 2.150 | no |
| `rlow25_conf` | 4.032 / 55.35% / −26.4% / 2.095 | no |
| `rlow25_newlow_rvol` | 4.006 / 55.03% / −23.0% / 2.388 | no |
| `rlow25_newlow` | 3.974 / 54.64% / −22.9% / 2.389 | no |

Verdict: **fail** on the pre-registered significant bar — 24 added layers in three batches, none reaches CAGR +2 pts
with DD 3 pts shallower in-sample, so none got an OOS run. Closest: `rlow25_rvol`, +1.66 pts CAGR and 6.0 pts shallower
max DD (Calmar 2.892 vs 2.170). The ETH/BTC-low BTC lock is the strongest drawdown cut found for v2 (−26.4% -> −20.4%,
rlow20 −17.9%); guards against trending declines (`conf`, `newlow`) undo it. Its out-of-sample check is pre-registered
separately as EXP-181.

## Deviations

- The flags were chosen after looking at v2's in-sample drawdowns (stated in the hypothesis); IS results are therefore
  partly in-sample by design, and OOS decides.
