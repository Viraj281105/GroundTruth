# Video production preflight report

Date: 2026-11-10. Done after the application passed its regression checks, before any real take.

## Tools found

| Tool | Result |
|---|---|
| Playwright | 1.65.0 (`apps/web`), driving the installed Google Chrome (`channel: chrome`). No download needed. |
| Playwright's built-in `recordVideo` | **Does not work here**: it needs Playwright's own ffmpeg build (`ms-playwright/ffmpeg-1013`), which is not installed. Not installed either, to stay offline and free. |
| FFmpeg / FFprobe | 9.0 full build (Gyan, via winget). Encoders present: `libx264`, `aac`, `libmp3lame`; filters: `subtitles` (libass), `amix`, `loudnorm`, `adelay`. |
| Screen capture | Chrome DevTools screencast (`Page.startScreencast`): timestamped JPEG frames of the page at 1920x1080, captured from Chrome itself, so no desktop, no browser UI, no developer tools and no notifications can appear. Chosen over an OS screen recorder for that reason. |
| Text to speech | Windows `System.Speech` voices `Microsoft David Desktop` and `Microsoft Zira Desktop`: local, offline, free. `edge-tts` (Python) is installed but Microsoft's endpoint answered **HTTP 403** (`WSServerHandshakeError`), so no neural voice was available. Piper, Kokoro, pyttsx3 are not installed. |
| Subtitles | Generated from the same narration file and the recorded start time of each sentence; burned in by ffmpeg, and also written as `GROUNDTRUTH_DEMO_VIDEO.srt`. |
| Music | Synthesised by ffmpeg (a quiet sustained A-major add9 chord, slow tremolo, low-passed, about 30 dB under the voice, faded in and out). No samples, no licence. |

## Disposable recording test

A 5 second capture of the sign-in page and the Method page (typing into a field, a scroll), narrated with the local voice, a music bed and burned subtitles, then verified:

| Check | Result |
|---|---|
| Screen capture works | Yes: 114 frames in 3.9 s of activity; frame size 1920x1080 |
| Resolution | 1920x1080, 16:9 |
| Narration can be added | Yes: SAPI WAV (22.05 kHz mono) resampled to 48 kHz, delayed to a given start time |
| MP4 / H.264 export | `h264 (High)`, `yuv420p`, 30 fps, AAC-LC 48 kHz, `+faststart` |
| File plays | Full decode with `ffmpeg -v error -f null -` returned no errors |

Findings from the test that changed the pipeline:

1. The screencast emits a frame only when the page changes, so frames are not evenly spaced. They are assembled with ffmpeg's concat demuxer using each frame's real duration, then converted to a constant 30 fps.
2. Chrome's JPEG frames are full range (`yuvj420p`). The encode converts to limited range (`in_range=full:out_range=tv`) and tags BT.709, otherwise players show lifted blacks.
3. Chrome's screencast has no mouse pointer. The recorder injects a small ring that follows the pointer and shrinks on click, so viewers can see what is being clicked.
4. The wall clock and the screencast clock differ by about 0.02 s (measured on every take), so narration start times are corrected by that amount.
5. Subtitles at the first size tried were too large and covered the page; the final style is smaller with a translucent box.

## Production pipeline (commands)

All paths are relative to the repository root. The demo stack must be running (see the remediation report) and `.demo-secrets/demo-passwords.tsv` must exist.

```bash
# 1. narration audio: one WAV per sentence, then each duration
powershell -NoProfile -ExecutionPolicy Bypass -File apps/web/e2e/demo/video/tts.ps1 \
  -Narration apps/web/e2e/demo/video/narration.json -OutDir <work>/wav -Rate 0
#    (write <work>/durations.json: {"s0-1": seconds, ...} from ffprobe)

# 2. put the demo project in the state the recording starts from (real Sentinel-2 fetch, ~1 minute)
cd apps/web
AUDIT_PASSWORDS_FILE=../../.demo-secrets/demo-passwords.tsv node e2e/demo/prepare-demo.mjs

# 3. rehearse (same actions, almost no waiting, no capture), then the real take
FAST=1 VIDEO_OUT=<work> AUDIT_PASSWORDS_FILE=../../.demo-secrets/demo-passwords.tsv node e2e/demo/video/record.mjs
       VIDEO_OUT=<work> AUDIT_PASSWORDS_FILE=../../.demo-secrets/demo-passwords.tsv node e2e/demo/video/record.mjs

# 4. assemble frames + narration + music + subtitles into the MP4
cd ../..
python apps/web/e2e/demo/video/assemble.py <work> GROUNDTRUTH_DEMO_VIDEO.mp4
```

Note: the real take downloads a dossier, which adds a `Report sealed` record to the demo project's ledger. To repeat a take with a clean ledger, reset the isolated stack (`down -v`, `up -d`) and run step 2 again.

## Result

* `GROUNDTRUTH_DEMO_VIDEO.mp4`: 406.7 s (6:47), 1920x1080, 30 fps, H.264 High / yuv420p, AAC-LC 48 kHz stereo, about 75 MB, full decode clean. Subtitle file `GROUNDTRUTH_DEMO_VIDEO.srt` beside it.
* Four takes were made. Take 1 ran 7:13 because one scroll target did not exist on the page (22 s of dead time); take 2 showed the welcome-tour popup over the landing page and subtitles that were too large; take 3 still opened with the tour popup over the title card and the landing page still said "nothing real yet". Each was fixed at the cause (the recorder, or the product copy: issue U-10 in the audit report) and re-recorded from a clean database. Only the final take is kept.

## Limits to know

* The synthetic Windows voice is intelligible but plainly synthetic; no neural voice was reachable. Replacing it means re-running `tts.ps1` with another engine and re-assembling; the timing comes from the measured sentence lengths, so nothing else changes.
* The satellite values were fetched live during preparation, so a re-run will show the same scenes only if Microsoft Planetary Computer still serves them; the numbers on screen in this take (for example NDVI 0.289, 0.298, 0.388, 0.288, 0.279, 0.340) are what that fetch returned.
* Two statements in the narration are described rather than shown on screen: the ledger tamper test and the server's refusals (HTTP 403) for the funder. Both were performed and are recorded in the audit report.
