# /goal "swap v6's concepts + a dynamic ±20% until one beats v6" (EXP-169..175, 2026-10-07/08)

Bar (pre-registered in each EXP): the team's full-history rule on the seven pools of EXP-157..164 (`judge_full.py`, spec v1
baseline, >= 4 of 7 with an ETH and a BTC pool; per pool CAGR higher, Calmar at least equal, max DD at most 3 pts deeper) and a
win on WBTC/ETH `0x4585` against v6. Batch 1 screened on `0x88e6` + `0x4585` first; batch 2 ran all eight pools.

| EXP | version | swapped concept + dynamic width | single pools | seven pools | verdict |
|---|---|---|---|---|---|
| 169 | v6.154 | v6.75 refill + refill-low lower edge | 1/2 | — | fail |
| 170 | v6.155 | ETH share 50% + refill-low edge | 1/2 | — | fail |
| 171 | v6.156 | no engine lower stop + refill-low edge | 0/2 | — | fail |
| 172 | v6.157 | v6.75 + share 50% + refill-low edge | 2/2 | 3/7 (BTC 0) | fail |
| 173 | v6.158 | v6.75 + +40% top only while F = 1 | WBTC/ETH win | 1/7 | fail |
| 174 | v6.159 | v6.75 + +40% top at F = 1 + refill-low edge while refilling | WBTC/ETH win | 3/7 (BTC 0) | fail |
| 175 | v6.160 | fee tier: v6.75 + refill-low edge on 0.3% pools, v6.75 on cheaper pools | WBTC/ETH win | **4/7** | **pass** |

## What it means

- **EXP-175 passes, but its pass is v6.75's.** On 0.05% pools and WBTC/ETH it is v6.75 exactly; its BTC win (+0.06 pt) and
  WBTC/ETH win (+0.04 pt) are v6.75's and within noise. The dynamic width (refill-low edge, 0.3% pools only) helps Base 0.3%
  (+1.8 pts CAGR over v6.75), trades 0.6 pt CAGR for Calmar on mainnet 0.3%, and loses WBTC 0.3% (-0.3 pt), so it scores 4/7
  where v6.75 alone scores 5/7. Not better than v6.75; a candidate for the forward window at most.
- **The refill-low edge is a drawdown tool.** With share 50% it made max DD shallower on all seven pools (EXP-172, 1..6 pts),
  but cost CAGR where the trend carried the return (L2 0.05% ETH, both BTC pools).
- **A wider top in strong trends is an ETH return tool.** EXP-173/174 add 2.4..5.5 pts CAGR on mainnet and Base ETH and give
  the best WBTC/ETH results so far (+1.5 / +1.1 pts), but max DD on mainnet ETH is 2..4 pts deeper and both BTC/USD pools
  lose about 2 pts CAGR. Arbitrum ETH loses 5.8 pts with every wide-top variant.
- **BTC/USD pools reject every width change tried** (EXP-030, 164, 172..175): seven variants, none raises CAGR on `0x99ac` or
  `0xfbb6`. Only v6.75's refill rule wins there, by +0.06 pt.

## Next

- The forward window (data after 2026-09-17) for EXP-157 (v6.75) and EXP-175.
- If more width work: an ETH-only rule (the BTC pools never gain), judged on ETH pools with BTC reported, would need Dino to
  change the bar (it now requires a BTC win).
