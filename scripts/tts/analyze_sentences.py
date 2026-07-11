#!/usr/bin/env python3
"""
script_sentences.json + tts_map.json + alignment.json → sentences.json

문장 구조는 script_sentences.json(원본)을 기준으로 하고,
alignment.json에서 타이밍만 매핑합니다.

출력:
- tts_sentences.json: TTS 변환된 문장 목록 (중간 산출물)
- sentences.json: 문장별 타이밍 + 분할 필요 여부
- sentences_to_split.json: 분할 필요한 문장만 추출
"""

import argparse
import json
from pathlib import Path


def apply_tts_map_to_sentences(sentences: list[dict], tts_map: dict) -> list[dict]:
    """
    script_sentences의 각 문장에 tts_map 변환을 적용합니다.

    Returns:
        [{"idx": 0, "original_text": "연봉 1억.", "tts_text": "연봉 일억."}, ...]
    """
    # tts_map의 문장별 변환을 idx로 매핑
    conversion_by_idx = {}
    for entry in tts_map.get("sentences", []):
        idx = entry.get("idx")
        conversions = entry.get("conversions", [])
        if idx is not None and conversions:
            conversion_by_idx[idx] = conversions

    tts_sentences = []
    for sent in sentences:
        idx = sent["idx"]
        orig_text = sent["text"]
        tts_text = orig_text

        if idx in conversion_by_idx:
            for conv in conversion_by_idx[idx]:
                original = conv.get("original", "")
                tts = conv.get("tts", "")
                if original and tts:
                    tts_text = tts_text.replace(original, tts)

        tts_sentences.append({
            "idx": idx,
            "original_text": orig_text,
            "tts_text": tts_text
        })

    return tts_sentences


def match_sentences_to_alignment(tts_sentences: list[dict], alignment: dict) -> list[dict]:
    """
    tts_sentences의 각 문장을 alignment의 글자별 타이밍과 매칭합니다.

    공백을 무시하고 비공백 글자만 순서대로 매칭하여
    ElevenLabs가 공백을 누락하는 문제를 회피합니다.
    """
    characters = alignment.get("characters", [])
    start_times = alignment.get("character_start_times_seconds", [])
    end_times = alignment.get("character_end_times_seconds", [])

    # 비공백 글자만 추출 (타이밍 포함)
    aligned_chars = []
    for i, char in enumerate(characters):
        if char not in (" ", "\n"):
            aligned_chars.append({
                "char": char,
                "start": start_times[i],
                "end": end_times[i]
            })

    ac_idx = 0
    results = []
    mismatch_count = 0

    for sent in tts_sentences:
        tts_text = sent["tts_text"]
        tts_words = tts_text.split()

        words = []

        for tts_word in tts_words:
            word_start = None
            word_end = None

            for char in tts_word:
                if ac_idx < len(aligned_chars):
                    ac = aligned_chars[ac_idx]
                    if ac["char"] != char:
                        mismatch_count += 1

                    if word_start is None:
                        word_start = ac["start"]
                    word_end = ac["end"]
                    ac_idx += 1

            words.append({
                "word": tts_word,
                "start": word_start,
                "end": word_end
            })

        results.append({
            "idx": sent["idx"],
            "tts_text": tts_text,
            "original_text": sent["original_text"],
            "words": words
        })

    if mismatch_count > 0:
        print(f"⚠️ 글자 불일치: {mismatch_count}개")

    # 매칭 안 된 alignment 글자 확인
    remaining = len(aligned_chars) - ac_idx
    if remaining > 0:
        print(f"⚠️ 매칭 안 된 alignment 글자: {remaining}개")

    return results


def apply_conversions_to_words(
    words: list[dict],
    tts_text: str,
    conversions: list[dict]
) -> list[dict]:
    """
    TTS words에 conversion을 적용하여 원본 텍스트 기반 words로 변환합니다.

    예: conversions = [{"original": "1년", "tts": "일 년"}]
        words = [{"word": "일", ...}, {"word": "년", ...}]
        → [{"word": "1년", start=첫번째.start, end=마지막.end}]

    마지막 tts token은 startswith 허용 (조사 처리):
        tts token "배" → word "배." → suffix "."
        → merged word = "3배."
    """
    if not conversions:
        return words

    # 뒤에서부터 처리 (인덱스 밀림 방지)
    conv_with_pos = []
    for conv in conversions:
        pos = tts_text.find(conv["tts"])
        if pos >= 0:
            conv_with_pos.append((pos, conv))
    conv_with_pos.sort(key=lambda x: -x[0])

    result = list(words)  # shallow copy

    for _, conv in conv_with_pos:
        tts_tokens = conv["tts"].split()

        for i in range(len(result)):
            if i + len(tts_tokens) > len(result):
                break

            matched = True
            suffix = ""
            for j, tt in enumerate(tts_tokens):
                w = result[i + j]["word"]
                if j == len(tts_tokens) - 1:  # 마지막 token: startswith 허용
                    if w == tt:
                        pass
                    elif w.startswith(tt):
                        suffix = w[len(tt):]
                    else:
                        matched = False
                        break
                else:  # 나머지: exact match
                    if w != tt:
                        matched = False
                        break

            if matched:
                merged = {
                    "word": conv["original"] + suffix,
                    "start": result[i]["start"],
                    "end": result[i + len(tts_tokens) - 1]["end"]
                }
                result = result[:i] + [merged] + result[i + len(tts_tokens):]
                break

    return result


def count_chars_without_spaces(text: str) -> int:
    """공백 제외 글자 수"""
    return len(text.replace(" ", ""))



def analyze_sentences(
    script_sentences: dict,
    tts_map: dict,
    alignment: dict,
    max_chars: int = 20
) -> tuple[dict, list[dict]]:
    """
    문장 구조(script_sentences) + TTS 변환(tts_map) + 타이밍(alignment)을
    결합하여 sentences.json을 생성합니다.

    words에 conversion을 적용하여 원본 텍스트 기반으로 출력합니다.
    """
    sentences = script_sentences.get("sentences", [])

    # tts_map의 문장별 변환을 idx로 매핑
    conversion_by_idx = {}
    for entry in tts_map.get("sentences", []):
        idx = entry.get("idx")
        conversions = entry.get("conversions", [])
        if idx is not None and conversions:
            conversion_by_idx[idx] = conversions

    # 1. TTS 변환 적용
    tts_sentences = apply_tts_map_to_sentences(sentences, tts_map)
    print(f"문장 수: {len(tts_sentences)}개")

    # 2. alignment와 매칭 (TTS 텍스트 기준)
    matched = match_sentences_to_alignment(tts_sentences, alignment)

    # 3. word 레벨 conversion 적용 + 분할 필요 여부 판별
    result_sentences = []
    needs_split_count = 0
    conversion_count = 0

    for m in matched:
        idx = m["idx"]
        tts_text = m["tts_text"]
        words = m["words"]

        # conversion 적용: TTS words → 원본 words
        conversions = conversion_by_idx.get(idx, [])
        if conversions:
            words = apply_conversions_to_words(words, tts_text, conversions)
            conversion_count += len(conversions)

        # 원본 텍스트 = words 재결합
        original_text = " ".join(w["word"] for w in words)
        chars = count_chars_without_spaces(original_text)
        needs_split = chars > max_chars

        if needs_split:
            needs_split_count += 1

        sentence_data = {
            "idx": idx,
            "text": original_text,
            "chars": chars,
            "needs_split": needs_split,
            "words": words
        }
        # tts_text가 다를 때만 포함 (디버깅용)
        if tts_text != original_text:
            sentence_data["tts_text"] = tts_text

        result_sentences.append(sentence_data)

    if conversion_count > 0:
        print(f"변환 적용: {conversion_count}개")
    print(f"분할 필요: {needs_split_count}개 (max_chars={max_chars})")

    result = {
        "settings": {
            "max_chars": max_chars
        },
        "sentences": result_sentences
    }

    return result, tts_sentences


def main():
    parser = argparse.ArgumentParser(
        description="문장 구조(script_sentences) + 타이밍(alignment) 매핑"
    )
    parser.add_argument("alignment_path", help="alignment.json 경로")
    parser.add_argument(
        "--script-sentences", required=True,
        help="script_sentences.json 경로"
    )
    parser.add_argument(
        "--tts-map", required=True,
        help="tts_map.json 경로"
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="출력 경로 (sentences.json)"
    )
    parser.add_argument("--config", help="설정 파일 경로 (settings.json)")
    parser.add_argument(
        "--max-chars", type=int, default=25,
        help="최대 글자 수 (기본값: 25)"
    )

    args = parser.parse_args()

    # 파일 로드
    with open(args.alignment_path, "r", encoding="utf-8") as f:
        alignment = json.load(f)
    with open(args.script_sentences, "r", encoding="utf-8") as f:
        script_sentences = json.load(f)
    with open(args.tts_map, "r", encoding="utf-8") as f:
        tts_map = json.load(f)

    # config에서 max_chars 로드
    max_chars = args.max_chars
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
            max_chars = config.get("subtitle", {}).get("max_chars", max_chars)

    # 분석 실행
    result, tts_sentences = analyze_sentences(
        script_sentences, tts_map, alignment, max_chars
    )

    # sentences.json 저장
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✓ 저장: {output_path}")

    # tts_sentences.json 저장
    tts_sent_path = output_path.parent / "tts_sentences.json"
    tts_sent_data = {
        "total": len(tts_sentences),
        "sentences": tts_sentences
    }
    with open(tts_sent_path, "w", encoding="utf-8") as f:
        json.dump(tts_sent_data, f, ensure_ascii=False, indent=2)
    print(f"✓ 저장: {tts_sent_path}")



if __name__ == "__main__":
    main()
