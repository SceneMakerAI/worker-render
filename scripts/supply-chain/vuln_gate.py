#!/usr/bin/env python3
"""취약점 게이트 + 예외 승인 연동 (가이드라인 3장 7절)

BomLens 보안 리포트(_security.json)의 취약점 중 기준 심각도 이상을
docs/supply-chain/exceptions.md 의 "유효한" 예외와 대조한다.

  - 유효한 예외: 상태가 '유효', 승인자 기재, 만료일이 오늘 이후
  - 예외가 없거나 만료된 취약점이 하나라도 있으면 실패(종료 코드 1)
  - 보안 리포트가 없으면 판정 불가로 실패(종료 코드 2). 살펴보지 못한 스캔을
    통과시키지 않는다.

사용법:
  python3 vuln_gate.py --security <..._security.json> [--severity critical|high|medium|low]
                       [--exceptions docs/supply-chain/exceptions.md] [--report-only] [--redact]

--redact(공개 저장소): 로그·요약에 건수와 적용된 예외번호만 남긴다.

--report-only: 결과만 기록하고 실패시키지 않는다(관찰 모드).
결과는 표준 출력과 GitHub Step Summary($GITHUB_STEP_SUMMARY)에 남고,
--json-out 을 주면 판정 결과를 JSON으로 저장한다(완료 증거용).
"""
import argparse
import datetime
import json
import os
import re
import sys

ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


def load_findings(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out, seen = [], set()
    for res in data.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            key = (v.get("VulnerabilityID"), v.get("PkgName"), v.get("InstalledVersion"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"id": key[0], "pkg": key[1], "ver": key[2],
                        "sev": (v.get("Severity") or "UNKNOWN").upper(),
                        "fix": v.get("FixedVersion") or ""})
    return out


ID_RE = r"^(CVE-\d{4}-\d+|GHSA-[\w-]+)$"


def load_exceptions(path, today):
    """exceptions.md 표에서 취약점 예외를 읽는다. 열 이름으로 찾으므로 열 순서는 바뀌어도 된다."""
    valid, invalid = {}, []
    if not path or not os.path.exists(path):
        return valid, invalid
    header = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        ident = row.get("식별자", row.get("CVE/식별자", "")).strip()
        if not re.match(ID_RE, ident, re.I):
            continue
        ident = ident.upper()
        exp = row.get("만료일", "")
        ok = (row.get("상태") == "유효" and row.get("승인자") and re.match(r"^\d{4}-\d{2}-\d{2}$", exp) and exp >= today)
        if ok:
            valid[ident] = row
        else:
            invalid.append((ident, row.get("예외번호", ""), "만료" if exp and exp < today else "상태·승인자·만료일 확인"))
    return valid, invalid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--security")
    ap.add_argument("--severity", default="critical", choices=["critical", "high", "medium", "low"])
    ap.add_argument("--exceptions", default="docs/supply-chain/exceptions.md")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--json-out")
    ap.add_argument("--redact", action="store_true",
                    help="공개 저장소용: 로그·요약에 건수만 남기고 식별자·구성요소는 숨긴다 (--json-out에는 전체 기록)")
    a = ap.parse_args()
    if not a.security:
        ap.error("--security 가 필요합니다")

    today = datetime.date.today().isoformat()
    lines = [f"## 취약점 게이트 (기준: {a.severity.upper()} 이상{', 관찰 모드' if a.report_only else ''})", ""]

    if not os.path.exists(a.security):
        lines.append(f"판정 불가: 보안 리포트가 없습니다 ({a.security})")
        emit(lines)
        sys.exit(0 if a.report_only else 2)

    findings = load_findings(a.security)
    valid, invalid = load_exceptions(a.exceptions, today)

    def exc(f):
        return valid.get((f["id"] or "").upper())

    cut = ORDER[a.severity.upper()]
    target = [f for f in findings if ORDER.get(f["sev"], 0) >= cut]
    blocked = [f for f in target if not exc(f)]
    excepted = [f for f in target if exc(f)]

    counts = {s: sum(1 for f in findings if f["sev"] == s) for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}
    lines.append("전체: " + " · ".join(f"{k.title()} {v}" for k, v in counts.items()))
    lines.append(f"기준 이상 {len(target)}건 → 예외 승인 {len(excepted)}건, 차단 {len(blocked)}건")
    lines.append("")
    if a.redact and target:
        lines.append("상세 목록은 공개 로그에 남기지 않습니다 (--redact). 담당자는 비공개 산출물·사내 원장을 확인하세요.")
        nos = sorted({exc(f).get("예외번호", "") for f in excepted} - {""})
        if nos:
            lines.append("적용된 예외번호: " + ", ".join(nos))
    elif target:
        lines += ["| 판정 | 식별자 | 구성요소 | 심각도 | 수정 버전 | 예외번호 |", "|---|---|---|---|---|---|"]
        for f in sorted(target, key=lambda x: (-ORDER.get(x["sev"], 0), x["pkg"])):
            ex = exc(f)
            lines.append(f"| {'예외' if ex else '차단'} | {f['id']} | {f['pkg']} {f['ver']} | {f['sev']} | {f['fix']} | "
                         f"{ex.get('예외번호', '') if ex else ''} |")
    for ident, no, why in invalid:
        lines.append(f"- 예외 무효: {no} {'(식별자 숨김)' if a.redact else ident} ({why})")

    result = {"date": today, "severity": a.severity, "report_only": a.report_only, "counts": counts,
              "blocked": blocked, "excepted": [dict(f, exception=exc(f).get("예외번호")) for f in excepted],
              "verdict": "pass" if not blocked else ("warn" if a.report_only else "fail")}
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    lines.append("")
    lines.append(f"**판정: {result['verdict']}**")
    emit(lines)
    sys.exit(1 if blocked and not a.report_only else 0)


def emit(lines):
    text = "\n".join(lines)
    print(text)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
