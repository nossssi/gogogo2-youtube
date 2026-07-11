#!/usr/bin/env python3
"""
script_sentences.json에서 TTS 변환이 필요한 문장을 추출합니다.

script_sentences.json을 읽고 숫자나 영어가 포함된 문장을 찾아
tts_map.json 초안을 생성합니다.
Claude가 이 파일을 보고 conversions 배열을 채웁니다.
"""

import argparse
import json
import re
from pathlib import Path


def needs_conversion(text: str) -> bool:
    """텍스트에 TTS 변환이 필요한 요소가 있는지 확인 (숫자 또는 영어)"""
    # 숫자 포함
    if re.search(r'\d', text):
        return True
    # 영어 포함 (SK, TV, IMF 등)
    if re.search(r'[a-zA-Z]', text):
        return True
    return False


def extract_tts_targets(sentences_path: str | Path) -> list[dict]:
    """
    script_sentences.json에서 TTS 변환이 필요한 문장을 추출합니다.

    Args:
        sentences_path: script_sentences.json 경로

    Returns:
        [{"idx": 3, "text": "정년 64세 보장해라.", "conversions": []}, ...]
    """
    with open(sentences_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []

    for sentence in data["sentences"]:
        if needs_conversion(sentence["text"]):
            results.append({
                "idx": sentence["idx"],
                "text": sentence["text"],
                "conversions": []  # Claude가 채울 부분
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="script_sentences.json에서 TTS 변환 대상 추출")
    parser.add_argument("sentences_path", help="script_sentences.json 경로")
    parser.add_argument("-o", "--output", help="출력 JSON 경로")

    args = parser.parse_args()

    results = extract_tts_targets(args.sentences_path)

    output = {
        "total": len(results),
        "sentences": results
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✓ 저장: {args.output} ({len(results)}개 문장)")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
