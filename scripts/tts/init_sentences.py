#!/usr/bin/env python3
"""
대본(script.txt)을 문장 단위로 분리하여 script_sentences.json을 생성합니다.

이 파일이 이후 파이프라인 전체의 sentence_idx 기준 원본(source of truth)이 됩니다.

문장 분리 로직은 analyze_sentences.py의 group_into_sentences와 동일:
- 마침표(.), 물음표(?), 느낌표(!) 기준 분리
- 따옴표("") 안의 구두점은 분리하지 않음

Usage:
    python src/tts/init_sentences.py <script_path> [-o <output_path>]

Example:
    python src/tts/init_sentences.py channels/메인경제채널/input/현대제철귀족노조.txt
"""

import argparse
import json
import re
from pathlib import Path


def split_into_sentences(text: str) -> list[str]:
    """
    텍스트를 문장 단위로 분리합니다.
    analyze_sentences.py의 group_into_sentences와 동일한 로직.

    규칙:
    - 마침표(.), 물음표(?), 느낌표(!) 뒤에서 분리
    - 따옴표("") 안의 구두점은 분리하지 않음
    """
    sentence_end_marks = ('.', '?', '!')
    sentences = []
    current = ""
    in_quote = False

    # 단어 단위로 처리 (analyze_sentences.py와 동일)
    words = text.split()

    for i, word in enumerate(words):
        current += (" " if current else "") + word

        # 따옴표 상태 토글
        if '"' in word:
            if word.count('"') % 2 == 1:
                in_quote = not in_quote

        # 문장 끝 체크: 따옴표 밖에서만 분리
        last_char = word.rstrip()[-1:]
        if last_char in sentence_end_marks and not in_quote:
            # 마침표인 경우: 다음 단어가 숫자로 시작하면 소수점일 수 있으므로 분리하지 않음
            # 예: "6.5%로" → 단어 자체에 소수점 포함 (이 경우 마지막 글자가 .이 아님)
            # 예: "6." + "5%로" → 이런 분할은 일어나지 않지만 방어적으로 체크
            if last_char == '.' and i + 1 < len(words):
                next_word = words[i + 1]
                if next_word[:1].isdigit():
                    continue
            sentences.append(current.strip())
            current = ""

    # 남은 텍스트 처리
    if current.strip():
        sentences.append(current.strip())

    return sentences


def init_sentences(script_path: str | Path, output_path: str | Path | None = None) -> dict:
    """
    대본을 문장으로 분리하여 JSON을 생성합니다.

    Args:
        script_path: 대본 파일 경로
        output_path: 출력 JSON 경로 (None이면 stdout)

    Returns:
        {"total": N, "sentences": [{"idx": 0, "text": "..."}, ...]}
    """
    script_path = Path(script_path)

    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    sentences = split_into_sentences(text)

    result = {
        "total": len(sentences),
        "sentences": [
            {"idx": idx, "text": sentence}
            for idx, sentence in enumerate(sentences)
        ]
    }

    print(f"문장 수: {len(sentences)}개")

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✓ 저장: {output_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="대본을 문장 단위로 분리")
    parser.add_argument("script_path", help="대본 파일 경로 (script.txt)")
    parser.add_argument("-o", "--output", help="출력 JSON 경로 (script_sentences.json)")

    args = parser.parse_args()

    result = init_sentences(args.script_path, args.output)

    if not args.output:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
