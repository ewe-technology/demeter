# gamma_ig_gap_bands_defense_v6.py 說明

谷型 LP 防禦邏輯規格書 v6（ETH 70%・單一階梯方式）的回測實作，跑在 Demeter 回測框架上。
從 `remix_dao_gamma_ig_gap_bands.py` 複製後加入三層規格書邏輯：ETH 占比 s 切換、四帳戶訊號引擎算部署比例 F、每日追隨 F 重建。

相關文件：
- [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md)：2024／2025 對規格書的對照報告，給規格書作者
- [ETH_SHARE_TODO.md](ETH_SHARE_TODO.md)：開發過程的待辦與決策紀錄
- [GAP_BANDS_FINDINGS.md](GAP_BANDS_FINDINGS.md)：階梯 gap 與 range 的先前結論
- [IG_GAP_BANDS_RESULTS.md](IG_GAP_BANDS_RESULTS.md)：原始 `ig_gap_bands` 的結果摘要
- [BACKTEST_COST_TODO.md](BACKTEST_COST_TODO.md)：swap 成本模型的待辦

---

## 1. 快速開始

```bash
cd /Users/makersu/work/githubEwe/demeter/samples/strategy-example && PYTHONPATH=../.. python3 gamma_ig_gap_bands_defense_v6.py
```

- 必須在 `samples/strategy-example` 目錄下執行，結果才會寫到該目錄的 `result/`。
- 分鐘資料從 `../real-data/<pool address>/` 讀取，第一次載入後會快取到 `~/.demeter/`。
- 啟動時會先跑 `_self_check()`，任何 assert 失敗代表引擎邏輯被改壞。
- 預設一個 run 約 4 分鐘。多個 run 用 `multiprocessing.Pool` 並行，`_workers = 5`。

輸出資料夾：`result/gamma-pdfv6-<shape>-gap-up<上緣>-dn<下緣>-<eth_share>-<deploy>-usdceth-usdc-<投入>-<起日>-<迄日>/`

---

## 2. 目前預設設定

| 項目 | 值 | 位置 |
|---|---|---|
| 池子 | Ethereum 主網 WETH/USDC 0.05%，`0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`，tick spacing 10 | `process_for_date` 第 1193 行 |
| 投入 | 100,000 USDC，quote 為 USDC | 第 1165 行 |
| 期間 | 2025/1/1 建倉到 2025/12/31 | `date_ranges` 第 1599 行 |
| `_shapes` | `["inverted_gaussian"]`，8+8 段 | 第 1218 行 |
| `_upper_ratios` | `[0.20]`，上緣 +20% | 第 1226 行 |
| `_lower_ratios` | `[MIRROR_PRICE]`，下緣真 −20% | 第 1232 行 |
| `_centre_half_gaps` | `[0]`，中心無 gap | 第 1239 行 |
| `_eth_shares` | `[EMA_SHARE]`，依 EMA100 切換 70%/50% | 第 1245 行 |
| `_deploy_modes` | `[DEPLOY_SIGNAL]`，訊號引擎決定 F | 第 1247 行 |
| `_rescale_frequencies` | `[daily]`，每日 00:00 判定 | 第 1283 行 |
| swap 成本 | 池子 0.05%，`swap_fee=False` 不另計滑價 | 第 1262 行 |
| 手續費 | 收取時賣成 USDC，不再投入 | `collect_fee_as_quote` |

每個清單參數多給一個值就多一組 run，組合數 = shapes × upper × lower × gaps × eth_shares × deploy × frequencies。

---

## 3. 策略邏輯

### 3.1 三個獨立的旋鈕

| 旋鈕 | 決定什麼 | 參數 |
|---|---|---|
| **區間形狀** | 16 段在價格軸上各佔多寬 | `_shapes`、`_upper_ratios`、`_lower_ratios`、`_centre_half_gaps` |
| **投入比例 F** | 總資產有多少放進 LP，其餘留 USDC | `_deploy_modes` |
| **ETH 占比 s** | 放進 LP 的錢，ETH 側和 USDC 側各佔多少價值 | `_eth_shares` |

三者互不影響。區間形狀不決定資金分配，這點和原本 `ig_gap_bands` 的 `sgeo` 模式不同。

### 3.2 建倉／重建的流程

每次建倉或重建（`first_lp` 與 `rescale_work`）：

1. 撤掉全部舊部位，收手續費並賣成 USDC（`collect_fee_as_quote`）。
2. `pre_placement_swap`：
   - `resolve_share` 決定 s（見 3.4）。
   - `target_fraction_for` 取前一個完整日的 F（見 3.5）。
   - 算 `reserve_quote = (1 − F) × 總值`，這筆留在場外。
   - `swap_to_value_share` 把持倉換到 ETH 佔總值 s × F。
3. 依權重表放 16 段：上方 8 段用完 ETH，下方 8 段用完 `USDC − reserve_quote`。每側權重合計 100%，側總額 × 權重就是該段金額。
4. 流動性為 0 的段（現價 tick 剛好落在段邊界時 demeter 需要兩種幣）直接丟棄，不追蹤。
5. 印出實際 ETH 側佔比、F、保留金額與兩側剩餘比例。

以 $100k、F = 100%、s = 70% 為例：ETH 側 $70k，最內段 $0.9k、最外段 $13.6k；USDC 側 $30k，最內段 $0.4k、最外段 $5.8k。

### 3.3 重建的三種觸發

| 觸發 | 判定 | 函式 |
|---|---|---|
| 漲出上緣 | 現價 tick 高於 16 段的上界 | `check_rebalance` → `rescale_work` |
| 跌出下緣 | 現價 tick 低於下界 | 同上 |
| 追隨 F | 每日 00:00，\|F − 目前部署比例\| ≥ 12.5%，或 F = 0 但仍有部位，或 F = 100% 但未滿倉 | `follow_work` → `rescale_work` |

出區間的判定頻率由 `_rescale_frequencies` 決定，追隨 F 固定每日一次。目前部署比例 = LP 淨值 ÷ 總權益，總權益不含已收的手續費。「滿倉」與「空倉」判定容忍 2% 塵埃（`FULL_TOLERANCE`），否則會每日重建。

`rescale_work` 的計數：`Upper Rescale Count`／`Lower Rescale Count` 只算出區間觸發的；追隨 F 的次數印在 `final result` 那行的 `follow rebuilds`。

### 3.4 ETH 占比 s（`resolve_share`）

`eth_share` 參數接受四種值：

| 值 | 標籤 | 行為 |
|---|---|---|
| `None` | `sgeo` | 原本的算法，`calculate_swap_amount` 依整個區間的幾何算出比例，對稱 ±20% 約 ETH 45% |
| `Decimal("0.5")` 等 | `s50` | 固定比例 |
| `EMA_SHARE` | `sema100` | 前一個完整日收盤 > EMA100 → 0.7，否則 0.5（規格書 2.1） |

`signal` 模式不接受 `None`，因為幾何算法無法搭配 F < 1。

### 3.5 訊號引擎 F（`VirtualAccount`、`daily_ema_frame`）

規格書 2.2。四個虛擬帳戶，EMA 週期 90、100、110、120，各自跑同一套規則，F = 四者部署比例的平均，所以 F 是 0 到 1 之間 1/16 的倍數。

每個帳戶每天依序執行（`VirtualAccount.step`）：

1. **EMA 退出**：已武裝且收盤 < EMA → 部署歸零、centre 清空、low = 收盤、段數歸零、改為未武裝。空倉帳戶也照做（規格書字面）。
2. **再武裝**：未武裝且收盤 > EMA → 改為已武裝，不買入。
3. **下緣停損**：有部位且收盤 < centre × 0.80 → 同退出，武裝狀態不變。
4. **上破重建**：有部位且收盤 > centre × 1.20 → centre = 收盤，規模不變。
5. **四段回補**（部署 < 100% 時）：low 每日取更低值；第 1 段需收盤 ≥ low × 1.05 連續 3 日，第 2、3、4 段分別為 ≥ low × 1.0833、1.1167、1.15；**每日最多前進一段**，回落不退段；每段以當日收盤為新 centre。

引擎自回測視窗前 360 天（`EMA_WARMUP_DAYS`）起算，第一天收盤 > EMA 就滿倉，否則空倉。規格書是從 2017 連續跑，這是刻意簡化。

`daily_ema_frame` 把暖身加視窗內的分鐘價格取每日最後一筆當 UTC 日收盤，算出 `close`、`ema`（EMA100，s 用）、`F` 三欄。`daily_row_for` 取「時間戳減一天」那列，所以 00:00 的判定用的是剛結束那天的收盤。

### 3.6 每日的執行順序

demeter 依 trigger 註冊順序觸發，同一分鐘的順序是：

1. `rescale_work`（出區間判定，頻率依 `_rescale_frequencies`）
2. `follow_work`（追隨 F，每日）
3. `log_fees`（每日手續費快照）

1 和 2 都可能重建，但一天最多只會真的重建一次：前者重建後 cur ≈ F，後者不會再觸發；後者重建後在區間內，前者不會觸發。

---

## 4. 主要函式與類別

### 模組層（第 65 到 375 行）

| 名稱 | 用途 |
|---|---|
| `MIRROR_PRICE` / `MIRROR_TICKS` | 下緣算法：真實價格比例，或和上緣相同 tick 數 |
| `EMA_SHARE`、`DEPLOY_FULL`、`DEPLOY_SIGNAL` | 參數的字串常數 |
| `EMA_SPANS`、`LOWER_STOP`、`UPPER_REBUILD`、`REFILL_STAGES`、`REFILL_CONFIRM_DAYS`、`FOLLOW_THRESHOLD`、`FULL_TOLERANCE` | 引擎常數，對應規格書第 3 節參數表 |
| `VirtualAccount` | 一個虛擬帳戶的狀態機，`step(close, ema)` 走一天 |
| `share_label` / `ratio_label` / `gap_label` | 報表與資料夾名稱的標籤 |
| `daily_ema_frame(minute_price)` | 日收盤、EMA100、F 三欄的 DataFrame |
| `daily_row_for` / `ema_share_for` / `target_fraction_for` | 依時間戳取前一日的判定值 |
| `swap_to_value_share(base, quote, price, base_share)` | 純函式，算出要買賣多少 base 才能讓 base 佔總值 `base_share` |
| `build_gap_bands` | 16 段的 tick 偏移 |
| `build_shape_config` | 每段的 `[下偏移, 上偏移, 該側佔比]`，中心權重 0 的段會被丟掉 |

### 策略類別 `RemixDaoDcaWeekStratStrategy`（第 379 行起）

| 方法 | 用途 |
|---|---|
| `__init__` | 收 `shape`、`upper_ratio`、`lower_ratio`、`half_gap`、`eth_share`、`daily_ema`、`deploy` |
| `initialize` | 註冊 `first_lp`、`rescale_work`、`follow_work`、`log_fees`、`calculate_final_result` 五個 trigger |
| `resolve_share(timestamp)` | 決定這次的 s，並累計各比例被選次數 |
| `pre_placement_swap(...)` | 算 F、保留金額，回傳要換多少幣 |
| `follow_work(row_data)` | 追隨 F 的每日判定 |
| `log_fees(row_data)` | 每日記錄已收與未收手續費、LP 淨值 |
| `collect_fee_as_quote(lp_market, position_info)` | 收手續費並把 ETH 部分賣成 USDC |
| `band_amounts(base, quote, share)` | 該段要放的兩種幣數量，clamp 到可用餘額 |
| `check_rebalance` | 現價是否在 16 段之外 |
| `rescale_work(row_data)` | 撤倉、換幣、放置、記錄 `ExportData` 的完整流程 |
| `first_lp(row_data)` | 建倉，流程與 `rescale_work` 相同但沒有撤倉 |
| `calculate_final_result(row_data)` | 期末收手續費、寫 `fees_*.csv`、印 `final result` 摘要 |

### 執行層（第 998 行起）

| 名稱 | 用途 |
|---|---|
| `run_test(...)` | 建 market、載資料、跑 actuator、算指標，回傳結果 dict |
| `_run_one(...)` | Pool worker，頂層函式才能 pickle |
| `process_for_date(csd, dsd, ded, id, flip)` | 一個回測期間的全部 run：建參數、載暖身資料算 `daily_ema`、展開組合、starmap、寫總表 |
| `_with_share(p, lower_ratio, eth_share, deploy)` | 把每組基礎參數展開成 lower × eth_share × deploy 的組合並補報表名 |
| `_self_check()` | 啟動時的自我檢查 |
| `__main__` | 遍歷 `date_ranges` 呼叫 `process_for_date` |

---

## 5. 輸出檔案

每個回測期間一個資料夾，內含：

### `apr_remix_<投入>_results.csv`

一列一個 run。常用欄位：

| 欄位 | 意思 |
|---|---|
| `Rate of Return` | 期末總值 ÷ 投入 − 1 |
| `Total Net Value` | 期末總值 = LP 淨值 + 帳上 USDC + 帳上 ETH 市值 |
| `LP Net Value` | 期末 LP 淨值，即本金部分（F = 1 時） |
| `Total Fee` | 全年收到的手續費，USDC 計 |
| `Total Swap Fee` | 換幣付的池子手續費 |
| `Max Draw Down` | 總值最大回撤 |
| `Benchmark return rate` | 同期 ETH 持有報酬（池價） |
| `Rescale Count` / `Upper` / `Lower` | 出區間觸發的重建次數，不含追隨 F |

### `result_<報表名>.csv`

一列一個事件（建倉、每次重建、期末）。常用欄位：`time`、`price`、`total_net_value`、`lp_net_value`、`quote_balance`、`base_balance`、`base_added`、`quote_added`、`tick`、`tick_lower`、`tick_upper`、`new_tick_lower`、`new_tick_upper`、`total_base_fee`、`total_quote_fee`。

- 部署後比例 = `lp_net_value ÷ total_net_value`。
- ETH 側佔比 = `base_added × price ÷ (base_added × price + quote_added)`。
- F = 0 的事件 `base_added` 與 `quote_added` 都是 0，`new_tick_*` 為 0。
- 池子 token0 是 USDC，tick 越高 ETH 價越低，所以 `new_tick_upper` 是價格下緣。

### `fees_<報表名>.csv`

每日一列：`date`、`price`、`collected_quote`（已收）、`pending_quote`（部位內未收）、`lp_value`。月度手續費 = 月底 `collected + pending` 的增量。

### stdout

每次重建印一行 `rescale placed base share ... F ... reserve quote ...`，`sema100` 模式另印 `ema100 on <日期>: close ... -> s=...`，追隨 F 印 `follow F: target ... current ... -> rebuild`。期末印 `final result: ... follow rebuilds: N, share picks: {...}, last F: ...`。

多進程時 stdout 可能有部分 worker 的輸出被截掉，以 csv 為準。

---

## 6. 目前結果（2026-09-29）

| 年 | ETH 持有 | 規格書本邏輯 | 本程式 1d | 本金 | 手續費 |
|---|---|---|---|---|---|
| 2024 | +46% | +39.0%（$103.4k + $35.5k） | **+36.5%** | $105.5k | $30.9k |
| 2025 | −11% | +22.3%（$94.7k + $27.6k） | **+16.6%** | $95.1k | $20.8k |

本金兩年都與規格書一致，差距全在手續費收入：實際池子手續費比規格書的獎勵模型低 13% 到 25%。詳見 [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md)。

其他已測的變體：
- `MIRROR_TICKS`（下緣 −16.8%）：2024 差 6.4 pt，2025 持平，維持 `MIRROR_PRICE`。
- 8h／12h 判定：2024 明顯較差（8h +29.5%），2025 差距 1 pt 內。
- 固定 s = 0.5 / 0.7 / `sgeo`、`DEPLOY_FULL`：2025 全年在 −6% 到 −15% 之間，證明獲利來自 F 而非 s。

---

## 7. 刻意簡化與已知限制

| 項目 | 現況 | 若要改 |
|---|---|---|
| 引擎起算日 | 視窗前 360 天，非 2017 | 加長 `EMA_WARMUP_DAYS`，資料從 2021-05 起有 |
| 空倉時 EMA 退出重設 low | 照規格書字面執行 | `VirtualAccount.step` 規則 1 加 `deployed > 0` 條件 |
| 上破重建 | 直接重建為 F × 權益 | 規格書是先保留舊規模再追隨，差異只在 \|F − cur\| < 12.5% 時 |
| 滿倉／空倉判定 | 容忍 2% 塵埃 | `FULL_TOLERANCE` |
| 價格來源 | Uniswap 池價 | 規格書用 Binance，門檻邊緣的判定可能差一天 |
| 滑價 | 未模擬，只有池子 0.05% | `GlobalParams.swap_fee=True` 走原本的成本模型 |
| 乾涸 band | 丟棄，該段的 1.27% 留在場外 | 現價 tick 落在段邊界時發生，一年一兩次 |
| 手續費模型 | 實際池子成交量按流動性占比分配 | 與規格書獎勵模型差 13% 到 25%，非程式可改 |

---

## 8. 常見改法

| 想做什麼 | 改哪裡 |
|---|---|
| 換年份 | `date_ranges`（第 1599 行）換或加一行 `(datetime(Y,1,1), date(Y,1,1), date(Y,12,31), "", [])` |
| 對照兩種下緣 | `_lower_ratios = [MIRROR_PRICE, MIRROR_TICKS]` |
| 對照固定 s | `_eth_shares = [Decimal("0.5"), EMA_SHARE]` |
| 對照永遠滿倉 | `_deploy_modes = [DEPLOY_FULL, DEPLOY_SIGNAL]` |
| 加判定頻率 | `_rescale_frequencies` 加 `RescaleFrequency.hour8` 等 |
| 改 EMA 週期 | `EMA_SPANS`，`EMA_WARMUP_DAYS` 會自動跟著最大值 |
| 改回補門檻 | `REFILL_STAGES`、`REFILL_CONFIRM_DAYS` |
| 改追隨門檻 | `FOLLOW_THRESHOLD` |
| 改結果資料夾前綴 | `_folder_prefix`（第 1250 行）的 `gamma-pdfv6-` |

改引擎常數後先跑 `_self_check`，它會直接失敗。

---

## 9. 自我檢查涵蓋的項目

`_self_check()` 用合成資料驗證：
- `build_gap_bands` 各種 gap 的 tick 偏移。
- `build_shape_config` 中心段被丟掉、每側權重合計 1。
- `swap_to_value_share` 四種起始狀態換完比例精確等於目標，且不會出現負餘額。
- `share_label` 標籤。
- `daily_ema_frame` 平盤 EMA 收斂；`ema_share_for` 判定日是前一日。
- 引擎：平盤 F = 0；+20% 三日確認後只到第 1 段（每日一段）；下跌後 EMA 退出 F = 0；單帳戶回落不退段、再回升才進下一段。
