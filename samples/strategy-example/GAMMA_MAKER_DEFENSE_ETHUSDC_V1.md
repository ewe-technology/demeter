# gamma_maker_defense_ethusdc_v1.py 說明

谷型 LP 防禦邏輯規格書 v6（ETH 70%・單一階梯方式）的回測實作，跑在 Demeter 回測框架上。
從 `remix_dao_gamma_ig_gap_bands.py` 複製後加入三層規格書邏輯：ETH 占比 s 切換、四帳戶訊號引擎算部署比例 F、每日追隨 F 重建。

相關文件：
- [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md)：2024／2025 對規格書的對照報告，給規格書作者

---

## 1. 快速開始

```bash
cd /Users/makersu/work/githubEwe/demeter/samples/strategy-example && PYTHONPATH=../.. python3 gamma_maker_defense_ethusdc_v1.py
```

- 必須在 `samples/strategy-example` 目錄下執行，結果才會寫到該目錄的 `result/`。
- 分鐘資料從 `../real-data/<pool address>/` 讀取，第一次載入後會快取到 `~/.demeter/`。
- 啟動時會先跑 `_self_check()`，任何 assert 失敗代表引擎邏輯被改壞。
- 預設一個 run 約 4 分鐘。多個 run 用 `multiprocessing.Pool` 並行，`_workers = 5`。
- 預設跑 2022 到 2025 四個年份，每年 1 個 run（8+8 段規格書權重且價格等寬、Binance 訊號、swap 成本 0.1%，即規格書設定），共 4 個。四個年份各開一個行程，同時跑；只想跑一年就把 `date_ranges` 其他行註解掉。要對照池價訊號或 8 個 position，把 `POOL_SIGNAL`、`"inverted_gaussian_9"` 加進清單，run 數相乘。
- Binance 訊號需要同目錄的 `binance_ethusdt_1d.csv`（見 3.5.1），沒有就改 `_signal_sources = [POOL_SIGNAL]`。

輸出資料夾（兩種訊號來源的 run 放在同一個資料夾，以 report 名稱尾端的 `_pool`／`_binance` 區分）：`result/gamma-maker-defense-ethusdc-v1-<shape>-gap-up<上緣>-dn<下緣>-<eth_share>-<deploy>-usdceth-usdc[-swap<bp>bp][-slip<model>]-<投入>-<起日>-<迄日>/`（`SWAP_COST_RATE` 非 `None` 時有 `swap10bp` 之類的標籤，`SLIPPAGE_MODEL` 開啟時有 `slipdepth`；預設是 `...-ig17s-price-...-swap10bp-...`）

---

## 2. 目前預設設定

| 項目 | 值 | 位置 |
|---|---|---|
| 池子 | Ethereum 主網 WETH/USDC 0.05%，`0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`，tick spacing 10 | `process_for_date` 第 1320 行 |
| 投入 | 100,000 USDC，quote 為 USDC | 第 1292 行 |
| 期間 | 2022、2023、2024、2025 各一年，1/1 建倉到 12/31 | `date_ranges` 第 1765 行 |
| `_shapes` | `["inverted_gaussian_spec_price"]`：8+8 段、規格書權重、**價格等寬**（每段 2.5%），即規格書設定（見 3.7）。可加 `"inverted_gaussian_spec"`（tick 等寬）、`"inverted_gaussian"`（舊權重，tick 等寬）、`"inverted_gaussian_9"`（4+4 段，8 個 position，見 6.1）一起跑 | 第 1349 行 |
| `_upper_ratios` | `[0.20]`，上緣 +20% | 第 1357 行 |
| `_lower_ratios` | `[MIRROR_PRICE]`，下緣真 −20% | 第 1363 行 |
| `_centre_half_gaps` | `[0]`，中心無 gap | 第 1370 行 |
| `_eth_shares` | `[EMA_SHARE]`，依 EMA100 切換 70%/50% | 第 1376 行 |
| `_deploy_modes` | `[DEPLOY_SIGNAL]`，訊號引擎決定 F | 第 1378 行 |
| `_signal_sources` | `[BINANCE_SIGNAL]`，訊號的日收盤取規格書使用的 Binance；加 `POOL_SIGNAL` 可同時用池價各跑一次（見 3.5.1） | 第 1381 行 |
| `_rescale_frequencies` | `[daily]`，每日 00:00 判定 | 第 1419 行 |
| `SWAP_COST_RATE` | `Decimal("0.001")`，再平衡換匯的總成本 0.1%（規格書）；設 `None` 則只付池子 0.05%（見 3.6） | 第 138 行 |
| `SLIPPAGE_MODEL` | `None`（關閉）；`"depth"` 依池子深度加價格衝擊（見 3.6）。與規格書的 0.1% 同時開會重複計算，開滑價時請把 `SWAP_COST_RATE` 設 `None` | 第 143 行 |
| swap 滑價旗標 | `swap_fee=False`；此旗標在 v1 沒有作用 | 第 1398 行 |
| 手續費 | 收取時賣成 USDC，不再投入 | `collect_fee_as_quote` |
| Binance 日線 | `binance_ethusdt_1d.csv`，2017-08-17 到 2025-12-31，3,059 筆 | `BINANCE_CSV` |

每個清單參數多給一個值就多一組 run，組合數 = shapes × upper × lower × gaps × eth_shares × deploy × signal_sources × frequencies。預設每個清單都只有一個值，所以每個年份跑 1 個 run。

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

### 3.5.1 訊號價格來源（`_signal_sources`）

只決定訊號引擎（F 與 EMA100 的 s 規則）吃哪一組 UTC 日收盤，**LP 本身的建倉、重建、撤倉永遠用池價**。

| 值 | 日收盤來源 | 備註 |
|---|---|---|
| `POOL_SIGNAL` | 池子分鐘價，取每日最後一筆 | 暖機受池子資料限制，最早 2021-05-05 |
| `BINANCE_SIGNAL` | `binance_ethusdt_1d.csv` 的 Binance ETHUSDT 日收盤 | 規格書的價格來源，從 2017-08-17 起算，暖機與規格書相同 |

- 兩個來源可同時列入，每組參數各跑一次，report 名稱尾端分別加 `_pool`、`_binance`。
- `binance_daily_frame` 會檢查 CSV 涵蓋「視窗前一天」到「結束日」、日期連續，否則直接 `ValueError`；暖機不足 `EMA_WARMUP_DAYS` 時印出警告。
- CSV 要更新時直接換檔，欄位 `date`（`YYYY-MM-DD`，UTC）、`close`，不需改程式。
- 為什麼要兩個來源：USDC 脫鉤（2023/3）時池價偏高最多 4.5%，EMA 訊號因此早一天觸發，詳見 [GAMMA_IG_V6_1_DIFF_EXPLAINED.md](GAMMA_IG_V6_1_DIFF_EXPLAINED.md)。

### 3.6 swap 成本（`SWAP_COST_RATE`）

規格書：每次再平衡的實際換匯金額 × 0.1%。`SWAP_COST_RATE = Decimal("0.001")` 對應這個設定。

- 池子本來就在每筆 swap 收 0.05%，所以只額外扣 (0.1% − 0.05%) × 換匯的 quote 金額，總成本剛好 0.1%。
- 只用在**再平衡換匯**（`first_lp`、`rescale_work` 的放置前換匯）。手續費賣成 USDC 那筆不加：規格書的獎勵以 USDC 發放，本來就沒有這個 swap。
- 額外成本從 quote 餘額扣，並計入 `Total Swap Fee`，所以該欄大約是設 `None` 時的兩倍。
- 設 `None` 回到只付池子 0.05%。資料夾名稱帶 `swap<bp>bp`（`0.001` 是 `swap10bp`），不同設定不會互相覆蓋；`None` 時沒有這個標籤。
- 這個設定是模組常數，不像其他參數是 `process_for_date` 內的清單，所以一次只能跑一種成本；要對照就改常數跑兩次。

**滑價（`SLIPPAGE_MODEL`）**

demeter 的 `buy`／`sell` 以資料裡的池價成交，只扣池子手續費，沒有價格衝擊（`GlobalParams.swap_fee` 在 v1 不被讀取，沒有作用）。`SLIPPAGE_MODEL = "depth"` 用池子的深度估價格衝擊：

- 目前 tick 內可視為 `x * y = k` 的虛擬池。USDC 為 token0 時，USDC 的虛擬準備量 = `currentLiquidity ÷ 1.0001^(closeTick/2) ÷ 10⁶`（`quote_depth`）。
- 換匯金額 D（美元）的平均滑價 ≈ D ÷ 準備量，額外成本 = D × D ÷ 準備量，從 quote 餘額扣，計入 `Total Swap Fee`。只用在再平衡換匯，`currentLiquidity` 缺值的分鐘不收。
- 用真實資料算的量級（$70k 換匯）：2022-03 約 0.6 bp、2023-03 約 0.7 bp、2024-03 約 1.5 bp、2025-06 約 2.8 bp、2025-11 約 8 bp（流動性從 $1.2B 掉到 $88M）。2025 年實測多付 $403（約 0.4 pt）。
- 假設換匯不跨出目前的 tick 區間（$70k 的價格影響不到 10 bp，成立）。不含聚合器價差、MEV、私有 RPC 的費用。
- **與 `SWAP_COST_RATE = 0.001` 同時開會重複計算**（規格書的 0.1% 可能已含滑點）。要比較「池子 0.05% 加實際價格衝擊」，請設 `SWAP_COST_RATE = None`、`SLIPPAGE_MODEL = "depth"`。

### 3.7 區段切法（tick 等寬／價格等寬）

規格書（v6 第 2.1 節、v2 第 4 節）：上下各 8 段，**每段寬度為中心價的 2.5%**，合計 c×0.80 到 c×1.20。v2 規格書還附了 tick 對照表（總長上 +1,823、下 −2,231；每段上約 247 → 211、下約 253 → 308），並明說「不可以 tick 數上下對稱設定」。

| 切法 | 形狀名稱 | 邊界（上方第 1／4／8 段，下方同） | 對規格書 |
|---|---|---|---|
| 價格等寬 | 後綴 `_price`，例如 `inverted_gaussian_spec_price`（標籤 `ig17s-price`） | 1.0253／1.0997／1.1996；0.9753／0.9003／0.8001（總長 +1,820／−2,230 tick） | 符合（差 0.1% 內是捨入到 tick 間距 10） |
| tick 等寬 | 無後綴，例如 `inverted_gaussian_spec`（標籤 `ig17s-tick`） | 1.0233／1.0964／1.202；0.9724／0.894／0.7993（總長 +1,840／−2,240 tick） | 中間邊界最多偏約 0.6 個百分點，**外緣也多出約 0.2%**（見下） |

**外緣為什麼不同：** tick 等寬的程式先把**每段寬度**取整到 tick 間距（10）的倍數再乘 8：上方 1823 ÷ 8 ≈ 227.9 取整成 230，乘 8 得 1,840（目標 1,823，多 17 tick，約 +0.17%）；下方 2231 ÷ 8 ≈ 278.9 取整成 280，得 2,240（多 9 tick）。每段的取整誤差被乘 8 倍累積，最大可達 ±40 tick（0.4%）。價格等寬是對**每個邊界**各自取整，誤差最多 5 tick，不累積。所以 tick 等寬的階梯實際上比規格書的 ±20% 寬了一點。

**這會造成邊緣事件：** 2024-03-12 的例子。中心 $3,384，價格 $4,067.1。規格書的上破門檻是 3,384 × 1.2 = $4,061，價格已超過；用 Binance 資料檢查，規格書自己判定用的 3/11 收盤 $4,064.8 也高於中心（Binance 2/28 收盤 $3,383.1）× 1.2 = $4,059.7，所以**規格書的規則在 3/12 也會觸發重建**；3/19 收盤 $3,158.6 低於新中心的 0.8 倍（約 $3,252），3/20 又會觸發下破。價格等寬的上緣是 $4,060，同樣出界、重建；tick 等寬的上緣是 $4,068，剛好把 $4,067.1 圈在裡面，沒有重建。兩者 2024 年差約 6.6 pt（見 6.5）。

- 其餘形狀名稱同理：`inverted_gaussian`（標籤 `ig17-tick`）、`inverted_gaussian_9`（`ig9-tick`）；加 `_price` 即價格等寬。價格等寬只支援中心無 gap 且下緣為價格比例（`MIRROR_PRICE`），其他組合直接報錯。
- 我們的池子 token0 是 USDC，tick 越高 ETH 價越低。tick 等寬路徑要先把上下比例換算（0.2／0.2 變成 0.25／0.1667）；價格等寬路徑改用 `build_price_bands`，直接吃原始比例並依 `token0_is_quote` 決定方向。兩條路徑都在 `shape_config_for`，`_self_check` 驗證實際路徑的 ETH 價格邊界。
- v2 程式用全域開關 `EQUAL_PRICE_BANDS`（預設 `True`）；v1 改用形狀後綴，可以在 `_shapes` 同時放兩種切法比較。
- 兩種切法的報酬比較見 6.5。

### 3.8 每日的執行順序

demeter 依 trigger 註冊順序觸發，同一分鐘的順序是：

1. `rescale_work`（出區間判定，頻率依 `_rescale_frequencies`）
2. `follow_work`（追隨 F，每日）
3. `log_fees`（每日手續費快照）

1 和 2 都可能重建，但一天最多只會真的重建一次：前者重建後 cur ≈ F，後者不會再觸發；後者重建後在區間內，前者不會觸發。

---

## 4. 主要函式與類別

### 模組層（第 65 到 480 行）

| 名稱 | 用途 |
|---|---|
| `MIRROR_PRICE` / `MIRROR_TICKS` | 下緣算法：真實價格比例，或和上緣相同 tick 數 |
| `EMA_SHARE`、`DEPLOY_FULL`、`DEPLOY_SIGNAL` | 參數的字串常數 |
| `EMA_SPANS`、`LOWER_STOP`、`UPPER_REBUILD`、`REFILL_STAGES`、`REFILL_CONFIRM_DAYS`、`FOLLOW_THRESHOLD`、`FULL_TOLERANCE` | 引擎常數，對應規格書第 3 節參數表 |
| `VirtualAccount` | 一個虛擬帳戶的狀態機，`step(close, ema)` 走一天 |
| `share_label` / `ratio_label` / `gap_label` | 報表與資料夾名稱的標籤 |
| `daily_ema_frame(minute_price)` | 日收盤、EMA100、F 三欄的 DataFrame |
| `binance_daily_frame(dsd, ded)` | 讀 `BINANCE_CSV`、檢查涵蓋範圍與連續性，再交給 `daily_ema_frame` |
| `quote_depth(liquidity, tick, token0_is_quote, quote_decimal)` | 目前 tick 的 quote 虛擬準備量（美元），供滑價估算（見 3.6） |
| `POOL_SIGNAL`／`BINANCE_SIGNAL`／`BINANCE_CSV` | 訊號來源常數與 Binance 日線檔路徑 |
| `daily_row_for` / `ema_share_for` / `target_fraction_for` | 依時間戳取前一日的判定值 |
| `swap_to_value_share(base, quote, price, base_share)` | 純函式，算出要買賣多少 base 才能讓 base 佔總值 `base_share` |
| `build_gap_bands` | 16 段的 tick 偏移，**tick 等寬** |
| `build_price_bands` | 16 段的 tick 偏移，**價格等寬**（每段 2.5%），依 `token0_is_quote` 決定方向（自 v2 複製） |
| `build_shape_config` | 每段的 `[下偏移, 上偏移, 該側佔比]`，中心權重 0 的段會被丟掉；可傳入預先算好的 `bands` |
| `shape_config_for` | 策略實際呼叫的入口：依形狀名稱後綴 `_price` 選切法，並處理 token0 = quote 的比例換算 |

### 策略類別 `RemixDaoDcaWeekStratStrategy`（第 484 行起）

| 方法 | 用途 |
|---|---|
| `__init__` | 收 `shape`、`upper_ratio`、`lower_ratio`、`half_gap`、`eth_share`、`daily_ema`、`deploy` |
| `initialize` | 註冊 `first_lp`、`rescale_work`、`follow_work`、`log_fees`、`calculate_final_result` 五個 trigger |
| `resolve_share(timestamp)` | 決定這次的 s，並累計各比例被選次數 |
| `pre_placement_swap(...)` | 算 F、保留金額，回傳要換多少幣 |
| `follow_work(row_data)` | 追隨 F 的每日判定 |
| `execute_swap(lp_market, base, quote, rebalance=False)` | 覆寫基底版本；`rebalance=True`（建倉、重建）時額外扣 `SWAP_COST_RATE` 減池子費率的成本（見 3.6） |
| `log_fees(row_data)` | 每日記錄已收與未收手續費、LP 淨值 |
| `collect_fee_as_quote(lp_market, position_info)` | 收手續費並把 ETH 部分賣成 USDC |
| `band_amounts(base, quote, share)` | 該段要放的兩種幣數量，clamp 到可用餘額 |
| `check_rebalance` | 現價是否在 16 段之外 |
| `rescale_work(row_data)` | 撤倉、換幣、放置、記錄 `ExportData` 的完整流程 |
| `first_lp(row_data)` | 建倉，流程與 `rescale_work` 相同但沒有撤倉 |
| `calculate_final_result(row_data)` | 期末收手續費、寫 `fees_*.csv`、印 `final result` 摘要 |

### 執行層（第 1125 行起）

| 名稱 | 用途 |
|---|---|
| `run_test(...)` | 建 market、載資料、跑 actuator、算指標，回傳結果 dict |
| `_run_one(...)` | Pool worker，頂層函式才能 pickle |
| `process_for_date(csd, dsd, ded, id, flip)` | 一個回測期間的全部 run：建參數、依 `_signal_sources` 各算一份 `daily_ema`（池價版載暖身資料，Binance 版讀 CSV）、展開組合、starmap、寫總表 |
| `_with_share(p, lower_ratio, eth_share, deploy, source)` | 把每組基礎參數展開成 lower × eth_share × deploy × signal_source 的組合並補報表名 |
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

### `signal_v1_daily_<起>_<迄>.csv`／`signal_v1_binance_daily_<起>_<迄>.csv`

`result/` 底下，每個訊號來源一份，欄位 `date, close, ema, F`。前者是池價版（檔名沿用舊的，供 v2 對照），後者是 Binance 版。兩者的 `F` 欄逐日相減就能看出哪幾天訊號不同。檔案含暖身期，要看視窗內請取 `date` ≥ 起日。

report 名稱（`result_`、`fees_` 檔名與總表的列名）尾端是 `_pool` 或 `_binance`，看列就知道是哪個來源。

---

## 6. 目前結果（2026-10-01 重跑）

報酬欄括號內是「本金 + 手續費（規格書稱獎勵）」，單位 $k。規格書數字取自規格書 5.1 節（Binance 價格，每年 1/1 投入 $100k）。

**預設設定**（`ig17s-price`：規格書權重、價格等寬、Binance 訊號、swap 成本 0.1%、無滑價），2026-10-01：

| 年 | ETH 持有（池價） | 規格書 | 本程式 | 差 |
|---|---|---|---|---|
| 2022 | −68% | +6.5%（90.3 + 16.2） | **+11.8%**（90.2 + 21.6） | +5.3 pt |
| 2023 | +91% | +43.5%（118.3 + 25.2） | **+40.4%**（117.9 + 22.4） | −3.1 pt |
| 2024 | +46% | +39.0%（103.4 + 35.5） | **+28.5%**（97.4 + 31.0） | −10.5 pt |
| 2025 | −11% | +22.3%（94.7 + 27.6） | **+16.9%**（94.8 + 21.4） | −5.4 pt |

- **本金：** 2022、2023、2025 與規格書差 0.4k 以內；2024 少 6.0k，原因是 3 月的兩次重建（3/12 上破、3/20 下破），見 6.5。
- **報酬差距全在手續費：** 實際池子手續費比規格書的獎勵模型，2022 高 33%，2023–2025 低 11% 到 22%；這部分不是程式可以調整的。
- 權重、swap 成本、切法各自的影響見 6.3、6.4、6.5。

**池子 0.05% 加深度滑價**（`SWAP_COST_RATE = None`、`SLIPPAGE_MODEL = "depth"`，其餘同上）：

| 年 | 報酬 | 差（對規格書） | 本金 | 手續費 | `Total Swap Fee` |
|---|---|---|---|---|---|
| 2022 | +12.2% | +5.7 pt | 90.5 | 21.7 | $379 |
| 2023 | +40.8% | −2.8 pt | 118.3 | 22.4 | $461 |
| 2024 | +28.8% | −10.2 pt | 97.8 | 31.0 | $585 |
| 2025 | +17.1% | −5.2 pt | 94.9 | 21.5 | $961 |

比 0.1% 設定每年高 0.1 到 0.35 pt。滑價只在流動性變低的年份顯著（見 3.6），2022、2023 遠小於額外的 0.05%，2025 兩者接近（$961 對 $1,099）。規格書的 0.1% 在這四年是較保守的假設。

**以下三組表（訊號來源、8 個 position）是先前的設定**跑出來的（tick 等寬；`inverted_gaussian` 舊權重；swap 成本只有池子 0.05%），用來比較各因素的影響。先前資料夾標籤 `ig17`、`ig17s`、`ig9` 即現在的 `ig17-tick`、`ig17s-tick`、`ig9-tick`（只是改名，邏輯不變）。訊號來源對照：

| 年 | ETH 持有（池價） | 規格書 | 池價訊號 | Binance 訊號 |
|---|---|---|---|---|
| 2022 | −68% | +6.5%（90.3 + 16.2） | +7.6%（87.5 + 20.1） | **+11.9%**（90.6 + 21.3） |
| 2023 | +91% | +43.5%（118.3 + 25.2） | +32.3%（108.9 + 23.3） | **+38.9%**（117.0 + 21.9） |
| 2024 | +46% | +39.0%（103.4 + 35.5） | +36.5%（105.5 + 30.9） | **+35.5%**（104.8 + 30.7） |
| 2025 | −11% | +22.3%（94.7 + 27.6） | +16.5%（95.1 + 20.8） | **+16.5%**（95.1 + 20.8） |

- **訊號價格來源只在兩年有影響：** 2022（池價版 F 有 18 天不同：3/25–4/10 和 9/11）與 2023（16 天不同：3/13–3/16 與 8/3–8/14，USDC 脫鉤）。2024 只差 6 天（5/19–5/24），2025 沒有差。
- **本金：** 改用 Binance 訊號後，2022、2023 的本金與規格書差 0.3k 與 1.3k 以內；2024、2025 本來就一致。2021 起算與 2017 起算的暖機結果完全相同。
- **手續費：** 與價格來源無關。2024、2025 實際池子手續費比規格書的獎勵模型低 13% 到 25%；2022 相反，高出 31%（21.3k 對 16.2k），所以 2022 的報酬超過規格書。2023 低 13%。
- 詳見 [PDFV6_COMPARISON_REPORT.md](PDFV6_COMPARISON_REPORT.md) 與 [GAMMA_IG_V6_1_DIFF_EXPLAINED.md](GAMMA_IG_V6_1_DIFF_EXPLAINED.md)。

### 6.1 8 個 position（`inverted_gaussian_9`，4+4 段）對 16 個 position（`inverted_gaussian`，8+8 段）

`inverted_gaussian_9` 把 17 段裡相鄰兩段的權重合併，中心段權重 0 放置時丟掉，每側剩 4 個。範圍仍是 ±20%，每段約 5% 寬。報酬（%）：

| 年 | 訊號 | 16 個（ig17） | 8 個（ig9） | 差 |
|---|---|---|---|---|
| 2022 | 池價 | +7.64 | +9.68 | +2.04 |
| 2022 | Binance | +11.89 | +13.86 | +1.97 |
| 2023 | 池價 | +32.27 | +31.93 | −0.34 |
| 2023 | Binance | +38.93 | +38.97 | +0.04 |
| 2024 | 池價 | +36.46 | +36.86 | +0.40 |
| 2024 | Binance | +35.51 | +35.90 | +0.39 |
| 2025 | 池價 | +16.55 | +16.63 | +0.08 |
| 2025 | Binance | +16.55 | +16.63 | +0.08 |

- 2023 到 2025 差在 ±0.4 pt 內；2022 多 2.0 pt，原因未查。本金差最多 0.3k（2022 多 1.3k），手續費 ig9 四年都略高（+0.0k 到 +0.8k）。
- 重建次數、最大回撤、swap 成本幾乎不變：出界與追隨 F 的判定看整個範圍，與段數無關。
- 回測**不算 gas**，所以看不出 8 個 position 的主要好處，見 6.2。
- 沒有讓結果更接近規格書：2023–2025 與規格書的差距仍在手續費模型。

### 6.2 gas 估計（粗估，非實測）

每次重建要撤掉舊 position、再放新 position，gas 與 position 個數成正比。放置事件數取自 `result_*.csv`（Binance 訊號，每次放置 = 一次重建或建倉，F = 0 的不算）：

| 年 | 放置事件 | 16 個：mint 次數 | 8 個：mint 次數 | 少 |
|---|---|---|---|---|
| 2022 | 31 | 496 | 248 | 248 |
| 2023 | 18 | 288 | 144 | 144 |
| 2024 | 23 | 368 | 184 | 184 |
| 2025 | 25 | 400 | 200 | 200 |

假設：每個 position 的一輪（mint + 撤倉 + collect）約 **450k gas**（直接用池子約 300k，經 NonfungiblePositionManager 約 600k，這個數字是經驗估計，沒有實測），ETH $2,000。則每個 position 一輪約 **$0.9 × gas 價格（gwei）**。8 個比 16 個省下的錢：

| 年 | 2 gwei | 10 gwei | 30 gwei | 占 $100k 的比例（10 gwei） |
|---|---|---|---|---|
| 2022 | $446 | $2,232 | $6,696 | 2.2% |
| 2023 | $259 | $1,296 | $3,888 | 1.3% |
| 2024 | $331 | $1,656 | $4,968 | 1.7% |
| 2025 | $360 | $1,800 | $5,400 | 1.8% |

- 在 10 gwei 以上，8 個 position 省下的 gas 超過報酬差距，淨結果會比 16 個好 1 到 2 個百分點。
- gas 是固定成本，AUM 越大占比越小；$100k 這個規模最敏感。
- 各年實際 gas 價格要自行代入；要精確請用實際鏈上交易的 gas used 取代 450k。

**估計涵蓋與未涵蓋的動作**（依 `rescale_work`、`collect_fee_as_quote`、`calculate_final_result` 的實際呼叫）：

| 動作 | 發生時機 | 估計是否涵蓋 | 與 position 個數的關係 |
|---|---|---|---|
| mint（建倉） | 每次建倉、重建 | 涵蓋 | 成正比 |
| 撤倉 + collect | 每次重建、F = 0 退出 | 涵蓋（與先前 mint 配成一輪） | 成正比 |
| 放置前換幣（換到目標 ETH 占比） | 每次重建 | 未涵蓋 | 每次 1 筆，與段數無關 |
| 手續費中的 ETH 賣成 USDC | 每次重建、期末 | 未涵蓋 | 回測逐 position 各賣一次；實際可合併成一筆（與段數無關），逐個賣則 16 個比 8 個多 8 筆 |
| 單獨 claim 手續費 | 無 | 不適用 | 程式沒有此動作；`log_fees` 每日只記錄快照，不上鏈 |

- 手續費只在重建與期末收取，收費的 gas 已含在撤倉的 collect 裡，不需另外加 claim。
- 一次性的 approve、失敗交易、MEV、優先費都未計入。
- 期末仍在場內的 position 沒有撤，所以每年的撤倉次數略少於 mint 次數，估計偏高一點。
- 若手續費賣出是逐 position 各一筆 swap，8 個 position 省下的 gas 會比表格更多。

### 6.3 階梯權重：規格書原值（`ig17s`）對由權重表推出的舊值（`ig17`）

兩者每側從中心往外：規格書 1.2/4.6/8.8/13.0/16.0/18.0/19.0/19.4%，舊值 1.27/4.61/8.89/12.93/16.0/17.94/18.96/19.4%，差最多 0.07 個百分點。Binance 訊號、swap 成本 0.05% 下：

| 年 | `ig17` | `ig17s` | 差 | 本金差 | 手續費差 |
|---|---|---|---|---|---|
| 2022 | +11.89% | +11.88% | −0.01 pt | +$30 | −$40 |
| 2023 | +38.93% | +38.93% | 0.00 pt | +$20 | −$20 |
| 2024 | +35.51% | +35.51% | 0.00 pt | +$40 | −$40 |
| 2025 | +16.55% | +16.61% | +0.06 pt | +$110 | −$10 |

重建次數四年相同，最大回撤差最多 0.1 pt。權重差異在雜訊以內，不是與規格書差距的來源，預設改用規格書原值。

### 6.4 swap 成本：池子 0.05% 對規格書 0.1%

`ig17s`、Binance 訊號下，`SWAP_COST_RATE` 由 `None`（0.05%）改為 `0.001`（0.1%）：

| 年 | 0.05% 報酬 | 0.1% 報酬 | 差 | `Total Swap Fee` |
|---|---|---|---|---|
| 2022 | +11.88% | +11.49% | −0.39 pt | $332 → $714 |
| 2023 | +38.93% | +38.54% | −0.39 pt | $419 → $782 |
| 2024 | +35.51% | +35.08% | −0.43 pt | $446 → $870 |
| 2025 | +16.61% | +16.08% | −0.53 pt | $556 → $1,097 |

- 報酬少 0.4 到 0.5 pt，`Total Swap Fee` 約為原來的 1.9 到 2.2 倍，方向與「額外多收 0.05%」的預期一致；不是剛好兩倍的原因沒有逐項拆解。
- 重建次數相同，最大回撤差 0.2 pt 內，手續費收入差 $60 內，成本只吃掉本金。

### 6.5 區段切法：價格等寬（`ig17s-price`）對 tick 等寬（`ig17s-tick`）

Binance 訊號、swap 成本 0.1%、規格書權重，只換切法（括號內是對規格書的差）：

| 年 | 報酬 價格等寬 | 報酬 tick 等寬 | 本金 價格等寬 | 本金 tick 等寬 | 規格書本金 |
|---|---|---|---|---|---|
| 2022 | +11.83% | +11.49% | 90.2（−0.1） | 90.3（0.0） | 90.3 |
| 2023 | +40.40% | +38.54% | 117.9（−0.4） | 116.6（−1.7） | 118.3 |
| 2024 | +28.49% | +35.08% | 97.4（**−6.0**） | 104.4（+1.0） | 103.4 |
| 2025 | +16.93% | +16.08% | 94.8（+0.1） | 94.7（0.0） | 94.7 |

- **2024 的差距來自兩次重建：** 價格等寬在 3/12（價格 $4,067）上破重建、3/20（$3,162）下破又重建，重建次數 4 次；tick 等寬一次都沒有，只有 2 次。差距在 3/12 到 4/14 之間形成（總值 $120.7k 對 $127.0k），之後維持不變（年底 $128.8k 對 $135.0k）。
- **機制（依 LP 運作推論，未逐筆驗證）：** 價格漲過階梯時 ETH 被一路賣成 USDC；沒重建的階梯在頂端幾乎全是 USDC，價格回落時再低買 ETH。重建的階梯在高點把 USDC 換成 ETH（F = 0.9、ETH 70%），價格回落 22% 虧損，3/20 再實現。
- **tick 等寬沒重建是取整誤差**（見 3.7）：它的上緣 $4,068 剛好圈住 $4,067.1。用 Binance 資料檢查，規格書自己的規則（3/11 收盤 $4,064.8 > 中心 × 1.2 = $4,059.7）在 3/12 也會觸發重建；3/19 收盤 $3,158.6 也跌破新中心的 0.8 倍，3/20 觸發下破。所以**價格等寬的事件序列才與規格書的規則一致**。
- **本金逐年的絕對誤差加總：** 價格等寬 6.6k，tick 等寬 2.7k。tick 等寬在 2024 看起來較貼近規格書，是因為它沒有重建而規格書有；這是巧合，不能當依據。
- **未解：** 價格等寬在 2024 的本金仍比規格書少 $6.0k。可能與重建時的價格來源有關（我們用 00:00 當分鐘的池價，規格書用 Binance 日收盤）或規格書對下破時的處理，需要規格書 2024 的逐日部位才能確認。
- **結論：** 預設用價格等寬（符合規格書的定義與事件規則）。其餘三年價格等寬較好 0.3 到 1.9 pt，2024 差 6.6 pt 是單一邊緣事件；4 年資料看不出切法穩定地優劣。

其他已測的變體：
- `MIRROR_TICKS`（下緣 −16.8%）：2024 差 6.4 pt，2025 持平，維持 `MIRROR_PRICE`。
- 8h／12h 判定：2024 明顯較差（8h +29.5%），2025 差距 1 pt 內。
- 固定 s = 0.5 / 0.7 / `sgeo`、`DEPLOY_FULL`：2025 全年在 −6% 到 −15% 之間，證明獲利來自 F 而非 s。

---

## 7. 刻意簡化與已知限制

| 項目 | 現況 | 若要改 |
|---|---|---|
| 引擎起算日 | 池價版：視窗前 360 天（2022 只有 241 天，EMA120 在 3/25 尚未收斂）。Binance 版：2017-08-17 起連續，與規格書相同 | 池價版受池子資料限制（2021-05-05 起） |
| 空倉時 EMA 退出重設 low | 照規格書字面執行 | `VirtualAccount.step` 規則 1 加 `deployed > 0` 條件 |
| 上破重建 | 直接重建為 F × 權益 | 規格書是先保留舊規模再追隨，差異只在 \|F − cur\| < 12.5% 時 |
| 滿倉／空倉判定 | 容忍 2% 塵埃 | `FULL_TOLERANCE` |
| 出界判定 | 看池價落在階梯的 tick 範圍外（價格等寬的上緣約中心 × 1.1996、下緣 × 0.8001），不是規格書的「收盤 > 中心 × 1.20」「收盤 < 中心 × 0.80」 | 邊緣日（如 2024-03-12）可能與規格書差一天；要完全對齊得改用日收盤與中心的比例判斷 |
| 價格來源 | 訊號可選池價或 Binance（`_signal_sources`）；LP 下單一律用池價 | 規格書的本金要完全對齊還需要 LP 也用 Binance 價，但那不是真實 LP 會遇到的價格 |
| swap 成本 | 預設 `SWAP_COST_RATE = 0.001`（規格書 0.1%）；只對再平衡換匯，手續費賣成 USDC 那筆只付池子 0.05% | 改 `SWAP_COST_RATE`，`None` 為只付池子 0.05% |
| 滑價 | 未模擬：demeter 的 `buy`／`sell` 以資料裡的池價成交，只扣池子手續費，沒有價格衝擊。規格書的 0.1% 可能已含滑點，我們的 `SWAP_COST_RATE` 是固定比例 | `GlobalParams.swap_fee` 沒有作用（v1 不讀它）。要算滑價得另寫：資料有每分鐘的 `currentLiquidity`，可由換匯金額與流動性估價格衝擊 |
| 乾涸 band | 丟棄，該段的 1.27% 留在場外 | 現價 tick 落在段邊界時發生，一年一兩次 |
| 手續費模型 | 實際池子成交量按流動性占比分配 | 與規格書獎勵模型差 13% 到 25%，非程式可改 |

---

## 8. 常見改法

| 想做什麼 | 改哪裡 |
|---|---|
| 對照 tick 等寬 | `_shapes = ["inverted_gaussian_spec_price", "inverted_gaussian_spec"]` |
| 對照舊權重 | `_shapes = ["inverted_gaussian_spec_price", "inverted_gaussian_price"]` |
| 對照 8 個 position | `_shapes = ["inverted_gaussian_spec_price", "inverted_gaussian_9_price"]` |
| 自訂權重 | 在 `SHAPE_WEIGHTS` 加一行（17 個值，中心 0，左右對稱，總和不必剛好 1），再放進 `_shapes`；在 `SHAPE_LABELS` 給短名 |
| 對照 swap 成本 | 改 `SWAP_COST_RATE`（`None` 或 `Decimal("0.001")`）各跑一次，資料夾名稱不同 |
| 池子 0.05% 加滑價 | `SWAP_COST_RATE = None`、`SLIPPAGE_MODEL = "depth"`（資料夾帶 `slipdepth`）；規格書 0.1% 則 `Decimal("0.001")` 與 `None` |
| 對照池價訊號 | `_signal_sources = [BINANCE_SIGNAL, POOL_SIGNAL]` |
| 更新 Binance 日線 | 換 `binance_ethusdt_1d.csv`（欄位 `date, close`，UTC，日期連續，要涵蓋回測前一天到結束日） |
| 換年份 | `date_ranges`（第 1765 行）換或加一行 `(datetime(Y,1,1), date(Y,1,1), date(Y,12,31), "", [])` |
| 對照兩種下緣 | `_lower_ratios = [MIRROR_PRICE, MIRROR_TICKS]` |
| 對照固定 s | `_eth_shares = [Decimal("0.5"), EMA_SHARE]` |
| 對照永遠滿倉 | `_deploy_modes = [DEPLOY_FULL, DEPLOY_SIGNAL]` |
| 加判定頻率 | `_rescale_frequencies` 加 `RescaleFrequency.hour8` 等 |
| 改 EMA 週期 | `EMA_SPANS`，`EMA_WARMUP_DAYS` 會自動跟著最大值 |
| 改回補門檻 | `REFILL_STAGES`、`REFILL_CONFIRM_DAYS` |
| 改追隨門檻 | `FOLLOW_THRESHOLD` |
| 改結果資料夾前綴 | `_folder_prefix`（第 1384 行）的 `gamma-maker-defense-ethusdc-v1-` |

改引擎常數後先跑 `_self_check`，它會直接失敗。

---

## 9. 自我檢查涵蓋的項目

`_self_check()` 用合成資料驗證：
- `build_gap_bands` 各種 gap 的 tick 偏移。
- `build_shape_config` 中心段被丟掉、每側權重合計 1；規格書形狀產出 16 個 position，每側權重正好是 1.2 到 19.4%。
- `build_price_bands`：token0 = quote 時上升側 1820 tick、下降側 2230 tick，段寬在上升側往外變窄、下降側往外變寬；token0 = base 時為鏡像。
- `quote_depth`：用 2025-06-15 00:00 分鐘的真實數字（L = 5.0146e18、tick 197949）驗證準備量約 $254M、$70k 換匯約 2.8 bp；`liquidity` 為 0 或 `None` 回傳 0。
- `shape_config_for`（策略實際走的路徑，token0 = quote）：價格等寬的各段邊界落在 ETH 價格的 1 ± 2.5% × k，差在 0.15% 內。
- `swap_to_value_share` 四種起始狀態換完比例精確等於目標，且不會出現負餘額。
- `share_label` 標籤。
- `daily_ema_frame` 平盤 EMA 收斂；`ema_share_for` 判定日是前一日。
- 引擎：平盤 F = 0；+20% 三日確認後只到第 1 段（每日一段）；下跌後 EMA 退出 F = 0；單帳戶回落不退段、再回升才進下一段。
