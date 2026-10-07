# v6 weekly 2026-10-07: explainer video

The video is made with Manim (3b1b style) and an edge-tts voice-over (`zh-TW-YunJheNeural`, rate −10%). The script is
`../narration.json`: 11 scenes, and each scene's `lines` are both the narration and the burned-in subtitles. The chart
in s08 is drawn from `../curve_eth_mainnet.json`.

## Files

| file | role |
|---|---|
| `tts.py` | Makes one mp3 per narration line (cached by a hash of voice, rate and text). It measures each clip with ffprobe and writes `timings.json` (per-line `start` / `dur`, per-scene `total`). Gaps: 2.5 s title card before s01, 0.4 s at the start of each scene, 0.5 s between lines, 1.0 s at the end of each scene. |
| `estimate_timings.py` | Writes `estimated_timings.json` in the same format, at 0.2 s per character and with no audio. Use it to check the layout without generating speech. |
| `weekly.py` | Scenes `S01`..`S11`. `$V6_TIMINGS` names the timings file. Each narration line is one beat: its subtitle is on screen from `start` to `start+dur`, and the beat's animations are fitted into that window. Scenes render without sound. |
| `assemble.py` | Joins the scene mp4s and places every clip at (rendered length of the earlier scenes + `start`), so A/V drift cannot build up. It then muxes to H.264/yuv420p + AAC and exports a thumbnail. |
| `build.sh` | Runs the whole pipeline. |

## Rebuild

```bash
OUT=/Users/dinohuang/.claude/jobs/fb05b408/tmp/video          # venv, audio, media (override with V6_VIDEO_OUT)
uv venv -p 3.12 $OUT/.venv && uv pip install -p $OUT/.venv/bin/python manim requests edge-tts
./build.sh real high      # final: ~/Desktop/v6-weekly-2026-10-07.mp4 + .png (1920x1080, 30 fps)
./build.sh real low       # 480p15 smoke test with audio -> $OUT/v6-weekly-real-low.mp4
./build.sh est low        # silent layout check with estimated timings
./build.sh real high S05  # re-render one scene, then reassemble
```

Requirements: Homebrew cairo / pango / pkgconf (for manimpango), ffmpeg, the PingFang TC font (macOS). There is no
LaTeX, so the scenes use `Text` only (no `Tex` / `MathTex` / `DecimalNumber`). If you edit a narration line, only that
clip is generated again. The scenes follow the new timings automatically.
