"""
Backtests on feat/dino-v6-opt run on the Rust engine (rust/, Steven's port of demeter, byte-identical to the python
engine and ~10x faster: experiments/RUST-ENGINE-2026-10-14.md). `require_rust()` stops a backtest that would run on
the old python engine; `ENGINE=python` lets it through (engine_check.py does that for the python side of a comparison).
"""
import os
import sys

import demeter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUST = hasattr(demeter, "_rs")
ENGINE = "rust" if RUST else "python"

BUILD = f"""build the Rust engine once per checkout (first build ~4 min, later ~1 min):
    cd {ROOT}
    uv venv -p 3.12 .venv-rs && uv pip install -p .venv-rs/bin/python maturin -r samples/strategy-example/requirements-lab.txt
    cd rust && CARGO_TARGET_DIR=~/.cache/demeter-rs-target VIRTUAL_ENV={ROOT}/.venv-rs ../.venv-rs/bin/maturin develop --release
then run with {ROOT}/.venv-rs/bin/python and no PYTHONPATH pointing at the repo root."""


def require_rust(script: str) -> None:
    if not RUST:
        if os.environ.get("ENGINE") == "python":
            print(f"{script}: ENGINE=python, running on the python engine ({demeter.__file__})", file=sys.stderr)
            return
        sys.exit(f"{script}: this python imports the old python demeter ({demeter.__file__}).\n"
                 f"Backtests on this branch run on the Rust engine; set ENGINE=python only to compare engines.\n{BUILD}")
    own = os.path.join(ROOT, "rust", "python", "demeter")
    if not os.path.abspath(demeter.__file__).startswith(own):
        print(f"{script}: warning: the Rust engine comes from {os.path.dirname(demeter.__file__)}, not this checkout's "
              f"{own}; changes under this checkout's rust/ are not in it.\n{BUILD}", file=sys.stderr)
