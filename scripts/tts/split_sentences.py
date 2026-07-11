#!/usr/bin/env python3
"""
sentences.json → split.json (Python 기반 자막 분할)

sentences.json에서 needs_split=true인 문장을 찾아
2-pass 알고리즘으로 분할하고 split.json을 생성합니다.

출력 형식: [{"sentence_idx": N, "parts": ["파트1", "파트2"]}, ...]
(create_srt.py --split-data 호환)
"""

import argparse
import json
import math
from pathlib import Path


# ── 한국어 분할 규칙 ──────────────────────────────────────

CONJUNCTIONS = {
    "그런데", "근데", "하지만", "그래서", "결국", "그리고",
    "또한", "반면", "다만", "그러나", "그렇지만", "따라서", "즉",
}

PARTICLES = (
    "은", "는", "이", "가", "을", "를", "에", "에서",
    "으로", "로", "와", "과", "도", "까지", "부터", "에게", "한테",
)

DEPENDENT_NOUNS = {
    "게", "걸", "건", "거", "것", "수", "줄", "데", "때",
    "뿐", "셈", "법", "척", "듯", "채", "탓", "덕", "리", "바",
}

DEPENDENT_POSTPOSITIONS = {"만에", "만큼", "대로", "뿐만", "조차"}


# ── 핵심 함수 ──────────────────────────────────────────

def count_chars(text: str) -> int:
    """공백 제외 글자 수"""
    return len(text.replace(" ", ""))


def calc_num_parts(chars: int, max_chars: int) -> int:
    """분할 파트 수 결정 (1.7배 간격)"""
    if chars <= max_chars:
        return 1
    return math.ceil(chars / max_chars + 0.3)


def split_bonus(word: str, next_word: str | None, part_chars: int) -> float:
    """분할점 보너스 점수 (이 word 뒤에서 끊을 때)"""
    if part_chars < 8:
        return 0.0

    bonus = 0.0
    clean = word.rstrip('.,?!"\')')

    if word.endswith(",") or word.endswith("."):
        bonus += 1.5
    if word.endswith("?") or word.endswith("!"):
        bonus += 1.0

    if any(clean.endswith(p) for p in PARTICLES):
        bonus += 0.5

    if next_word:
        next_clean = next_word.rstrip('.,?!"\')')
        if next_clean in CONJUNCTIONS:
            bonus += 1.5

    return bonus


def split_sentence(words: list[dict], num_parts: int, max_chars: int) -> list[str]:
    """
    2-pass 방식으로 문장을 분할합니다.

    Pass 1: 목표 절단점 계산 (총글자수 / num_parts 간격)
    Pass 2: 각 목표점에서 가장 가까운 word 경계 선택
    """
    if num_parts <= 1:
        return [" ".join(w["word"] for w in words)]

    # 누적 글자수 계산
    cumulative = []
    total = 0
    for w in words:
        total += count_chars(w["word"])
        cumulative.append(total)

    total_chars = cumulative[-1]

    # Pass 1: 목표 절단점 (num_parts - 1개)
    targets = [total_chars * i / num_parts for i in range(1, num_parts)]

    # Pass 2: 각 목표점에서 최적 word 경계 찾기
    cut_indices = []
    min_word_idx = 0

    for target in targets:
        best_idx = None
        best_score = float("inf")

        for wi in range(min_word_idx, len(words) - 1):
            distance = abs(cumulative[wi] - target)

            # 최소 글자수 하한 체크
            part_start_chars = cumulative[min_word_idx - 1] if min_word_idx > 0 else 0
            part_chars = cumulative[wi] - part_start_chars
            if part_chars < 4:
                continue

            # 나머지 파트의 최소 글자수 체크
            remaining_parts = num_parts - len(cut_indices) - 1
            remaining_chars = total_chars - cumulative[wi]
            if remaining_parts > 0 and remaining_chars / remaining_parts < 4:
                continue

            # 보너스 적용
            next_word = words[wi + 1]["word"] if wi + 1 < len(words) else None
            bonus = split_bonus(words[wi]["word"], next_word, part_chars)
            score = distance - bonus

            # 의존 표현 페널티
            if next_word:
                next_clean = next_word.rstrip('.,?!"\')')
                if next_clean in DEPENDENT_NOUNS:
                    score += 3.0
                if next_clean in DEPENDENT_POSTPOSITIONS:
                    score += 3.0

            if score < best_score:
                best_score = score
                best_idx = wi

        if best_idx is not None:
            cut_indices.append(best_idx)
            min_word_idx = best_idx + 1

    # cut_indices로 parts 생성
    parts = []
    start = 0
    for ci in cut_indices:
        part_words = [w["word"] for w in words[start:ci + 1]]
        parts.append(" ".join(part_words))
        start = ci + 1

    if start < len(words):
        part_words = [w["word"] for w in words[start:]]
        parts.append(" ".join(part_words))

    return parts


# ── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="sentences.json → split.json (Python 기반 자막 분할)"
    )
    parser.add_argument("sentences_path", help="sentences.json 파일 경로")
    parser.add_argument(
        "-o", "--output",
        help="출력 경로 (기본: sentences.json과 같은 디렉토리의 split.json)"
    )

    args = parser.parse_args()

    # sentences.json 로드
    sentences_path = Path(args.sentences_path)
    with open(sentences_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    max_chars = data["settings"]["max_chars"]
    sentences = data["sentences"]

    # needs_split 문장 필터
    to_split = [s for s in sentences if s.get("needs_split")]
    print(f"전체 문장: {len(sentences)}개, 분할 대상: {len(to_split)}개 (max_chars={max_chars})")

    # 분할 실행
    split_results = []
    for s in to_split:
        chars = s["chars"]
        num_parts = calc_num_parts(chars, max_chars)
        parts = split_sentence(s["words"], num_parts, max_chars)

        split_results.append({
            "sentence_idx": s["idx"],
            "parts": parts,
        })

    # 출력 경로
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = sentences_path.parent / "split.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(split_results, f, ensure_ascii=False, indent=2)

    print(f"✓ 저장: {output_path} ({len(split_results)}개 문장 분할)")


if __name__ == "__main__":
    main()
