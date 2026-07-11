"""대본 제작 제약 기계 검증 (script-constraints.md의 검증 도구).

사용법:
    python3 scripts/script/validate_script.py {P}/script.txt --target 30000,40000
    python3 scripts/script/validate_script.py {P}/_script/chapters --chapter-target 2500,3500

검사 항목:
    - 공백 제외 글자수 (목표 범위)
    - 아라비아 숫자 / 로마자 (0건이어야 함 — tts_map 생략 조건)
    - 20자 초과 호흡 (쉼표·구두점 구간, 공백 제외 — vrew 자막 줄 기준)
    - 문어체 어미 (였다/하였다/이었다/거늘/허나)
    - 경어체 이탈 의심 (~다. 종결 — 대사 밖, 경고만)
    - 문단 수

종료 코드: 위반(에러) 있으면 1, 없으면 0. 경고는 실패로 치지 않는다.
"""

import argparse
import os
import re
import sys

QUOTE_RE = re.compile(r'["“][^"“”]*["”]')
BREATH_SPLIT_RE = re.compile(r'[,.!?…:;"“”]')
MUNEOCHE_RE = re.compile(r'(하였다|이었다|거늘|허나)(?=[\s".,!?…”)]|$)|(?<![니습])였다(?=[\s".,!?…”)]|$)')
PLAIN_END_RE = re.compile(r'([가-힣])다[.!?…]')


def no_space_len(s):
    return len(re.sub(r"\s", "", s))


def check_text(text, max_breath):
    """반환: (errors, warnings) — 각 항목 (줄번호, 코드, 내용)."""
    errors, warnings = [], []
    lines = text.splitlines()

    for ln, line in enumerate(lines, 1):
        for m in re.finditer(r"[0-9]+", line):
            errors.append((ln, "숫자", f"'{m.group()}' → 한글 표기"))
        for m in re.finditer(r"[A-Za-z]+", line):
            errors.append((ln, "영어", f"'{m.group()}' → 한글 표기"))

        for seg in BREATH_SPLIT_RE.split(line):
            seg_len = no_space_len(seg)
            if seg_len > max_breath:
                errors.append((ln, "호흡", f"{seg_len}자 > {max_breath}자: \"{seg.strip()[:30]}…\""))

        for m in MUNEOCHE_RE.finditer(line):
            errors.append((ln, "문어체", f"'{m.group()}' — 경어체 구술로"))

        # 대사(따옴표 안)는 반말 허용 — 따옴표 밖 평서 종결만 경고
        outside = QUOTE_RE.sub("", line)
        for m in PLAIN_END_RE.finditer(outside):
            if m.group(1) != "니":  # ~습니다/~입니다 계열 제외
                warnings.append((ln, "종결", f"'…{outside[max(0, m.start()-8):m.end()]}' — 경어체 확인"))

    return errors, warnings


def report_one(path, text, max_breath, target):
    total = no_space_len(text)
    paragraphs = len([p for p in re.split(r"\n\s*\n", text) if p.strip()])
    errors, warnings = check_text(text, max_breath)

    if target:
        lo, hi = target
        if not (lo <= total <= hi):
            errors.append((0, "분량", f"공백 제외 {total:,}자 — 목표 {lo:,}~{hi:,}자 벗어남"))

    status = "✗" if errors else "✓"
    print(f"\n{status} {path} — 공백 제외 {total:,}자 (약 {total/240:.0f}분), 문단 {paragraphs}개, "
          f"에러 {len(errors)} / 경고 {len(warnings)}")

    by_code = {}
    for ln, code, msg in errors:
        by_code.setdefault(code, []).append((ln, msg))
    for code, items in by_code.items():
        print(f"  [{code}] {len(items)}건")
        for ln, msg in items[:8]:
            loc = f"L{ln}" if ln else "-"
            print(f"    {loc}: {msg}")
        if len(items) > 8:
            print(f"    … 외 {len(items) - 8}건")
    if warnings:
        print(f"  [경고] {len(warnings)}건 (실패 아님)")
        for ln, code, msg in warnings[:5]:
            print(f"    L{ln} ({code}): {msg}")
        if len(warnings) > 5:
            print(f"    … 외 {len(warnings) - 5}건")

    return len(errors) == 0, total


def parse_range(s):
    lo, hi = s.split(",")
    return int(lo), int(hi)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="대본 제작 제약 검증")
    parser.add_argument("path", help="script.txt 또는 chapters 폴더")
    parser.add_argument("--target", type=parse_range, default=None, help="전체 분량 min,max (공백 제외)")
    parser.add_argument("--chapter-target", type=parse_range, default=None, help="장별 분량 min,max (폴더 모드)")
    parser.add_argument("--max-breath", type=int, default=20, help="호흡 최대 글자수 (기본 20)")
    args = parser.parse_args()

    ok_all, grand_total = True, 0

    if os.path.isdir(args.path):
        files = sorted(
            f for f in os.listdir(args.path)
            if f.endswith((".md", ".txt")) and not f.startswith((".", "_"))
        )
        if not files:
            print(f"검사할 파일 없음: {args.path}")
            sys.exit(1)
        for fname in files:
            fpath = os.path.join(args.path, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
            ok, total = report_one(fname, text, args.max_breath, args.chapter_target)
            ok_all &= ok
            grand_total += total
        print(f"\n합계: 공백 제외 {grand_total:,}자 (약 {grand_total/240:.0f}분)")
        if args.target:
            lo, hi = args.target
            if not (lo <= grand_total <= hi):
                print(f"✗ 전체 분량 목표 {lo:,}~{hi:,}자 벗어남")
                ok_all = False
    else:
        with open(args.path, encoding="utf-8") as f:
            text = f.read()
        ok_all, _ = report_one(args.path, text, args.max_breath, args.target)

    print("\n" + ("통과 — 다음 단계 진행 가능" if ok_all else "위반 있음 — 수정 후 재검증"))
    sys.exit(0 if ok_all else 1)
