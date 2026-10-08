"""Appendix slides: every version of EXP-052..164 grouped by the deck's 9 categories.

Reads appendix_versions.csv (exp, version, category, status, label_zh) and writes
deck/project/slides/appx<N>.html, two tables of ROWS rows per slide. Prints the slide ids.
"""
import csv
import html
from pathlib import Path

HERE = Path(__file__).parent
SLIDES = HERE / "deck/project/slides"
ROWS = 13  # rows per column under the header row

CATS = [("fee_tier", "fee-tier 分組"), ("refill", "refill 時機"), ("f_engine", "F 引擎結構"),
        ("rebuild", "rebuild／置中"), ("exit_stop", "exit／stop"), ("macro", "macro 事件"),
        ("ladder", "ladder 形狀"), ("routing", "swap routing"), ("idle", "閒置資金"),
        ("baseline", "基準重跑")]
STATUS = {"dropped-at-dev": ("dev 淘汰", "#5B6B7C"), "holdout-pass": ("holdout 通過", "#2B5BB8"),
          "holdout-fail": ("holdout 失敗", "#B5601F"), "pass": ("全歷史通過", "#2B5BB8"),
          "fail": ("全歷史失敗", "#B5601F"), "dev-done": ("待判", "#5B6B7C")}

rows = list(csv.DictReader(open(HERE / "appendix_versions.csv", encoding="utf-8")))
by_cat = {k: [r for r in rows if r["category"] == k] for k, _ in CATS}
assert sum(len(v) for v in by_cat.values()) == len(rows) == 112, len(rows)

lines = []  # each: ("cat", name, n) or ("row", r)
for key, name in CATS:
    lines.append(("cat", name, len(by_cat[key])))
    lines += [("row", r) for r in by_cat[key]]

cols = [lines[i:i + ROWS] for i in range(0, len(lines), ROWS)]
pages = [cols[i:i + 2] for i in range(0, len(cols), 2)]

def table(col):
    out = ['<table style="width:816px;font-size:24px;color:#16202B;padding:4px 8px">',
           '<tr><th style="width:10%;text-align:left">EXP</th><th style="width:13%;text-align:left">版本</th>'
           '<th style="width:58%;text-align:left">改了什麼</th><th style="width:19%;text-align:left">結果</th></tr>']
    for item in col:
        if item[0] == "cat":
            out.append(f'<tr style="background:#E3EBF8"><td></td><td></td><td>{html.escape(item[1])} · {item[2]} 個</td><td></td></tr>')
        else:
            r = item[1]
            label, color = STATUS[r["status"]]
            out.append(f'<tr><td>{r["exp"].replace("EXP-", "")}</td><td>{html.escape(r["version"])}</td>'
                       f'<td>{html.escape(r["label_zh"])}</td><td style="color:{color}">{label}</td></tr>')
    out.append("</table>")
    return "\n".join(out)


ids = []
for n, page in enumerate(pages, 1):
    sid = f"appx{n}"
    ids.append(sid)
    keys = {item[1]["category"] for col in page for item in col if item[0] == "row"}
    cat_name = "、".join(name for k, name in CATS if k in keys)
    body = "\n".join(table(c) for c in page)
    note = "EXP-052..164（EXP-155 撤回）。高費＝0.3% 池、低費＝0.05% 池；「v6.xx＋」＝在該版本上再改。「通過」在 EXP-152 以前指 holdout，之後指 7 池全歷史。"
    (SLIDES / f"{sid}.html").write_text(
        f'<section id="{sid}" data-transition="fade" style="background:#F4F1EA;color:#16202B;font-family:\'Noto Sans TC\', Arial, sans-serif;padding:128px 128px 160px;display:flex;flex-direction:column;gap:24px">\n'
        f'<h2 style="font-size:52px;font-weight:700">附錄 {n}/{len(pages)}：{html.escape(cat_name)}</h2>\n'
        f'<div style="display:flex;gap:32px;align-items:start">\n{body}\n</div>\n'
        f'<p style="position:absolute;left:128px;bottom:64px;width:1664px;font-size:24px;color:#5B6B7C">{note}</p>\n'
        f'<aside>附錄 {n}：本週每個版本改了什麼、結果如何，依 9 類排列。來源：registry.csv 與各 EXP 檔。</aside>\n'
        '</section>\n', encoding="utf-8")
print(" ".join(ids))
