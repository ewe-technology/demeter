"""
Compare outputs of the Rust engine (rust/golden/out_rs) with the python golden files (rust/golden/out).

    rust/.venv/bin/python rust/golden/compare.py [--tol 1e-18]

Numbers are compared as Decimal with a relative tolerance; text cells must match exactly.
"""

import argparse
import csv
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent


def num(s: str):
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def close(a: str, b: str, tol: Decimal) -> bool:
    if a == b:
        return True
    x, y = num(a), num(b)
    if x is None or y is None:
        return False
    if x.is_nan() and y.is_nan():
        return True
    scale = max(abs(x), abs(y))
    if scale == 0:
        return True
    return abs(x - y) / scale <= tol


def compare_csv(golden: Path, got: Path, tol: Decimal, skip_cols=()) -> list[str]:
    with open(golden) as f:
        g = list(csv.reader(f))
    with open(got) as f:
        r = list(csv.reader(f))
    errs = []
    if len(g) != len(r):
        errs.append(f"{golden.name}: {len(g)} rows vs {len(r)}")
    worst = (Decimal(0), None)
    for i, (gr, rr) in enumerate(zip(g, r)):
        if len(gr) != len(rr):
            errs.append(f"{golden.name}:{i}: {len(gr)} cols vs {len(rr)}")
            continue
        for j, (a, b) in enumerate(zip(gr, rr)):
            if j in skip_cols:
                continue
            if not close(a, b, tol):
                x, y = num(a), num(b)
                if x is not None and y is not None:
                    rel = abs(x - y) / max(abs(x), abs(y))
                    if rel > worst[0]:
                        worst = (rel, (i, j, a, b))
                if len(errs) < 10:
                    errs.append(f"{golden.name}:{i}:{j} {g[0][j] if j < len(g[0]) else ''}/{g[1][j] if len(g) > 1 and j < len(g[1]) else ''}: {a!r} vs {b!r}")
    if worst[1]:
        errs.append(f"{golden.name}: worst relative diff {worst[0]:.3e} at {worst[1]}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", default="1e-18")
    ap.add_argument("--golden", default=str(HERE / "out"))
    ap.add_argument("--got", default=str(HERE / "out_rs"))
    args = ap.parse_args()
    tol = Decimal(args.tol)
    gdir, rdir = Path(args.golden), Path(args.got)
    total = 0
    failed = 0
    for g in sorted(gdir.rglob("*.csv")):
        rel = g.relative_to(gdir)
        r = rdir / rel
        if not r.exists():
            continue
        total += 1
        errs = compare_csv(g, r, tol)
        status = "OK " if not errs else "DIFF"
        print(f"[{status}] {rel}")
        for e in errs:
            print("      ", e)
        failed += bool(errs)
    for g in sorted(gdir.rglob("actions_*.json")):
        r = rdir / g.relative_to(gdir)
        if not r.exists():
            continue
        total += 1
        ga, ra = json.load(open(g)), json.load(open(r))
        same = [(a["t"], a["type"]) for a in ga] == [(a["t"], a["type"]) for a in ra]
        print(f"[{'OK ' if same else 'DIFF'}] {g.relative_to(gdir)} ({len(ga)} vs {len(ra)} actions)")
        failed += not same
    print(f"\n{total - failed}/{total} files match (tolerance {tol})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
