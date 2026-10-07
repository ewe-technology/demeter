# gamma_maker_defense_ethusdc_v2.py 說明

谷型 LP 防禦邏輯規格書 **v2**（ETH-USDC MGL，標準／複利模式）的回測實作，跑在 Demeter 回測框架上。
從 [GAMMA_MAKER_DEFENSE_ETHUSDC_V1.md](GAMMA_MAKER_DEFENSE_ETHUSDC_V1.md) 對應的 v1 程式複製，逐步對齊 v2 規格；v1 保持不動當比較基準。

**對齊進度（v2 相對 v1）**

| 項目 | 狀態 |
|---|---|
| 回補階梯 +7.5/12.5/17.5/22.5% | 已改（`REFILL_STAGES`） |
| 各段等價格寬（每段 = 中心價 × 2.5%） | 已改（`build_price_bands`）。形狀名稱加 `_price` 後綴切換：`inverted_gaussian_spec_price` = 等價格寬，`inverted_gaussian_spec` = 等 tick 寬；條件不合（有 gap、下緣用 `MIRROR_TICKS`）時報錯，不會悄悄退回等 tick |
| swap 成本與滑價 | 已改，自 v1 移植。`SWAP_COST_RATE` 是規格書的 0.1%（池子 0.05% 已算在內，只補差額；手續費換 USDC 不加收）。**2026-10-06 起預設改為池子 0.05% + 模擬滑價**：`SWAP_COST_RATE = None`、`SLIPPAGE_MODEL = "depth"`（`quote_depth`，滑價 = swap 的 USDC 金額² ÷ 當下 tick 的 USDC 虛擬儲備）。要規格書的 0.1% 平價就改回 `Decimal("0.001")` 與 `None`，兩者同時開會重複計算 |
| 規格書原始權重 1.2／4.6／…／19.4% | 已改，自 v1 移植：`inverted_gaussian_spec`（標籤 `ig17s-tick`／`ig17s-price`） |
| F 用虛擬 LP 價值比例 | 已改（`F_BY_VALUE = True`）。虛擬帳戶追蹤虛擬資產（USDC + 虛擬谷型 LP 的價值），F = 四者「LP 價值 ÷ 資產」的平均，會隨價格漂。`False` 回到階段值（資料夾名加 `-fstage`）。規格書第 8 節仍列為待決 |
| Binance 價格、EMA 自 2017-08-17 起算 | 已加 `_signal_sources`（目前設 `[BINANCE_SIGNAL]`，要對照池價就加回 `POOL_SIGNAL`），來源是 run 參數，同一個 Pool 一起跑，兩列結果寫進同一個 `apr_*_results.csv`，報表名結尾 `_pool`／`_binance`。`pool`：池價日收盤、EMA 暖身 360 天；`binance`：讀 `binance_ethusdt_1d.csv`，EMA 從 2017-08-17 連續算，讀取時檢查範圍涵蓋、日期缺口、暖身天數。池價仍用於 LP 評價 |
| `signal_daily.csv` 匯出 | 已改，寫到 `result/signal_daily_<起日>_<迄日>.csv`（池價）與 `result/signal_daily_bn_<起日>_<迄日>.csv`（Binance），含暖身期 |
| 複利模式（規格書第 5 節） | 已改（`process_for_date` 的 `_compound`，`True` = 複利、`False` = 標準）。每月 1 日 00:00 把已收手續費加進現有 band，見 3.7 |
| 分鐘級淨值匯出 | 已加，`netvalue_<報表名>.csv`（`time`、`net_value`、`price`），供回撤檢查，見第 5 節 |
| claim 規則／25% 成功報酬／執行手續費 | 未改 |

以下章節除回補階梯與資料夾前綴外，內容沿用 v1。
從 `remix_dao_gamma_ig_gap_bands.py` 複製後加入三層規格書邏輯：ETH 占比 s 切換、四帳戶訊號引擎算部署比例 F、每日追隨 F 重建。

相關文件：
- [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md)：2024／2025 對規格書的對照報告，給規格書作者

---

## 1. 快速開始

```bash
cd /Users/makersu/work/githubEwe/demeter/samples/strategy-example && ../../.venv/bin/python gamma_maker_defense_ethusdc_v2.py
```

用 repo 的 `.venv`（anaconda 的 base 環境 numpy 2 與 pandas 不相容，會 import 失敗）。

- 必須在 `samples/strategy-example` 目錄下執行，結果才會寫到該目錄的 `result/`。
- 分鐘資料從 `../real-data/<pool address>/` 讀取，第一次載入後會快取到 `~/.demeter/`。
- 啟動時會先跑 `_self_check()`，任何 assert 失敗代表引擎邏輯被改壞。
- 預設一個 run 約 4 分鐘。多個 run 用 `multiprocessing.Pool` 並行，`_workers = 5`。

輸出資料夾：`result/gamma-maker-defense-ethusdc-v2-<shape>-gap-up<上緣>-dn<下緣>-<eth_share>-<deploy>-usdceth-usdc[-swap<bp>bp][-slip<模式>][-compound][-fstage][-v1start]-<投入>-<起日>-<迄日>/`。方括號的後綴只在對應設定開啟時出現，所以標準／複利、0.1% 平價／滑價的結果各在自己的資料夾，互不覆蓋。

---

## 2. 目前預設設定

| 項目 | 值 | 位置 |
|---|---|---|
| 池子 | Ethereum 主網 WETH/USDC 0.05%，`0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`，tick spacing 10 | `process_for_date` 第 1193 行 |
| 投入 | 100,000 USDC，quote 為 USDC | 第 1165 行 |
| 期間 | 2022、2023、2024、2025 各一年，**1/2 00:00 建倉**到 12/31（規格書的「1/1 投入」以 1/1 日線收盤成交，約 1/2 00:00 UTC，見 [V1 說明 6.6](GAMMA_MAKER_DEFENSE_ETHUSDC_V1.md)） | `date_ranges` |
| `_shapes` | `["inverted_gaussian_spec_price"]`，8+8 段，規格書原始權重、等價格寬 | `process_for_date` 內 |
| `_upper_ratios` | `[0.20]`，上緣 +20% | 第 1226 行 |
| `_lower_ratios` | `[MIRROR_PRICE]`，下緣真 −20% | 第 1232 行 |
| `_centre_half_gaps` | `[0]`，中心無 gap | 第 1239 行 |
| `_eth_shares` | `[EMA_SHARE]`，依 EMA100 切換 70%/50% | 第 1245 行 |
| `_deploy_modes` | `[DEPLOY_SIGNAL]`：四個虛擬帳戶決定 F。改 `[DEPLOY_FULL]` 則不用虛擬帳戶，F 永遠 1，階梯永遠滿倉（只在價格離開區間時重建），s 仍依 EMA100；兩個都放就各跑一次 | `process_for_date` 內 |
| `_signal_sources` | `[BINANCE_SIGNAL]`，Binance 日收盤，EMA 自 2017-08-17 起算。要對照池價就加 `POOL_SIGNAL` | `process_for_date` 內 |
| `_compound` | `True`：複利模式，每月 1 日把已收手續費加進現有 band（3.7）。`False` 為標準模式，手續費留在場外 | `process_for_date` 內 |
| `_rescale_frequencies` | `[daily]`，每日 00:00 判定 | 第 1283 行 |
| swap 成本 | `SWAP_COST_RATE = None`：只有池子 0.05%。設 `Decimal("0.001")` 為規格書的 0.1%（池子 0.05% 之外補差額），資料夾名帶 `-swap10bp` | 模組層常數 |
| 滑價 | `SLIPPAGE_MODEL = "depth"`：重建的 swap 另收「swap 金額² ÷ 當下 tick 的 USDC 虛擬儲備」，約每筆 $70k 的 swap 0.6 到 8 bp；資料夾名帶 `-slipdepth`。設 `None` 關閉。不要與 0.1% 同時開 | 模組層常數、`execute_swap` |
| 手續費 | 收取時賣成 USDC。標準模式留在場外；複利模式每月 1 日併入本金（3.7） | `collect_fee_as_quote`、`compound_work` |

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

出區間的判定頻率由 `_rescale_frequencies` 決定，追隨 F 固定每日一次。目前部署比例 = LP 淨值 ÷ 總權益，總權益不含已收的手續費。「滿倉」判定是 F ≥ 99.9%（`FOLLOW_FULL_F`）且目前比例低於 99%（`FOLLOW_FULL_GAP` = 1%），「空倉」判定是 F = 0 且仍有任何部位（`FOLLOW_EMPTY_TOL` = 0），都是規格書第 4 節的值；之前的跑法用 2% 容忍。

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

規格書 2.2。四個虛擬帳戶，EMA 週期 90、100、110、120，各自跑同一套規則，F = 四者「虛擬 LP 價值 ÷ 虛擬資產」的平均（`F_BY_VALUE = True`），建倉或回補當天剛好等於階段比例，之後隨價格漂，所以 F 不是 1/16 的倍數。`F_BY_VALUE = False` 時用階段值（段數 ÷ 4），是 1/16 的倍數。

每個帳戶每天依序執行（`VirtualAccount.step`）：

1. **EMA 退出**：已武裝且收盤 < EMA → 虛擬 LP 以收盤價換成 USDC、centre 清空、low = 收盤、段數歸零、改為未武裝。空倉帳戶也照做（規格書字面）。
2. **再武裝**：未武裝且收盤 > EMA → 改為已武裝，不買入。
3. **下緣停損**：有部位且收盤 < centre × 0.80 → 同退出，武裝狀態不變。
4. **上破重建**：有部位且收盤 > centre × 1.20 → 以收盤為新 centre 重建虛擬 LP，LP 價值不變（USDC 也不變）；ETH 占比：收盤 < EMA100 × 0.95 為 25%，收盤 > 該帳戶 EMA 為 70%，其餘 50%。
5. **四段回補**（部署 < 100% 時）：low 每日取更低值；第 1 段需收盤 ≥ low × 1.075 連續 3 日，第 2、3、4 段分別為 ≥ low × 1.125、1.175、1.225；**每日最多前進一段**，回落不退段；每段以當日收盤為新 centre 重建虛擬 LP，規模 = 段數 ÷ 4 × 虛擬資產，ETH 占比同規則 4（規格書只寫了重建時的占比，回補與起始建倉沿用同一規則，是我的假設）。

起算規則同規格書第 3 節：第一天收盤只用來當 EMA 的初始值，帳戶不動作；第二天起算，收盤 ≥ EMA 就已武裝、滿倉，否則未武裝、L = 收盤。`binance` 訊號從 2017-08-17 起（初始值 302.00，2017-08-18 起算）連續跑到視窗，與規格書一致；`pool` 訊號從視窗前 360 天（`EMA_WARMUP_DAYS`）的第一天當初始值，是刻意簡化。

開關 `SPEC_START`（預設 `True`，規格書起算）：設 `False` 回到 v1 的起算（第一天就起算，收盤 > EMA 才武裝；種子日收盤等於 EMA，所以起始是未武裝、空倉），結果資料夾名加 `-v1start`。用 Binance 訊號（2017 起連續）時，兩種起算在 2022 到 2025 的 F 完全相同；只可能影響池價訊號，因為它的起算點是視窗前 360 天。

`daily_ema_frame` 把暖身加視窗內的分鐘價格取每日最後一筆當 UTC 日收盤，算出 `close`、`ema`（EMA100，s 用）、`F` 三欄。`daily_row_for` 取「時間戳減一天」那列，所以 00:00 的判定用的是剛結束那天的收盤。

### 3.6 每日的執行順序

demeter 依 trigger 註冊順序觸發，同一分鐘的順序是：

1. `rescale_work`（出區間判定，頻率依 `_rescale_frequencies`）
2. `follow_work`（追隨 F，每日）
3. `compound_work`（複利模式才有，只在每月 1 日動作）
4. `log_fees`（每日手續費快照）

1 和 2 都可能重建，但一天最多只會真的重建一次：前者重建後 cur ≈ F，後者不會再觸發；後者重建後在區間內，前者不會觸發。3 不重建，只對現有 band 加流動性。

### 3.7 複利模式（`compound_work`，規格書第 5 節）

兩種模式的訊號、F、梯子、重建規則完全相同，只差手續費怎麼處理。

| | 標準模式（`_compound = False`） | 複利模式（`_compound = True`） |
|---|---|---|
| 手續費 | 收取時賣成 USDC，留在場外，不進 LP | 同左，但每月 1 日併入本金 |
| 本金 | 不增加 | 每月增加上個月的已收手續費 |

實作上有兩個計數：`total_quote_fee` 是累計已收手續費（只用於報表），`reinvested_fee` 是其中已併入本金的部分；`held_quote_fee = total_quote_fee − reinvested_fee` 才是「還在場外、不可動用」的手續費。重建、追隨 F、`band_amounts`、`lp_fraction` 的可用餘額都扣 `held_quote_fee`，所以標準模式它等於累計值，複利模式每月歸零。

每月 1 日 00:00，在當天的重建與追隨 F 判定之後：

1. 把所有 band 內未收的手續費收進來（`collect_fee_as_quote`）。規格書是每天超過 $5 就 claim，本程式其餘日子只在重建時才收，所以月初先補收，不然複利金額會偏小。
2. 沒有新手續費就結束。
3. 先以「目前 LP 比例」`ratio = lp_fraction` 算出 LP 要分到多少：`新錢 × ratio`；其餘留 USDC（規格書：「依當時的 LP 比例分配到 LP 與 USDC」，F = 0 時全部留 USDC）。比例要在併入之前算，否則新錢會把比例稀釋。
4. `reinvested_fee = total_quote_fee`，新錢成為本金。
5. LP 的部分直接加進現有的每個 band：每個 band 的流動性放大同一個係數 `k = 新錢 × ratio ÷ LP 淨值`，梯子的形狀與中心不變。需要的 ETH 用 USDC 換（走一般的重建成本：池費 + 滑價）。

**不要用「月初重建」實作再投入**：第一版這樣做，2023 年多 +$19.3k、2024 年少 −$17.1k，遠超過複利該有的幅度（規格書複利比標準多 +$0.2k 到 +$2.0k），因為重建會把梯子重新置中、重設 ETH 佔比，變成另一種策略。

每個複利事件印一行 `compound: reinvest <金額> at LP ratio <比例>`，`final result` 那行的 `compounds` 是次數。複利事件不寫進 `result_*.csv`。

單年回測（各年 $100k 起算）複利的效果很小，連續多年才會明顯（規格書 2022 到 2025 連續：標準 $185.9k、複利 $224.5k）。

---

## 4. 主要函式與類別

### 模組層（第 65 到 375 行）

| 名稱 | 用途 |
|---|---|
| `MIRROR_PRICE` / `MIRROR_TICKS` | 下緣算法：真實價格比例，或和上緣相同 tick 數 |
| `EMA_SHARE`、`DEPLOY_FULL`、`DEPLOY_SIGNAL` | 參數的字串常數 |
| `EMA_SPANS`、`LOWER_STOP`、`UPPER_REBUILD`、`REFILL_STAGES`、`REFILL_CONFIRM_DAYS`、`FOLLOW_THRESHOLD`、`FOLLOW_FULL_F`、`FOLLOW_FULL_GAP`、`FOLLOW_EMPTY_TOL` | 引擎常數，對應規格書第 3 節參數表 |
| `VirtualAccount` | 一個虛擬帳戶的狀態機（虛擬 USDC 與虛擬谷型 LP），`step(close, ema, ema100)` 走一天 |
| `build_virtual_lp` / `virtual_lp_value` | 虛擬谷型 LP：16 段（每段 2.5%、規格書權重），依 ETH 占比分配後，以 V3 集中流動性公式估值；不含手續費與 swap 成本 |
| `share_label` / `ratio_label` / `gap_label` | 報表與資料夾名稱的標籤 |
| `daily_ema_frame(minute_price)` | 日收盤、EMA100、F 三欄的 DataFrame |
| `daily_row_for` / `ema_share_for` / `target_fraction_for` | 依時間戳取前一日的判定值 |
| `swap_to_value_share(base, quote, price, base_share)` | 純函式，算出要買賣多少 base 才能讓 base 佔總值 `base_share` |
| `quote_depth(liquidity, tick, token0_is_quote, quote_decimal)` | 當下 tick 的 quote 虛擬儲備（quote 單位），滑價 = swap 的 quote 金額² ÷ 儲備，自 v1 移植 |
| `build_gap_bands` | 16 段的 tick 偏移 |
| `build_shape_config` | 每段的 `[下偏移, 上偏移, 該側佔比]`，中心權重 0 的段會被丟掉 |

### 策略類別 `RemixDaoDcaWeekStratStrategy`（第 379 行起）

| 方法 | 用途 |
|---|---|
| `__init__` | 收 `shape`、`upper_ratio`、`lower_ratio`、`half_gap`、`eth_share`、`daily_ema`、`deploy` |
| `initialize` | 註冊 `first_lp`、`rescale_work`、`follow_work`（`DEPLOY_SIGNAL`）、`compound_work`（複利）、`log_fees`、`calculate_final_result`，共六個 trigger（`follow_work`、`compound_work` 視設定才有） |
| `held_quote_fee`（property） | 還在場外、不可動用的已收手續費 = `total_quote_fee − reinvested_fee` |
| `compound_work(row_data)` | 複利：每月 1 日補收手續費，依目前 LP 比例把新錢加進現有 band（3.7） |
| `execute_swap(..., rebalance)` | 重建的 swap：另收 `SWAP_COST_RATE` 的差額與 `depth` 滑價，記入 `total_slippage_cost` |
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

每日一列：`date`、`price`、`collected_quote`（已收）、`pending_quote`（部位內未收）、`lp_value`。月度手續費 = 月底 `collected + pending` 的增量。`collected_quote` 是累計值，複利模式併入本金後也不歸零。

### `netvalue_<報表名>.csv`

每分鐘一列：`time`、`net_value`（帳戶總淨值，USDC）、`price`（ETH 池價）。約 52 萬列、49 MB 一年，`result/` 已被 git 忽略。`apr_*_results.csv` 的 `Max Draw Down` 就是用這個分鐘級序列算的，所以比規格書的日級口徑嚴格（見 6.0）。

要看日級回撤：取每日 00:00 的列再算。沒有這個檔時可以用 `result_*.csv` 的事件列餘額加 `fees_*.csv` 每日 `lp_value` 重建（事件日與回測內部數字完全一致），但第一個建倉事件之前的天數要用 $100k。

### stdout

每次重建印一行 `rescale placed base share ... F ... reserve quote ...`，`sema100` 模式另印 `ema100 on <日期>: close ... -> s=...`，追隨 F 印 `follow F: target ... current ... -> rebuild`。期末印 `final result: ... follow rebuilds: N, share picks: {...}, last F: ...`。

多進程時 stdout 可能有部分 worker 的輸出被截掉，以 csv 為準。

---

## 6. 目前結果

### 6.0 最新（2026-10-06）：池費 0.05% + 滑價、Binance 訊號、`DEPLOY_SIGNAL`，標準與複利

設定見第 2 節，各年 $100k 起算、不連續。總值 = LP 淨值 + 場外 USDC／ETH + 已收手續費。「本金」= 總值 − 手續費（手續費含 LP 內未領的部分）。最大回撤是分鐘級（見第 5 節 `netvalue_*.csv`）。

**標準模式**（資料夾 `…-slipdepth-…`）

| 年 | 報酬 | 期末總值 | 本金 | 手續費 | swap 總成本 | 最大回撤 |
|---|---|---|---|---|---|---|
| 2022 | +20.7% | $120,696 | $99,317 | $21,379 | $338 | 19.7% |
| 2023 | +21.9% | $121,923 | $106,157 | $15,767 | $487 | 14.6% |
| 2024 | +19.5% | $119,544 | $93,992 | $25,552 | $565 | 30.5% |
| 2025 | +22.6% | $122,580 | $102,515 | $20,066 | $922 | 25.3% |

**對照規格書 v2（年底總資產，扣成功報酬前，單位 $k）**

| 年 | 規格書標準 | 本程式標準 | 差 | 規格書複利 | 本程式複利 | 差 |
|---|---|---|---|---|---|---|
| 2022 | 115.1 | 120.7 | +5.6 | 115.3 | 120.8 | +5.5 |
| 2023 | 123.1 | 121.9 | −1.2 | 124.3 | 122.5 | −1.8 |
| 2024 | 125.2 | 119.5 | −5.7 | 127.2 | 119.4 | −7.8 |
| 2025 | 128.7 | 122.6 | −6.1 | 129.1 | 122.2 | −6.9 |

標準模式絕對差加總 $18.6k（0.1% 平價時是 $19.0k）。差距主要是手續費模型，不是 swap 成本。

**複利 − 標準**（本程式 vs 規格書）：2022 +0.1 vs +0.2、2023 +0.5 vs +1.2、2024 −0.2 vs +2.0、2025 −0.3 vs +0.4（$k）。單年都很小，方向在 2022、2023 與規格書一致，2024、2025 本程式略負，原因未查（可能是再投入的 swap 成本或月初加碼的時點）。複利的分鐘級最大回撤：2022 16.7%、2023 15.7%、2024 33.7%、2025 28.2%，2023 起比標準深，因為本金變大，同樣的波動損失金額更大。

**規格書給了拆分的兩年**（原資 + 已領取獎勵 = 合計，最大回撤）：

| 年 | | 規格書 | 本程式（標準） | 差 |
|---|---|---|---|---|
| 2022 | 原資 | $99,081 | $99,317 | +$236（+0.24%） |
| | 獎勵 | $16,062 | $21,379 | +$5,317（+33%） |
| | 合計 | $115,142 | $120,696 | +$5,554 |
| | 最大回撤 | −14.3% | −19.7%（分鐘）／約 −13% （日級） | |
| 2023 | 原資 | $105,494 | $106,157 | +$663（+0.63%） |
| | 獎勵 | $17,629 | $15,767 | −$1,862（−10.6%） |
| | 合計 | $123,123 | $121,923 | −$1,200 |
| | 最大回撤 | −11.6% | −14.6%（分鐘）／約 −13% （日級） | |

- 原資幾乎對上：規格書第 7 節階段 2 的合格標準是原資差 < 0.5%，2022 在內，2023 差 0.63%。0.1% 平價時 2023 是 +0.32%，因為滑價模型比 0.1% 便宜，我們的原資略多。要最貼近規格書就改回 0.1% 平價。
- 合計的差全在獎勵：2022 實際池子手續費比規格書的獎勵模型高 33%，2023 低 10.6%。規格書自己寫了獎勵模型要重新校準，程式不能改。

**最大回撤的口徑**：`Max Draw Down` 是分鐘級淨值算的，規格書是 UTC 0 時日收盤。2022 年分鐘級 −19.70% 的高點在 2022-02-10 11:38（ETH 3,280，淨值 $106,975），低點在 2022-02-24 07:37（ETH 2,303，淨值 $85,902），那天是當年單日盤中最大跌幅（−9.9%）；日級（每日 00:00）重算是 13.15%（高點 2022-08-14、低點 2022-11-22），比規格書 −14.3% 淺 1.1 pt。2023 日級約 13.3%，比規格書 −11.6% 深 1.7 pt，推測與手續費偏低有關，未驗證。這兩個日級數字是用 0.1% 平價設定的跑法算的（2023 是用事件列重建），沒有用目前的池費 + 滑價設定重算；兩種設定的分鐘級回撤只差 0.2 pt 內，預期影響很小。2/24 的盤中低點未用 Binance 分鐘線核對。

**swap 成本設定的影響**（總值，0.1% 平價 → 池費 0.05% + 滑價）：2022 120,391 → 120,696、2023 121,575 → 121,923、2024 119,208 → 119,544、2025 122,494 → 122,580。swap 總成本 645／801／885／979 → 338／487／565／922。最大回撤與手續費幾乎不變。

### 6.1 舊（2026-10-01）：swap 成本 0.1% 平價、池價與 Binance 兩種訊號、標準模式

對照 ETH-USDC MGL 規格書 v2 標準模式。設定：`ig17s-price`（規格書原始權重、等價格寬）、swap 成本 0.1%、回補階梯 +7.5/12.5/17.5/22.5%、F 用虛擬 LP 價值比例（`F_BY_VALUE = True`）。訊號分別用池價（`pool`）與 Binance 日收盤（`binance`），兩列在同一個 `apr_*_results.csv`。

規格書 v2 第 6 節「各年度結果」：各年以 $100k 加入（v2 起日 1/2 00:00，用 1/1 日線收盤成交，見上），年底總資產，扣除成功報酬與執行手續費前。本程式的總值 = LP 淨值 + 場外 USDC／ETH + 已收手續費（賣成 USDC 不再投入），與標準模式「原資＋已領取獎勵」同一口徑。

| 年 | ETH 持有（池價） | 規格書 v2 | 池價訊號 | 差 | Binance 訊號 | 差 |
|---|---|---|---|---|---|---|
| 2022 | −67.6% | +15.1% | +20.5% | +5.4 pt | +20.4% | +5.3 pt |
| 2023 | +90.8% | +23.1% | +27.1% | +4.0 pt | +21.5% | **−1.6 pt** |
| 2024 | +46.1% | +25.2% | +19.4% | −5.8 pt | +19.3% | **−5.9 pt** |
| 2025 | −10.9% | +28.7% | +22.6% | −6.1 pt | +22.6% | −6.1 pt |

| 年 | 訊號 | 期末總值 | LP 淨值 | 手續費 | swap 費 | 最大回撤 | 出區間重建 |
|---|---|---|---|---|---|---|---|
| 2022 | 池價 | $120.5k | $74.1k | $20.7k | $0.6k | 19.7% | 1 |
| 2022 | Binance | $120.4k | $72.8k | $21.4k | $0.6k | 19.7% | 1 |
| 2023 | 池價 | $127.1k | $111.1k | $16.0k | $0.8k | 13.5% | 2 |
| 2023 | Binance | $121.5k | $105.7k | $15.8k | $0.8k | 14.8% | 3 |
| 2024 | 池價 | $119.3k | $93.8k | $25.6k | $0.9k | 30.6% | 2 |
| 2024 | Binance | $119.2k | $93.7k | $25.6k | $0.9k | 30.7% | 2 |
| 2025 | 池價 | $122.5k | $75.2k | $20.1k | $1.0k | 25.4% | 6 |
| 2025 | Binance | $122.5k | $75.2k | $20.1k | $1.0k | 25.4% | 6 |

規格書各年年底總值：2022 $115.1k、2023 $123.1k、2024 $125.2k、2025 $128.7k，沒有拆成原資與獎勵，無法逐項對照。LP 淨值不是本金：F < 1 的年底有一部分資產在場外。

**（以下兩段是起日 1/1 時的比較）三項對齊（swap 成本 0.1%、規格書原始權重、F 用價值比例）的影響很小**：移植前（swap 0.05%、`inverted_gaussian` 權重、階段值 F）Binance 版為 +21.8／+22.0／+12.8／+23.7%，移植後 +20.4／+21.6／+12.5／+23.2%，每年變動不到 1.5 pt，2024 的差距沒有縮小。

**追隨 F 的滿倉／空倉容忍改成規格書值**（F ≥ 99.9% 且目前比例 < 99%、空倉容忍 0；原本 2%）後重跑，八列結果與 2% 版完全相同（小數點後四位），每個 run 的建倉與重建事件 21～33 筆，沒有每日重建的循環。所有追隨重建都是由 12.5% 門檻觸發，容忍度沒有實際影響。

**池價 vs Binance 訊號（視窗內逐日）**

| 年 | F 差超過 0.05 的天數 | 首次不同 | s 判定（收盤 > EMA100）不同天數 |
|---|---|---|---|
| 2022 | 31 | 2022-03-25 | 0 |
| 2023 | 15 | 2023-03-18、08-03 起 | 1（03-11） |
| 2024 | 1 | 2024-05-25 | 2 |
| 2025 | 0 | — | 0 |

F 用價值比例後，兩種訊號的 F 因為價格略有不同幾乎每天都有小差（< 0.05），上表只算差距明顯的天數。

- 2022-03-25 與規格書第 0 節第 7 點「2022 年 3 月 25 日判定相反」是同一天。
- 2023 改用 Binance 後差距由 +4.1 pt 縮到 −1.5 pt，與規格書第 0 節第 6 點（2023 年 3 月 USDC 脫鉤，池價偏離導致回補提前）相符。
- 2025 兩種訊號的 F 幾乎一致，結果相同。

**起日改 1/2（規格書的「1/1 投入」以 1/1 日線收盤成交）後，2024 從 +12.5% 變成 +19.4%（+6.9 pt），出區間重建從 4 次降成 2 次**，與 V1 說明 6.6 的結論一致（v1 改 1/2 後 2024 本金與規格書相同）。2022 完全不變（起始 F = 0，起始日不影響），2023 變動 0.1 pt，2025 變動 −0.6 pt。

**2024 剩下的 −5.9 pt（Binance）**：起日改 1/2 後差距由 −12.7 pt 縮到 −5.9 pt，與價格來源無關（兩種訊號相同）。剩下的差距大小與手續費模型的差距相當：規格書的獎勵模型以全年滿倉校準 2024 為 $46.7k，本程式平均 F 約 0.6，按比例縮放約 $29k，實收 $25.6k，差約 $3.5k（約 3.5 pt）；其餘約 2 pt 說不清楚。

可能原因：
1. 手續費模型：規格書第 6 節自己寫實際手續費比模型少 13～25%（不是程式能改的）。
2. 某幾次出場或回補與規格書差一天。
3. 規則 4 以外的 ETH 占比假設（回補與起始建倉沿用規則 4 的占比，規格書沒寫）。

需要規格書作者的 `signal_daily.csv` 與 2024 事件 CSV（規格書第 7 節階段 1、2）才能逐日比對。

**其他差距**
- 2025 −6.1 pt：訊號已一致，推測主要是手續費模型（改 1/2 後比 1/1 起日的 −5.5 pt 略差）。
- 2022 +5.3 pt：本程式偏高，原因未拆開。

**與規格書不同的前提**：（當時）未實作 claim、25% 成功報酬、gas、複利模式（複利之後已加，見 3.7）；池子為 Ethereum 主網 WETH/USDC 0.05%（規格書為 Base）；`pool` 模式 EMA 只暖身 360 天（2022 年僅約 240 天），`binance` 模式從 2017-08-17 連續算；重建以 00:00 池價執行，不是 Binance 收盤價。

**舊版參考（v1，對照舊規格書 v6）**

| 年 | ETH 持有 | 規格書 v6 | 本程式 v1 1d | 本金 | 手續費 |
|---|---|---|---|---|---|
| 2024 | +46% | +39.0%（$103.4k + $35.5k） | +36.5% | $105.5k | $30.9k |
| 2025 | −11% | +22.3%（$94.7k + $27.6k） | +16.6% | $95.1k | $20.8k |

詳見 [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md)。規格書從 v6 改到 v2，2024 由 +39.0% 降到 +25.2%（−13.8 pt）、2025 由 +22.3% 升到 +28.7%（+6.4 pt）；本程式 v1 到 v2 為 2024 −23.6 pt、2025 +7.1 pt，方向一致、2024 降幅較大。

其他已測的變體（v1）：`MIRROR_TICKS`（下緣 −16.8%）2024 差 6.4 pt、2025 持平，維持 `MIRROR_PRICE`；8h／12h 判定 2024 明顯較差；固定 s、`DEPLOY_FULL` 2025 全年在 −6% 到 −15%，證明獲利來自 F 而非 s。

---

## 7. 刻意簡化與已知限制

| 項目 | 現況 | 若要改 |
|---|---|---|
| 引擎起算日 | `pool`：視窗前 360 天起算；`binance`：2017-08-17 初始值、08-18 起算，與規格書一致 | `pool` 加長 `EMA_WARMUP_DAYS`（池子資料從 2021-05 起有） |
| 空倉時 EMA 退出重設 low | 照規格書字面執行 | `VirtualAccount.step` 規則 1 加 `deployed > 0` 條件 |
| 突破重建（`DEPLOY_SIGNAL`） | 照規格書第 4 節規則 1、2：上破以收盤為中心重建、**維持目前規模**（`build_fraction` = 重建前的 LP 比例）；下破全部換成 USDC（`build_fraction` = 0）。同一天接著跑追隨 F，達到門檻才調成 F × 權益，所以 F < 0.125 時下破後留在全 USDC。`DEPLOY_FULL` 不受影響 | 要退回舊行為：`rescale_work` 兩個分支拿掉 `build_fraction` 的設定 |
| 滿倉／空倉判定 | 規格書值：F ≥ 99.9% 且目前比例低於 99% 才補滿，F = 0 且仍有任何部位就清掉。丟掉乾涸段時比例可能到不了 99%，會每天重建；若出現就放寬 | `FOLLOW_FULL_F`、`FOLLOW_FULL_GAP`、`FOLLOW_EMPTY_TOL`（之前的跑法是 0.98／0.02／0.02） |
| 價格來源 | `_signal_sources` 選 `pool` 或 `binance`（訊號用），LP 評價固定用池價 | 目前只跑 `binance`；兩種都放就同一輪各跑一次 |
| 滑價 | 預設 `SLIPPAGE_MODEL="depth"`（池子 0.05% + 深度滑價），不是規格書的 0.1% 平價；規格書的 0.1% 可能已含滑價，所以兩者不能同時開 | 要貼近規格書：`SWAP_COST_RATE = Decimal("0.001")`、`SLIPPAGE_MODEL = None` |
| 複利再投入 | 每月 1 日把已收手續費加進現有 band；不重建、不置中；新錢的 ETH 用 USDC 換，走一般重建成本 | `_compound = False` 回標準模式 |
| claim 頻率 | 手續費只在重建與複利月初才收，規格書是每天超過 $5 就 claim；未收的手續費不參與複利，複利偏小 | 要更貼近就加每日 claim 判定（含 gas 條件） |
| 最大回撤口徑 | 報表是分鐘級，規格書是 UTC 0 時日級；2022 年差 19.7% vs 約 13% | 看 `netvalue_*.csv` 取每日 00:00 重算 |
| 乾涸 band | 丟棄，該段的 1.27% 留在場外 | 現價 tick 落在段邊界時發生，一年一兩次 |
| 手續費模型 | 實際池子成交量按流動性占比分配 | 與規格書獎勵模型差 13% 到 25%，非程式可改 |

---

## 8. 常見改法

| 想做什麼 | 改哪裡 |
|---|---|
| 虛擬帳戶用 v1 的起算規則 | `SPEC_START = False`（資料夾名加 `-v1start`） |
| 換年份 | `date_ranges` 換或加一行 `(datetime(Y,1,2), date(Y,1,2), date(Y,12,31), "", [])`；要改回 12/31 收盤成交就把起日改回 1/1 |
| 對照兩種下緣 | `_lower_ratios = [MIRROR_PRICE, MIRROR_TICKS]` |
| 對照固定 s | `_eth_shares = [Decimal("0.5"), EMA_SHARE]` |
| 對照永遠滿倉 | `_deploy_modes = [DEPLOY_FULL, DEPLOY_SIGNAL]` |
| 切換標準／複利 | `process_for_date` 的 `_compound`（`True` 複利、`False` 標準），複利的資料夾名帶 `-compound` |
| 切換 swap 成本 | 池費 0.05% + 滑價：`SWAP_COST_RATE = None`、`SLIPPAGE_MODEL = "depth"`；規格書 0.1% 平價：`Decimal("0.001")` 與 `None` |
| 加池價訊號對照 | `_signal_sources = [POOL_SIGNAL, BINANCE_SIGNAL]` |
| 加判定頻率 | `_rescale_frequencies` 加 `RescaleFrequency.hour8` 等 |
| 改 EMA 週期 | `EMA_SPANS`，`EMA_WARMUP_DAYS` 會自動跟著最大值 |
| 改回補門檻 | `REFILL_STAGES`、`REFILL_CONFIRM_DAYS` |
| 改追隨門檻 | `FOLLOW_THRESHOLD` |
| 改結果資料夾前綴 | `_folder_prefix`（第 1250 行）的 `gamma-maker-defense-ethusdc-v2-` |

改引擎常數後先跑 `_self_check`，它會直接失敗。

---

## 9. 自我檢查涵蓋的項目

`_self_check()` 用合成資料驗證：
- `build_gap_bands` 各種 gap 的 tick 偏移。
- `build_shape_config` 中心段被丟掉、每側權重合計 1。
- `swap_to_value_share` 四種起始狀態換完比例精確等於目標，且不會出現負餘額。
- `share_label` 標籤。
- `quote_depth`：2025-06-15 00:00 分鐘（L = 5.0146e18、tick 197949、USDC 為 token0）約 $254M，$70k 的 swap 約 2.8 bp；流動性為 0 或 `None` 回傳 0。
- 複利（`compound_work`）沒有合成資料的自我檢查，驗證方式是整年回測，看 `compound:` 行與複利 − 標準的總值差。
- `daily_ema_frame` 平盤 EMA 收斂；`ema_share_for` 判定日是前一日。
- 引擎：平盤 F = 0；+20% 三日確認後只到第 1 段（每日一段）；下跌後 EMA 退出 F = 0；單帳戶回落不退段、再回升才進下一段。
