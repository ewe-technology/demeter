# Backtest report (markdown in `reports/`)

The reports are the research record: what was asked, what was fixed before the run, what came out, and what it
means. Models: `reports/single_pool_loop.md` (a hypothesis loop) and `reports/spot_yield_and_basket.md` (one study
with numbered sections). Read the relevant one before writing; match its voice and layout.

## Where the text goes

- A new hypothesis in an ongoing loop: a new section in the loop's file (`single_pool_loop.md`), not a new file.
- A new study: a new file `reports/<topic>.md`, linked from the previous one's header ("前一份").
- A result of something already registered: fill in that hypothesis's 結果 section, under its 判定, in place.

## Two commits, in this order

1. **Before the run**: the hypothesis, the method and the verdict rule, committed on their own.
   `feat: pre-register H23, a WBTC/WETH LP while the BTC gate is on and parked stablecoins while it is off`
   (with the script, if it is new). From here on the rule does not change; if the run shows a bug in how the rule
   was coded, fix the code to match the text and say so in a 修改紀錄 note.
2. **After the run**: the results and their reading.
   `docs: report H15 (2021 agrees, barely, once gas is priced) and H16 ($10k passes at 3 gwei)`
   The subject line says what came out, in plain words.

Commit and push only when the user asks for it.

## Structure of one hypothesis section

```markdown
## H<n>：<一句話說要測什麼>（`<script>.py`）

**假設**：<一句可以被推翻的話。為什麼值得測，接在哪個前面的結果之後>

**做法**：
- 池子、資金、期間、窗口、成本（swap 手續費、價格衝擊、gas 的算法）
- 版本表：| 版本 | 看多時 | 看空時 | 對照組 |

### 判定（事先寫死）

- 通過的條件，可以直接拿數字判斷（中位數 > 0、至少 12/16 > 0、前後兩半中位數都 > 0 ……）
- 通過 / 不通過之後下一步做什麼
- 只列出、不判定的項目

### H<n> 結果（<日期>，判定條件在 `<commit>` commit 後才跑）

> 修改紀錄：<跑的過程中發現並修正的問題，修正前後的差別；沒有就不寫>

<結果表>

**判定：<通過 / 不通過，一句話理由>**

### 解讀

- **<粗體一句話結論>** <支持它的數字>
- 推論要標明是推論（「這是推論，還沒有驗證」）
- 事後才看的數字標「事後追加，只列出」
```

A study file opens with 日期, 計畫 / 前一份 links, and a 摘要 of bullets, each led by ✅ / ⚠️ / ❌ in a study, or
by a bold claim in a loop file; then sections numbered `## 1.`, `### 1.1`.

## Tables

- One row per window or per version; percentages with a sign and one decimal (`+10.6%`, `−3.5%`, the real minus
  sign); counts as `14/16`; pt for differences between returns.
- Bold the row or the number the verdict rests on, nothing else.
- A version's name in code font the first time (`g_down`, `0x99ac`), with the pool's pair and fee next to an address.
- Put a per-window list on one line when it is just numbers: `逐窗口（%）：−32.7 −33.2 +5.1 …`

## The closing summary of a loop or study

A 總結 section with a table of the one result that holds (檢查 | 結果), then 其他方向都結案 (one bullet each, with
the reason), 限制, and 下一步建議 (numbered and concrete: which data, which pool, which test).

## Checks before handing it over

- Every number in prose appears in a table above it or in a result file; recompute any you typed by hand.
- Each 結果 names the commit of its 判定.
- The verdict follows the rule as written, even when the result is disappointing; 差一點 is still 不通過.
- Limits are stated: the same price path, overlapping windows, parameters chosen after the fact, approximations.
