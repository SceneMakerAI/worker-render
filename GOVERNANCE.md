# worker-render Governance

> 상태: 초안 (승인 PR 병합일에 시행) / 버전: 1.0 / 다음 검토일: 2027-10-31
> 상위 정책: 솔박스 오픈소스 공급망 관리 정책 (사내 위키 「1. 정책 및 역할(RACI)」)

## 1. 목적과 적용범위

이 문서는 worker-render의 기술 및 운영 의사결정, 역할, 권한과 책임을 정의한다.
적용 대상은 GitHub 저장소 SceneMakerAI/worker-render와 그 이슈·PR·Release다.

## 2. 거버넌스 원칙

- 공개성: 보안·개인정보 사안을 제외한 논의와 결정은 이슈·PR에 기록한다.
- 존중: 모든 참여자는 CODE_OF_CONDUCT.md를 따른다.
- 기술적 타당성: 소속보다 근거, 재현 가능한 결과와 프로젝트 목표를 우선한다.
- 책임성: 권한자는 결정과 운영 결과에 책임지고 장기 비활동 시 권한을 이관한다.
- 보안 우선: 미공개 취약점은 공개 채널에서 다루지 않는다(SECURITY.md).

## 3. 역할과 권한

### Contributor

- 이슈, PR, 리뷰, 문서, 사용자 지원 등으로 기여한다.
- 저장소 write 권한은 필요하지 않다.

### Reviewer

- 지정 영역의 PR을 검토하고 테스트·설계·문서 개선을 요청한다.
- 단독으로 병합하거나 릴리즈하지 않는다.

### Maintainer

- PR 병합, 이슈 분류, 릴리즈 준비와 의존성 관리를 책임진다.
- CODEOWNERS 영역을 검토하고 결정기록을 유지한다.
- 자신이 작성한 PR을 자신의 승인만으로 병합하지 않는다.

### 공급망 관리자

- 거버넌스 문서(GOVERNANCE, MAINTAINERS, SECURITY, CODE_OF_CONDUCT, CODEOWNERS)와 공급망 CI·게이트(워크플로, `scripts/supply-chain/`, 의존성 점검 기준), 결정기록을 관리한다.
- 위 영역의 PR을 승인할 수 있다(CODEOWNERS). 다른 승인자와 같이, 자신이 작성한 PR은 승인하지 않는다.
- 월간 공급망 점검(스냅샷 결과, 예외 만료일, 릴리즈 승인 기록, 게이트 실패·첨부 누락 Release)을 수행하고 사내 위키에 기록한다.
- 일반 코드·의존성 PR, 릴리즈 게시·승인, 정책 예외(위험 수용) 승인 권한은 없다.

### Project Lead

- 프로젝트 범위와 대외 책임을 맡는다.
- 릴리즈(GitHub Environment `release`)와 정책 예외(`docs/supply-chain/exceptions.md`)를 승인한다.
- Maintainer와 함께 코드·의존성 PR을 리뷰·승인할 수 있다(CODEOWNERS). 두 사람 중 PR 작성자가 아닌 1명이 승인한다.
- 예외: 릴리즈 실행 승인(`release` Environment)은 Project Lead가 게시하고 본인이 승인한다. 승인 기록은 월간 점검에서 확인한다.
- 합의와 표결의 교착 상태에서 최종 근거를 기록하고 결정한다.
- 긴급결정을 독단적 상시 권한으로 사용하지 않는다.

현재 명단은 MAINTAINERS.md에서 관리한다.

### GitHub 권한 매핑

| 역할 | GitHub 권한 | 비고 |
|---|---|---|
| Contributor | read (fork 후 PR) | |
| Reviewer | triage | |
| Maintainer | maintain | main Ruleset 우회 불가 |
| 공급망 관리자 | write | 거버넌스·공급망 CI 경로 Code Owner, main Ruleset 우회 불가 |
| Project Lead | admin | `release` Environment 승인자, 예외 파일 Code Owner |

## 4. 의사결정 등급

| 등급 | 예시 | 기본 절차 |
|---|---|---|
| 일상 | 버그, 문서, 내부 리팩터링 | PR + CODEOWNERS 승인 + CI 통과 |
| 중요 | 새 의존성·버전 변경, CI·게이트 기준 변경, 저장소 설정 | PR + Maintainer 승인 + 공급망 PR 점검 통과, CI·게이트 변경은 Project Lead 또는 공급망 관리자 승인 |
| 중대 | 호환성 파괴, 라이선스, 거버넌스, 정책 예외 승인 | 제안 이슈 + 7일 의견수렴 + Project Lead 승인 + 결정기록 |
| 긴급 | 취약점, 자격증명 노출 | 제한 채널 임시조치 + 5영업일 내 사후기록 |

## 5. 합의와 표결

1. 합의는 중대한 미해결 반대가 없고 제안자가 합리적 우려를 처리한 상태를 뜻한다.
2. 합의를 우선하며 정해진 검토기간 동안 의견을 받는다.
3. 기간 후에도 합의되지 않으면 활동 중 Maintainer와 Project Lead의 과반으로 결정한다.
4. 가부동수이면 Project Lead가 근거를 남기고 결정한다.
5. 표결 결과, 반대 의견과 후속조치를 결정기록에 남긴다.

## 6. 제안과 결정기록

- 중요한 제안은 GitHub Issue에서 시작한다.
- 중대 결정과 공급망 게이트 기준 변경은 `docs/decisions/` 양식(GDR)으로 기록한다.
- 정책 예외는 `docs/supply-chain/exceptions.md`와 사내 예외 승인대장에 같은 번호로 기록한다.

## 7. 역할 부여

- Reviewer 후보는 최근 6개월의 지속적인 기여와 신뢰할 수 있는 리뷰를 보여야 한다.
- Maintainer 후보는 기존 Maintainer 또는 Project Lead의 추천을 받고 7일의 의견기간을 거친다.
- 코드뿐 아니라 문서, 리뷰, 사용자 지원, 보안 기여를 인정한다.
- 결정과 근거를 nomination 이슈에 기록한다.

## 8. 휴면·사임·해임

- 6개월간 활동이 없으면 연락 후 Reviewer·Maintainer를 emeritus로 전환할 수 있다.
- 자발적 사임은 이슈 또는 지정 연락처로 알린다.
- 보안사고, 권한 오용, 중대한 행동강령 위반 시 보호를 위해 권한을 임시 회수할 수 있다.
- 퇴사·이동 시 Project Lead가 GitHub 권한을 회수하고 MAINTAINERS.md를 갱신한다.

## 9. 이해충돌

결정 당사자는 고용, 투자, 계약 또는 개인관계를 공개한다. 직접적 이해충돌이 있는 경우
표결과 최종 승인에서 회피한다.

## 10. 분쟁과 상향

- 기술적 이견: Reviewer → Maintainer → Project Lead 순으로 상향한다.
- 행동강령 사건: CODE_OF_CONDUCT.md의 비공개 신고 채널을 사용한다.
- 보안 사건: SECURITY.md의 비공개 신고 채널을 사용한다.
- 당사자는 자신에 대한 신고의 단독 결정권자가 될 수 없다.

## 11. 회의와 투명성

- 정기회의: 별도 정기회의 없이 이슈·PR로 운영한다. 분기 1회 운영 점검을 사내 위키에 기록한다.
- 보안·개인정보·인사 사안을 제외한 결정은 공개한다.

## 12. 변경과 정기검토

- 이 문서 변경은 PR, 최소 7일 의견수렴과 Maintainer와 Project Lead의 승인을 필요로 한다.
- 매년 10월 실제 역할·권한·절차와 문서의 일치 여부를 검토한다.
- 외부 Maintainer가 2명 이상이 되면 위원회형 또는 위임형 거버넌스로의 전환을 검토한다.

## 13. 연락처

- 일반 문의: GitHub Issue
- 거버넌스 문의: jay@solbox.com
- 보안 신고: SECURITY.md 참조
- 행동강령 신고: CODE_OF_CONDUCT.md 참조
