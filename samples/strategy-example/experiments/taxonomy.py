"""Classify every experiment by the part of v6 it changes.

Writes experiments/TAXONOMY.csv (one row per EXP-001..) and prints a count per category.
EXP-052..164 keep the category of the 2026-10-07 weekly deck appendix (media/2026-10-07-weekly/
appendix_versions.csv); the rest are assigned in MANUAL below. A combination is filed under the rule
it adds last (EXP-048..051 add to EXP-046's 50% share; EXP-169..174 build on EXP-168's width).

    python experiments/taxonomy.py
"""
import collections
import csv
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent

# category key -> (Chinese label, the part of v6 it changes)
CATEGORIES = {
    "signal": ("訊號線", "把 EMA 換成別的趨勢線（Donchian、SMA、Aroon、Ichimoku…）"),
    "f_engine": ("F 引擎", "四帳戶怎麼算出部署比例 F、多久讀一次、下限"),
    "exit_stop": ("撤出 / 停損", "什麼時候把 LP 撤回 USDC"),
    "refill": ("回補", "撤出後分階段買回的條件"),
    "rebuild": ("重建時機", "什麼時候重建區間、重心放哪裡"),
    "width": ("區間寬度與形狀", "±20% 谷型的寬度、偏移、半邊梯子"),
    "share": ("ETH 比例 s", "LP 裡 ETH 佔 70% / 50% 的規則"),
    "macro": ("總經事件", "CPI / FOMC 等事件前後撤出或恢復"),
    "fee_tier": ("費率分層組合", "0.3% 池與 0.05% 池各用一組規則"),
    "routing": ("換匯路由", "重建時的 swap 走哪個池"),
    "non_lp": ("非 LP 本體", "現貨、永續空單、閒置資金收益（依規則不算改進）"),
    "validation": ("驗證 / 移植", "換池子、換基準、組合，不改策略"),
}

APPENDIX_RENAME = {"ladder": "width", "idle": "non_lp", "baseline": "validation"}

MANUAL = {
    "non_lp": [1, 2, 3, 4, 9, 14, 18, 19, 20, 21],
    "validation": [8, 11, 15],
    "refill": [5],
    "width": [6, 7, 10, 13, 30, 34, 49, 51] + list(range(165, 175)),
    "f_engine": [12, 22, 28, 45, 47],
    "exit_stop": [16, 17, 44, 48],
    "rebuild": [23],
    "signal": [24, 25, 26, 27, 31, 32, 33, 35, 36, 37, 38, 39, 40, 41, 42, 43, 50],
    "share": [29, 46],
    "fee_tier": [175],
}

PASSED = {"holdout-pass", "pass"}


def main():
    appendix = HERE / "media/2026-10-07-weekly/appendix_versions.csv"
    cat = {r["exp"]: APPENDIX_RENAME.get(r["category"], r["category"]) for r in csv.DictReader(open(appendix))}
    for key, nums in MANUAL.items():
        for n in nums:
            exp = f"EXP-{n:03d}"
            assert exp not in cat, exp
            cat[exp] = key

    rows = []
    for r in csv.DictReader(open(HERE / "registry.csv")):
        if r["id"] == "EXP-000":
            continue
        assert r["id"] in cat, f"{r['id']} has no category"
        version = re.search(r"\((v6\.[0-9a-z]+)\)", r["name"])
        rows.append({
            "exp": r["id"],
            "version": version.group(1) if version else "",
            "category": cat[r["id"]],
            "category_zh": CATEGORIES[cat[r["id"]]][0],
            "status": r["status"],
            "passed": int(r["status"] in PASSED),
            # EXP-153 on: full-history rule; before: dev + holdout windows
            "rule": "full-history" if int(r["id"][4:]) >= 153 else "dev+holdout",
            "has_v675": int(r["id"] in ("EXP-088", "EXP-157") or "v6.75" in r["name"] or "no-new-low" in r["name"]),
            "name": r["name"],
        })

    with open(HERE / "TAXONOMY.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    n = collections.Counter(r["category"] for r in rows)
    p = collections.Counter(r["category"] for r in rows if r["passed"])
    q = collections.Counter(r["category"] for r in rows if r["passed"] and not r["has_v675"])
    print(f"{len(rows)} experiments")
    for key, (zh, _) in CATEGORIES.items():
        print(f"{key:11s} {zh:10s} {n[key]:3d} tried {p[key]:3d} passed {q[key]:3d} without v6.75")


if __name__ == "__main__":
    main()
