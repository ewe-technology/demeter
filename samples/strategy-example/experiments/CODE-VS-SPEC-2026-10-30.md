# Code vs spec, rule by rule: ETH-USDC v3.2 / ETH-cbBTC v2.2 (2026-10-30)

Jira QUAN-1215 (stage 2d of QUAN-1209). Every rule of the two spec sheets dated 2026-10-27 (Maker's PDFs in
#scrum-quant-amm: ETH-USDC MGL v3.2, ETH-cbBTC MGL v2.2) checked against the scripts that the validation runs:
`gamma_maker_defense_ethusdc_v3_2.py` (mainnet USDC/WETH 0.05% `0x88e6`) and `gamma_ig_gap_bands_defense_btceth_v2_2.py`
(mainnet WBTC/WETH `0x4585`, Base WETH/cbBTC `0x7aea`). Earlier audits this builds on: `REPRO-2026-10-29-remix-v3_2-v2_1.md`
section 4 (logic audit, engine, data) and `LOOKAHEAD-AUDIT-2026-10-29.md` (inputs, live gaps).

**Verdict.** v3.2: 54 rules. 44 match, 6 differ, 4 are not modelled (fallback price, aggregator, Chainlink check,
deposits while the flag is ON). Of the 6 that differ:

* fixed here: the range break is now judged on the Binance close (row 24);
* kept and reported: depth slippage instead of the flat 0.1% (row 31), real pool fees instead of the fee formula (row 54);
* kept and documented: the dropped empty band (row 30), mainnet instead of Base (row 34);
* not modelled at first: the gas <= $0.2 claim condition (row 44); modelled since QUAN-1216 (`CLAIM_GAS_CAP=1`).

v2.2: 56 rules, no logic bug. One open point is for the spec: v2.2 judges "out of range" on the pool price, and its
spec does not say which price. The fix moves 1 of v3.2's 16 range breaks by 3 days and the end value by +$0.3k
(reinvest off) / +$1.1k (on). The look-ahead test still passes.

Line numbers in the two tables refer to commit `6202d01` (before the fix). Action key: none; fix (spec) = changed to
the spec; keep, report = kept, number reported both ways; keep, documented = kept on purpose, stated here; not modelled
= the backtest has no such step.

## 1. ETH-USDC v3.2

Known gaps decided in the ticket: (a) range break on the pool tick -> fix to the Binance close; (b) depth slippage
instead of a flat 0.1% -> keep, also report flat 0.1% (2026-10-30: validation uses the flat 0.1%, see
ENGINE-FEE-IN-RANGE-2026-10-29.md); (c) an inner band left without ETH by rounding is dropped -> keep
(<= 0.84% of the book idle); (d) gas <= $0.2 claim condition not modelled (LOOKAHEAD-AUDIT section 3) -> modelled in QUAN-1216.

| # | section | spec rule | code (file:line, what it does) | same / differs | action |
|---|---|---|---|---|---|
| 1 | 2 | Signal = Binance ETHUSDT daily close (UTC 00:00 K-line) | `BINANCE_CSV` L170, `binance_daily_frame` L379-389, `_signal_sources=[BINANCE_SIGNAL]` L1667 | same | none |
| 2 | 2 | Pool price only for LP valuation, ticks, fees; never for signals | Signal frame from Binance only (L1921); pool price for ticks / LP value (L1027-1029, L911). Exception: range break, row 24 | same except (a) | none (see 24) |
| 3 | 2 | Fallback price if Binance unavailable (median of exchanges / Chainlink) | Historical CSV only | not modelled | not modelled |
| 4 | 2 | EMA = `close.ewm(span=n, adjust=False)`, includes the day's close | L335, same call | same | none |
| 5 | 2 | EMA seed = 2017-08-17 close 302.00, continuous from then | CSV row 1 = `2017-08-17,302.00`; whole CSV read L381; first close only seeds (L341) | same | none |
| 6 | 2 | Spans 90/100/110/120 vote; EMA100 also for s and d | `EMA_SPANS` L162, `EMA_SPAN=100` L156, `frame["ema"]=EMA100` L350 | same | none |
| 7 | 2 | Judge on day D close, execute D+1 00:00, once a day | `daily_row_for` L392-395 (timestamp - 1 day); daily `PeriodTrigger`s L741-748, `RescaleFrequency.daily` L1709 | same (fills at pool 00:00 price) | none |
| 8 | 3 | Four virtual accounts (EMA90-120); F = mean of their LP shares | `VirtualAccount` L258-317, loop L336-347 | same | none |
| 9 | 3 | Rule 1: armed and close < EMA_n -> all USDC, unarmed, L = close | L293-295, `exit` L274-276 | same | none |
| 10 | 3 | Rule 2: unarmed and close > EMA_n -> armed, no buy; exit only a later day | `elif` L296-297 | same | none |
| 11 | 3 | Rule 3: close < virtual centre x 0.80 -> all USDC, L = close, refill restarts | L298-300 (only while a virtual LP exists) | same | none |
| 12 | 3 | Rule 4: close > centre x 1.20 -> rebuild at close, same size; ETH 70% if close > EMA_n else 50% | L301-302, `build` L278-280 (account's own EMA) | same | none |
| 13 | 3 | Rule 5: L = lowest close since exit; stages x1.075 (3 days) / 1.125 / 1.175 / 1.225; size k/4 x assets | `REFILL_STAGES` L188, `REFILL_CONFIRM_DAYS` L187, L303-315 | same | none |
| 14 | 3 | One stage per day; re-arm never skips stages; lower stop active during refill | `nxt = stage + 1` L308; stop L298 independent of `armed` | same | none |
| 15 | 3 | F = mean(virtual LP value / virtual account assets), not stage values | `F_BY_VALUE=True` L198, L317, `virtual_lp_value` L244-255 | same | none |
| 16 | 3 | Start 2017-08-18: close >= EMA_n -> armed, full; else unarmed, L = close; no reset | `SPEC_START=True` L203, L285-291, L341 | same | none |
| 17 | 3 | Virtual accounts keep running while the divergence flag is ON | Flag only builds `Fp` (L352-353) | same | none |
| 18 | 4 | 8 bands per side, 2.5% price steps, c x 0.80 .. c x 1.20 | `build_price_bands` L496-519; shape `inverted_gaussian_spec_price` L1633; ratios 0.20 / `MIRROR_PRICE` | same | none |
| 19 | 4 | Weights centre outward 1.2/4.6/8.8/13/16/18/19/19.4% | `SHAPE_WEIGHTS["inverted_gaussian_spec"]` L561-564; self-check L2022-2023 | same | none |
| 20 | 4 | ETH above / USDC below; s = 70% if build-day close > EMA100 else 50% | `resolve_share` L782-796, `ema_share_for` L398-402, swap to s x F' L814 | same | none |
| 21 | 4 | Daily order: upper break, lower break, follow F' | Trigger order L741 (`rescale_work`) -> L743 (`follow_work`) -> L745 claim -> L747 reinvest | same | none |
| 22 | 4 | Rule 1 upper break: rebuild centred at close, same size | L1041-1046: `build_fraction` = current LP share; flag ON -> 0 directly | same outcome | none |
| 23 | 4 | Rule 2 lower break: whole ladder to USDC | L1047-1050: `build_fraction = 0` | same | none |
| 24 | 4 | Breaks judged on the Binance close vs centre x 1.20 / 0.80 | `check_rebalance` L1000-1007: pool 00:00 tick vs the outermost placed band ticks | differs (a) | **fixed (spec), section 1.1** |
| 25 | 4 | Rule 3: abs(F' - cur) >= 12.5%, or F' = 0 with position, or F' >= 99.9% and gap > 1% | `follow_work` L926-929; constants L189, L194 | same | none |
| 26 | 4 | Rebuild at size F' x assets, rest USDC, centred at execution | `pre_placement_swap` L805-814; reserve outside the bands L1107 | same | none |
| 27 | 4 | Current LP share = LP / (LP + USDC outside), after break handling, excl. rewards | `lp_fraction` L908-915 (pool price, excludes `held_quote_fee`); runs after `rescale_work` | same (valued at the pool price, see N4) | keep, documented |
| 28 | 4 | Boundaries from price ratios then ticks (+1,823 / -2,231), not tick-symmetric; token order | Exact offsets `snap=False` L108-109, L513-514; self-check L1998-1999 | same | none |
| 29 | 4 | Centre = pool price at execution; each boundary the nearest tick-spacing multiple | `ROUND_EACH_BOUNDARY` L209, `calculate_range` L765-767 | same | none |
| 30 | 4 | All 16 bands placed | A band with zero liquidity after rounding is dropped (L1112-1114, L1256-1258) | differs (c) | keep, documented |
| 31 | 4 | Backtest swap cost flat 0.1% per rebalance | `SWAP_COST_RATE=None` L175 + `SLIPPAGE_MODEL="depth"` L180 (pool fee 0.05% + depth) | differs (b) | keep, report (section 1.1); validation uses flat 0.1% (`FLAT_SWAP_COST=1`, decided 2026-10-30, QUAN-1213) |
| 32 | 4 | Aggregator swap, 0.5% slippage tolerance, private RPC | Fills at the pool 00:00 price | not modelled | not modelled |
| 33 | 4 | Anti-manipulation: pool vs Chainlink / TWAP within 0.3-0.5% before executing | Not in code | not modelled | not modelled |
| 34 | 1/4 | Pool = Base ETH/USDC | Mainnet `0x88e6` 0.05%; Base `0x6c56` is the contract check (Dino, 2026-10-30) | differs (decided) | keep, documented |
| 35 | 5 | d = close / EMA100 - 1 | L351 | same | none |
| 36 | 5 | OFF -> ON at d >= 0.40; ON -> OFF at d < 0.20 | `divergence_flags` L357-363, constants L186 | same | none |
| 37 | 5 | F' = 0 while ON, F' = F while OFF | L353; `target_fraction_for` L405-408 | same | none |
| 38 | 5 | One shared flag, judged after the virtual accounts | Computed after the account loop, L350-353 | same | none |
| 39 | 5 | Flag starts OFF on 2017-08-17, never reset | Loop from the seed row L359-363 | same | none |
| 40 | 5 | ON day: rule 3 sends the ladder to USDC and claims | `follow_work` (F' = 0, cur > 0) L928 -> `rescale_work` collects fees L1055-1056 | same | none |
| 41 | 5 | Back to OFF: F' = F at once, full ladder if F = 1, no staged refill | `follow_work` rebuilds at F' (L926-937) | same | none |
| 42 | 5 | New deposits held in USDC while ON | One initial deposit only | not modelled | not modelled |
| 43 | 6 | Daily claim after the judgement when unclaimed > $5 | `claim_work` L829-845, `CLAIM_MIN_USD=5` L212 | same | none |
| 44 | 6 | ... and estimated gas <= $0.2 (else delay) | Not modelled (comment L211); QUAN-1216: `claim_work` waits while `claim_gas_usd` > $0.2 (`CLAIM_GAS_CAP=1`) | same with the flag (d) | fixed (QUAN-1216) |
| 45 | 6 | Claim at every rebuild regardless of size | `rescale_work` L1055-1056 | same | none |
| 46 | 6 | Success fee 25% deducted at claim | `SUCCESS_FEE_RATE=0` L220 (spec section 7 is before the fee) | same as the spec backtest | keep, documented |
| 47 | 6 | ETH part of the net reward swapped to USDC | L983-986, after the success fee (pays the 0.05% pool fee, N2) | same | none |
| 48 | 6 | Reward balance in USDC, outside principal, in daily P&L | `total_quote_fee` L987, `held_quote_fee` L847-851, excluded from the LP share L913 | same | none |
| 49 | 6 | Reinvest on the 1st 00:00 after judgement and claim; whole balance | `reinvest_work` L858-889; trigger order L744-747 | same | none |
| 50 | 6 | Split: F' of it to the LP, rest USDC; F' = 0 all USDC | `reinvest_split` L416-422; `add_to_bands` L891-906; F' > 0 with no ladder -> all USDC (N3) | same | keep, documented |
| 51 | 6 | Balance <= $5 not reinvested, carried | L419 | same | none |
| 52 | 6 | Auto reinvest on by default; off keeps the balance | `REINVEST_MODES=[True, False]` L216; `compound` gate L746 | same | none |
| 53 | fees | Execution fee $0.5-1 per rebalance, $0.2 per claim | Not charged (spec section 7 excludes them too) | same as the spec backtest | not modelled |
| 54 | 6/7 | Reward income (spec: calibrated formula) | Real pool fees; `FEE_IN_RANGE_LIQUIDITY` flag, off by default, on for validation (QUAN-1213) | differs (REPRO section 4) | keep, report |

New small differences (not in (a)-(d)), none changes a result by more than $30:

- **N1.** An upper break and a follow-F' rebuild can fall on the same morning: two rebuilds in one day. The spec orders
  the same two steps; a live bot would merge them into one transaction. Once in 2021-26 (2025-10-07), about $17 of swap cost.
- **N2.** Selling the reward ETH pays the 0.05% pool fee; the spec prices no such swap. About $25-30 over 2021-26.
- **N3.** A reinvest with F' > 0 but no ladder goes all to USDC. This needs 0 < F' < 12.5% on an empty book on the 1st.
  It happened 0 times in 63 months.
- **N4.** The "current LP share" in the 12.5% follow rule is valued at the pool price. Spec section 4 says "at the
  UTC 0 close", but section 2 gives LP valuation to the pool price. The basis is usually < 0.1%, far below the 12.5%
  threshold. Kept.
- **N5.** A dropped inner band leaves at most 1.2% x s of the book idle (0.84% at s = 70%), below the 1% gap of the
  99.9% rule, so it cannot cause a daily rebuild loop. The stale "~1.3%" code comment is corrected.

### 1.1 The range-break fix

Spec section 4 daily rules 1-2: "close > centre x 1.20 -> rebuild; close < centre x 0.80 -> all USDC", with section 2's
close = the Binance daily close and the centre = "the close at the build". The code tested the 00:00 pool tick against
the outermost placed band ticks instead.

Change (`gamma_maker_defense_ethusdc_v3_2.py`):

* `range_break(close, centre)` returns 1 / -1 / 0 with the spec's strict comparisons; `_self_check` tests both edges.
* Every build (`first_lp`, `rescale_work`) stores the Binance close of the judged day as `centre_close`. The reinvest
  top-up keeps the ladder's ticks, so it keeps the centre too.
* Which centre: the spec has two. Section 4's shape says "c = the close at the build"; v3.1's execution rule centres the
  placed bands on the pool price. The break test uses the close-based centre, because rules 1 and 3 rebuild "centred on
  the close" and section 2 keeps signals off the pool price. The two centres differ by the 00:00 pool-vs-Binance basis,
  usually < 0.1%.
* In signal mode `rescale_work` asks `range_side`, which judges the day's Binance close with `range_break`. The rebuild
  itself still trades and places the bands at the pool price (spec v3.1 section 4).
* `BREAK_ON_POOL_TICK=1` (environment) restores the old test; its result folder gets `-breaktick`. The old test reads
  the break side from tick order and assumes USDC is token0 (mainnet `0x88e6`). On Base `0x6c56`, where WETH is token0,
  it would swap upper and lower breaks; the new close-based test has no such dependence.

Checks:

* The old path (`BREAK_ON_POOL_TICK`) reproduces the earlier full run byte for byte (all 8 output files equal
  `result/remix_check/_work/...-slipdepth-100000-20210506-20260831`).
* Look-ahead truncation test rerun on the fixed code: 5 of 5 dates PASS, 0 mismatches
  (`result/quan1215_lookahead/summary_v32.csv`). The new rule reads day D's close at D+1 00:00, like the other rules.

Effect, $100k, 2021-05-06..2026-08-31, mainnet `0x88e6`, fee-in-range off (as REPRO section 2). Max DD on UTC 00:00
daily values in % (REPRO section 4 item 2). All four runs in one code version, raw in `result/quan1215/` (main checkout):

| swap cost | range break | reinvest off: end | DD | reinvest on: end | DD | range breaks (up / down) |
|---|---|---|---|---|---|---|
| pool fee + depth (default) | pool tick (old) | $222,864 | −17.82% | $295,614 | −24.16% | 15 / 1 |
| pool fee + depth (default) | **Binance close (spec)** | **$223,193** | −17.82% | **$296,702** | −24.16% | 15 / 1 |
| flat 0.1% (spec) | pool tick (old) | $222,414 | −17.22% | $296,065 | −24.27% | 15 / 1 |
| flat 0.1% (spec) | **Binance close (spec)** | **$222,744** | −17.22% | **$297,167** | −24.27% | 15 / 1 |

Spec section 7 for comparison: $231.9k (−19%) off, $323.7k (−24%) on; the gap is its fee formula (REPRO section 2).
The flat-0.1% pool-tick row equals the 2026-10-29 run in `result/...-swap10bp-100000-20210506-20260831` to the cent.

What moved: one break of 16, the same in all four pairs. The ladder built on 2023-01-12 had a centre close of $1,389.39,
so its close-based upper edge was $1,667.27. Its placed edge came from the pool price at the build ($1,389.70, tick
202130). On 2023-02-05 00:00 the pool price was $1,667.58 (tick 202129), 1 tick past the placed edge, so the old test
rebuilt. The Binance close of 02-04 was $1,666.38, below the close-based edge, so the spec does not rebuild. The first close
above it is 02-07 ($1,671.03), so the spec rebuilds on 02-08. All other 163 rebuilds keep their dates. The +$0.3k / +$1.1k
come from the ladder earning three more days of fees at the old centre. The effect is path luck, not a gain to expect.

## 2. ETH-cbBTC v2.2

| # | section | spec rule | code (file:line, what it does) | same / differs | action |
|---|---|---|---|---|---|
| 1 | 2 | E = Binance ETHUSDT daily close | L198-200 reads `binance_ethusdt_1d.csv` | same | none |
| 2 | 2 | B = Binance BTCUSDT daily close | L198-200 reads `binance_btcusdt_1d.csv` | same | none |
| 3 | 2 | R = Binance ETHBTC pair close (BTC per ETH) | L198-207 `ethbtc` pair passed as R, not E/B | same | none |
| 4 | 2 | G = sqrt(E x B) | L207 `(btcusdt * ethusdt) ** 0.5` | same | none |
| 5 | 2 | Close of D = D 00:00..D+1 00:00 K-line; records labelled D | Rows indexed by K-line day; `target` reads row `timestamp - 1 day` (L361); daily log `date` = D (L523) | same | none |
| 6 | 2 | Judge on the D close, execute D+1 00:00, once a day | `PeriodTrigger(1 day)` at 00:00 (L325), row D (L361) | same | none |
| 7 | 2 | Pool price only for LP valuation, ticks, fees | Signals use Binance only (L195-231); the pool price also judges out-of-range (row 33) | differs (row 33) | keep, report |
| 8 | 2 | EMA = `ewm(span=n, adjust=False)`, includes today | L214-215 | same | none |
| 9 | 2 | EMA seed 2017-08-17 for G and R, continuous | L68, L201 refuses data not starting 2017-08-17; L204 refuses gaps | same | none |
| 10 | 2 | G EMAs 90/100/110/120; R EMA100 | `EMA_SPANS` L71, `STRENGTH_SPAN` L87, L214-215 | same | none |
| 11 | 2 | Strong if R > EMA100(R), weak if R < | L230 `r > r_ema`; a tie counts weak (spec silent) | same | none |
| 12 | 3 | One virtual ±20% valley LP per G EMA; F = mean of four | L217, L229; valley bands L80-81, L106-118 | same | none |
| 13 | 3 | EMA exit: armed, close < EMA_n, EMA_n(today) < EMA_n(20 d ago) -> exit, unarmed, L = close | L172-174, `shift(20)` L216 | same | none |
| 14 | 3 | Re-arm: unarmed and close > EMA_n, no buy | L175-176 | same | none |
| 15 | 3 | Lower stop: close < centre x 0.80 -> exit, L = close, refill restarts | L177-179 (`LOWER_STOP` L73) | same | none |
| 16 | 3 | Upper rebuild: close > centre x 1.20 -> recentre at close, no exit | L180-181 | same | none |
| 17 | 3 | Rebuild shape: 25% below EMA100(G) x 0.95, 70% above EMA_n, else 50% | L156 (`VIRTUAL_*` L84) | same | none |
| 18 | 3 | Same shape rule at refill / start builds (spec states it for the rebuild only) | L83 comment; `build` L167, L190 | same (assumption) | keep, documented |
| 19 | 3 | Refill stage 1: close >= L x 1.05 three consecutive days -> 25% | L183-186 `confirm` counter, reset on a miss | same | none |
| 20 | 3 | Stages 2-4: L x 1.0833 / 1.1167 / 1.15 -> 50 / 75 / 100% | `REFILL_STAGES` L75, L187-190 | same | none |
| 21 | 3 | L = lowest close since exit; at most one stage a day | L183 `min`; L185 one `nxt` per day | same | none |
| 22 | 3 | F = mean(virtual LP value / virtual assets) | `F_BY_VALUE=True` L78, L192, L229 | same | none |
| 23 | 3 | Start 2017-08-18: close >= EMA_n armed + full, else unarmed, L = close | L163-169; seed day only seeds (L222) | same | none |
| 24 | 3 | State never reset by deposits | One signal frame per run (L686) | same | none |
| 25 | 4 | Strong: LP F x 75%, ETH F x 25%, BTC 0, USDC 1 - F | L236-237 (`ETH_KEEP` L88) | same | none |
| 26 | 4 | Weak: LP F, ETH 0, BTC 1 - F, USDC 0 | L238 | same | none |
| 27 | 4 | One uniform range centred on the pool price at the build | L407, L419 `range_ticks(current_tick, ...)` | same | none |
| 28 | 4 | 50/50 ETH/BTC at the centre | L420: v3 geometry with the price edges gives 52.4% / 54.8% ETH | differs (spec wording) | keep, documented |
| 29 | 4 | Width ±20% weak, ±10% otherwise | `RANGE_WEAK/STRONG` L89 | same | none |
| 30 | 4 | Out of range (either side) -> rebuild at today's price, no exit | L511-514 -> `rebuild` L530 at target shares | same | none |
| 31 | 4 | Trigger 1: any of LP / ETH / BTC / USDC off target by >= 12.5% | L515 (`FOLLOW_THRESHOLD` L92) | same | none |
| 32 | 4 | Triggers 2-4: target LP 0 with LP; target LP >= 99.9% short > 1%; target USDC 0 with > 0.1% | L517, L519 (vs 99%, <= 0.1 pt from the spec), L521 | same | none |
| 33 | 4 | "Price out of range" (section 2: Binance for signals, pool for ticks) | L510-511: pool tick of the 00:00 row, `lo <= tick < hi` | differs (spec ambiguous) | keep, report; spec to say |
| 34 | 4 | Edges in ETH per BTC: +953 / −1,054, +1,823 / −2,231 ticks | L261; tests L733-735 | same | none |
| 35 | 4 | Token order sets the pool direction (Base mirrored) | L262-263; tests L740-746 | same | none |
| 36 | 4 | Centre and edges rounded to the nearest tick-spacing multiple | L260, L264 | same | none |
| 37 | 4 | Swap cost 0.1% per rebalance | `SWAP_COST` L96, `swap_deltas` L277-282 | same | none |
| 38 | 4 | Anti-manipulation check vs Chainlink / TWAP | none | not modelled | not modelled |
| 39 | 5 | Claim when unclaimed > $5 and gas <= $0.2 | L382: claims at >= $5; no gas test | differs (gas) | not modelled |
| 40 | 5 | USD conversions via Chainlink | `0x88e6` pool price (L336, L583-584) | differs | not modelled |
| 41 | 5 | Always claim at a rebalance and at withdrawal | L408 `force=True`; L536 at the end | same | none |
| 42 | 5 | Unclaimed rewards in daily P&L | net value = liquidity + uncollected fees | same | none |
| 43 | 5 | 25% success fee at claim | `PERFORMANCE_FEE = 0` L101 (spec numbers are before the fee) | same as the spec backtest | keep, documented |
| 44 | 5 | Net WETH reward -> cbBTC | L393 swap at `REWARD_SWAP_COST` 0.1% (L102; the spec names no cost) | differs (tiny) | keep, report |
| 45 | 5 | Net reward to a reward balance in cbBTC | `reward_btc` L395, outside principal | same | none |
| 46 | 5 | Reward balance valuation (reinvest off) | cbBTC marked at market; the spec fixes it in ETH at the claim; moves max DD | differs | keep, documented |
| 47 | 5 | Reinvest on the 1st, after the judgement (and claim, rebuild) | L531-532 after L504 claim and L530 rebuild | same | none |
| 48 | 5 | Whole balance reinvested, split by the target allocation | L241-252, L446-480 | same | none |
| 49 | 5 | F = 0 -> all to the retreat asset | `allocation` gives LP 0 at F = 0; tests L723-724 | same | none |
| 50 | 5 | Balance <= $5 not reinvested, carried | L246; tests L725-726 | same | none |
| 51 | 5 | Target LP > 0 but no LP position (spec silent) | L249-251: LP part to the retreat asset (REPRO section 5, assumption 1) | silent | keep, documented |
| 52 | 5 | Reinvest LP part: add to the range or recentre (spec silent) | L466-478 adds to the existing ticks (assumption 2) | silent | keep, documented |
| 53 | 5 | Reinvest swaps at 0.1% | L469-474 | same | none |
| 54 | 5 | Toggle takes effect from the next month-end | Mode fixed per run | n/a | not modelled |
| 55 | 5 | Execution fees $0.5-1 / rebalance, $0.2 / claim | Not charged (spec numbers exclude them too) | same as the spec numbers | keep, documented |
| 56 | 6 | 1 ETH start; spec periods | `init_quote = 1`; windows start on 1/2 | same | none |

New small differences in v2.2:

- **Row 33, out of range on the pool tick.** Measured on the existing v2.2 runs (`result/quan1212_v2_2/`), re-judged
  with Binance 1/R against the same ranges. Mainnet `0x4585` 2022-25: 11 out-of-range rebuilds on the pool tick, 10 on
  Binance. The one extra is 2025-07-15: the pool was 8 ticks past the lower edge, Binance 7.7 ticks inside. That range broke
  anyway on 07-18, so the cost is one extra rebuild (about 0.001 ETH) and a recentre 3 days early. Base `0x7aea`
  2024-09..2026-08: 9 of 9 agree. The pool vs Binance gap is a median of 5 ticks on mainnet (max 115, WBTC basis) and
  0.5 ticks on Base. Kept: being in range is a pool fact a live bot reads from `slot0`, and v2.1's centre rule already
  uses the live pool price. Unlike v3.2's spec, v2.2's spec does not say "close" here.
- **Row 44.** The WETH -> cbBTC reward swap is charged 0.1%: about 0.0008 ETH over 2022-25.
- **Row 28.** "50/50 at the centre" cannot hold with price edges of ±10% / ±20%; the code follows the edges. Spec wording only.
- Ties, all negligible: claim at >= $5 vs "> $5"; R = EMA100(R) counts weak; trigger 3 tests 99%, not target − 1%.

## 3. Open for the spec owner (not blocking stage 3)

1. v2.2 section 4: should "out of range" use the pool price (as now) or the Binance R close (as v3.2's section 4 says
   for ETH-USDC)? One rebuild in four years differs on mainnet, none on Base.
2. v3.2 section 4: should the "current LP share" be valued at the Binance close or the pool price (N4)? No effect on the
   2021-26 run.

## 4. Reproduce

    cd samples/strategy-example     # Rust engine, $PY = ../../.venv-rs/bin/python, no PYTHONPATH
    $PY gamma_maker_defense_ethusdc_v3_2.py                           # spec rule (default)
    BREAK_ON_POOL_TICK=1 $PY gamma_maker_defense_ethusdc_v3_2.py      # old pool-tick rule, "-breaktick" folder
    # flat 0.1%: set SWAP_COST_RATE = Decimal("0.001") and SLIPPAGE_MODEL = None at the top of the script
