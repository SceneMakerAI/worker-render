# render

Highlight **video assembly** served over HTTP — the **GPU stage** that turns a list of time
ranges into one finished MP4. Fetches the source from S3 if it is not on disk, cuts every
piece, re-encodes it to a single spec, concatenates, and uploads the result back.

[한국어 README](README.ko.md)

## Overview

Given `v_id` and grouped time ranges, `render` cuts each range, optionally prepends a title
card (**bumper**) to each group, joins everything in order, and writes
`{v_id}/result/{v_id}_{c_id}.mp4`.

Sports differ only in *how the groups are named* — baseball uses innings (`1_top`, `5_bot`),
soccer will use halves. Once the request becomes a flat list of `ReqTimeRange`, everything
below is common: nothing under `lib/svc/render.py` knows what an inning is.

## Pipeline

```
request {group: [time ranges]}
[1] download_video     — source on disk? else pull from S3 (skipped if sizes match)
[2] check_video_format — probe for the output spec, validate the ranges     (404/400)
[3] to_media_parts     — groups → flat part list, bumper prepended per group
[4] cut_parts          — one ffmpeg per part, re-encoded to the source spec  (GPU, sequential)
[5] render             — concat demuxer + stream copy → work/final.mp4 → move to result/
[6] upload             — every S3URL gets the mp4 and a .json of the ranges
```

Steps 1–3 run in the request thread; 4–6 run in a **single** worker thread.

**Why one worker.** Every ffmpeg holds an NVDEC decoder context worth >400 MB of VRAM. On a
24 GB card, opening 86 inputs at once dies at the 61st with `CUDA_ERROR_OUT_OF_MEMORY`
(measured). Sequentially, VRAM stays flat at ~620 MB no matter how many parts there are.
FastAPI runs `def` handlers on its own 40-thread pool, so without funnelling them here,
concurrent requests would spawn concurrent ffmpeg.

**Why re-encode instead of `-c copy`.** A stream copy can only start on a keyframe. Sources
here have keyframes every 5 s while the average highlight is 16 s, so copying would shift
every cut by up to 5 s. Worse, ffmpeg hides the overshoot behind an mp4 *edit list* that the
concat demuxer ignores — each piece looks right alone but drags its pre-roll into the join
(measured: 10.03 s with the edit list, 14.07 s without).

**Why bumpers are re-encoded too.** They are 1280x720 / 24 fps / 96 kHz while a source may be
1920x1080 / 30 fps / 44.1 kHz. `concat` + `-c copy` requires identical codec, resolution, fps,
audio rate and timebase across all pieces, so every part is normalized to the **source** spec —
never upscaled past it.

**Why a bumper is just a part with no range.** `to_media_parts` inserts it as a
`ReqTimeRange` with `start_sec == end_sec == 0`, meaning "the whole file". Below that point
the word *bumper* never appears — the renderer sees one uniform list.

**Why `work/` then move.** Writing straight to the output truncates the previous result the
moment ffmpeg opens it, so a failed re-render would leave neither the old file nor a new one.
The join lands in `work_{c_id}/final.mp4` and is renamed into place only on success — same
filesystem, so it is an atomic rename.

**Why the source download compares sizes.** Sources are tens of GB. `download_file` calls
`head_object` first and skips the transfer when the local file already matches, the same rule
`aws s3 sync` uses. It downloads to `.part` and renames on completion, so an interrupted
transfer never leaves a half file that the next request would mistake for the real one.

## Paths

Everything for one video lives under `{VOD_DIR}/{v_id}/`, and every rule is in
[lib/util.py](lib/util.py) — nothing else assembles paths.

```
{VOD_DIR}/{v_id}/source.mp4                  source                    vod_paths()
{VOD_DIR}/{v_id}/result/{v_id}_{c_id}.mp4    result                    render_paths()
{VOD_DIR}/{v_id}/result/{v_id}_{c_id}.json   the ranges that made it   render_paths()
{VOD_DIR}/{v_id}/work_{c_id}/                intermediate pieces       render_paths()

{S3URL[0]}/vod/{v_id % 50}/{v_id}.mp4        source in S3              s3_paths()
{S3URL[n]}/result/{v_id}/{v_id}_{c_id}.*     upload targets            s3_result_paths()
```

Local and S3 names differ on purpose: locally the folder is `{v_id}` so the file is
`source.mp4`, while in S3 the folder is `{v_id % 50}` (to spread files) so the id moves into
the filename.

## Layout

```
config.py                    settings — port / log / ffmpeg / paths / limits (reads .env)
main.py                      FastAPI entrypoint — app + routers + startup (lifespan)
test.sh                      one curl request, for a smoke check
lib/
  dto.py                     shared models — ReqTimeRange(s), MediaInfo, ResRender
  util.py                    hms + every path rule
  http/
    sports/baseball.py       POST /render/sports/baseball — request DTO, validate, call svc
    sports/soccer.py         POST /render/sports/soccer — placeholder, returns 501
    status.py                GET /render/{v_id}/{c_id}
    http_util.py             logging, error shape, download_video(), check_video_format()
  svc/
    compose.py               groups → flat part list (bumper insertion)
    render.py                worker pool, job registry, cut_parts / render / start / status
    bumper.py                bumper table + startup probe
  media/
    ffmpeg.py                probe / cut_encode / concat — one ffmpeg call each
  storage/
    s3.py                    download_file / upload_file
```

## Requirements

- Python **3.13**
- [uv](https://github.com/astral-sh/uv)
- An ffmpeg build with **NVENC/NVDEC** (`ffmpeg -encoders | grep nvenc`)
- NVIDIA GPU
- AWS credentials reachable by the boto3 default chain, if `S3URL` is set

## Setup

```bash
uv sync
cp .env.example .env
```

### Configuration (`.env`)

```bash
HOST=0.0.0.0
PORT=19700

FFMPEG_DIR="/usr/local/ffmpeg-gpu"   # directory holding ffmpeg and ffprobe
GPU_NUM=0                            # GPU index for NVDEC/NVENC

VOD_DIR="/stg/vod/scenemaker"        # sources, results and work dirs, all under {v_id}/

S3URL='["s3://bucket-a", "s3://bucket-b"]'   # JSON array; [] disables S3 entirely
```

`S3URL` is a list. The result is uploaded to **every** entry; the source is pulled from the
**first** one. With `[]` the service is local-only — a missing source is then a 404 rather
than something to fetch.

Everything else is a constant in [config.py](config.py):

| Constant | Value | Meaning |
|---|---|---|
| `MAX_THREAD_QUEUE` | `5` | unfinished jobs allowed; over that → `429 TOO_MANY_JOBS` |
| `DELETE_WORK_DIR` | `{SUCCESS: 1, ERROR: 0}` | keep the intermediate pieces on failure, to see which part broke |
| `BUMPER_DATA_DIR` | `{baseball: …}` | where each sport's title cards live |
| `LOG_DIR` | `/usr/service/logs/scenemaker/render` | `render.log` |

Bumper filenames are a baseball rule and live in [lib/svc/bumper.py](lib/svc/bumper.py)
(`inning_bumper_{NN}_{top|bot}.mp4`, innings 1–15), not in `config.py`.

## Run

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 19700 --reload   # development
.venv/bin/python main.py                                       # production
sudo systemctl enable --now render                             # via system/render.service
```

Run as a **single process** — **no** `uvicorn --workers`. Each worker would bring its own
render thread, so one ffmpeg per worker would run at once and the VRAM guarantee is gone.

Start it detached (systemd, or `setsid nohup`). Started in a foreground shell, the service and
its running ffmpeg both die on SIGHUP when the terminal closes.

At startup `lifespan` probes every bumper and creates the S3 client. Both must happen on the
main thread: creating a boto3 client inside a worker thread fails with
`SSLError: unknown error (_ssl.c:3123)` on this Python 3.13 / OpenSSL 3.0 pair.

Logs go to `$LOG_DIR/render.log`, not stdout.

## API

Base URL: `http://$HOST:$PORT`.

### `POST /render/sports/baseball`

```bash
curl -X POST http://localhost:19700/render/sports/baseball \
  -H 'Content-Type: application/json' \
  -d '{"v_id": 201, "c_id": 1, "sync_yn": true, "bumper_yn": true,
       "innings": {"1_top": [{"start_sec": 714, "end_sec": 725}],
                   "5_bot": [{"start_sec": 3721, "end_sec": 3742}]}}'
```

| Field | Description |
|---|---|
| `v_id` / `c_id` | video id and composition id — together they name the output and the job |
| `sync_yn` | `true` waits for the render and returns `done`; `false` returns `accepted` at once |
| `bumper_yn` | prepend each inning's title card |
| `innings` | `{inning: [ranges]}`, key `{n}_{top\|bot}`. Rendered in the order given |

There is no `file_name` — the source path comes from `v_id` alone.

Only `start_sec` / `end_sec` are used; `start_hms` / `end_hms` are carried through to the
result `.json` for debugging and are not trusted.

### `GET /render/{v_id}/{c_id}`

```json
{"status": "done", "output_path": "/…/201/result/201_1.mp4", "error": ""}
```

`status` is `accepted` | `running` | `done` | `error`. `output_path` is filled only when
`done`; `error` only when `error`. If the job is gone from memory (restart) but the output
file exists, it still reports `done`. Otherwise `404 JOB_NOT_FOUND`.

Job state *is* the worker's `Future` — queued, running, finished, or finished-with-exception —
so there is no second copy of the truth to keep in sync.

### Errors

| Code | HTTP | When |
|---|---|---|
| `INVALID_REQUEST` | 400 | schema violation |
| `INVALID_SEGMENT` | 400 | empty, negative, reversed, or past the end of the source |
| `INVALID_VIDEO` | 400 | not readable as a video |
| `SOURCE_NOT_FOUND` | 404 | source missing locally and not fetchable from S3 |
| `JOB_NOT_FOUND` | 404 | no such job and no output file |
| `TOO_MANY_JOBS` | 429 | queue is full |
| `NOT_IMPLEMENTED` | 501 | soccer |

Everything that can fail is checked **before** the worker starts, so an `accepted` response
means the only thing left is ffmpeg.

## Performance

Measured on 2×RTX 4090, one worker:

| Source | Parts | Output | Cut | Speed |
|---|---|---|---|---|
| 1280x720 | 70 | 2118 s | 116 s | 18.3× realtime |
| 1920x1080 | 51 | 621 s | 77 s | 8.1× realtime |

Time scales with pixel count — 1080p costs 2.26× of 720p, matching the 2.25× pixel ratio.
`concat` is negligible: 0.26 s for a 200 MB join, ~60× cheaper than the cutting. VRAM sits at
~620 MB (1080p) regardless of part count.

## License

MIT — see [LICENSE](LICENSE).
