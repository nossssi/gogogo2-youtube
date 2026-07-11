#!/usr/bin/env python3
"""
sentences.json 기반 SRT 생성기

sentences.json의 문장과 단어별 타이밍을 사용하여 정확한 자막을 생성합니다.
문장 분할 정보는 외부(Claude)에서 split.json으로 전달받습니다.

sentences.json의 text/words는 이미 원본 텍스트이므로 역변환 불필요.
"""

import argparse
import json
from pathlib import Path


def format_srt_time(seconds: float) -> str:
    """초를 SRT 시간 형식으로 변환 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def map_timing_to_parts(parts: list[str], words: list[dict]) -> list[dict]:
    """
    분할된 텍스트 파트에 단어 기반 정확한 타이밍을 매핑합니다.

    Args:
        parts: ["작년 한 해", "대한민국에서", ...]
        words: [{"word": "작년", "start": 0.0, "end": 0.32}, ...]

    Returns:
        [{"text": "작년 한 해", "start": 0.0, "end": 0.96}, ...]
    """
    result = []
    word_index = 0

    for part in parts:
        part_clean = part.replace(" ", "")
        part_start = None
        part_end = None
        matched_chars = 0

        while word_index < len(words) and matched_chars < len(part_clean):
            word = words[word_index]
            word_clean = word["word"].replace(" ", "")

            if part_start is None:
                part_start = word["start"]

            part_end = word["end"]
            matched_chars += len(word_clean)
            word_index += 1

        if part_start is not None:
            result.append({
                "text": part,
                "start": part_start,
                "end": part_end
            })

    return result


def create_srt(
    sentences: list[dict],
    output_path: str | Path,
    split_data: list[dict] | None = None,
) -> list[dict]:
    """
    sentences 데이터에서 SRT 파일을 생성합니다.

    Args:
        sentences: analyze_sentences.py 출력의 sentences 배열 (원본 텍스트 기반)
        output_path: 출력 SRT 파일 경로
        split_data: 문장 분할 데이터 [{"sentence_idx": 0, "parts": ["분할1", "분할2"]}, ...]
                    None이면 문장 단위로만 자막 생성

    Returns:
        생성된 자막 리스트
    """
    print(f"문장 수: {len(sentences)}개")

    # 1. 분할 데이터 적용
    subtitles = []

    if split_data:
        split_map = {item["sentence_idx"]: item["parts"] for item in split_data}
        print(f"분할 적용: {len(split_map)}개 문장")

        for sentence in sentences:
            idx = sentence["idx"]
            if idx in split_map:
                parts = split_map[idx]
                timed_parts = map_timing_to_parts(parts, sentence["words"])
                subtitles.extend(timed_parts)
            else:
                subtitles.append({
                    "text": sentence["text"],
                    "start": sentence["words"][0]["start"],
                    "end": sentence["words"][-1]["end"],
                })
    else:
        for sentence in sentences:
            subtitles.append({
                "text": sentence["text"],
                "start": sentence["words"][0]["start"],
                "end": sentence["words"][-1]["end"],
            })

    # 2. 자막 간격 없애기 (이전 자막 끝 = 다음 자막 시작)
    for i in range(len(subtitles) - 1):
        subtitles[i]["end"] = subtitles[i + 1]["start"]

    # 3. SRT 파일 작성 (UTF-8 BOM + CRLF for CapCut)
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        for i, sub in enumerate(subtitles, 1):
            f.write(f"{i}\n")
            f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
            f.write(f"{sub['text']}\n\n")

    print(f"✓ SRT 저장: {output_path} ({len(subtitles)}개 자막)")
    return subtitles


def main():
    parser = argparse.ArgumentParser(description="sentences.json 기반 SRT 생성기")
    parser.add_argument("sentences_path", help="sentences.json 파일 경로")
    parser.add_argument("-o", "--output", required=True, help="출력 SRT 파일 경로")
    parser.add_argument("--split-data", help="문장 분할 JSON 파일 경로")

    args = parser.parse_args()

    # sentences 로드
    with open(args.sentences_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        sentences = data["sentences"]

    # split_data 로드
    split_data = None
    if args.split_data:
        with open(args.split_data, "r", encoding="utf-8") as f:
            split_data = json.load(f)

    create_srt(sentences, args.output, split_data)


if __name__ == "__main__":
    main()
