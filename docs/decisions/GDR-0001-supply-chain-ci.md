# GDR-0001: 공급망 CI 도입과 취약점 게이트 기준

- 상태: 제안
- 제안일: 2026-10-22
- 결정일: (승인 PR 병합일)
- 책임자: @jplee-creator
- 참여자: @MinsungIM @SolboxOSS
- 관련 이슈·PR: (이 파일을 추가하는 PR)

## 상황

「오픈소스 공급망 관리 가이드라인」 Lv4는 빌드마다 SBOM을 자동 생성하고 고위험을 자동 차단할 것을 요구한다.
지금까지는 담당자가 월 1회 BomLens UI로 수동 스캔했다.

## 선택지

1. 수동 스캔 유지: 추가 작업이 없지만 Lv4 요건과 Release 게시 증거를 충족하지 못한다.
2. Syft 기반 예제 워크플로: 가이드라인 예제와 같지만 고지문·적합성 검사를 별도로 구성해야 한다.
3. BomLens CI: 수동 스캔과 같은 도구로 SBOM(SPDX·CycloneDX)·고지문·보안 리포트·적합성 검사를 한 번에 생성한다.

## 결정

3번을 채택한다.

- PR: dependency review (Critical, GPL-3.0/AGPL-3.0 거부) + BomLens Critical 취약점 알림(예외 반영, 실패시키지 않음)
- main·매월: 스냅샷 스캔, 관찰 모드
- Release: SBOM 검증 게이트 + 취약점 게이트 **Critical** 이상 차단, 예외는 `exceptions.md`의 유효한 승인만 인정
- 릴리즈 job은 `release` Environment에서 Project Lead 승인 후 실행
- 게이트 실패 시 Release를 Pre-release로 바꾸고 "사용 금지" 경고를 붙인다. 배포에는 정식 Release + 첨부 6개만 쓴다

## 근거와 영향

- 수동 스캔과 같은 도구라 결과를 비교·검증할 수 있다.
- 처음부터 High를 차단하면 오탐 우회가 일상화될 수 있어(가이드라인 3장 12절) Critical부터 시작한다.
- 공개 저장소에서는 보안 리포트를 Actions 산출물로 올리지 않고 로그에도 상세를 남기지 않는다.

## 반대 의견

없음 (의견수렴 기간에 추가)

## 후속조치

- [ ] main Ruleset·`release` Environment 설정 / @jplee-creator / 시행일
- [ ] 3개월 운영 후 게이트 기준 High 상향 검토 / @MinsungIM / (적용일 + 3개월)

## 재검토 조건

- Critical 차단이 분기 2회 이상 예외로 처리되는 경우
- BomLens 주요 버전 변경, 고객·발주기관의 SBOM 요구 변경
