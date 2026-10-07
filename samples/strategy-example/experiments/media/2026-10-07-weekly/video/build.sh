#!/usr/bin/env bash
# Build the v6 weekly explainer.
#   ./build.sh real high   # edge-tts clips (cached) + 1080p30 final -> Desktop mp4 + png
#   ./build.sh est low     # estimated timings, silent, 480p15 smoke test (no API calls)
# Optional 3rd arg: a single scene to (re)render, e.g. S05 (assembly still uses all 11).
set -euo pipefail
MODE=${1:-real}
QUAL=${2:-high}
ONLY=${3:-}
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=${V6_VIDEO_OUT:-/Users/dinohuang/.claude/jobs/fb05b408/tmp/video}
PY="$OUT/.venv/bin/python"

if [ "$MODE" = real ]; then
  "$PY" "$HERE/tts.py" "$OUT"
  TIM="$OUT/timings.json"
else
  "$PY" "$HERE/estimate_timings.py" "$OUT"
  TIM="$OUT/estimated_timings.json"
fi

if [ "$QUAL" = high ]; then
  FLAGS=(--resolution 1920,1080 --frame_rate 30); RES=1080p30
else
  FLAGS=(-ql); RES=480p15
fi

MEDIA="$OUT/media-$MODE"
for S in S01 S02 S03 S04 S05 S06 S07 S08 S09 S10 S11; do
  if [ -n "$ONLY" ] && [ "$S" != "$ONLY" ]; then continue; fi
  V6_TIMINGS="$TIM" "$PY" -m manim render "${FLAGS[@]}" --disable_caching --media_dir "$MEDIA" \
    -o "$S.mp4" "$HERE/weekly.py" "$S" >"$OUT/render-$S.log" 2>&1 || { tail -30 "$OUT/render-$S.log"; exit 1; }
  echo "rendered $S"
done

VDIR="$MEDIA/videos/weekly/$RES"
if [ "$MODE" = real ] && [ "$QUAL" = high ]; then
  "$PY" "$HERE/assemble.py" "$TIM" "$VDIR" /Users/dinohuang/Desktop/v6-weekly-2026-10-07.mp4 \
    /Users/dinohuang/Desktop/v6-weekly-2026-10-07.png 2.2
else
  "$PY" "$HERE/assemble.py" "$TIM" "$VDIR" "$OUT/v6-weekly-$MODE-$QUAL.mp4" "$OUT/thumb-$MODE-$QUAL.png" 2.2
fi
