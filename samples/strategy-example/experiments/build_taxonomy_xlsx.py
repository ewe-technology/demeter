"""Seed the team's shared experiment sheet (QUAN-1107 / QUAN-1108).

The sheet lives in Google Drive and the team maintains it there:
https://docs.google.com/spreadsheets/d/1wRgWxo6PyXtHUAEX-tObBQzKb5oZEvG_7bQDJfT-llo/edit
This script only built the first version from TAXONOMY.csv + registry.csv. Do not re-run it over the live
sheet: rows added by others would be lost. Google's xlsx import drops the cross-sheet dropdowns, so after the
upload they were set again with a Sheets API batchUpdate (setDataValidation, ONE_OF_RANGE on 清單).

Layout: 總覽 (defense v1/v2/v3 + per-category and per-owner counts, all formulas), 填寫說明 (how to add a
row, column guide, one example row), one sheet per category with the same 15 columns, 其他類別, 清單
(dropdown sources: owners, statuses, judging rules).

    python experiments/taxonomy.py && python experiments/build_taxonomy_xlsx.py <out.xlsx>
    gws drive files create --json '{"name": "...", "mimeType": "application/vnd.google-apps.spreadsheet"}' \
        --upload <out.xlsx>
"""
import csv
import datetime
import pathlib
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from taxonomy import CATEGORIES

HERE = pathlib.Path(__file__).resolve().parent
DOC_URL = "https://github.com/ewe-technology/demeter/blob/feat/dino-v6-opt/samples/strategy-example/experiments/"
JIRA_URL = "https://ewetechnology.atlassian.net/browse/"
LAST_ROW = 1000

SHEET = {
    "signal": "訊號線", "f_engine": "F引擎", "exit_stop": "撤出停損", "refill": "回補",
    "rebuild": "重建時機", "width": "區間寬度形狀", "share": "ETH比例s", "macro": "總經事件",
    "fee_tier": "費率分層組合", "routing": "換匯路由", "non_lp": "非LP本體", "validation": "驗證移植",
    "other": "其他類別",
}
OTHER = ("其他類別", "放不進上面 12 類的嘗試")

LESSON = {
    "signal": "EMA 換成別的趨勢線都沒贏；Donchian 只在單獨等級通過",
    "f_engine": "全部失敗；四帳戶 EMA 引擎不要動",
    "exit_stop": "兩天確認單獨通過，全歷史只贏 1/7；盤中停損只對 WBTC 有用；v3 的過熱撤出屬於這類，尚未在 7 池測",
    "refill": "唯一一再成立的發現：v6.75（5/7）；跨資產回補只對 ETH 有用",
    "rebuild": "上漲 / 比例翻轉時重建，跨時間不成立；通過的都含 v6.75",
    "width": "固定 ±20% 保留：5 條動態寬度規則全輸；+40% 上緣回撤較深、輸 BTC",
    "share": "固定 50% 單獨表現一樣好：EMA100 比例規則貢獻小",
    "macro": "ETH +0.4 pt CAGR，但重建次數翻倍（gas 未計）",
    "fee_tier": "23 個通過約等於 4 個發現；0.05% 那側都跑 v6.75",
    "routing": "swap 走 0.05% 池：WBTC 約 +1 pt",
    "non_lp": "範圍外：閒置收益不算改進（2026-10-05 裁定），2026-10-01 起只做純 LP",
    "validation": "不是策略改動",
    "other": "",
}

OWNERS = ["Dino Huang", "Maker Su", "Steven Yang", "Joy Hsu", "Austin"]
STATUSES = ["規劃中", "進行中", "通過", "失敗", "開發期淘汰", "待前測", "撤回", "基準"]
RULES = ["全歷史（多池）", "dev + holdout", "單池 / 單期間", "規格書模型", "其他"]
STATUS_MAP = {"dropped-at-dev": "開發期淘汰", "holdout-pass": "通過", "pass": "通過", "holdout-fail": "失敗",
              "fail": "失敗", "dev-done": "待前測", "baseline": "基準"}
LEVEL_ZH = {"improvement": "改進", "standalone": "單獨", "validation": "驗證", "both": "改進 + 單獨"}

COLUMNS = [  # header, width, what to fill, required
    ("ID", 10, "自己的前綴 + 流水號，例如 MK-001；Dino 的實驗沿用 EXP-NNN", "必填"),
    ("名稱 / 版本", 14, "版本名或短名稱，例如 v6.75、v3", "必填"),
    ("負責人", 12, "下拉選單；新成員先加到「清單」分頁", "必填"),
    ("日期", 11, "開始或登記日期，YYYY-MM-DD", "必填"),
    ("改動說明", 46, "一句話：改了什麼、什麼時候觸發", "必填"),
    ("基於版本", 14, "在哪個版本上改，例如 spec v1、v2、v6.75", "必填"),
    ("狀態", 11, "下拉選單；狀態變了就改同一列，不新增一列", "必填"),
    ("判定規則", 14, "下拉選單：用什麼方式判定通過", "選填"),
    ("結果摘要", 40, "勝幾池、增益多少、輸在哪裡", "選填"),
    ("CAGR", 9, "小數，0.15 會顯示 15.0%", "選填"),
    ("最大回撤", 9, "負的小數，-0.23 會顯示 -23.0%", "選填"),
    ("數字口徑", 30, "CAGR / 回撤用哪個池、哪段期間、哪個基準", "有數字時必填"),
    ("Jira", 11, "票號，例如 QUAN-1044", "選填"),
    ("研究成果連結", 40, "一個網址：HTML 報告、artifact、GitHub 文件、Google 文件", "選填"),
    ("其他 / 備註", 30, "任何補充：成功等級、注意事項、相關實驗", "選填"),
]

PLAIN_ZH = {
    1: "現貨趨勢倉：F × 資產的一半改持現貨 ETH",
    2: "現貨倉加 0.80 移動停損",
    3: "現貨倉的停損高點在重建後保留",
    4: "閒置 USDC 賺 Aave 存款利率",
    5: "回補改用只放 USDC 的區間掛單，不用市價買",
    6: "半邊梯子：ETH 那半邊持現貨，只有 USDC 那半邊做 LP",
    7: "只在 EMA100 一階、二階差分都 > 0 時用半邊梯子",
    8: "ETH 與 BTC 各半的 v6 組合",
    9: "v6.1 現貨倉改用 Calmar 規則重新判定",
    10: "v6.6 半邊梯子改用 Calmar 規則重新判定",
    11: "v6 與 v6.4 在 Base cbBTC 池驗證（上線條件 5）",
    12: "手續費 vs LVR 閘門：7 日每單位流動性手續費 < LVR 時 F = 0",
    13: "趨勢偏移區間：谷型往 EMA100 趨勢方向偏 5 pt",
    14: "部分永續對沖：在 Binance 空梯子 ETH delta 的 60%",
    15: "v6 跑 Base WETH/USDC 0.3%，並估算 0.05% / 0.3% 輪換",
    16: "毒性暫停：5 分鐘內波動 1% 後撤梯子 30 分鐘",
    17: "v6.13 毒性暫停改用 Calmar 規則在 Base 重新判定",
    18: "熊市空單：F = 0、低於所有 EMA 且 12 個月報酬 < 0 時，空 0.5 × 資產的永續",
    19: "熊市空單加閒置資金收益（v6.14 + v6.4）",
    20: "熊市空單，但 2 sigma 暴跌日不進場；無閒置收益",
    21: "v6.16 在 LINK/WETH、UNI/WETH 新池重新判定",
    22: "LP 手續費再投入梯子（複利），不領出",
    23: "價格到建倉價 +10% 就重新置中，不等到 +20% 邊緣",
    24: "趨勢線改用 n 日 Donchian 通道中線",
    25: "趨勢線改用 Hull MA(n)",
    26: "趨勢判斷改用 n 日報酬 > 0（時間序列動能）",
    27: "趨勢線改用 Supertrend（ATR(n) × 3）",
    28: "F = 8 個帳戶平均（4 個 EMA、4 個 Donchian 中線）",
    29: "ETH 比例 s 隨收盤價高於幾條 EMA 而變",
    30: "梯子半寬 = 30 日 sigma × √30，限 10..30%",
    31: "帳戶只在收盤同時高於 EMA(n) 與 Donchian 中線時武裝",
    32: "Donchian 中線版本（v6.19）單獨判定",
    33: "EMA + Donchian 合成（v6.23）單獨判定",
    34: "波動率調寬（v6.25）單獨判定",
    35: "EMA / Donchian 共識（v6.26）單獨判定",
    36: "趨勢線改用 SMA(n)，n = 170/190/210/230",
    37: "趨勢線改用 Ichimoku 雲頂",
    38: "趨勢判斷改用 Aroon Up(n) > Aroon Down(n)",
    39: "趨勢判斷改用收盤價在 n 日高點 20% 以內",
    40: "Aroon 版本單獨判定為 BTC 池策略",
    41: "Ichimoku 版本單獨判定為 BTC 池策略",
    42: "SMA200 系列單獨判定為 BTC 池策略",
    43: "時間序列動能單獨判定為 BTC 池策略",
    44: "連續兩天的每日檢查都在梯子外，才算出區間",
    45: "F 每週讀一次（用週日的值）",
    46: "ETH 比例固定 50%（拿掉 EMA100 比例規則）",
    47: "F 不低於 25%（永遠保留一個回補階段）",
    48: "ETH 50% + 兩天確認出區間",
    49: "ETH 50% + 波動率調寬",
    50: "ETH 50% + EMA / Donchian 共識",
    51: "ETH 50% + 兩天確認 + 波動率調寬",
    165: "梯子半寬 = ETH DVOL 一個月預期波動（10..30%）",
    166: "梯子半寬 = 0.10 + 0.40 × ER30（效率比，10..30%）",
    167: "梯子半寬 = 0.10 + 0.20 × F（10..30%）",
    168: "回補期間（0 < F < 1）梯子下緣設在回補低點",
    169: "EXP-168 的下緣 + v6.75",
    170: "EXP-168 的下緣 + ETH 50%",
    171: "EXP-168 的下緣 + 取消引擎下緣停損",
    172: "EXP-168 的下緣 + v6.75 + ETH 50%",
    173: "v6.75 + F = 1 時上緣延到 +40%",
    174: "v6.75 + F = 1 時上緣 +40% + 回補期間下緣在回補低點",
    175: "費率分層：0.3% 池用 v6.75 + 回補低點下緣；較便宜的池只用 v6.75",
}

FONT = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
PASS_FILL = PatternFill("solid", fgColor="E2EFDA")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
LINK = Font(name=FONT, color="0563C1", underline="single")


def head_row(ws, row, values):
    for c, v in enumerate(values, 1):
        cell = ws.cell(row, c, v)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEAD_FILL
        cell.alignment = WRAP
        cell.border = BOX


def body_row(ws, row, values, fmt=None):
    for c, v in enumerate(values, 1):
        cell = ws.cell(row, c, v)
        cell.font = Font(name=FONT)
        cell.alignment = WRAP
        cell.border = BOX
        if fmt and c in fmt and v is not None:
            cell.number_format = fmt[c]


def link(cell, url, text=None):
    cell.value = text or url
    cell.hyperlink = url
    cell.font = LINK


def section(ws, row, text, width):
    ws.cell(row, 1, text).font = Font(name=FONT, bold=True, size=12)
    for c in range(1, width + 1):
        ws.cell(row, c).fill = SECTION_FILL


def note(ws, row, text):
    ws.cell(row, 1, text).font = Font(name=FONT, italic=True, color="595959")
    return row + 1


def owner_count(owner_ref, status=None):
    """Sum over every category sheet of rows owned by owner_ref (optionally with that status)."""
    st = "" if status is None else f",'{{s}}'!$G$2:$G${LAST_ROW},\"{status}\""
    return "+".join(f"COUNTIFS('{s}'!$C$2:$C${LAST_ROW},{owner_ref}{st.format(s=s)})" for s in SHEET.values())


def overview(ws):
    W = 8
    for col, w in zip("ABCDEFGH", (24, 40, 14, 14, 14, 14, 14, 46)):
        ws.column_dimensions[col].width = w
    ws["A1"] = "LP 策略研究總表：defense v1 / v2 / v3 與全部實驗（團隊共同維護）"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    r = note(ws, 2, "新增實驗前先看「填寫說明」分頁。本頁的計數都是公式，新增一列就會自動更新。初版 2026-10-12（QUAN-1108）。")

    r += 1
    section(ws, r, "1. 實驗分類（每類一個分頁）", W)
    r += 1
    head_row(ws, r, ["分頁", "改動 v6 的哪個部分", "試過", "通過", "進行中", "待前測", "", "目前結論"])
    first = r + 1
    cats = dict(CATEGORIES)
    cats["other"] = OTHER
    for key, (_, part) in cats.items():
        r += 1
        s = SHEET[key]
        st = f"'{s}'!$G$2:$G${LAST_ROW}"
        body_row(ws, r, [None, part, f"=COUNTA('{s}'!$A$2:$A${LAST_ROW})", f'=COUNTIF({st},"通過")',
                         f'=COUNTIF({st},"進行中")', f'=COUNTIF({st},"待前測")', "", LESSON[key]])
        link(ws.cell(r, 1), f"#'{s}'!A1", s)
    r += 1
    body_row(ws, r, ["合計", ""] + [f"=SUM({c}{first}:{c}{r - 1})" for c in "CDEF"] + ["", ""])
    for c in range(1, 7):
        ws.cell(r, c).font = Font(name=FONT, bold=True)
    r += 1
    r = note(ws, r, "Dino 的 EXP-001..175：EXP-052 之後通過的全部含 v6.75（回補日當天不能創盤中新低），LP 本體上達到改進等級的只有這一個發現。")

    r += 1
    section(ws, r, "2. 各負責人的實驗數", W)
    r += 1
    head_row(ws, r, ["負責人", "", "試過", "通過", "進行中", "", "", ""])
    for k in range(2, 2 + 8):
        r += 1
        ref = f"$A{r}"
        body_row(ws, r, [f'=IF(清單!$A{k}="","",清單!$A{k})', "",
                         f'=IF({ref}="","",{owner_count(ref)})',
                         f'=IF({ref}="","",{owner_count(ref, "通過")})',
                         f'=IF({ref}="","",{owner_count(ref, "進行中")})',
                         "", "", ""])

    r += 2
    section(ws, r, "3. Defense v1 / v2 / v3（Maker Su）：共同邏輯", W)
    r += 1
    for line in (
        "池子：ETH/USDC，谷型 LP（inverted gaussian），中心 ±20%，16 段。",
        "訊號：Binance ETHUSDT 日收盤，EMA 90/100/110/120 四個虛擬帳戶，各自撤出與分 4 階段回補；部署比例 F = 四帳戶平均。",
        "ETH 比例 s：收盤 > EMA100 時 70%，否則 50%。跌破下緣（−20%）撤出，突破上緣（+20%）重建。",
        "三版的差別只在下表的增改規則，屬於同一類策略。",
    ):
        ws.cell(r, 1, line).font = Font(name=FONT)
        r += 1

    r += 1
    section(ws, r, "4. 版本差異", W)
    r += 1
    head_row(ws, r, ["版本", "相對前一版的改動", "規格書", "程式", "程式位置", "", "", "備註"])
    for row in (
        ["v1", "規格書基準版。8+8 段、每段價格等寬 2.5%、規格書權重、swap 成本平價 0.1%。",
         "USDC/ETH gamma maker defence v1（Google Sheet）", "gamma_maker_defense_ethusdc_v1.py",
         "maker-defense", "", "", "Dino 實驗的基準（SPEC=v1），自 EXP-156 起"],
        ["v2", "回補階梯改為 +7.5 / 12.5 / 17.5 / 22.5%；F 改用虛擬 LP 價值比例；新增複利模式（每月 1 日把手續費加回 LP）。",
         "ETH-USDC MGL 規格書 v2", "gamma_maker_defense_ethusdc_v2.py", "maker-defense（ca675a1，10-06）",
         "", "", "程式預設改為池費 0.05% + 深度滑價"],
        ["v3", "v2 再加「均線乖離規則」：收盤 ≥ EMA100 × 1.40 時 LP 全部撤成 USDC；乖離縮回 +20% 以下才恢復一般規則。",
         "ETH-USDC Maker-Grade Liquidity 規格書 v3（新增均線乖離規則），Slack 10-06",
         "gamma_maker_defense_ethusdc_v3.py", "只在 Slack（10-12），尚未進 git", "", "",
         "ETH-cbBTC 不導入乖離規則（規格書第 0 節）"],
    ):
        r += 1
        body_row(ws, r, row)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)

    r += 2
    section(ws, r, "5. 逐年績效（每年 1/2 以 $100k 起算，各年不連續）", W)
    r += 1
    head_row(ws, r, ["系列", "2022", "2023", "2024", "2025", "四年平均", "", "口徑"])
    for name, a, b, c, d, src in (
        ["v1 程式（規格書設定）", 0.118, 0.404, 0.323, 0.163, "swap 平價 0.1%；Maker，Slack 2026-10-06"],
        ["v2 程式，標準模式", 0.207, 0.219, 0.195, 0.226, "池費 0.05% + 深度滑價；GAMMA_MAKER_DEFENSE_ETHUSDC_V2.md 6.0"],
        ["v2 規格書，標準模式", 0.151, 0.231, 0.252, 0.287, "規格書獎勵模型（年底資產 115.1 / 123.1 / 125.2 / 128.7 $k）"],
    ):
        r += 1
        body_row(ws, r, [name, a, b, c, d, f"=AVERAGE(B{r}:E{r})", "", src],
                 fmt={2: "0.0%", 3: "0.0%", 4: "0.0%", 5: "0.0%", 6: "0.0%"})
    r += 1
    r = note(ws, r, "v3 沒有逐年數字：規格書只給 2021-05-05..2026-08-31 連續期（見第 6 節），程式結果尚未公布。")

    r += 1
    section(ws, r, "6. 連續期績效", W)
    r += 1
    head_row(ws, r, ["系列", "期間", "期末資產（$k，起始 100）", "總報酬", "最大回撤", "", "", "口徑"])
    for name, period, end, dd, src in (
        ["v1 Google Sheet", "2022-01-02..2025-12-31", 183.5, -0.258, "APR 16.4%；Maker 回測，swap 0.1%、池費 0.05%"],
        ["v1 Dino 重現（EXP-156 的 A）", "2022-01-02..2025-12-31", 184.0, None, "CAGR 16.5%；v6_validate.py SPEC=v1"],
        ["v2 規格書，標準", "2021-05-05..2026-08-31", 186.2, -0.28, "規格書 v3 第 7 節，UTC 0 時判定"],
        ["v3 規格書，標準", "2021-05-05..2026-08-31", 231.9, -0.19, "原資 125.4 + 已領獎勵 106.5"],
        ["v2 規格書，複利", "2021-05-05..2026-08-31", 262.5, -0.36, "規格書 v3 第 7 節"],
        ["v3 規格書，複利", "2021-05-05..2026-08-31", 323.7, -0.24, "規格書 v3 第 7 節"],
        ["v2 規格書，24 種判定時間平均", "2021-05-05..2026-08-31", 142.8, -0.38, "判定時間偏移 UTC 0..23 時的平均"],
        ["v3 規格書，24 種判定時間平均", "2021-05-05..2026-08-31", 193.4, -0.23, "實際運作應預期接近此值（規格書）"],
        ["ETH 持有", "2021-05-05..2026-08-31", 70.0, -0.79, "規格書 v3 第 7 節"],
    ):
        r += 1
        body_row(ws, r, [name, period, end, f"=C{r}/100-1", dd, "", "", src], fmt={3: "0.0", 4: "0.0%", 5: "0.0%"})
    r += 1
    r = note(ws, r, "規格書數字來自作者的獎勵模型，不是 Demeter 分鐘資料回測；v2 程式與規格書逐年差 −6.1..+5.6 $k，主要差在手續費模型。")

    r += 1
    section(ws, r, "7. 目前最佳候選 vs v1：EXP-157（v6.75），全歷史 7 池", W)
    r += 1
    head_row(ws, r, ["池子", "起日", "v1 CAGR", "EXP-157 CAGR", "v1 最大回撤", "EXP-157 最大回撤", "CAGR 差", "結果"])
    first = r + 1
    for p in (
        ["ETH 主網 0.05% 0x88e6", "2021-05-06", 0.1355, 0.1509, -0.229, -0.235, "贏"],
        ["ETH 主網 0.3% 0x8ad5", "2021-05-06", 0.1378, 0.1586, -0.210, -0.217, "贏"],
        ["ETH Base 0.05% 0xd0b5", "2023-12-01", 0.1696, 0.1692, -0.347, -0.359, "輸（Calmar）"],
        ["ETH Arbitrum 0.05% 0xc696", "2023-06-09", 0.2688, 0.2656, -0.314, -0.325, "輸（Calmar）"],
        ["ETH Base 0.3% 0x6c56", "2025-01-01", 0.1648, 0.1704, -0.246, -0.246, "贏"],
        ["BTC 主網 WBTC 0.3% 0x99ac", "2021-11-02", 0.1043, 0.1049, -0.301, -0.302, "贏（雜訊內）"],
        ["BTC Base cbBTC 0.05% 0xfbb6", "2024-10-01", 0.2046, 0.2052, -0.167, -0.167, "贏（雜訊內）"],
    ):
        r += 1
        body_row(ws, r, p[:6] + [f"=D{r}-C{r}", p[6]],
                 fmt={3: "0.00%", 4: "0.00%", 5: "0.0%", 6: "0.0%", 7: "+0.00%;-0.00%"})
    r += 1
    body_row(ws, r, ["贏的池數", "", "", "", "", "", f'=COUNTIF(H{first}:H{r - 1},"贏*")', "7 池中"])
    r += 1
    note(ws, r, "來源：EXP-157-nolow-specv1.md（SPEC=v1，到 2026-09-17；Arbitrum 到 2025-07-23）。v2、v3 尚未在這 7 池上跑。")
    ws.freeze_panes = "A2"


def guide(ws):
    for col, w in zip("ABCD", (16, 60, 14, 50)):
        ws.column_dimensions[col].width = w
    ws["A1"] = "填寫說明"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    r = 3
    section(ws, r, "新增一個實驗", 4)
    for i, step in enumerate((
        "找出改動屬於哪個類別分頁（總覽第 1 節有每類的定義）；都不合就放「其他類別」。",
        "在該分頁最下面新增一列，黃底欄位必填。",
        "ID 用自己的前綴加流水號，例如 MK-001（Maker）、ST-001（Steven）；Dino 的實驗沿用 EXP-NNN。",
        "負責人、狀態、判定規則用下拉選單；新成員先加到「清單」分頁的負責人欄。",
        "研究成果連結貼一個網址：HTML 報告、artifact、GitHub 文件或 Google 文件都可以。",
        "狀態改變時更新同一列，不要新增一列；總覽的計數會自動更新。",
    ), 1):
        r += 1
        ws.cell(r, 1, f"步驟 {i}").font = Font(name=FONT, bold=True)
        ws.cell(r, 2, step).font = Font(name=FONT)
        ws.cell(r, 2).alignment = WRAP

    r += 2
    section(ws, r, "欄位說明（每個類別分頁都一樣）", 4)
    r += 1
    head_row(ws, r, ["欄位", "填什麼", "必填", ""])
    for name, _, what, req in COLUMNS:
        r += 1
        body_row(ws, r, [name, what, req, ""])
        if req == "必填":
            ws.cell(r, 1).fill = INPUT_FILL

    r += 2
    section(ws, r, "狀態的意思", 4)
    for s, d in (
        ("規劃中", "已寫好假設，還沒開始跑"), ("進行中", "正在回測"), ("通過", "達到預先登記的成功規則"),
        ("失敗", "沒達到成功規則"), ("開發期淘汰", "開發期就沒過，沒進入最終判定"), ("待前測", "回測通過，等前測窗口的資料"),
        ("撤回", "設定有誤或不再適用，結果不採用"), ("基準", "拿來比較的基準版本"),
    ):
        r += 1
        body_row(ws, r, [s, d, "", ""])

    r += 2
    section(ws, r, "範例列（不要複製到類別分頁；數字取自規格書 v3）", 4)
    r += 1
    example = ws.cell(r, 1, "以下欄位順序與類別分頁相同")
    example.font = Font(name=FONT, italic=True, color="595959")
    r += 1
    for (name, *_), value in zip(COLUMNS, (
        "MK-001", "v3", "Maker Su", "2026-10-06",
        "收盤 ≥ EMA100 × 1.40 時 LP 全部撤成 USDC；乖離縮回 +20% 以下才恢復一般規則", "v2", "待前測",
        "規格書模型", "標準模式 $186.2k → $231.9k；最大回撤 −28% → −19%", "", "-0.19",
        "規格書 v3，2021-05-05..2026-08-31，獎勵模型", "",
        "https://ewetechnology.slack.com/files/U0ATRJ0P5LK/F0C6K7RHRRD", "程式尚未進 git；尚未在 7 池測",
    )):
        body_row(ws, r, [name, value, "", ""])
        r += 1


def lists(ws):
    head_row(ws, 1, ["負責人", "狀態", "判定規則"])
    for i, v in enumerate(OWNERS, 2):
        ws.cell(i, 1, v).font = Font(name=FONT)
    for i, v in enumerate(STATUSES, 2):
        ws.cell(i, 2, v).font = Font(name=FONT)
    for i, v in enumerate(RULES, 2):
        ws.cell(i, 3, v).font = Font(name=FONT)
    for col in "ABC":
        ws.column_dimensions[col].width = 18
    ws["E1"] = "下拉選單的來源。新增選項時直接往下加（負責人最多 30 人，其他最多 20 項）。"
    ws["E1"].font = Font(name=FONT, italic=True, color="595959")


def category_sheet(ws, rows, reg, appendix):
    head_row(ws, 1, [c[0] for c in COLUMNS])
    for c, (name, *_, req) in enumerate(COLUMNS, 1):
        if req == "必填":
            ws.cell(1, c).value = f"{name} *"
    for i, x in enumerate(rows, 2):
        g = reg[x["exp"]]
        n = int(x["exp"][4:])
        v675 = x["has_v675"] == "1"
        era = "spec v1" if n >= 156 else "v6"
        base = f"v6.75（{era}）" if v675 and n not in (88, 157) else era
        summary = []
        if g["dev_median_gain_pts"]:
            summary.append(f"dev 中位數 {float(g['dev_median_gain_pts']):+.2f} pt，勝 {g['dev_wins']}")
        if g["holdout_wins"]:
            h = g["holdout_wins"]
            if g["holdout_median_gain_pts"]:
                h += f"，中位數 {float(g['holdout_median_gain_pts']):+.2f} pt"
            summary.append(h)
        cagr = float(g["eth_cont_cagr"]) if g["eth_cont_cagr"] else None
        dd = float(g["eth_cont_maxdd"]) if g["eth_cont_maxdd"] else None
        basis = ""
        if cagr is not None:
            basis = "ETH 0x88e6 連續 2022-01..2026-09，v6 基準" if n < 156 else "ETH 0x88e6，spec v1 基準；期間見文件"
        other = [f"成功等級：{LEVEL_ZH[g['level']]}"] if g.get("level") in LEVEL_ZH else []
        if v675:
            other.append("含 v6.75")
        body_row(ws, i, [
            x["exp"], x["version"] or x["exp"], "Dino Huang", datetime.date.fromisoformat(g["date"]),
            appendix.get(x["exp"]) or PLAIN_ZH[n], base, STATUS_MAP[x["status"]],
            "全歷史（多池）" if x["rule"] == "full-history" else "dev + holdout", "；".join(summary),
            cagr, dd, basis, None, None, "；".join(other),
        ], fmt={4: "yyyy-mm-dd", 10: "0.0%", 11: "0.0%"})
        if g["jira"]:
            link(ws.cell(i, 13), JIRA_URL + g["jira"], g["jira"])
        link(ws.cell(i, 14), DOC_URL + g["doc"], g["doc"])

    for c, (_, width, *_rest) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(c)].width = width
    for c in (4,):
        for r in range(len(rows) + 2, LAST_ROW + 1):
            ws.cell(r, c).number_format = "yyyy-mm-dd"
    for c in (10, 11):
        for r in range(len(rows) + 2, LAST_ROW + 1):
            ws.cell(r, c).number_format = "0.0%"

    for col, src in (("C", "$A$2:$A$31"), ("G", "$B$2:$B$21"), ("H", "$C$2:$C$21")):
        dv = DataValidation(type="list", formula1=f"=清單!{src}", allow_blank=True)
        dv.add(f"{col}2:{col}{LAST_ROW}")
        ws.add_data_validation(dv)
    ws.conditional_formatting.add(f"A2:O{LAST_ROW}", FormulaRule(formula=['$G2="通過"'], fill=PASS_FILL))
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:O{LAST_ROW}"


def main(out):
    rows = list(csv.DictReader(open(HERE / "TAXONOMY.csv")))
    reg = {r["id"]: r for r in csv.DictReader(open(HERE / "registry.csv"))}
    appendix = {r["exp"]: r["plain_zh"] for r in
                csv.DictReader(open(HERE / "media/2026-10-07-weekly/appendix_versions.csv")) if r["plain_zh"]}
    missing = [x["exp"] for x in rows if x["exp"] not in appendix and int(x["exp"][4:]) not in PLAIN_ZH]
    assert not missing, missing

    wb = Workbook()
    wb.active.title = "總覽"
    overview(wb.active)
    guide(wb.create_sheet("填寫說明"))
    for key, name in SHEET.items():
        category_sheet(wb.create_sheet(name), [x for x in rows if x["category"] == key], reg, appendix)
    lists(wb.create_sheet("清單"))
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
