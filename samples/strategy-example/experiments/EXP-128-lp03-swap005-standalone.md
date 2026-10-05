# EXP-128: v6.104 (0.3%-tier ladder, swaps on the 0.05% route) judged standalone (v6.104r)

Standalone level (README *Success levels*): a re-judge of EXP-117 on its own fresh holdouts, run once each.

- Jira: QUAN-1013
- Status: dev-done (H-a pass, H-b pending)
- Pre-registration commit: fda7278 · Result commit (H-a): 5393511
- Scope: Dino, 2026-10-06: "開" — open v6.104r, a standalone re-judge of EXP-117 validated on forward data. Number EXP-128 reserved with
  the goal3 session.

## Hypothesis

EXP-117 (v6.104) failed the improvement level on one condition only (ETH yearly wins 2/5, 2023 −12.1 pts in the yearly-reset
segment) while its continuous runs beat v6 on every other measure (ETH CAGR 15.0% vs 14.0%, Calmar 0.79 vs 0.61, max DD −18.9%
vs −22.8%; WBTC 18.2% vs 17.3%, Calmar 1.10 vs 0.97). The question here is the standalone one: is the strategy good by itself
on data it has not seen? Mechanism (EXP-117): the 0.3% tier loses less to LVR per unit of liquidity than the 0.05% tier
(mainnet fee/LVR 1.70 vs 0.75), and routing the rebuild swaps through the 0.05% tier removes the 6x swap fee that sank EXP-015.

## Change

None beyond EXP-117: variant `DD` (`SWAP_ROUTE = "pool"`), same code path. One table entry is added so the rule can run on Base:
`SWAP_ROUTES["0x6c561b44…"] = (("0xd0b53d92…", 0.05),)` (Base WETH/USDC 0.3% ladder, swaps on Base WETH/USDC 0.05%), and the
route's reserve formula accepts hop pools whose token0 is WETH (Base `d0b5`): WETH-side virtual reserve L/√P (token0) or L·√P
(token1), in USD at the hour's ETH/USD. No constant changes.

## Pre-registration

- Development: EXP-117's dev numbers, already seen (see *Deviations*). Standalone dev bar (README): continuous ETH and WBTC
  Calmar ≥ 0.60 and max DD no deeper than −30%, ETH positive in at least 4 of 5 yearly segments. EXP-117: ETH 0.79 / −18.9%,
  WBTC 1.10 / −16.5%, yearly segments +10.1 / +20.1 / +33.8 / +17.0 / +18.3% → 5/5 positive. Passes; not rerun.
- Holdout, two parts, each run once:
  - **H-a, now — Base, another chain and pool pair**: ladder in Base WETH/USDC 0.3% `0x6c56`, swaps on Base WETH/USDC 0.05%
    `0xd0b5`, continuous 2025-01-01..2026-09-17 (`opt:A,DD` on `0x6c56`; v6 on `0xd0b5` `opt:A` in a separate invocation, same
    code). 2024 is excluded before any run: EXP-015 showed the 0.3% pool too thin for a $100k ladder then (impact > equity).
    Freshness: this variant never ran on Base; the ETH/USD price path is the dev one (in-sample), so H-a tests the pool and
    chain, not the price sample. v6's numbers on `0xd0b5` and `0x6c56` over 2025–26 are known (EXP-015).
  - **H-b, forward — data after 2026-09-17**: 2026-09-18..2026-12-31, ETH (`DD` on mainnet `0x8ad5`, route `0x88e6`) and WBTC
    (`DD` on `0x99ac`, route `0x4585` → `0x88e6`), v6 on `0x88e6` / `0x99ac` alongside. Run once, after the data for all four
    pools up to 2026-12-31 is fetched (`samples/fetch_uni_minute.py`), not before 2027-01-01. Warm-up: the pools' own data before
    2026-09-18. Freshness: a new price sample on both assets.
- Success rule (standalone; Calmar is not used on H-b, 3.5 months is too short for it):
  - H-a: total return > 0, Calmar ≥ 0.50, max DD no deeper than −35%.
  - H-b: ETH and WBTC each total return > 0 and max DD no deeper than −35%.
  - H-a fails → `holdout-fail` at once. H-a passes → status `dev-done` with "H-a pass, H-b pending" until H-b runs; then
    `holdout-pass` if H-b passes, else `holdout-fail`.
- Reported, not deciding: v6 on the same windows and pools; daily-return correlation of v6.104r with v6 on each window
  (README: near-copies are not independent evidence).

## Result

### H-a — Base, 2025-01-01..2026-09-17 (run once, code `4909136`)

`opt:A,DD` on `0x6c56` (tag `ADD`) and `opt:A` on `0xd0b5` (tag `A`), same code.

| run | total | CAGR | max DD | Sharpe | Calmar | LP fees | rebuilds | route fee credit | impact (net ledger) |
|---|---|---|---|---|---|---|---|---|---|
| v6.104r (`6c56` ladder, `d0b5` route) | +32.2% | 17.7% | −20.9% | 0.77 | 0.85 | $22.6k | 55 | $3.5k | −$3.12k |
| v6 in `6c56`, swaps at 0.3% (ablation) | +28.1% | 15.6% | −22.0% | 0.69 | 0.71 | $22.6k | 55 | — | $1.98k |
| v6 (`d0b5`) | +32.2% | 17.7% | −21.2% | 0.77 | 0.84 | $24.5k | 55 | — | $0.34k |

Calendar years: 2025 +13.8% (v6 +13.4%, ablation +10.4%); 2026-01..09-17 +16.2% (v6 +16.6%, ablation +16.1%).

H-a rule: total +32.2% > 0, Calmar 0.85 ≥ 0.50, max DD −20.9% ≥ −35% → **pass**.

Reported: daily-return correlation with v6 on `d0b5` **0.998** — on Base the variant is a near-copy of v6 (same return, Calmar
0.85 vs 0.84). The ablation repeats EXP-015's finding (0.3% swaps cost ~4 pts over 21 months) and shows routing recovering it.
Unlike mainnet ETH, the Base 0.3% pool gave no gain over v6 in the 0.05% pool on this window: fees $22.6k vs $24.5k, and the
lower LVR the fee/LVR scan measured (2.53 vs 1.13) did not show up as a higher result.

Status: **dev-done — H-a pass, H-b pending** (forward window 2026-09-18..12-31, run once after the data to 2026-12-31 is
fetched, not before 2027-01-01).

### H-b — forward window

Pending.

## Deviations

- Dev numbers reused from EXP-117 (seen before this pre-registration), as the README prescribes for a re-judged experiment.
  The calendar-year split of EXP-117's continuous runs (ETH wins 3/5, WBTC 5/5) was also seen before; it decides nothing here.
- v6's results on the H-a pools over 2025–26 are known from EXP-015 (v6 on `0x6c56` 2025 +9.9%, 2026-01..09 +18.2%; on `0xd0b5`
  +13.9%, +19.1%).
