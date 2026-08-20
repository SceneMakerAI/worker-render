# render

하이라이트 **영상 합성**을 HTTP 로 제공하는 서비스 — 구간 목록을 완성된 MP4 하나로 바꾸는
**GPU 단계**. 원본이 로컬에 없으면 S3 에서 받아오고, 조각을 잘라 하나의 규격으로 재인코딩한
뒤 이어붙여 다시 S3 에 올린다.

[English README](README.md)

## 개요

`v_id` 와 그룹별 구간을 받아, 각 구간을 자르고 그룹마다 타이틀 카드(**범퍼**)를 앞에 붙인 뒤
순서대로 이어 `{v_id}/result/{v_id}_{c_id}.mp4` 를 만든다.

종목이 갈리는 건 *그룹 이름을 어떻게 붙이는가* 뿐이다 — 야구는 이닝(`1_top`, `5_bot`), 축구는
전후반. 요청이 `ReqTimeRange` 평평한 목록이 되고 나면 그 아래는 전부 공통이라,
`lib/svc/render.py` 아래로는 이닝이 뭔지 아무도 모른다.

## 파이프라인

```
요청 {그룹: [구간들]}
[1] download_video     — 원본이 로컬에 있나? 없으면 S3에서 (크기 같으면 건너뜀)
[2] check_video_format — 출력 규격을 읽고 구간을 검증                    (404/400)
[3] to_media_parts     — 그룹 → 평평한 조각 목록, 그룹마다 범퍼 삽입
[4] cut_parts          — 조각마다 ffmpeg 한 번, 원본 규격으로 재인코딩    (GPU, 순차)
[5] render             — concat demuxer + stream copy → work/final.mp4 → result/ 로 이동
[6] upload             — S3URL 전부에 mp4 와 구간 목록 .json 을 올림
```

1~3 은 요청 스레드에서, 4~6 은 **워커 스레드 하나**에서 돈다.

**워커가 하나인 이유.** ffmpeg 하나가 NVDEC 디코더 컨텍스트로 400 MB 넘는 VRAM 을 잡는다.
24 GB 카드에서 입력 86개를 한 번에 열면 61번째에서 `CUDA_ERROR_OUT_OF_MEMORY` 로 죽는다(실측).
순차로 돌면 조각이 몇 개든 VRAM 이 620 MB 대로 일정하다. FastAPI 는 `def` 핸들러를 자기
40개짜리 스레드풀에서 돌리므로, 여기로 모으지 않으면 동시 요청 수만큼 ffmpeg 이 뜬다.

**`-c copy` 가 아니라 재인코딩하는 이유.** stream copy 는 키프레임에서만 시작할 수 있다. 이
원본들은 키프레임이 5초 간격인데 하이라이트 평균 길이가 16초라, copy 로 자르면 모든 컷이
최대 5초씩 어긋난다. 게다가 ffmpeg 은 그 초과분을 mp4 *edit list* 로 감추는데 concat demuxer
는 그걸 무시한다 — 조각 하나씩 보면 멀쩡한데 이어붙이면 앞부분이 되살아난다
(실측: edit list 반영 10.03초, 무시 14.07초).

**범퍼도 재인코딩하는 이유.** 범퍼는 1280x720 / 24 fps / 96 kHz 인데 원본은 1920x1080 /
30 fps / 44.1 kHz 일 수 있다. `concat` + `-c copy` 는 모든 조각의 코덱·해상도·fps·오디오
규격·타임베이스가 같아야 하므로, 전부 **원본** 규격에 맞춘다 — 원본보다 키우지는 않는다.

**범퍼가 그냥 "구간 없는 조각"인 이유.** `to_media_parts` 가 `start_sec == end_sec == 0`
(= 파일 전체) 인 `ReqTimeRange` 로 끼워 넣는다. 그 아래로는 *범퍼* 라는 단어가 한 번도 안
나온다 — 렌더는 균일한 목록 하나만 본다.

**`work/` 에 만들고 옮기는 이유.** 결과물에 바로 쓰면 ffmpeg 이 파일을 여는 순간 기존 결과가
잘려나가서, 재처리가 실패하면 새것도 옛것도 없어진다. 이어붙이기는 `work_{c_id}/final.mp4`
에 하고 성공했을 때만 제자리로 옮긴다 — 같은 파일시스템이라 원자적 rename 이다.

**원본 다운로드가 크기를 비교하는 이유.** 원본이 수십 GB 다. `download_file` 은 `head_object`
로 먼저 크기를 보고 로컬과 같으면 전송을 건너뛴다 — `aws s3 sync` 와 같은 규칙이다. 받을 때는
`.part` 로 받고 다 되면 이름을 바꾸므로, 중간에 끊겨도 다음 요청이 반쪽 파일을 진짜로
착각하지 않는다.

## 경로

영상 하나에 딸린 건 전부 `{VOD_DIR}/{v_id}/` 아래에 있고, 규칙은 [lib/util.py](lib/util.py)
한 곳에만 있다 — 다른 데서는 경로를 조립하지 않는다.

```
{VOD_DIR}/{v_id}/source.mp4                  원본                      vod_paths()
{VOD_DIR}/{v_id}/result/{v_id}_{c_id}.mp4    결과물                    render_paths()
{VOD_DIR}/{v_id}/result/{v_id}_{c_id}.json   어떤 구간으로 만들었는지  render_paths()
{VOD_DIR}/{v_id}/work_{c_id}/                중간 조각                 render_paths()

{S3URL[0]}/vod/{v_id % 50}/{v_id}.mp4        S3 의 원본                s3_paths()
{S3URL[n]}/result/{v_id}/{v_id}_{c_id}.*     업로드 대상               s3_result_paths()
```

로컬과 S3 의 파일명이 다른 건 의도한 것이다. 로컬은 폴더가 `{v_id}` 라 파일명이 `source.mp4`
면 되고, S3 는 폴더가 `{v_id % 50}`(파일을 흩뜨리려고) 라 id 가 파일명으로 옮겨간다.

## 구성

```
config.py                    설정 — 포트 / 로그 / ffmpeg / 경로 / 상한 (.env 읽음)
main.py                      FastAPI 진입점 — app + 라우터 + 기동 준비 (lifespan)
test.sh                      curl 요청 하나, 동작 확인용
lib/
  dto.py                     계층 공통 모델 — ReqTimeRange(s), MediaInfo, ResRender
  util.py                    hms + 모든 경로 규칙
  http/
    sports/baseball.py       POST /render/sports/baseball — 요청 DTO, 검증, svc 호출
    sports/soccer.py         POST /render/sports/soccer — 자리만, 501 반환
    status.py                GET /render/{v_id}/{c_id}
    http_util.py             로깅, 에러 규격, download_video(), check_video_format()
  svc/
    compose.py               그룹 → 평평한 조각 목록 (범퍼 삽입)
    render.py                워커 풀, 잡 레지스트리, cut_parts / render / start / status
    bumper.py                범퍼 목록 + 기동 시 확인
  media/
    ffmpeg.py                probe / cut_encode / concat — 각각 ffmpeg 한 번
  storage/
    s3.py                    download_file / upload_file
```

## 요구 사항

- Python **3.13**
- [uv](https://github.com/astral-sh/uv)
- **NVENC/NVDEC** 가 빌드된 ffmpeg (`ffmpeg -encoders | grep nvenc`)
- NVIDIA GPU
- `S3URL` 을 쓸 경우, boto3 기본 체인으로 찾아지는 AWS 자격증명

## 설치

```bash
uv sync
cp .env.example .env
```

### 설정 (`.env`)

```bash
HOST=0.0.0.0
PORT=19700

FFMPEG_DIR="/usr/local/ffmpeg-gpu"   # ffmpeg 과 ffprobe 가 있는 디렉토리
GPU_NUM=0                            # NVDEC/NVENC 가 쓸 GPU 인덱스

VOD_DIR="/stg/vod/scenemaker"        # 원본·결과물·작업 디렉토리가 전부 {v_id}/ 아래

S3URL='["s3://bucket-a", "s3://bucket-b"]'   # JSON 배열. [] 면 S3 를 쓰지 않는다
```

`S3URL` 은 목록이다. 결과물은 **전부**에 올리고, 원본은 **첫 번째**에서 받아온다. `[]` 면
로컬만 쓰는 환경이 되고, 원본이 없으면 받아오는 대신 404 다.

나머지는 [config.py](config.py) 의 상수다:

| 상수 | 값 | 의미 |
|---|---|---|
| `MAX_THREAD_QUEUE` | `5` | 안 끝난 잡 허용치, 초과하면 `429 TOO_MANY_JOBS` |
| `DELETE_WORK_DIR` | `{SUCCESS: 1, ERROR: 0}` | 실패 시 중간 조각 보존 — 어느 조각에서 깨졌는지 봐야 하므로 |
| `BUMPER_DATA_DIR` | `{baseball: …}` | 종목별 타이틀 카드 위치 |
| `LOG_DIR` | `/usr/service/logs/scenemaker/render` | `render.log` |

범퍼 파일명 규칙(`inning_bumper_{NN}_{top|bot}.mp4`, 1~15회)은 야구 규칙이라 `config.py` 가
아니라 [lib/svc/bumper.py](lib/svc/bumper.py) 에 있다.

## 실행

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 19700 --reload   # 개발
.venv/bin/python main.py                                       # 운영
sudo systemctl enable --now render                             # system/render.service 로
```

**단일 프로세스**로 띄운다 — `uvicorn --workers` 는 **쓰지 않는다**. 워커마다 자기 렌더
스레드를 갖게 되어 ffmpeg 이 워커 수만큼 동시에 돌고, VRAM 보장이 깨진다.

**세션과 분리해서 띄운다** (systemd 나 `setsid nohup`). 터미널에서 그냥 띄우면 터미널이 닫힐
때 SIGHUP 으로 서비스와 돌던 ffmpeg 이 같이 죽는다.

기동 시 `lifespan` 이 범퍼를 전부 probe 하고 S3 클라이언트를 만든다. 둘 다 메인 스레드여야
한다 — 워커 스레드에서 boto3 클라이언트를 만들면 이 Python 3.13 / OpenSSL 3.0 조합에서
`SSLError: unknown error (_ssl.c:3123)` 로 실패한다.

로그는 stdout 이 아니라 `$LOG_DIR/render.log` 로 간다.

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

| 필드 | 설명 |
|---|---|
| `v_id` / `c_id` | 영상 ID 와 편성 ID — 둘이 합쳐 결과물 이름과 잡 키가 된다 |
| `sync_yn` | `true` 면 렌더가 끝날 때까지 기다렸다 `done`, `false` 면 즉시 `accepted` |
| `bumper_yn` | 이닝마다 타이틀 카드를 앞에 붙인다 |
| `innings` | `{이닝: [구간들]}`, 키는 `{n}_{top\|bot}`. **요청에 온 순서 그대로** 렌더한다 |

`file_name` 은 없다 — 원본 경로는 `v_id` 하나로 정해진다.

`start_sec` / `end_sec` 만 사용한다. `start_hms` / `end_hms` 는 결과 `.json` 에 그대로 실려
나가지만 렌더에는 쓰지 않는다.

### `GET /render/{v_id}/{c_id}`

```json
{"status": "done", "output_path": "/…/201/result/201_1.mp4", "error": ""}
```

`status` 는 `accepted` | `running` | `done` | `error`. `output_path` 는 `done` 일 때만,
`error` 는 `error` 일 때만 채운다. 재기동으로 메모리에서 잡이 사라져도 결과 파일이 있으면
`done` 으로 답한다. 둘 다 없으면 `404 JOB_NOT_FOUND`.

잡 상태는 워커의 `Future` **그 자체**다 — 대기 중인지, 도는 중인지, 끝났는지, 예외로 끝났는지.
그래서 따로 맞춰줄 두 번째 진실이 없다.

### 에러

| 코드 | HTTP | 상황 |
|---|---|---|
| `INVALID_REQUEST` | 400 | 스키마 위반 |
| `INVALID_SEGMENT` | 400 | 구간이 비었거나 음수·역전이거나 원본 길이를 넘음 |
| `INVALID_VIDEO` | 400 | 영상으로 읽을 수 없음 |
| `SOURCE_NOT_FOUND` | 404 | 원본이 로컬에 없고 S3 에서도 못 받음 |
| `JOB_NOT_FOUND` | 404 | 잡도 결과 파일도 없음 |
| `TOO_MANY_JOBS` | 429 | 대기열이 가득 참 |
| `NOT_IMPLEMENTED` | 501 | 축구 |

실패할 수 있는 건 전부 워커가 뜨기 **전에** 검사한다. `accepted` 를 받았다면 남은 건 ffmpeg
뿐이라는 뜻이다.

## 성능

2×RTX 4090, 워커 1개 기준 실측:

| 원본 | 조각 | 결과 길이 | cut | 배속 |
|---|---|---|---|---|
| 1280x720 | 70개 | 2118초 | 116초 | 18.3배속 |
| 1920x1080 | 51개 | 621초 | 77초 | 8.1배속 |

시간은 픽셀 수에 비례한다 — 1080p 가 720p 의 2.26배로, 픽셀 비율 2.25배와 일치한다.
`concat` 은 무시해도 된다: 200 MB 이어붙이기에 0.26초로, 자르기의 60분의 1이다. VRAM 은
조각 수와 무관하게 620 MB 대(1080p)를 유지한다.

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
