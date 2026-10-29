"""
Rust engine vs python engine, two checks; both must match byte for byte:

1. engine_probe.py on both engines: every market operation on three pools, every value as its full Decimal text
   (catches a last-digit difference anywhere, even one a backtest's rounded CSVs would hide), with the
   fee_in_range_liquidity flag off and on;
2. short v6_validate runs: every result file (and the summary CSV except its `secs` column).

Run it after any change under rust/ or demeter/; the pre-commit hook (.githooks) runs it when a commit touches those
folders. Exit code 0 = engines equal, 1 = a difference, 2 = cannot run.

    python experiments/engine_check.py [--keep]      # from samples/strategy-example, any python; ~2 min

Python side: this checkout's demeter/ via PYTHONPATH with .venv-lab (this checkout's, else the main checkout's).
Rust side: this checkout's .venv-rs, whose `demeter` must be this checkout's rust/python/demeter.
Pool data: samples/real-data and samples/holdout-data (symlinked in a worktree).
"""
import filecmp
import os
import shutil
import subprocess
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SE = os.path.dirname(HERE)                       # samples/strategy-example
SAMPLES = os.path.dirname(SE)
ROOT = os.path.dirname(SAMPLES)
# (pool, start, end, grid, extra env): both quote sides, spec v1 and the old pool-price v6, a macro variant,
# partial removals (AR resize, AX tranches: python then holds a Decimal liquidity)
CASES = [
    ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "2022-05-01", "2022-06-30", "opt:A,GA,GD,AR,AX", {"SPEC": "v1"}),
    ("0x99ac8ca7087fa4a2a1fb6357269965a2014abc35", "2022-05-01", "2022-06-30", "opt:A,GA,AR", {"SPEC": "v1"}),
    ("0x4585fe77225b41b697c938b018e2ac67ac5a20c0", "2021-11-02", "2021-12-31", "opt:A", {"BINANCE_WARM": "1"}),
]
DATA_DIRS = {"0x88e6": "real-data", "0x99ac": "holdout-data", "0x4585": "holdout-data"}


def fail(msg: str, code: int = 2):
    print(f"engine_check: {msg}", file=sys.stderr)
    sys.exit(code)


def main_checkout() -> str:
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True).stdout
    return os.path.dirname(os.path.abspath(os.path.join(ROOT, common.strip())))


def pythons() -> tuple[str, str]:
    lab = next((p for p in (os.path.join(ROOT, ".venv-lab/bin/python"), os.path.join(main_checkout(), ".venv-lab/bin/python"))
                if os.path.exists(p)), None)
    rs = os.path.join(ROOT, ".venv-rs/bin/python")
    if lab is None:
        fail("no .venv-lab (python engine's packages); see CLAUDE.md Environment")
    if not os.path.exists(rs):
        fail(f"no {rs}; build the Rust engine (CLAUDE.md Environment)")
    where = subprocess.run([rs, "-I", "-c", "import demeter; print(demeter.__file__)"], capture_output=True, text=True).stdout.strip()
    if not where.startswith(os.path.join(ROOT, "rust", "python", "demeter")):
        fail(f".venv-rs imports {where or 'nothing'}, not this checkout's rust/python/demeter; rerun maturin develop --release")
    return lab, rs


def compare(a: str, b: str, tag: str) -> list[str]:
    diffs = [f for f in sorted(os.listdir(os.path.join(a, tag)))
             if not filecmp.cmp(os.path.join(a, tag, f), os.path.join(b, tag, f), shallow=False)]
    if sorted(os.listdir(os.path.join(a, tag))) != sorted(os.listdir(os.path.join(b, tag))):
        diffs.append("(file lists differ)")
    sa = pd.read_csv(os.path.join(a, tag + ".csv")).drop(columns="secs").set_index("variant").sort_index()
    sb = pd.read_csv(os.path.join(b, tag + ".csv")).drop(columns="secs").set_index("variant").sort_index()
    if not sa.astype(str).equals(sb.astype(str)):
        diffs.append(tag + ".csv")
    errors = [str(e) for s in (sa, sb) if "error" in s for e in s["error"].dropna()]
    if errors:   # equal errors on both engines would compare equal and prove nothing
        diffs.append("(a variant raised: " + "; ".join(errors)[:600] + ")")
    return diffs


def main():
    keep = "--keep" in sys.argv
    for pool, *_ in CASES:
        if not os.path.isdir(os.path.join(SAMPLES, DATA_DIRS[pool[:6]], pool)):
            fail(f"pool data missing: samples/{DATA_DIRS[pool[:6]]}/{pool} (symlink it from the main checkout)")
    lab, rs = pythons()
    dirs = {e: os.path.join(SAMPLES, f".engine-check-{e}") for e in ("py", "rs")}
    for d in dirs.values():
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    bad = 0
    t0 = time.time()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SPEC", "BINANCE_WARM", "ENGINE")}
    probe = os.path.join(HERE, "engine_probe.py")
    traces = {e: os.path.join(dirs[e], "probe.txt") for e in dirs}
    procs = {"py": subprocess.Popen([lab, probe, traces["py"]], cwd=dirs["py"], env={**env, "PYTHONPATH": ROOT},
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
             "rs": subprocess.Popen([rs, probe, traces["rs"]], cwd=dirs["rs"], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)}
    outs = {e: p.communicate()[0] for e, p in procs.items()}
    for e, p in procs.items():
        if p.returncode != 0:
            fail(f"{e} engine probe failed:\n{outs[e][-3000:]}")
    a, b = (open(traces[e]).read().splitlines() for e in ("py", "rs"))
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None if len(a) == len(b) else min(len(a), len(b)))
    bad += first is not None
    print(f"{'DIFF' if first is not None else 'same'}  engine_probe  {len(a)} values  ({time.time() - t0:.0f} s)"
          + (f"  first at line {first + 1}:\n  py {a[first] if first < len(a) else '<end>'}\n"
             f"  rs {b[first] if first < len(b) else '<end>'}" if first is not None else ""), flush=True)
    script = os.path.join(SE, "v6_validate.py")
    for pool, start, end, grid, extra in CASES:
        t0 = time.time()
        procs = {"py": subprocess.Popen([lab, script, pool, start, end, grid, "2"], cwd=dirs["py"],
                                        env={**env, **extra, "PYTHONPATH": ROOT, "ENGINE": "python"},
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
                 "rs": subprocess.Popen([rs, script, pool, start, end, grid, "2"], cwd=dirs["rs"], env={**env, **extra},
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)}
        outs = {e: p.communicate()[0] for e, p in procs.items()}
        for e, p in procs.items():
            if p.returncode != 0:
                fail(f"{e} engine run failed on {pool[:6]}:\n{outs[e][-3000:]}")
        tag = f"{pool[:6]}-{grid.replace(':', '-').replace(',', '')}{'-spec' + extra['SPEC'] if 'SPEC' in extra else ''}-{start}-{end}"
        diffs = compare(*(os.path.join(dirs[e], "result", "v6_validate") for e in ("py", "rs")), tag)
        bad += bool(diffs)
        print(f"{'DIFF' if diffs else 'same'}  {tag}  ({time.time() - t0:.0f} s){'  ' + ', '.join(diffs) if diffs else ''}",
              flush=True)
    if not keep:
        for d in dirs.values():
            shutil.rmtree(d, ignore_errors=True)
    print("engine_check: " + ("engines equal" if not bad else f"{bad} case(s) differ"
                              + ("" if keep else " (rerun with --keep to inspect samples/.engine-check-*)")))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
