# EXP-178: factors and filters on ETH-cbBTC MGL v2, WBTC/WETH `0x4585`, in-sample to 2024 / out-of-sample 2025-26

- Jira: QUAN-1172 (subtask of QUAN-1107)
- Status: pass (2 of 10 count: `keep50` IS +0.82 / OOS +1.47 pts CAGR in ETH, `f2low` +4.13 / +0.35)
- Pre-registration commit: f0a0917 · Result commit: f29910a

/goal 2026-10-19 (Dino): "在v2上新增一些因子或濾網，找到比v2好的策略".

## Hypothesis

MGL v2 (Isao, 2026-09-30) earns its ETH from the USD retreat in falling markets (2022 x2.88) and loses ETH when ETH
rallies against BTC (2021 x0.59) or while parked in USDC during an ETH rally (2025 max DD in ETH −37%). Its strength
switch (R vs EMA100) and its exits are unfiltered single-close rules. One added factor or filter, or one deleted rule,
may improve the ETH result before and after 2025; EXP-176 found three such changes on v3 that held out of sample
(short EMA for the share switch, slower stage-1 refill, F from the second-lowest account).

## Change

Base (`v2`): Maker's `gamma_maker_defense_btceth_v1.py` at `maker-defense` 5cec767, the implementation of the
"WB + ETH-strong 25%" spec, whose signals, allocation and ranges MGL v2 keeps unchanged (MGL v2 section 0). Defaults =
MGL v2 definitions: Binance UTC closes from 2017-08-17 (G = sqrt(BTCUSDT x ETHUSDT), R = ETHBTC), ladder x1.0, 0.1% swap
cost, no slippage, rewards collected into the wallet and not reinvested (standard mode). Runner `experiments/v2_goal.py`
(Rust engine, mainnet WBTC/WETH 0.05% `0x4585` + WETH/USDC `0x88e6` for the USD price, 1 ETH start). Check before any
variant ran: v2 reproduces Maker's single years exactly, 2023 x1.3002 (Maker 1.300), 2025 x1.1570 (1.157), same USD ratio
and rebuild counts.

Batch 1 (10 variants, one element each, written 2026-10-19 before any variant run; exact replacements in `VARIANTS`):

| variant | element of v2 | change |
|---|---|---|
| `rspan20` | ETH strength line | R vs EMA20(R) instead of EMA100(R) |
| `rconfirm3` | ETH strength filter | added: the flag flips only after 3 consecutive closes on the other side |
| `divG` | overheat filter | added (v3's divergence rule on G): F = 0 while G >= EMA100(G) x 1.40, released below x 1.20 |
| `confirm5` | refill stage-1 confirmation | 5 closes instead of 3 |
| `f2low` | F aggregation | second-lowest of the four accounts instead of the mean |
| `btctrend` | weak-ETH retreat destination | added: while ETH is weak, retreat to USDC instead of BTC when BTC/USD < its EMA100 |
| `keep50` | ETH kept outside the LP while strong | 50% of F instead of 25% |
| `wide20` | LP width while strong | +-20% always instead of +-10% |
| `noslope` | EMA exit slope filter | deleted |
| `follow0625` | rebuild threshold | 6.25% instead of 12.5% |

`btctrend` uses BTC/USD = G / sqrt(R) (Binance closes). `divG` uses EMA100 of G, the second of the four account EMAs.

## Pre-registration

- Pool: mainnet WBTC/WETH 0.05% `0x4585` (the spec's calibration pool; Base cbBTC/WETH has no data).
- In-sample (IS): 2021-11-02 (first minute-data day) .. 2024-12-31. Out-of-sample (OOS): 2025-01-01 .. 2026-09-17.
  Separate runs from 1 ETH each; v2 rerun in the same batch.
- Metric: per-minute net value in ETH, collected rewards included at current prices (standard mode "principal +
  rewards"): CAGR, max drawdown in ETH, Calmar. USD ratio, USD max DD, rebuilds and swap cost reported, not judged.
- Beats v2 on a segment: CAGR above v2, Calmar >= v2, max DD no more than 3 pts deeper (EXP-176 / 177 bar).
- Procedure: designed and judged on IS only; only a variant that beats v2 IS gets an OOS run; a variant **counts** when
  it beats v2 on IS and OOS. Every run is reported. Later batches may use IS results only and are committed before their
  runs.
- Goal reached when at least one variant counts with a margin of 0.1 pt CAGR or more on both halves (a smaller margin is
  noise, EXP-176 convention). If batch 1 has none, a second batch of at most 10 is written from IS results; the search
  stops after batch 3 either way and reports what it found.

## Result

Run 2026-10-19, `v2_goal.py is all 3` then `oos v2,f2low,keep50,noslope,follow0625 3` (Rust engine; raw runs in the main
checkout's `result/v2_goal/{is,oos}-*`, table `result/v2_goal/runs.csv`). All numbers in ETH, rewards included.

| variant | IS ETH x / CAGR / max DD / Calmar | beats v2 IS | OOS ETH x / CAGR / max DD / Calmar | beats v2 OOS |
|---|---|---|---|---|
| v2 | 4.197 / 57.33% / −26.4% / 2.170 | – | 1.384 / 20.90% / −37.2% / 0.562 | – |
| **`keep50`** | 4.266 / 58.15% / −24.9% / 2.339 | yes (+0.82 pt) | 1.413 / 22.37% / −33.6% / 0.666 | **yes (+1.47 pts)** |
| **`f2low`** | 4.556 / 61.46% / −27.9% / 2.206 | yes (+4.13 pts) | 1.391 / 21.25% / −37.2% / 0.571 | **yes (+0.35 pt)** |
| `noslope` | 4.445 / 60.21% / −26.5% / 2.276 | yes | 1.258 / 14.33% / −43.6% / 0.329 | no |
| `follow0625` | 4.198 / 57.35% / −26.4% / 2.170 | yes (+0.02 pt, noise) | 1.381 / 20.78% / −37.2% / 0.559 | no |
| `wide20` | 4.146 / 56.72% / −27.4% / 2.069 | no | – | – |
| `confirm5` | 4.048 / 55.55% / −28.3% / 1.962 | no | – | – |
| `divG` | 3.901 / 53.74% / −26.4% / 2.034 | no | – | – |
| `btctrend` | 3.893 / 53.65% / −40.8% / 1.316 | no | – | – |
| `rconfirm3` | 3.667 / 50.76% / −27.7% / 1.836 | no | – | – |
| `rspan20` | 2.822 / 38.79% / −28.5% / 1.359 | no | – | – |

USD view (reported, not judged): v2 IS x3.233 / USD max DD −53.7%, OOS x1.016 / −53.9%; `keep50` x3.287 / −52.3%, x1.037 /
−54.9%; `f2low` x3.509 / −52.0%, x1.021 / −53.3%. Rebuilds IS / OOS: v2 137 / 76, `keep50` 137 / 76, `f2low` 116 / 68.

ETH ratio by calendar year (2021 = 11-02..12-31, 2026 = to 09-17):

| year | v2 | `keep50` | `f2low` |
|---|---|---|---|
| 2021 | 1.009 | 1.028 | 1.012 |
| 2022 | 2.726 | 2.790 | 2.898 |
| 2023 | 1.295 | 1.282 | 1.308 |
| 2024 | 1.190 | 1.168 | 1.199 |
| 2025 | 1.139 | 1.154 | 1.138 |
| 2026 | 1.212 | 1.222 | 1.219 |

Verdict: **pass** — two variants count with margins of 0.1 pt or more on both halves; goal reached after batch 1.

- **`keep50` (ETH kept outside the LP while strong: 50% of F instead of 25%)** is the cleaner one: CAGR up on both
  halves (+0.82 / +1.47 pts), max DD shallower on both (−24.9 vs −26.4, −33.6 vs −37.2), Calmar up on both, same
  rebuild count. It wins 4 of 6 calendar years and loses 2023-24 (ETH weak against BTC). The spec's own sensitivity
  (6.1) found the same direction (8 years 5.35 vs 3.11 ETH, 4 years 4.87 vs 4.88). Mechanism: while ETH is strong more of
  the book sits in plain ETH, which neither leaks LVR nor sells ETH into a rally.
- **`f2low` (F = second-lowest account)** wins IS by +4.13 pts, almost all in 2022 (x2.898 vs 2.726: it retreats earlier
  and refills later), and OOS by only +0.35 pt with the same max DD; it also cuts rebuilds (116 vs 137). The OOS margin
  is small; read it as "no worse, fewer rebuilds" rather than a clear gain. It was also an EXP-176 finding on v3 (ETH).
- `noslope` (no 20-day falling-EMA test) wins IS but loses OOS badly (14.3% vs 20.9%, DD −43.6%): the slope filter of
  the spec earns its place. `btctrend` (USDC when BTC/USD falls) deepens ETH max DD to −40.8%; shorter or debounced
  strength lines (`rspan20`, `rconfirm3`) lose clearly: the EMA100 strength line holds.
- Caveats: one pool, 11 tries (two counted, about what chance gives for small margins); 0.1% flat swap cost as the spec,
  no gas. Next: the two winners together, and on another BTC/ETH pool (Base `0x7aea`, Arbitrum `0x2f5e`).

## Deviations

- Before any variant ran, v2 alone ran three short checks of the runner on the Rust engine: 2025-03-01..03-10 (smoke),
  2023 and 2025 single years (reproduction of Maker's numbers above). The 2025 year overlaps OOS; only v2 was run there.
- Several variants set a value (EMA span, days, threshold, share), which is parameter tuning inside v2's family; each
  has a reason from EXP-176 or the spec's own sensitivity table. With 10+ tries, single passes are expected by chance.
