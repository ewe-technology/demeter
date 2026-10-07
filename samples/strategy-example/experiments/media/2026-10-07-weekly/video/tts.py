"""Generate one edge-tts mp3 per narration line (cached) and write timings.json.

Usage: python tts.py <out_dir>
Voice comes from narration.json ("voice", engine "edge-tts"; no API key).
A clip that already exists is reused, so reruns only synthesize new or changed
lines (delete a clip to force it). Clip names carry a hash of the text.
"""
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
NARRATION = HERE.parent / "narration.json"
LINE_GAP = 0.5    # pause between lines (s)
SCENE_HEAD = 0.4  # silence before the first line of a scene (s)
FIRST_HEAD = 2.5  # the first scene opens on a silent title card (s)
SCENE_TAIL = 1.0  # silence after the last line of a scene (s)
RATE = "-10%"     # edge-tts speaking rate (default voice speed gives only ~4:45 total)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def synth(text, voice, path, tries=4):
    for k in range(tries):
        try:
            tmp = path.with_suffix(".part")
            asyncio.run(edge_tts.Communicate(text, voice, rate=RATE).save(str(tmp)))
            if tmp.stat().st_size < 1000:
                raise RuntimeError("empty audio")
            tmp.rename(path)
            return
        except Exception as e:  # network hiccups
            if k == tries - 1:
                raise
            print(f"retry {path.name}: {e}")
            time.sleep(2 * (k + 1))


def main():
    out_dir = Path(sys.argv[1])
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    nar = json.loads(NARRATION.read_text())
    voice = nar["voice"]
    made = 0
    timings = {"scenes": []}
    for k, scene in enumerate(nar["scenes"]):
        t = FIRST_HEAD if k == 0 else SCENE_HEAD
        lines = []
        for i, text in enumerate(scene["lines"]):
            h = hashlib.sha1(f"{voice}|{RATE}|{text}".encode()).hexdigest()[:8]
            mp3 = audio_dir / f"{scene['id']}_{i:02d}_{h}.mp3"
            if not mp3.exists():
                synth(text, voice, mp3)
                made += 1
                print(f"generated {mp3.name}")
            d = duration(mp3)
            lines.append({"text": text, "audio": str(mp3.resolve()),
                          "start": round(t, 3), "dur": round(d, 3)})
            t += d + (LINE_GAP if i < len(scene["lines"]) - 1 else 0)
        timings["scenes"].append({"id": scene["id"], "lines": lines,
                                  "total": round(t + SCENE_TAIL, 3)})
    (out_dir / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=1))
    n = sum(len(s["lines"]) for s in timings["scenes"])
    speech = sum(l["dur"] for s in timings["scenes"] for l in s["lines"])
    grand = sum(s["total"] for s in timings["scenes"])
    print(f"{n} clips ({made} new), speech {speech:.1f}s, total runtime {grand:.1f}s")


if __name__ == "__main__":
    main()
