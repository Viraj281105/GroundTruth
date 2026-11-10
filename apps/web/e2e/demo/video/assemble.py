"""Assembles the final MP4 from a take made by record.mjs.

Inputs (in the work directory): frames.txt (timestamped screencast frames), cues.json (when each
narrated sentence starts on screen), wav/<id>.wav (the rendered narration) and narration.json.

  python assemble.py <work dir> <output.mp4>

Output: 1920x1080, 30 fps, H.264 (High, yuv420p), AAC 48 kHz stereo, burned subtitles, plus the
.srt beside it. Music is synthesised here (a quiet sustained chord, no samples, no licence).
"""

import json
import subprocess
import sys
from pathlib import Path

work = Path(sys.argv[1])
out = Path(sys.argv[2])
cues = json.loads((work / "cues.json").read_text(encoding="utf-8"))
total = cues["duration"] + 0.6
items = cues["cues"]


def stamp(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap(sentence: str, width: int = 62) -> str:
    """Two balanced lines at most per cue part; long sentences become several cues."""
    words, lines, cur = sentence.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# Subtitles: each sentence is split into cues of at most two lines, timed in proportion to length,
# so the words on screen follow the words being spoken.
srt, n = [], 1
for c in items:
    lines = wrap(c["text"])
    chunks = [lines[i : i + 2] for i in range(0, len(lines), 2)]
    weights = [sum(len(x) for x in ch) for ch in chunks]
    span, t = c["dur"], c["start"]
    for ch, wt in zip(chunks, weights):
        d = span * wt / sum(weights)
        srt.append(f"{n}\n{stamp(t)} --> {stamp(t + d - 0.04)}\n" + "\n".join(ch) + "\n")
        n += 1
        t += d
(work / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")

# --- audio: narration at the recorded start times, over a quiet synthesised bed ------------------------
inputs, filters, labels = [], [], []
for i, c in enumerate(items):
    inputs += ["-i", str(work / "wav" / f"{c['id']}.wav")]
    delay = int(round(c["start"] * 1000))
    filters.append(f"[{i}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay={delay}|{delay}[n{i}]")
    labels.append(f"[n{i}]")
k = len(items)
filters.append("".join(labels) + f"amix=inputs={k}:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=7,apad=whole_dur={total:.2f}[voice]")

# music: a sustained A-major add9 pad (A2 E3 A3 C#4 B4), slow tremolo, low-passed, ~-30 dB under the voice
tones = [110.0, 164.81, 220.0, 277.18, 493.88]
music_inputs = []
for f in tones:
    music_inputs += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", f"sine=frequency={f}:sample_rate=48000"]
mi = k
mix = "".join(f"[{mi + j}:a]" for j in range(len(tones)))
filters.append(
    f"{mix}amix=inputs={len(tones)}:normalize=0,tremolo=f=0.11:d=0.35,lowpass=f=1100,"
    f"volume=0.045,afade=t=in:st=0:d=4,afade=t=out:st={total - 5:.2f}:d=5,pan=stereo|c0=c0|c1=c0[bed]"
)
filters.append("[voice][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")

audio_mix = work / "audio.wav"
cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, *music_inputs,
       "-filter_complex", ";".join(filters), "-map", "[a]", "-t", f"{total:.2f}", "-ar", "48000", str(audio_mix)]
subprocess.run(cmd, check=True)

# --- video: frames -> constant 30 fps, limited range, subtitles burned in ----------------------------------
style = ("FontName=Segoe UI Semibold,FontSize=8,PrimaryColour=&H00FFFFFF,OutlineColour=&H8C101010,BackColour=&H8C101010,"
         "BorderStyle=3,Outline=2,Shadow=0,MarginV=22,Alignment=2")
vf = (f"fps=30,scale=1920:1080:in_range=full:out_range=tv:flags=lanczos,format=yuv420p,"
      f"subtitles=subtitles.srt:force_style='{style}'")
out.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "frames.txt",
     "-i", "audio.wav", "-vf", vf, "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
     "-profile:v", "high", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
     "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out.resolve())],
    check=True, cwd=work,
)
(out.with_suffix(".srt")).write_text((work / "subtitles.srt").read_text(encoding="utf-8"), encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {total:.1f} s)")
