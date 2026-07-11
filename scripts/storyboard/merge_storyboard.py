#!/usr/bin/env python3
"""
스토리보드 청크 병합 + 검증 — 장편(다장·수백 씬) 파이프라인용.

장편(3~4만자)은 STORYBOARD를 장 단위로 서브에이전트에 위임해 짜므로, 각 장이 낸
storyboard 청크(scenes[])를 하나로 합치고 무결성을 검증해야 한다. 단일 세션에서 통으로
authored 한 storyboard.json 검수에도 --check로 그대로 쓴다 (빈 씬·문장 틈을 자동 검출).

검증 항목:
  1) 씬 id     — 중복 없음, 1..N 연속(경고 가능)
  2) sentences — 각 씬 [a,b] a<=b, 전체가 0..max 를 빠짐없이·겹침없이 타일링
  3) cast      — 모든 id(:variant 제외)가 characters.json 레지스트리에 존재
  4) location  — null 또는 locations.json 키에 존재

Usage:
    # 청크 병합 → {P}/storyboard.json (검증 통과 시에만 기록)
    python3 scripts/storyboard/merge_storyboard.py {P} --chunks ch01.json ch02.json ...
    python3 scripts/storyboard/merge_storyboard.py {P} --chunks-dir {P}/_chunks

    # 기존 storyboard.json 검증만 (병합 없음)
    python3 scripts/storyboard/merge_storyboard.py {P} --check
"""
import argparse
import json
import pathlib
import sys


def load_json(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def scenes_of(board):
    return board["scenes"] if isinstance(board, dict) and "scenes" in board else board


def registry_ids(obj):
    """characters/locations.json에서 '_' 로 시작하지 않는 최상위 키 = 유효 id 집합."""
    root = obj
    for wrap in ("characters", "locations"):
        if isinstance(obj, dict) and wrap in obj and isinstance(obj[wrap], dict):
            root = obj[wrap]
            break
    return {k for k in root if not k.startswith("_")}, root


def validate(scenes, char_ids, loc_keys, char_root, sent_total=None):
    """검증 → (errors[], warnings[]). errors 있으면 기록/사용 금지."""
    errors, warnings = [], []

    # 1) 씬 id
    ids = [s.get("id") for s in scenes]
    if any(i is None for i in ids):
        errors.append("id 없는 씬 존재")
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"중복 씬 id: {sorted(dupes)}")
    ordered = [i for i in ids if isinstance(i, int)]
    if ordered and ordered != list(range(ordered[0], ordered[0] + len(ordered))):
        warnings.append(f"씬 id가 연속이 아님: {ordered}")

    # 2) sentences 타일링
    ranges = []
    for s in scenes:
        sent = s.get("sentences")
        if not (isinstance(sent, list) and len(sent) == 2 and all(isinstance(x, int) for x in sent)):
            errors.append(f"씬 {s.get('id')}: sentences 누락/형식오류 ({sent})")
            continue
        a, b = sent
        if a > b:
            errors.append(f"씬 {s.get('id')}: sentences 역순 [{a},{b}]")
        ranges.append((a, b, s.get("id")))
    if ranges and not any("sentences" in e for e in errors):
        ranges_sorted = sorted(ranges)
        cursor = 0
        for a, b, sid in ranges_sorted:
            if a > cursor:
                errors.append(f"문장 {cursor}..{a - 1} 누락 (씬 {sid} 앞에 빈 구간)")
            elif a < cursor:
                errors.append(f"씬 {sid}: 문장 {a}..{min(b, cursor - 1)} 이전 씬과 겹침")
            cursor = max(cursor, b + 1)
        if sent_total is not None and cursor != sent_total:
            errors.append(f"문장 커버리지 {cursor} ≠ sentences.json 총수 {sent_total} (끝 {sent_total - cursor}문장 누락/초과)")

    # 3) cast id
    for s in scenes:
        for c in s.get("cast", []):
            base = c.split(":")[0]
            if base not in char_ids:
                errors.append(f"씬 {s.get('id')}: cast '{c}' → id '{base}' 가 characters.json 에 없음")
            elif ":" in c:
                v = c.split(":")[1]
                variants = (char_root.get(base, {}) or {}).get("variants") or (char_root.get(base, {}) or {}).get("variant") or {}
                if isinstance(variants, dict) and variants and v not in variants:
                    warnings.append(f"씬 {s.get('id')}: '{c}' variant '{v}' 미정의 (있는 것: {list(variants)})")

    # 4) location
    for s in scenes:
        loc = s.get("location")
        if loc is not None and loc not in loc_keys:
            errors.append(f"씬 {s.get('id')}: location '{loc}' 가 locations.json 에 없음")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--chunks", nargs="*", type=pathlib.Path, help="병합할 청크 storyboard JSON들(순서대로)")
    ap.add_argument("--chunks-dir", type=pathlib.Path, help="청크 폴더(*.json 정렬해 병합)")
    ap.add_argument("--check", action="store_true", help="기존 storyboard.json 검증만(병합 없음)")
    ap.add_argument("--out", type=pathlib.Path, help="출력 경로(기본 {P}/storyboard.json)")
    args = ap.parse_args()

    P = args.project_dir.resolve()
    char_ids, char_root = registry_ids(load_json(P / "characters.json"))
    loc_keys, _ = registry_ids(load_json(P / "locations.json"))
    sent_total = None
    sfile = P / "_video" / "sentences.json"
    if sfile.exists():
        sd = load_json(sfile)
        sent_total = len(sd["sentences"] if isinstance(sd, dict) and "sentences" in sd else sd)

    if args.check:
        scenes = scenes_of(load_json(P / "storyboard.json"))
        src = "storyboard.json (기존)"
    else:
        files = []
        if args.chunks_dir:
            files = sorted(args.chunks_dir.glob("*.json"))
        if args.chunks:
            files += list(args.chunks)
        if not files:
            print("병합할 청크가 없다 — --chunks 또는 --chunks-dir 필요 (검증만은 --check)", file=sys.stderr)
            return 2
        scenes = []
        for f in files:
            scenes += scenes_of(load_json(f))
        src = f"{len(files)}개 청크 병합"

    errors, warnings = validate(scenes, char_ids, loc_keys, char_root, sent_total)

    print(f"[{src}] 씬 {len(scenes)}개" + (f", 문장총수 {sent_total}" if sent_total else ""))
    for w in warnings:
        print(f"  ⚠️  {w}")
    if errors:
        print(f"\n✗ 검증 실패 — {len(errors)}건:")
        for e in errors:
            print(f"  ✗ {e}")
        print("\n위반한 부분만 고쳐 다시 실행하세요. (병합 시 기록 안 함)")
        return 1

    print("  ✓ 씬 id 연속 · 문장 빠짐없이/겹침없이 커버 · cast/location 유효")
    if not args.check:
        out = args.out or (P / "storyboard.json")
        out.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ 기록: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
