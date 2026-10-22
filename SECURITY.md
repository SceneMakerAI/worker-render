# Security Policy

## 지원 버전

가장 최근 릴리즈와 main 브랜치를 지원한다.

## 취약점 신고

공개 이슈에 올리지 말고 다음 비공개 채널로 신고한다.

- GitHub: 저장소의 **Security → Report a vulnerability** (Private vulnerability reporting)
- 이메일: jay@solbox.com (제목에 `[worker-render security]`)

신고에는 영향 버전, 재현 방법, 영향 범위를 적어 주면 좋다.

## 처리 절차

1. 접수 확인: 3영업일 이내
2. 영향 평가와 임시조치: Maintainer와 Project Lead가 제한된 채널에서 진행
3. 조치 기한: Critical 10일, High 30일 (솔박스 공급망 관리 정책)
4. 수정 릴리즈 후 공개 가능한 범위에서 Security Advisory로 공지

## 의존성 취약점

이 저장소는 CI에서 BomLens로 SBOM과 취약점을 점검한다(`.github/workflows/supply-chain-*.yml`).
기준을 넘는 취약점이 있으면 릴리즈에 SBOM·고지패키지가 게시되지 않고 Release에 "사용 금지" 표시(Pre-release)가 붙는다. 위험 수용은 `docs/supply-chain/exceptions.md`에
승인자와 만료일을 남긴 경우에만 허용한다.
