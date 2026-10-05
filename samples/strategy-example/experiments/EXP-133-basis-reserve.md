# EXP-133: idle reserve held as a basis trade, spot + short USDT-M perp, earning funding (v6.119)

Standalone level (README *Success levels*). Idle-capital yield does not count as an improvement (Dino, 2026-10-05); the
comparison with v6, v6.4 (Aave) and v6.39 (stable LP) is reported, not judged.

- Jira: QUAN-1018
- Status: dropped-at-dev
- Pre-registration commit: 636e7d0 · Result commit: 27a1660
- Scope: Dino, 2026-10-06: "不管，有沒有其他方向" then "做 basis trade" — the pure-LP scope (no perps) is waived for this
  experiment. Number EXP-133 / v6.119 and OPT key `DE` reserved with the goal4 session.

## Hypothesis

v6 lags holding the asset in bull markets because its ETH exposure is low (≈ 34–38% of equity in up regimes,
`RESEARCH-2026-10-05-lp-vs-hold.md` §2.3) and every way of adding exposure paid back in bears (EXP-001..003, 009, 073) or
was fairly priced (a 30-day call overlay at DVOL, rough sketch 2026-10-06: CAGR unchanged, max DD −25% to −30%). Perp funding
is the one return stream that is high in bull markets without adding price exposure: Binance USDT-M funding received by a
short, annualised, ETHUSDT 2021 37.5%, 2022 0.8%, 2023 8.3%, 2024 13.0%, 2025 4.9%, 2026-01..09 1.9%; BTCUSDT 30.6%, 4.2%,
7.9%, 11.9%, 5.1%, 2.9%; 14% of 8-hour periods negative (input statistics, seen before this registration). v6's reserve
(1 − F) x equity, mean F 0.65 on ETH 2022–26, is idle USDC. Holding it as spot + an equal short perp earns that funding with
the price risk hedged. Expected: CAGR +1 to +2.5 pts over v6, most of it in 2021 and 2024, max DD about unchanged.

## Change

Variant `DE` (`BASIS = "pool"`): once a day at 00:00, the reserve held then (quote outside the ladder minus the paid-out
fees and income, the same base as EXP-052's `accrue_stable`) earns the basis trade's return for the previous UTC day:

- Hedge size: 90% of the reserve is the hedged notional (spot bought, the same notional shorted on the pool asset's
  USDT-M perp); 10% stays USDC as margin buffer.
- Daily return per $ of reserve = 0.9 x the sum of that day's three 8-hour funding rates (`binance_funding_ETHUSDT_long.csv`
  for ETH pools, `..._BTCUSDT_long.csv` for WBTC pools), signed: negative funding is paid. Held through negative funding; no
  gate.
- Switching cost: every change of the reserve since the last accrual pays 0.9 x moved x 0.15% (spot taker 0.10% + perp
  taker 0.05%, Binance base tier), one way.
- Booked as income like the fees (not deployed), as EXP-004 and EXP-052 do.
- Not modelled (stated): the spot-perp basis at entry and exit, USDT/USDC conversion, exchange and liquidation risk (the
  10% buffer plus spot collateral in a unified account is assumed to cover margin calls).
- Constants: 0.9, 0.15%, the two funding files. Everything else is v6.

## Pre-registration

- Development (in-sample price paths): `opt:A,E,AO,DE` (v6, v6.4 Aave, v6.39 stable LP, this) on ETH/USDC 0.05% yearly
  segments 2022 .. 2026-01-01..09-17 and continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% continuous 2022-11-01..2026-09-17.
- Holdout (run once, only if dev passes): time-split out-of-time with `BINANCE_WARM=1`, `opt:A,E,AO,DE`: H5 ETH/USDC 0.05%
  2021-05-06..12-31 (the 37.5% funding year), H4 WBTC/USDC 0.3% 2022-01-01..10-31 (the 4.2% funding bear). Both windows were
  used for other variants; this variant never ran there.
- Success rule (standalone, absolute):
  - Dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%; ETH positive in at least 4 of 5 yearly
    segments. Fails → `dropped-at-dev`.
  - Holdout: H5 and H4 each total return > 0 and max DD no deeper than −35%; Calmar ≥ 0.50 on at least one of the two →
    `holdout-pass`; otherwise `holdout-fail`.
- Reported, not deciding: CAGR / Calmar / max DD vs v6, v6.4 and v6.39 on every window; funding income by year; daily-return
  correlation with v6.

## Result

Development, code `eaceb12`, `opt:A,E,AO,DE` per window (tag `AEAODE`). v6 reproduces EXP-000 (+85.4% ETH, +85.6% WBTC).

| year (ETH, yearly reset) | v6 | v6.4 Aave | v6.39 stable LP | this | this: funding income net of switching | mean F |
|---|---|---|---|---|---|---|
| 2022 | +7.6% | +8.3% | +7.9% | +5.2% | −$2.37k | 0.55 |
| 2023 | +32.2% | +33.7% | +32.9% | +32.2% | −$0.03k | 0.73 |
| 2024 | +36.4% | +38.9% | +37.6% | +36.9% | +$0.51k | 0.77 |
| 2025 | +16.3% | +18.4% | +17.7% | +16.7% | +$0.40k | 0.58 |
| 2026-01..09-17 | +18.7% | +19.9% | +19.1% | +18.3% | −$0.38k | 0.61 |

| continuous | total | CAGR | max DD | Sharpe | Calmar | reserve income |
|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.614 | — |
| ETH v6.4 Aave | +101.0% | 16.0% | −20.7% | 0.82 | 0.771 | +$15.6k |
| ETH v6.39 stable LP | +89.1% | 14.5% | −22.2% | 0.75 | 0.653 | +$3.7k |
| ETH this | +83.4% | 13.8% | −23.0% | 0.71 | **0.599** | −$1.9k |
| WBTC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.970 | — |
| WBTC v6.4 Aave | +96.6% | 19.1% | −16.3% | 1.10 | 1.166 | +$11.1k |
| WBTC v6.39 stable LP | +89.0% | 17.9% | −17.1% | 1.04 | 1.044 | +$3.5k |
| WBTC this | +85.5% | 17.3% | −18.1% | 1.00 | 0.952 | −$0.1k |

Daily-return correlation with v6: ETH 0.9998, WBTC 0.9999.

Standalone dev rule: ETH Calmar 0.599 < 0.60 (fails), max DD −23.0% ≥ −30%; WBTC Calmar 0.952, max DD −18.1%; ETH positive
years 5/5. Verdict: **dropped-at-dev** — ETH Calmar 0.0011 below the bar; the funding leg lost money over 4.7 years
(ETH −$1.9k, WBTC −$0.1k). Holdout not run. Reported: it is the worst of the three reserve treatments; v6.4's Aave rate is the
best (+2.0 pts ETH CAGR, +1.8 pts WBTC).

Why (measured, diagnostic rerun of ETH 2024 with the income split, same code): mean reserve $24.4k (F 0.77), gross funding
+$1,680, switching cost −$1,165; the reserve moved $862k in the year, all of it on 26 days with F changes (quiet days $452 in
total — the cost is real, not ledger noise). Two mechanisms:
- Funding and the reserve are out of phase: v6's reserve is largest in bears (F 0.55 in 2022, funding 0.8%) and smallest in
  bulls (F 0.77 in 2024, funding 13%), so the high-funding years carry the least notional.
- Every F step moves a quarter or all of the reserve; at 0.135% per move the basis leg pays ~0.5–1% of the reserve per
  rebuild-heavy year, as much as the funding it earns outside the bull peaks. Aave has no switching cost and pays 3–5% in
  bears too.
The hypothesis "funding adds bull-year return to v6" is refuted for v6's idle reserve; a basis leg on capital that does not
follow F (a fixed allocation beside v6) is a different question, not tested here.

## Deviations

- The funding statistics above and the call-overlay sketch were seen before this registration; v6's numbers on every window
  are known.
- Diagnostic rerun after the verdict: ETH 2024 yearly segment with `accrue_basis` wrapped to log gross funding, switching cost
  and the daily reserve (job-local script, not committed). It does not change any number above (net return 0.3689 = the dev
  run's 2024 segment).
- The final exit from the basis leg at the end of a window is not charged (one move of 0.135% of the reserve, ≤ $0.15k).
