# EXP-017: v6.13 toxicity pause re-registered under a Calmar rule, decided on the Base holdout (v6.13r)

- Version: v6.13r
- Jira: [QUAN-863](https://ewetechnology.atlassian.net/browse/QUAN-863)
- Status: holdout-fail
- Pre-registration commit: 57c40f5 · Result commit: 2fccf26
- Parent: `EXP-016-toxicity-pause.md` (same variant, same constants, same code: variant `L`).

## Hypothesis

EXP-016 (v6.13) failed dev on the return-win count (2/5 ETH segments, median −1.9 pts), but its continuous runs
went the other way: ETH 2022–26 +120.3% vs v6 +85.4%, Calmar 0.65 vs 0.61; WBTC/USDC +102.8% vs +85.6%, Calmar 1.20
vs 0.97, max DD −16.7% vs −17.8%. The yearly-return rule and the continuous risk-adjusted numbers disagree because
the pause is a principal-protection effect (LP principal $99k → $166k on ETH) paid for with fees ($86k → $54k):
it loses in trend years and wins in chop and bear years, so a yearly win count sees mostly losses while the
compounded, drawdown-adjusted curve is better. Dino asked to judge it the way EXP-009/010 re-judged v6.1 and v6.6:
on Calmar, on a holdout.

The holdout is the deployment target, where the idea can live at all: EXP-016's pauses cost ≈ $1.35M of mainnet gas
over 4.7 years, but on Base a burn or mint costs cents. If the pause helps Calmar on Base USDC/WETH 0.05% too, it is
a Base-only candidate; if not, the ETH/WBTC continuous result was in-sample luck.

Honest caveats, stated before the run: (1) this is a second look at a variant that already failed its own rule —
the re-registration is Dino's decision and is recorded as such; (2) the ETH continuous max DD was worse (−28.1% vs
−22.8%), so the rule below adds a drawdown floor; (3) the Base pool is not virgin data — v6 (A) and v6.4 ran on it in
EXP-004 and EXP-015 — but no run of variant L has touched it.

## Change

None. Variant `L` exactly as in EXP-016 at its final implementation (commit b8f3c14): `PAUSE_RET = 0.01`,
`PAUSE_WINDOW = 5` minutes, `PAUSE_MINUTES = 30`; the resume re-runs the build loop at the build's tick with a
top-up pass; no swap; daily checks skip while paused. v6 (A) in the same invocation.

## Pre-registration

- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), yearly
  segments 2024, 2025, 2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17 run, 100,000 USDC, EMA warm-up on
  mainnet ETH/USD (as EXP-004). Gas column still prices mainnet; the Base cost is reported as pauses × 16
  transactions × a Base cost per transaction taken from nothing fitted (stated as a range, $0.01–$0.10).
- Success rule (EXP-009's Calmar family plus a drawdown floor):
  - continuous Base Calmar (CAGR / |max DD|, daily equity) ≥ v6's, **and**
  - continuous Base max DD no more than 3 pts deeper than v6's, **and**
  - yearly return wins in ≥ 2 of 3 Base segments
  → `holdout-pass`, else `holdout-fail`.
- No dev stage: EXP-016's dev numbers are the dev evidence; nothing is rerun on ETH or WBTC.

## Result

Holdout, Base USDC/WETH 0.05%, yearly reset, 100,000 USDC, run once:

| test | v6 | this | gain | max DD v6 → this | fees v6 → this | LP principal v6 → this | pauses |
|---|---|---|---|---|---|---|---|
| 2024 | +19.4% | +9.7% | −9.7 | 30.3% → 33.3% | $17.6k → $10.3k | $105.4k → $103.6k | 267 |
| 2025 | +13.9% | +24.8% | +10.9 | 24.4% → 20.3% | $18.2k → $10.9k | $96.1k → $114.3k | 314 |
| 2026-01..09-17 | +19.1% | +16.4% | −2.7 | 11.9% → 11.4% | $6.6k → $3.7k | $112.6k → $112.9k | 212 |

Wins 1/3, median −2.7 pts.

Continuous 2024-01-01..2026-09-17 (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | fees | LP principal | pauses |
|---|---|---|---|---|---|---|---|---|
| v6 | +55.9% | 17.8% | −28.1% | 0.76 | 0.63 | $43.1k | $114.5k | |
| this | +56.1% | 17.9% | −31.7% | 0.74 | 0.56 | $25.6k | $133.0k | 793 |

Base cost of the pauses: 793 × 16 transactions × $0.01–$0.10 ≈ $130–$1,270 over 2.7 years (mainnet: $470k).

Verdict: **holdout-fail** — all three conditions fail: Calmar 0.56 < 0.63, max DD 3.6 pts deeper (floor 3), yearly
wins 1/3. The pattern is EXP-016's exactly: the pause halves the fees ($43k → $26k) and protects principal
($114k → $133k), so it wins the choppy year (2025 +10.9, DD 24.4% → 20.3%) and loses the trend years; over the
whole window the two cancel (+56.1% vs +55.9%) and the drawdown is deeper, because the protected principal sits in
a thinner ladder when the 2024 fall comes. The ETH/WBTC continuous improvement in EXP-016 did not carry over: on
the deployment pool the toxicity pause is a wash at best. Idea closed; the principal-protection effect is real but
it is paid for in fees one for one.

## Deviations

- Holdout ran once, v6 + this in the same invocation (two workers per segment, segments in sequence). No reruns.
- No ETH mainnet curve for the dashboard: this experiment has no new continuous ETH run (EXP-016's curve stands).
