# EXP-178: factors and filters on ETH-cbBTC MGL v2, WBTC/WETH `0x4585`, in-sample to 2024 / out-of-sample 2025-26

- Jira: QUAN-1172 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

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

(pending)

## Deviations

- Before any variant ran, v2 alone ran three short checks of the runner on the Rust engine: 2025-03-01..03-10 (smoke),
  2023 and 2025 single years (reproduction of Maker's numbers above). The 2025 year overlaps OOS; only v2 was run there.
- Several variants set a value (EMA span, days, threshold, share), which is parameter tuning inside v2's family; each
  has a reason from EXP-176 or the spec's own sensitivity table. With 10+ tries, single passes are expected by chance.
