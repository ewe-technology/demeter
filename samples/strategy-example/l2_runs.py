"""
QUAN-1216 L2 decision test (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md, L2): reruns one L0 window through l6_runs.py once
per shift of the pre-registered grid (L2_SHIFT) or per draw of the shuffle (L2_SHUFFLE). Each run's full result folder (v3.2:
513 MB) is reduced to one file per reinvest mode, <out>/shift_<k>_<mode>.csv (daily net value and the run's rebuild count), then
deleted. A k whose two files exist is skipped, so a stopped batch resumes. ../real-data must hold the pools as for L0. In a
worktree, result/ must be a symlink to the main checkout's result/, or the results go when the worktree goes.

Usage, from samples/strategy-example with the Rust venv's python (each run starts two workers, so 3 parallel runs = 6 workers,
the machine's cap; run one invocation at a time):
    python l2_runs.py v32|v22mainnet|v22base [parallel runs, default 3] [shift|shuffle, default shift]
"""
import glob
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from strategy_layers import L2_DRAWS, daily_net_value, l2_grid, rebuild_count

WINDOWS = {"v32": (date(2021, 5, 6), date(2026, 8, 31)), "v22mainnet": (date(2021, 11, 2), date(2026, 8, 31)),
           "v22base": (date(2024, 9, 14), date(2026, 8, 31))}
FOLDER_PREFIX = {"v32": "gamma-maker-defense-ethusdc-v3.2", "v22mainnet": "mainnet-ethbtc", "v22base": "base-ethbtc"}
MODES = ("reinvest", "noreinvest")
METHODS = {"shift": ("L2_SHIFT", "l2s", Path("result/quan1216_l2")), "shuffle": ("L2_SHUFFLE", "l2d", Path("result/quan1216_l2_shuffle"))}


def run_one(which: str, method: str, k: int) -> bool:
    """One rerun; False when its files already exist."""
    switch, tag, root = METHODS[method]
    out = root / which
    if all((out / f"shift_{k}_{m}.csv").exists() for m in MODES):
        return False
    done = subprocess.run([sys.executable, "l6_runs.py", which], env={**os.environ, switch: str(k)},
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    folders = glob.glob(f"result/{FOLDER_PREFIX[which]}*-{tag}{k}-*")
    if done.returncode or len(folders) != 1:
        raise RuntimeError(f"{which} {method} {k}: exit {done.returncode}, folders {folders}\n{done.stderr[-2000:]}")
    for m in MODES:
        partial = out / f"partial_{k}_{m}.csv"
        (daily_net_value(folders[0], m).rename("net_value").rename_axis("timestamp").to_frame()
         .assign(rebuilds=rebuild_count(folders[0], m)).to_csv(partial))
        partial.replace(out / f"shift_{k}_{m}.csv")
    shutil.rmtree(folders[0])
    if which == "v32":   # v3.2 also writes its signal outside the run folder
        for f in glob.glob(f"result/signal_daily_v3.2_bn_{tag}{k}_*.csv"):
            os.remove(f)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in WINDOWS:
        sys.exit(__doc__)
    if any(os.environ.get(v) for v in ("L6_EMA_SHIFT", "L6_WIDTH", "L2_SHIFT", "L2_SHUFFLE")):
        sys.exit("an L6 or L2 switch in the environment would change every run of the batch")
    which, parallel = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3
    method = sys.argv[3] if len(sys.argv) > 3 else "shift"
    (METHODS[method][2] / which).mkdir(parents=True, exist_ok=True)
    start, end = WINDOWS[which]
    ks = l2_grid((end - start).days + 1) if method == "shift" else list(range(1, L2_DRAWS + 1))
    print(f"{which} {method}: {len(ks)} runs, {ks[0]}..{ks[-1]}", flush=True)
    with ThreadPoolExecutor(parallel) as pool:
        for i, (k, ran) in enumerate(zip(ks, pool.map(lambda k: run_one(which, method, k), ks))):
            print(f"{i + 1}/{len(ks)} {k}: {'done' if ran else 'skipped'}", flush=True)
