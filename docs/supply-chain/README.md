# Supply Chain / 공급망 관리

이 폴더는 「오픈소스 공급망 관리 가이드라인」(TTAK.KO-11.0246/R1 도메인 4)에 따른 이 저장소의 공급망 관리 기록이다.

| 파일 | 내용 |
|---|---|
| `asset-register.csv` | 통합자산목록 — 이 저장소가 사용하는 오픈소스 구성요소 (1구성요소 1행) |
| `exceptions.md` | 정책 예외(라이선스·취약점 위험 수용) 승인 기록. 릴리즈 CI의 취약점 게이트가 읽는다 |

## SBOM과 CI

| 워크플로 | 실행 시점 | 결과 |
|---|---|---|
| `supply-chain-pr.yml` | PR | 신규 의존성의 취약점·라이선스 점검 |
| `supply-chain-snapshot.yml` | main 변경, 매월 1일 | SBOM·보고서를 Actions 산출물로 보관 (관찰 모드) |
| `supply-chain-release.yml` | Release 게시 | SBOM(SPDX·CycloneDX)·NOTICE·고지패키지·체크섬을 **Release asset**으로 게시, attestation 생성 |

- 생성 도구: BomLens (https://github.com/sktelecom/bomlens), 버전은 워크플로의 `BOMLENS_VERSION`
- 생성 주체: Solbox Inc.
- 검증: `gh attestation verify <배포 tar.gz> --repo <owner>/<repo>`, `sha256sum -c SHA256SUMS`

## 배포 가능 판정 (Release)

릴리즈 워크플로는 Release가 게시된 뒤에 실행된다. 그래서 게이트에 걸려도 Release 자체는 남는다.
배포(장비 설치·납품)에는 아래 조건을 모두 만족하는 Release만 쓴다.

| 조건 | 확인 위치 |
|---|---|
| 정식 Release (Pre-release 아님) | Releases 화면의 표시 |
| 첨부 6개: `.tar.gz`, `.cdx.json`, `.spdx.json`, `-NOTICE.txt`, `-oss-docs.zip`, `SHA256SUMS` | Release의 Assets |
| 릴리즈 워크플로 실행 성공 | Actions → supply-chain-release |

- 게이트에 실패하면 워크플로가 Release를 **Pre-release로 바꾸고 본문 맨 앞에 "사용 금지" 경고**를 붙인다.
- 실패한 Release는 지우지 않고 기록으로 둔다. 조치(업그레이드) 또는 예외 승인 후 **새 태그**로 다시 게시한다(같은 Release를 다시 실행하면 태그 시점 파일을 써서 또 실패한다).
- 워크플로가 실행되지 않은 경우(취소, 승인 거부 등)에는 경고가 붙지 않는다. 첨부가 없는 정식 Release는 월간 점검에서 찾아 Pre-release로 바꾸고 경고를 붙인다.

## 문의

- 공급망 관리 담당: 솔박스 (Solbox) jay@solbox.com
