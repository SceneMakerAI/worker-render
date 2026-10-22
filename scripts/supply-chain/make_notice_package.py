#!/usr/bin/env python3
"""BomLens SBOM(_bom.json) -> 고지패키지(oss-docs) 자동 생성

사용법 (공급망관리 폴더에서):
  python3 _도구/make_notice_package.py "3. 저장소별 SBOM 현황/<저장소>_<버전>/<저장소>_<버전>_bom.json"

  선택 옵션
    --contact "<문의처>"   고지문의 문의처 (기본: 솔박스 (Solbox) jay@solbox.com)
    --out <폴더>                         결과 위치 (기본: 같은 작업 폴더의 '7. 고지패키지')

만드는 것: 7. 고지패키지/<저장소>_<버전>-oss-docs/ 와 같은 이름의 .zip
  OSS_NOTICE.txt          구성요소 목록 (이름·버전·라이선스·저작권 표기·라이선스 파일)
  licenses/               패키지에서 꺼낸 라이선스 원문
  THIRD_PARTY_NOTICES.txt 패키지에 NOTICE 파일이 있으면 그 원문
  확인필요.txt            사람이 봐야 하는 항목만 (없으면 '없음')

동작
  - PyPI(pkg:pypi), npm(pkg:npm) 구성요소: 배포 파일을 내려받아 LICENSE·NOTICE·COPYING 등을 꺼냄
    (내려받은 파일은 ~/.cache/oss-notice 에 보관해 다음 실행부터 재사용)
  - SBOM 라이선스가 비표준('BSD License' 등)이면 패키지 메타데이터·라이선스 원문으로 SPDX를 판별
  - 그 밖의 유형(GitHub, OS 패키지 등)은 자동 수집하지 않고 확인필요.txt에 올림
  - 인터넷 연결 필요. 다시 실행하면 같은 폴더를 새로 만듦.
"""
import argparse
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile

CACHE = os.path.expanduser("~/.cache/oss-notice")
LIC_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS|COPYRIGHT|THIRD[-_]PARTY[-_]NOTICES?)([-_.].*)?$", re.I)
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EPL|CDDL|SSPL|OSL|EUPL|CC-BY-SA)", re.I)
SPDX_TOKEN = re.compile(r"^[A-Za-z0-9.+-]+$")
NFC = lambda s: unicodedata.normalize("NFC", s)


# ---------- 내려받기 ----------
def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "oss-notice-tool"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except Exception:
        # macOS 파이썬 인증서 문제 등에 대비해 curl로 한 번 더 시도
        out = subprocess.run(["curl", "-fsSL", "--max-time", "120", url], capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"다운로드 실패: {url}")
        return out.stdout


def cached(url, fname):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, fname)
    if not os.path.exists(path):
        data = fetch(url)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


BIG = 20 * 1024 * 1024  # 이보다 큰 wheel/zip은 통째로 받지 않고 필요한 파일만 원격으로 읽음


def fetch_range(url, start, end):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "oss-notice-tool", "Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except Exception:
        out = subprocess.run(["curl", "-fsSL", "--max-time", "120", "-r", f"{start}-{end}", url], capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"다운로드 실패: {url}")
        return out.stdout


class RemoteFile(io.RawIOBase):
    """HTTP Range 요청으로 원격 파일을 seek/read 하는 읽기 전용 파일 (zipfile용)"""
    def __init__(self, url, size):
        self.url, self.size, self.pos, self.cache = url, size, 0, {}

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        blk = 1 << 18
        out = b""
        while n > 0:
            b0 = self.pos // blk
            if b0 not in self.cache:
                self.cache[b0] = fetch_range(self.url, b0 * blk, min(self.size, (b0 + 1) * blk) - 1)
            data = self.cache[b0][self.pos - b0 * blk:]
            take = data[:n]
            out += take
            self.pos += len(take)
            n -= len(take)
            if not take:
                break
        return out


def archive_files(url, filename, size):
    """배포 파일에서 라이선스 파일과 메타데이터를 꺼냄. 큰 zip/wheel은 필요한 부분만 원격으로 읽음"""
    os.makedirs(CACHE, exist_ok=True)
    memo = os.path.join(CACHE, filename + ".licenses.json")
    if os.path.exists(memo):
        with open(memo, encoding="utf-8") as f:
            m = json.load(f)
        return m["files"], m["metadata"]
    if size and size > BIG and filename.endswith((".whl", ".zip")):
        files, metadata = read_zip(zipfile.ZipFile(RemoteFile(url, size)))
    else:
        files, metadata = read_archive(cached(url, filename))
    with open(memo, "w", encoding="utf-8") as f:
        json.dump({"files": files, "metadata": metadata}, f, ensure_ascii=False)
    return files, metadata


def pypi_archive(name, version):
    try:
        meta = json.loads(fetch(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json"))
    except RuntimeError:
        if "+" not in version:
            raise
        # 예: torch 2.9.1+cu128 은 PyPI에 없으므로 같은 버전의 기본 배포본에서 라이선스 파일을 가져옴
        meta = json.loads(fetch(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version.split('+')[0])}/json"))
    urls = meta.get("urls") or []
    pick = next((u for u in urls if u.get("packagetype") == "bdist_wheel"), None) or \
        next((u for u in urls if u.get("packagetype") == "sdist"), None)
    if not pick:
        raise RuntimeError("PyPI에 배포 파일 없음")
    return pick["url"], pick["filename"], pick.get("size") or 0


def npm_archive(name, version):
    meta = json.loads(fetch(f"https://registry.npmjs.org/{name.replace('/', '%2f')}/{urllib.parse.quote(version)}"))
    url = (meta.get("dist") or {}).get("tarball")
    if not url:
        raise RuntimeError("npm에 tarball 없음")
    return url, name.replace("/", "__") + "-" + version + ".tgz", 0


# ---------- 압축 파일에서 라이선스 파일 꺼내기 ----------
def wanted(path):
    parts = path.strip("/").split("/")
    base = parts[-1]
    if not base:
        return False
    if ".dist-info" in path:
        return "/licenses/" in path or (len(parts) == 2 and LIC_FILE.match(base))
    if any(p.upper() in ("LICENSES", "LICENSE") for p in parts[:-1]) and len(parts) <= 3:
        return True
    return len(parts) <= 2 and bool(LIC_FILE.match(base))


def read_zip(z):
    files, metadata = {}, ""
    for n in z.namelist():
        if n.endswith(".dist-info/METADATA"):
            metadata = z.read(n).decode("utf-8", "replace")
        elif not n.endswith("/") and wanted(n):
            files[n] = z.read(n).decode("utf-8", "replace")
    return files, metadata


def read_archive(path):
    """{상대경로: 텍스트}와 메타데이터 텍스트를 돌려줌"""
    files, metadata = {}, ""
    if path.endswith(".whl") or path.endswith(".zip"):
        return read_zip(zipfile.ZipFile(path))
    else:
        t = tarfile.open(path)
        for m in t.getmembers():
            if not m.isfile():
                continue
            if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO"):
                metadata = t.extractfile(m).read().decode("utf-8", "replace")
            elif wanted(m.name):
                files[m.name] = t.extractfile(m).read().decode("utf-8", "replace")
    return files, metadata


# ---------- 라이선스·저작권 판별 ----------
def sbom_license(comp):
    out = []
    for e in comp.get("licenses") or []:
        if "expression" in e:
            out.append(e["expression"])
        else:
            lic = e.get("license") or {}
            out.append(lic.get("id") or lic.get("name") or "")
    out = [x for x in out if x]
    return " AND ".join(dict.fromkeys(out))


def is_standard(expr):
    if not expr:
        return False
    toks = [t.strip() for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", expr) if t.strip()]
    return bool(toks) and all(SPDX_TOKEN.match(t) for t in toks)


def guess_from_text(text):
    """라이선스 원문에서 알아볼 수 있는 라이선스를 모두 찾아 AND로 연결"""
    t = re.sub(r"\s+", " ", text)
    found = []
    if "Apache License" in t and "Version 2.0" in t:
        found.append("Apache-2.0")
    if "Permission is hereby granted, free of charge" in t:
        found.append("MIT")
    if "Redistribution and use in source and binary forms" in t:
        found.append("BSD-3-Clause" if re.search(r"endorse or promote", t, re.I) else "BSD-2-Clause")
    if "Mozilla Public License" in t and "2.0" in t:
        found.append("MPL-2.0")
    if "PYTHON SOFTWARE FOUNDATION LICENSE" in t.upper():
        found.append("PSF-2.0")
    if "Permission to use, copy, modify, and/or distribute this software for any" in t:
        found.append("ISC")
    return " AND ".join(found)


META_MAP = [(r"^BSD[- ]?3", "BSD-3-Clause"), (r"^BSD[- ]?2", "BSD-2-Clause"), (r"^MIT( License)?$", "MIT"),
            (r"^Apache( Software)?( License)?,? ?(Version )?2(\.0)?", "Apache-2.0"), (r"^MPL[- ]?2", "MPL-2.0"),
            (r"^ISC( License)?$", "ISC")]


def meta_license(metadata):
    m = re.search(r"^License-Expression:\s*(.+)$", metadata, re.M)
    if m and is_standard(m.group(1).strip()):
        return m.group(1).strip()
    m = re.search(r"^License:\s*(.+)$", metadata, re.M)
    if m:
        v = m.group(1).strip()
        for pat, spdx in META_MAP:
            if re.match(pat, v, re.I):
                return spdx
    return ""


def std_tokens(expr):
    toks = [t.strip() for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", expr or "") if t.strip()]
    return [t for t in toks if SPDX_TOKEN.match(t)]


def main_license_text(files):
    """번들된 다른 라이선스가 아닌, 패키지 자체의 대표 라이선스 파일"""
    cands = [(p.count("/"), p) for p in files
             if re.match(r"^(LICEN[CS]E|COPYING)(\.\w+)?$", os.path.basename(p), re.I)]
    return files[sorted(cands)[0][1]] if cands else ""


def resolve_license(sbom_lic, metadata, files):
    """반환: (라이선스, 판별 근거, 사람 확인 사유)"""
    m = re.search(r"^License-Expression:\s*(.+)$", metadata, re.M)
    if m and is_standard(m.group(1).strip()) and "LicenseRef" not in m.group(1):
        return m.group(1).strip(), "패키지 메타데이터", ""
    if re.search(r"Proprietary", sbom_lic or "", re.I) or re.search(r"Proprietary", metadata[:3000], re.I):
        lic = "LicenseRef-NVIDIA-Proprietary" if re.search(r"NVIDIA", (sbom_lic or "") + metadata[:3000], re.I) else "LicenseRef-Proprietary"
        return lic, "독점 라이선스 표기", "독점(상용) 라이선스 → 재배포·납품 허용 조건(EULA) 확인 필요"
    if is_standard(sbom_lic):
        return sbom_lic, "", ""
    ml = meta_license(metadata)
    if ml:
        return ml, "패키지 메타데이터", ""
    known = std_tokens(sbom_lic)
    guess = guess_from_text(main_license_text(files))
    if guess and (not known or any(g in known for g in guess.split(" AND "))):
        why = "" if known else f"라이선스 원문으로 추정 ({guess}) → 확인 권장"
        return guess, "라이선스 원문", why
    if known:
        lic = " AND ".join(dict.fromkeys(known))
        return lic, "SBOM 표준 표기", f"비표준 표기 제외 후 {lic}로 표기 (원문 추정: {guess or '판별 불가'}) → 확인 권장"
    return sbom_lic or "미확인", "", f"라이선스 판별 불가 (SBOM 표기: {sbom_lic or '없음'})"


def copyrights(files):
    found = []
    for path, text in sorted(files.items(), key=lambda kv: ("NOTICE" in kv[0].upper(), kv[0])):
        for line in text.splitlines():
            s = line.strip().strip("#*/ ").strip()
            if re.match(r"^Copyright\s*(\(c\)|©|\d{4})", s, re.I) and "copyright notice" not in s.lower():
                s = s[:160]
                if s not in found:
                    found.append(s)
            if len(found) >= 3:
                return found
    return found


def walk(cs):
    for c in cs or []:
        yield c
        yield from walk(c.get("components"))


def safe(s):
    return re.sub(r"[^A-Za-z0-9._@+-]+", "_", s)


# ---------- 본체 ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bom")
    ap.add_argument("--out")
    ap.add_argument("--contact", default="솔박스 (Solbox) jay@solbox.com")
    a = ap.parse_args()

    bom = json.load(open(a.bom, encoding="utf-8"))
    root = (bom.get("metadata") or {}).get("component") or {}
    project = root.get("name") or os.path.basename(a.bom).split("_")[0]
    version = root.get("version") or ""

    if a.out:
        out_base = a.out
    else:
        work = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(a.bom))))
        cand = [d for d in os.listdir(work) if NFC(d).startswith("7.") and os.path.isdir(os.path.join(work, d))]
        out_base = os.path.join(work, cand[0]) if cand else os.path.dirname(os.path.abspath(a.bom))
    name = f"{project}_{version}-oss-docs" if version else f"{project}-oss-docs"
    out = os.path.join(out_base, name)
    os.makedirs(os.path.join(out, "licenses"), exist_ok=True)
    for old in os.listdir(os.path.join(out, "licenses")):
        try:
            os.remove(os.path.join(out, "licenses", old))
        except OSError:
            pass

    comps = [c for c in walk(bom.get("components")) if c.get("purl")]
    comps.sort(key=lambda c: (c.get("name") or "").lower())
    items, notices, review = [], [], []
    total = len(comps)
    for i, c in enumerate(comps, 1):
        purl = c["purl"]
        cname = f'{c["group"]}/{c["name"]}' if c.get("group") else c.get("name", "")
        cver = c.get("version", "")
        sys.stdout.write(f"\r  [{i}/{total}] {cname} {cver}".ljust(70))
        sys.stdout.flush()
        lic_sbom = sbom_license(c)
        files, metadata, err = {}, "", ""
        try:
            if purl.startswith("pkg:pypi/"):
                files, metadata = archive_files(*pypi_archive(c.get("name", ""), cver))
            elif purl.startswith("pkg:npm/"):
                pname = urllib.parse.unquote(purl[len("pkg:npm/"):].split("@" + cver)[0].split("?")[0])
                files, metadata = archive_files(*npm_archive(pname, cver))
            else:
                err = "자동 수집 미지원 유형 (" + purl.split("/")[0] + ")"
        except Exception as e:
            err = str(e)

        lic, how, lic_why = resolve_license(lic_sbom, metadata, files)
        saved = []
        for p, text in sorted(files.items()):
            base = os.path.basename(p)
            if re.match(r"NOTICE", base, re.I):
                notices.append((cname, cver, text))
                continue
            sub = p.split(".dist-info/")[-1] if ".dist-info/" in p else "/".join(p.split("/")[1:])
            fn = safe(f"{cname}-{cver}-{sub.replace('/', '_')}")
            if not fn.lower().endswith((".txt", ".md", ".rst")):
                fn += ".txt"
            with open(os.path.join(out, "licenses", fn), "w", encoding="utf-8") as f:
                f.write(text)
            saved.append(fn)
        cr = copyrights(files)

        reasons = []
        if err:
            reasons.append(err)
        elif not saved:
            reasons.append("패키지 안에 라이선스 파일 없음 → 저장소에서 직접 확보")
        if lic_why:
            reasons.append(lic_why)
        if COPYLEFT.search(lic):
            reasons.append("카피레프트 계열 → 수정 여부 확인, 수정했다면 소스 제공 방법 기재")
        if reasons:
            review.append((cname, cver, reasons))
        items.append(dict(name=cname, ver=cver, lic=lic, how=how, sbom=lic_sbom, cr=cr, files=saved))
    sys.stdout.write("\r".ljust(72) + "\r")

    today = datetime.date.today().isoformat()
    snap = version.startswith("main-")
    lines = [
        f"{project} 오픈소스 고지문 (Open Source Software Notice)",
        "",
        f"대상: {project} {version}",
        f"작성일: {today} · 근거: BomLens SBOM + 각 패키지의 라이선스 파일",
    ]
    if snap:
        lines.append("※ 스냅샷(커밋) 기준 산출물. 배포·납품용은 릴리즈 태그 기준으로 다시 생성한다.")
    lines += [
        "",
        "본 제품은 아래 오픈소스 소프트웨어를 포함합니다. 각 구성요소의 라이선스 전문은 licenses/ 폴더에,",
        "NOTICE 파일이 있는 구성요소의 NOTICE 원문은 THIRD_PARTY_NOTICES.txt 에 수록되어 있습니다.",
        "",
        "오픈소스 구성요소의 수정 여부: [수정 없음 / 수정 목록 별첨]",
        f"문의: {a.contact}",
        "=" * 80,
    ]
    for n, x in enumerate(items, 1):
        lic = x["lic"] + (f'  (SBOM 표기 "{x["sbom"]}" → {x["how"]} 기준)' if x["how"] else "")
        lines.append(f"{n:3d}. {x['name']} {x['ver']}")
        lines.append(f"     라이선스: {lic}")
        for c in (x["cr"] or ["저작권 표기: 라이선스 파일 참조"]):
            lines.append(f"     {c}")
        lines.append("     라이선스 파일: " + (", ".join("licenses/" + f for f in x["files"]) or "없음 (확인필요.txt 참조)"))
    with open(os.path.join(out, "OSS_NOTICE.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    tpn = os.path.join(out, "THIRD_PARTY_NOTICES.txt")
    if not notices and os.path.exists(tpn):
        try:
            os.remove(tpn)
        except OSError:
            pass
    if notices:
        with open(os.path.join(out, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8") as f:
            f.write("THIRD-PARTY NOTICES (각 구성요소 NOTICE 파일 원문)\n\n")
            for n, v, t in notices:
                f.write(f"==== {n} {v} ====\n{t.strip()}\n\n")

    rv = [f"{project} {version} 고지패키지 — 사람이 확인할 항목", ""]
    if not review:
        rv.append("없음")
    for n, v, rs in review:
        rv.append(f"- {n} {v}")
        rv += [f"    · {r}" for r in rs]
    rv += ["", "공통 확인: OSS_NOTICE.txt 머리말의 '수정 여부'와 '문의' 칸을 채운다."]
    with open(os.path.join(out, "확인필요.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rv) + "\n")

    zpath = shutil.make_archive(out, "zip", out_base, name)
    print(f"[{project} {version}] 구성요소 {len(items)}개 · 라이선스 파일 {sum(len(x['files']) for x in items)}개 · "
          f"NOTICE {len(notices)}건 · 확인 필요 {len(review)}건")
    print(f"  → {out}")
    print(f"  → {zpath}")


if __name__ == "__main__":
    main()
