#!/usr/bin/env python3
"""
분할 결과 병합기

Subagent가 생성한 split_part_*.json 파일들을 하나의 split.json으로 병합합니다.
"""

import argparse
import json
from pathlib import Path


def _normalize(data, filename: str) -> list[dict]:
    """
    에이전트가 다양한 형식으로 출력할 수 있으므로 정규화한다.

    지원 형식:
      1) [{"sentence_idx": N, "parts": [...]}]          — 정상
      2) {"sentences": [{"idx": N, "parts": [...]}]}    — dict 래핑 + idx 키
      3) {"sentences": [{"sentence_idx": N, "parts": [...]}]}  — dict 래핑
      4) [{"idx": N, "parts": [...]}]                   — idx 키만 다름
    """
    # dict 래핑 해제: {"sentences": [...]} 또는 {"results": [...]} 등
    if isinstance(data, dict):
        for key in ("sentences", "results", "data", "splits"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                print(f"  ℹ️ {filename}: dict 래핑 해제 (key={key})")
                break
        else:
            print(f"  ⚠️ {filename}: 인식 불가 dict 형식, 스킵")
            return []

    if not isinstance(data, list):
        print(f"  ⚠️ {filename}: 예상치 못한 형식, 스킵")
        return []

    # 키 정규화: "idx" → "sentence_idx"
    normalized = []
    for item in data:
        if not isinstance(item, dict) or "parts" not in item:
            continue
        if "sentence_idx" not in item and "idx" in item:
            item["sentence_idx"] = item.pop("idx")
        normalized.append(item)

    return normalized


def merge_splits(
    chunks_dir: str | Path,
    output_path: str | Path
) -> list:
    """
    split_part_*.json 파일들을 병합합니다.

    Args:
        chunks_dir: 청크 파일이 있는 디렉토리
        output_path: 출력 파일 경로 (split.json)

    Returns:
        병합된 결과 리스트
    """
    chunks_dir = Path(chunks_dir)
    output_path = Path(output_path)

    # split_part_*.json 파일 찾기
    part_files = sorted(chunks_dir.glob("split_part_*.json"))

    if not part_files:
        print("⚠️ 병합할 파일이 없습니다.")
        # 빈 배열 저장
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []

    print(f"📦 {len(part_files)}개 파일 병합")

    # 모든 파트 읽기
    merged = []
    for part_file in part_files:
        print(f"  읽는 중: {part_file.name}")
        with open(part_file, "r", encoding="utf-8") as f:
            part_data = json.load(f)

        items = _normalize(part_data, part_file.name)
        merged.extend(items)

    # sentence_idx 기준 정렬
    merged.sort(key=lambda x: x.get("sentence_idx", 0))

    # 결과 저장
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"✓ 병합 완료: {output_path} ({len(merged)}개 문장)")

    return merged


def main():
    parser = argparse.ArgumentParser(description="분할 결과 병합기")
    parser.add_argument("chunks_dir", help="청크 디렉토리 경로 (_video/chunks)")
    parser.add_argument("-o", "--output", required=True, help="출력 파일 경로 (split.json)")

    args = parser.parse_args()

    merge_splits(args.chunks_dir, args.output)


if __name__ == "__main__":
    main()
