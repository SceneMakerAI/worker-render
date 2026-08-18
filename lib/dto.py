"""계층 공통 dataclass — http / svc / media 어디서든 갖다 쓴다.

특정 계층에 두면 아래 계층이 위를 import 하게 되어 순환이 생기므로 lib 루트에 둔다.
종목이나 API 하나에만 쓰이는 규격은 여기 넣지 않는다 (그건 해당 핸들러 파일에).
"""
from pathlib import Path

from pydantic import BaseModel, RootModel


class ReqTimeRange(BaseModel):
    """시간 구간 하나. 요청으로 들어오고, 서버가 src 를 채워 렌더까지 그대로 들고 간다.

    src 는 요청에 없어도 된다 — 어느 파일인지는 서버가 정한다 (file_name 으로 조립).
    start_sec 과 end_sec 이 **둘 다 0 이면 "그 파일 전체"** 라는 뜻이다. 범퍼처럼 짧은 파일을
    통째로 붙일 때 쓴다. 그래서 길이 0 짜리 구간은 표현할 수 없다 (의미가 없으므로 문제 없음).

    렌더링은 *_sec 만 사용하고 *_hms 는 디버깅 표기용 (신뢰하지 않는다).
    """
    src: Path | None = None
    start_sec: float
    end_sec: float
    start_hms: str = ""
    end_hms: str = ""

    @property
    def whole_file(self) -> bool:
        """구간 없이 파일 전체를 쓰는가."""
        return self.start_sec == 0 and self.end_sec == 0


class ReqTimeRanges(RootModel[list[ReqTimeRange]]):
    """요청으로 들어온 구간 목록. JSON 은 배열 그대로다 — {"1_top": [{...}, ...]}."""
    root: list[ReqTimeRange] = []

    def __iter__(self):
        return iter(self.root)

    def __len__(self):
        return len(self.root)

    def __getitem__(self, i):
        return self.root[i]


class ResRender(BaseModel):
    """렌더 접수·상태 응답. Res 접두사 = 밖으로 나가는 규격.

    종목이 늘어도 응답 모양은 같아서 여기 하나만 둔다. 접수(POST)와 조회(GET)가 같은 모양이다.

      accepted  큐에 넣었다 — output_path 는 예정 경로 (파일은 아직 없다)
      running   워커가 돌고 있다
      done      끝났다 — output_path 에 파일이 있다
      error     실패 — error 에 이유
    """
    status: str
    output_path: str = ""
    error: str = ""


class MediaInfo(BaseModel):
    """ffprobe 로 읽은 영상 규격. probe() 가 돌려주고 렌더 출력 규격의 근거가 된다.

    fps 는 분수 문자열('30000/1001') 그대로 둔다 — 29.97 로 반올림하면 긴 영상에서 오디오와 어긋난다.
    """
    duration: float                 # 초
    width: int
    height: int
    fps: str
    has_audio: bool


