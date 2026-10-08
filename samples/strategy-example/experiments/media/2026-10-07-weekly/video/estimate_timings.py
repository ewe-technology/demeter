"""Write estimated_timings.json (no audio) with the same layout as tts.py's timings.json.

Usage: python estimate_timings.py <out_dir>
Each line lasts SEC_PER_CHAR * len(text); gaps match tts.py.
"""
import json
import sys
from pathlib import Path

from tts import FIRST_HEAD, LINE_GAP, NARRATION, SCENE_HEAD, SCENE_TAIL, min_slot

SEC_PER_CHAR = 0.2


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    nar = json.loads(NARRATION.read_text())
    timings = {"scenes": []}
    for k, scene in enumerate(nar["scenes"]):
        t = FIRST_HEAD if k == 0 else SCENE_HEAD
        lines = []
        for i, text in enumerate(scene["lines"]):
            d = SEC_PER_CHAR * len(text)
            lines.append({"text": text, "audio": None, "start": round(t, 3), "dur": round(d, 3)})
            last = i == len(scene["lines"]) - 1
            t += max(d + (0 if last else LINE_GAP), min_slot(scene["id"], i))
        timings["scenes"].append({"id": scene["id"], "lines": lines, "total": round(t + SCENE_TAIL, 3)})
    (out_dir / "estimated_timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=1))
    print(f"estimated runtime {sum(s['total'] for s in timings['scenes']):.1f}s")


if __name__ == "__main__":
    main()
