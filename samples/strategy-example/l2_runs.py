"""
QUAN-1216 L2 decision test (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md, L2): reruns one L0 window through l6_runs.py once
per shift of the pre-registered grid, with L2_SHIFT set. Each run's full result folder (v3.2: 513 MB) is reduced to one file per
reinvest mode, <out>/shift_<k>_<mode>.csv (daily net value and the run's rebuild count), then deleted. A shift whose two files
exist is skipped, so a stopped batch resumes. ../real-data must hold the pools as for L0.

Usage, from samples/strategy-example (each run starts two workers, so 3 parallel runs = 6 workers, the machine's cap; run one
invocation at a time):
    python l2_runs.py v32|v22mainnet|v22base [parallel runs, default 3]
"""
import glob
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from strategy_layers import L2_GUARD, L2_MIN_SHIFTS, daily_net_value, rebuild_count, shift_grid

WINDOWS = {"v32": (date(2021, 5, 6), date(2026, 8, 31)), "v22mainnet": (date(2021, 11, 2), date(2026, 8, 31)),
           "v22base": (date(2024, 9, 14), date(2026, 8, 31))}
FOLDER_PREFIX = {"v32": "gamma-maker-defense-ethusdc-v3.2", "v22mainnet": "mainnet-ethbtc", "v22base": "base-ethbtc"}
MODES = ("reinvest", "noreinvest")
OUT = Path("result/quan1216_l2")


def grid(which: str) -> list[int]:
    """Every step days, the widest step that still gives at least L2_MIN_SHIFTS shifts."""
    start, end = WINDOWS[which]
    days = (end - start).days + 1
    return shift_grid(days, max(1, (days - 2 * L2_GUARD) // L2_MIN_SHIFTS))


def run_shift(which: str, k: int) -> bool:
    """One shifted run; False when its files already exist."""
    out = OUT / which
    if all((out / f"shift_{k}_{m}.csv").exists() for m in MODES):
        return False
    done = subprocess.run([sys.executable, "l6_runs.py", which], env={**os.environ, "L2_SHIFT": str(k)},
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    folders = glob.glob(f"result/{FOLDER_PREFIX[which]}*-l2s{k}-*")
    if done.returncode or len(folders) != 1:
        raise RuntimeError(f"{which} shift {k}: exit {done.returncode}, folders {folders}\n{done.stderr[-2000:]}")
    for m in MODES:
        partial = out / f"partial_{k}_{m}.csv"
        (daily_net_value(folders[0], m).rename("net_value").rename_axis("timestamp").to_frame()
         .assign(rebuilds=rebuild_count(folders[0], m)).to_csv(partial))
        partial.replace(out / f"shift_{k}_{m}.csv")
    shutil.rmtree(folders[0])
    if which == "v32":   # v3.2 also writes its signal outside the run folder
        for f in glob.glob(f"result/signal_daily_v3.2_bn_l2s{k}_*.csv"):
            os.remove(f)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in WINDOWS:
        sys.exit(__doc__)
    which, parallel = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3
    (OUT / which).mkdir(parents=True, exist_ok=True)
    shifts = grid(which)
    print(f"{which}: {len(shifts)} shifts, {shifts[0]}..{shifts[-1]}", flush=True)
    with ThreadPoolExecutor(parallel) as pool:
        for i, (k, ran) in enumerate(zip(shifts, pool.map(lambda k: run_shift(which, k), shifts))):
            print(f"{i + 1}/{len(shifts)} shift {k}: {'done' if ran else 'skipped'}", flush=True)
