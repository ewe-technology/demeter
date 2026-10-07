"""Concatenate the rendered scene videos and lay the narration clips on the same clock.

Usage: python assemble.py <timings.json> <scene_video_dir> <out.mp4> [<thumb.png> <thumb_time_s>]

Scene k's audio offset is the sum of the *rendered* durations of scenes 0..k-1
(ffprobe), so frame rounding never accumulates into A/V drift. Lines whose
`audio` is null (estimated timings) are skipped; with no clips at all the
output gets a silent AAC track.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path



def scene_class(sid):
    """Scene id -> Manim class name in weekly.py (s03b_edge -> S03B)."""
    return sid.split("_")[0].upper()


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    timings = json.loads(Path(sys.argv[1]).read_text())
    vdir, out = Path(sys.argv[2]), Path(sys.argv[3])
    names = [scene_class(sc["id"]) for sc in timings["scenes"]]
    vids = [vdir / f"{n}.mp4" for n in names]
    durs = [probe(v) for v in vids]
    total = sum(durs)
    tmp = Path(tempfile.mkdtemp(prefix="v6weekly_"))

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{v}'\n" for v in vids))
    video = tmp / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])

    clips, offset = [], 0.0
    for sc, d, sid in zip(timings["scenes"], durs, names):
        for ln in sc["lines"]:
            if ln.get("audio"):
                clips.append((ln["audio"], offset + ln["start"]))
        if abs(d - sc["total"]) > 0.1:
            print(f"warning: {sid} rendered {d:.2f}s, timings say {sc['total']:.2f}s")
        offset += d

    audio = tmp / "audio.m4a"
    if clips:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        for path, _ in clips:
            cmd += ["-i", path]
        parts = [f"[{i + 1}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={int(t * 1000)}:all=1[a{i}]"
                 for i, (_, t) in enumerate(clips)]
        mix = "[0:a]" + "".join(f"[a{i}]" for i in range(len(clips)))
        parts.append(f"{mix}amix=inputs={len(clips) + 1}:normalize=0:duration=first[out]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(audio)]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
               "-c:a", "aac", "-b:a", "128k", str(audio)]
    run(cmd)

    run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-c:a", "copy", "-movflags", "+faststart",
         "-t", f"{total:.3f}", str(out)])
    print(f"{out}: {probe(out):.2f}s, {len(clips)} narration clips")

    if len(sys.argv) > 5:
        run(["ffmpeg", "-y", "-ss", sys.argv[5], "-i", str(out), "-frames:v", "1", sys.argv[4]])
        print(f"thumbnail {sys.argv[4]}")


if __name__ == "__main__":
    main()
