#!/usr/bin/env python3
"""
tts_map.json을 적용하여 script.txt → tts_script.txt 변환

TTS용 대본 생성: 숫자/영어를 한글 읽기로 변환
예: "40%대에서" → "사십 퍼센트대에서"
"""

import argparse
import json
from pathlib import Path


def apply_tts_map(script_text: str, tts_map: dict) -> str:
    """
    tts_map의 매핑을 적용하여 TTS용 텍스트 생성

    Args:
        script_text: 원본 대본 텍스트
        tts_map: {"sentences": [{"idx": N, "text": ..., "conversions": [...]}]}

    Returns:
        TTS용으로 변환된 텍스트
    """
    result = script_text

    for sentence in tts_map.get("sentences", []):
        text = sentence.get("text", "")
        conversions = sentence.get("conversions", [])

        if not text or not conversions:
            continue

        # 원본 문장에서 변환 적용한 새 문장 생성
        converted = text
        for conv in conversions:
            original = conv.get("original", "")
            tts = conv.get("tts", "")
            if original and tts:
                converted = converted.replace(original, tts)

        # 전체 텍스트에서 원본 문장을 변환된 문장으로 교체
        result = result.replace(text, converted)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="tts_map.json을 적용하여 TTS용 대본 생성"
    )
    parser.add_argument(
        "script",
        type=Path,
        help="원본 대본 파일 (script.txt)"
    )
    parser.add_argument(
        "tts_map",
        type=Path,
        help="TTS 매핑 파일 (tts_map.json)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="출력 파일 (기본: script와 같은 폴더에 tts_script.txt)"
    )

    args = parser.parse_args()

    # 파일 읽기
    script_text = args.script.read_text(encoding="utf-8")

    # JSON 파일이 들어오면 거부 (script_sentences.json 등 잘못 넘기는 실수 방지)
    stripped = script_text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        raise ValueError(
            f"입력 파일이 JSON입니다: {args.script}\n"
            f"plain text script.txt를 넘겨야 합니다."
        )

    tts_map = json.loads(args.tts_map.read_text(encoding="utf-8"))

    # 변환 적용
    tts_script = apply_tts_map(script_text, tts_map)

    # 개행 제거 (TTS는 한 줄로 처리)
    tts_script = tts_script.replace("\n", " ").strip()

    # 출력 파일 경로 결정
    output_path = args.output or args.script.parent / "tts_script.txt"

    # 저장
    output_path.write_text(tts_script, encoding="utf-8")

    # 변환 통계 출력
    sentence_count = len(tts_map.get("sentences", []))
    conversion_count = sum(
        len(s.get("conversions", []))
        for s in tts_map.get("sentences", [])
    )
    print(f"✅ TTS 대본 생성 완료: {output_path}")
    print(f"   - 문장 {sentence_count}개에서 {conversion_count}개 변환 적용")


if __name__ == "__main__":
    main()
