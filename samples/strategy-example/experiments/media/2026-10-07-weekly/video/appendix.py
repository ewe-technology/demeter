"""Page plan for the appendix scene (s12), shared by tts.py (timing) and weekly.py (drawing).

Narration line k+1 of s12 introduces GROUPS[k]; a group is split into pages of at
most MAX_ROWS rows (balanced). Continuation pages have no narration line of their
own; they follow silently. Every page holds page_hold(rows) seconds.
"""
import csv
from pathlib import Path

CSV = Path(__file__).resolve().parent.parent / "appendix_versions.csv"
GROUPS = [["fee_tier"], ["refill"], ["f_engine"], ["rebuild"], ["exit_stop"], ["macro"],
          ["ladder"], ["routing"], ["idle", "baseline"]]
MAX_ROWS = 9


def load():
    return list(csv.DictReader(CSV.open(encoding="utf-8")))


def page_hold(n_rows):
    return max(4.0, 1.5 + 2.0 * n_rows)


def plan(rows=None):
    """[[page, ...] per group]; page = {"blocks": [(category, [row, ...])], "cont": bool, "rows": n}."""
    rows = rows if rows is not None else load()
    out = []
    for cats in GROUPS:
        blocks = [(c, [r for r in rows if r["category"] == c]) for c in cats]
        n = sum(len(b) for _, b in blocks)
        if len(cats) > 1 or n <= MAX_ROWS:
            out.append([{"blocks": blocks, "cont": False, "rows": n}])
            continue
        (cat, rs), = blocks
        k = -(-n // MAX_ROWS)
        sizes = [n // k + (1 if j < n % k else 0) for j in range(k)]
        pages, i = [], 0
        for j, s in enumerate(sizes):
            pages.append({"blocks": [(cat, rs[i:i + s])], "cont": j > 0, "rows": s})
            i += s
        out.append(pages)
    return out


def group_hold(k, rows=None):
    """Seconds from the start of narration line k+1 to the next beat."""
    return sum(page_hold(p["rows"]) for p in plan(rows)[k])
