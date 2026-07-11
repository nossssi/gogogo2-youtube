#!/usr/bin/env python3
"""
문장 분할용 청크 생성기

sentences_to_split.json을 chunk_size개씩 나눠서 청크 파일로 저장합니다.
"""

import argparse
import json
from pathlib import Path


def chunk_sentences(
    input_path: str | Path,
    output_dir: str | Path,
    chunk_size: int = 30
) -> dict:
    """
    sentences_to_split.json을 청크로 분할합니다.

    Args:
        input_path: sentences_to_split.json 경로
        output_dir: 청크 파일 저장 디렉토리
        chunk_size: 청크당 문장 수

    Returns:
        manifest 정보
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    # 입력 파일 읽기
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    settings = data.get("settings", {})
    sentences = data.get("sentences", [])

    total = len(sentences)
    print(f"📦 총 {total}개 문장")

    if total == 0:
        print("분할할 문장이 없습니다.")
        manifest = {"total": 0, "chunk_size": chunk_size, "chunk_count": 0, "files": []}
        manifest_path = output_dir / "chunk_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"✓ manifest 저장: {manifest_path}")
        return manifest

    # 청크 디렉토리 생성
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # 기존 청크 파일 정리
    for old_file in chunks_dir.glob("chunk_*.json"):
        old_file.unlink()
    for old_file in chunks_dir.glob("split_part_*.json"):
        old_file.unlink()

    # 청크 분할
    chunk_files = []
    for i in range(0, total, chunk_size):
        chunk_idx = i // chunk_size + 1
        chunk_sentences = sentences[i:i + chunk_size]

        chunk_data = {
            "settings": settings,
            "chunk_info": {
                "chunk_idx": chunk_idx,
                "start": i,
                "end": min(i + chunk_size, total),
                "count": len(chunk_sentences)
            },
            "sentences": chunk_sentences
        }

        chunk_filename = f"chunk_{chunk_idx:03d}.json"
        chunk_path = chunks_dir / chunk_filename
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        chunk_files.append(chunk_filename)
        print(f"  ✓ {chunk_filename}: {len(chunk_sentences)}개 문장")

    # manifest 생성
    manifest = {
        "total": total,
        "chunk_size": chunk_size,
        "chunk_count": len(chunk_files),
        "settings": settings,
        "files": chunk_files
    }

    manifest_path = output_dir / "chunk_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✓ manifest 저장: {manifest_path}")
    print(f"✓ {len(chunk_files)}개 청크 생성 완료")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="문장 분할용 청크 생성기")
    parser.add_argument("input_path", help="sentences_to_split.json 경로")
    parser.add_argument("-o", "--output-dir", required=True, help="출력 디렉토리 (_video)")
    parser.add_argument("--chunk-size", type=int, default=30, help="청크당 문장 수 (기본값: 30)")

    args = parser.parse_args()

    chunk_sentences(args.input_path, args.output_dir, args.chunk_size)


if __name__ == "__main__":
    main()
