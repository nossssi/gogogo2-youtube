#!/usr/bin/env python3
"""
ElevenLabs TTS Generator
대본 텍스트를 MP3와 alignment.json으로 변환합니다.
긴 텍스트는 청크로 분할하여 처리합니다.
"""

import os
import json
import base64
import requests
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")

# 청크 설정
MAX_CHUNK_CHARS = 2500  # ElevenLabs alignment 한계를 피하기 위한 청크 크기


def get_credit_info() -> dict | None:
    """ElevenLabs 크레딧 정보를 조회합니다."""
    url = "https://api.elevenlabs.io/v1/user/subscription"
    headers = {"xi-api-key": API_KEY}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return {
                "used": data.get("character_count", 0),
                "limit": data.get("character_limit", 0),
                "remaining": data.get("character_limit", 0) - data.get("character_count", 0),
                "tier": data.get("tier", "unknown")
            }
    except Exception as e:
        print(f"크레딧 조회 실패: {e}")
    return None


def check_credit(text_length: int) -> bool:
    """크레딧이 충분한지 확인합니다."""
    info = get_credit_info()
    if info is None:
        print("⚠️ 크레딧 정보를 조회할 수 없습니다. 계속 진행합니다.")
        return True

    print(f"📊 크레딧: {info['remaining']:,} / {info['limit']:,} ({info['tier']})")
    print(f"📝 필요한 글자 수: {text_length:,}")

    if info['remaining'] < text_length:
        print(f"❌ 크레딧 부족! {text_length - info['remaining']:,}자 더 필요합니다.")
        return False

    print(f"✓ 크레딧 충분 (사용 후 {info['remaining'] - text_length:,}자 남음)")
    return True


def split_text_to_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    텍스트를 청크로 분할합니다.
    문단(\n\n) 또는 문장(.) 단위로 분할하여 max_chars를 넘지 않도록 합니다.
    """
    # 먼저 문단으로 분할
    paragraphs = text.split('\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 문단 자체가 너무 길면 문장으로 분할
        if len(para) > max_chars:
            # 현재 청크가 있으면 먼저 저장
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # 문장 단위로 분할 (소수점은 문장 구분으로 처리하지 않음)
            sentences = []
            temp = ""
            for i, char in enumerate(para):
                temp += char
                if char in '.!?。':
                    # 마침표인 경우: 앞뒤가 숫자면 소수점이므로 분리하지 않음
                    if char == '.' and i > 0 and i < len(para) - 1:
                        if para[i - 1].isdigit() and para[i + 1].isdigit():
                            continue
                    sentences.append(temp.strip())
                    temp = ""
            if temp.strip():
                sentences.append(temp.strip())

            # 문장들을 청크로 그룹화
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_chars:
                    current_chunk += (" " if current_chunk else "") + sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
        else:
            # 현재 청크에 추가 가능한지 확인
            if len(current_chunk) + len(para) + 1 <= max_chars:
                current_chunk += ("\n" if current_chunk else "") + para
            else:
                # 현재 청크 저장하고 새 청크 시작
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para

    # 마지막 청크 저장
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def validate_chunk_alignment(alignment: dict, max_consecutive_zero: int = 3) -> tuple[bool, str]:
    """청크 alignment 품질 검증. (valid, reason) 반환."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if not (len(chars) == len(starts) == len(ends)) or not chars:
        return (False, "alignment 배열 길이 불일치 또는 비어있음") if chars else (True, "ok")

    # 실제 글자(한글/영문/숫자)만 대상 — 공백/구두점은 zero-duration 정상
    consecutive_zero = 0
    for i, ch in enumerate(chars):
        if ch.strip() and ch not in '.,!?…·:;"\'-()[]{}':
            if starts[i] == ends[i]:
                consecutive_zero += 1
                if consecutive_zero >= max_consecutive_zero:
                    return False, f"연속 {consecutive_zero}개 zero-duration 문자 (index {i})"
            else:
                consecutive_zero = 0
        # 공백/구두점은 카운트 리셋 안 함 (사이에 낀 경우 유지)

    return True, "ok"


def generate_tts_with_timestamps(
    text: str,
    voice_id: str,
    model_id: str = "eleven_v3",
    speed: float = 1.0,
    stability: float = 0.5,
    similarity_boost: float = 0.75
) -> dict:
    """
    ElevenLabs API를 호출하여 음성과 타임스탬프를 생성합니다.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "speed": speed
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code} - {response.text}")

    return response.json()


def generate_tts_with_retry(text, voice_id, model_id, speed, stability,
                            similarity_boost, max_retries=2) -> dict:
    """TTS 생성 + alignment 검증 + 자동 재시도."""
    for attempt in range(max_retries + 1):
        result = generate_tts_with_timestamps(text, voice_id, model_id, speed, stability, similarity_boost)

        alignment = result.get("alignment")
        if not alignment:
            if attempt < max_retries:
                print(f"   ⚠️ alignment 없음, 재시도 ({attempt+1}/{max_retries})")
                continue
            raise ValueError("alignment 데이터가 없습니다")

        valid, reason = validate_chunk_alignment(alignment)
        if valid:
            return result

        if attempt < max_retries:
            print(f"   ⚠️ alignment 불량: {reason} → 재시도 ({attempt+1}/{max_retries})")
        else:
            print(f"   ❌ alignment 불량: {reason} (재시도 소진)")
            raise ValueError(f"alignment 검증 실패: {reason}")

    return result  # unreachable but safe


def get_audio_duration(audio_path: Path) -> float:
    """ffprobe로 오디오 길이를 초 단위로 반환합니다."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def merge_audio_files(audio_paths: list[Path], output_path: Path):
    """ffmpeg로 여러 오디오 파일을 병합합니다."""
    # concat 파일 생성 (절대 경로 사용)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for path in audio_paths:
            # 절대 경로로 변환하고 이스케이프
            abs_path = str(path.resolve())
            f.write(f"file '{abs_path}'\n")
        concat_file = f.name

    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", str(output_path)
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ffmpeg stderr: {result.stderr}")
            raise Exception(f"ffmpeg failed with return code {result.returncode}")
    finally:
        os.unlink(concat_file)


def merge_alignments(alignments: list[dict], durations: list[float]) -> dict:
    """
    여러 alignment 데이터를 병합합니다.
    각 청크의 시작 시간을 오프셋으로 더합니다.
    """
    merged = {
        "characters": [],
        "character_start_times_seconds": [],
        "character_end_times_seconds": []
    }

    time_offset = 0.0

    for i, (alignment, duration) in enumerate(zip(alignments, durations)):
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        merged["characters"].extend(chars)
        merged["character_start_times_seconds"].extend([s + time_offset for s in starts])
        merged["character_end_times_seconds"].extend([e + time_offset for e in ends])

        time_offset += duration

    return merged


def generate_tts_chunked(
    text: str,
    output_dir: Path,
    voice_id: str,
    model_id: str = "eleven_v3",
    speed: float = 1.0,
    stability: float = 0.5,
    similarity_boost: float = 0.75
) -> tuple[Path, Path]:
    """
    긴 텍스트를 청크로 분할하여 TTS를 생성합니다.
    """
    intermediate_dir = output_dir
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    chunks = split_text_to_chunks(text)
    print(f"📦 텍스트를 {len(chunks)}개 청크로 분할")

    if len(chunks) == 1:
        # 청크가 1개면 기존 방식으로 처리
        print("🔄 ElevenLabs API 호출 중...")
        result = generate_tts_with_retry(text, voice_id, model_id, speed, stability, similarity_boost)
        return save_tts_result_single(result, output_dir)

    # 여러 청크 처리 (병렬)
    temp_dir = intermediate_dir / "_temp_chunks"
    temp_dir.mkdir(exist_ok=True)

    # 결과 저장용 (인덱스 순서 보장)
    results = [None] * len(chunks)

    try:
        # 병렬로 API 호출
        print(f"🔄 {len(chunks)}개 청크 병렬 처리 중...")
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            # 모든 청크 동시 요청
            futures = {
                executor.submit(
                    generate_tts_with_retry, chunk, voice_id, model_id, speed, stability, similarity_boost
                ): i
                for i, chunk in enumerate(chunks)
            }

            # 결과 수집 (완료되는 순서대로, 하지만 인덱스로 저장)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                    print(f"   ✓ 청크 {idx+1}/{len(chunks)} 완료 ({len(chunks[idx])}자)")
                except Exception as e:
                    print(f"   ✗ 청크 {idx+1} 실패: {e}")
                    raise

        # 모든 결과 도착 후, 순서대로 처리
        audio_paths = []
        alignments = []
        durations = []

        print("🔄 결과 처리 중...")
        for i, result in enumerate(results):
            # 임시 오디오 저장
            audio_path = temp_dir / f"chunk_{i:03d}.mp3"
            audio_base64 = result.get("audio_base64")
            if audio_base64:
                audio_data = base64.b64decode(audio_base64)
                audio_path.write_bytes(audio_data)
                audio_paths.append(audio_path)

                # 오디오 길이 측정
                duration = get_audio_duration(audio_path)
                durations.append(duration)
                print(f"   청크 {i+1}: {duration:.2f}초")

            # alignment 저장
            alignment = result.get("alignment")
            if alignment:
                alignments.append(alignment)

        # 오디오 병합
        print("🔄 오디오 파일 병합 중...")
        mp3_path = intermediate_dir / "audio_raw.mp3"
        merge_audio_files(audio_paths, mp3_path)
        total_duration = sum(durations)
        print(f"✓ MP3 저장: {mp3_path} ({total_duration:.2f}초)")

        # alignment 병합
        print("🔄 Alignment 데이터 병합 중...")
        merged_alignment = merge_alignments(alignments, durations)
        alignment_path = intermediate_dir / "alignment.json"
        with open(alignment_path, "w", encoding="utf-8") as f:
            json.dump(merged_alignment, f, ensure_ascii=False, indent=2)
        print(f"✓ Alignment 저장: {alignment_path}")

        return mp3_path, alignment_path

    finally:
        # 임시 파일 정리
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def save_tts_result_single(result: dict, output_dir: Path) -> tuple[Path, Path]:
    """단일 TTS 결과를 파일로 저장합니다."""
    intermediate_dir = output_dir
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    mp3_path = intermediate_dir / "audio_raw.mp3"
    alignment_path = intermediate_dir / "alignment.json"

    # MP3 저장
    audio_base64 = result.get("audio_base64")
    if audio_base64:
        audio_data = base64.b64decode(audio_base64)
        mp3_path.write_bytes(audio_data)
        print(f"✓ MP3 저장: {mp3_path}")

    # alignment 저장
    alignment = result.get("alignment")
    if alignment:
        with open(alignment_path, "w", encoding="utf-8") as f:
            json.dump(alignment, f, ensure_ascii=False, indent=2)
        print(f"✓ Alignment 저장: {alignment_path}")

    return mp3_path, alignment_path


def load_settings(config_path: str | Path | None) -> dict:
    """settings.json에서 설정 로드"""
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    """CLI 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="ElevenLabs TTS 생성기")
    parser.add_argument("input_path", help="입력 텍스트 파일 경로")
    parser.add_argument("output_dir", help="출력 디렉토리")
    parser.add_argument("--config", help="settings.json 경로")
    parser.add_argument("--speed", type=float, help="말하기 속도 (0.7~1.5)")
    parser.add_argument("--stability", type=float, help="안정성 (0~1)")
    parser.add_argument("--similarity-boost", type=float, help="유사도 (0~1)")
    parser.add_argument("--check-credit", action="store_true",
                       help="크레딧 사전 체크 후 부족하면 중단 (기본: 체크 안 함 — 오버유즈 결제로 진행)")
    parser.add_argument("--max-chunk-size", type=int, default=MAX_CHUNK_CHARS,
                       help=f"청크 최대 글자 수 (기본값: {MAX_CHUNK_CHARS})")

    args = parser.parse_args()

    # 설정 로드 (config 파일 → CLI 인자로 오버라이드)
    settings = load_settings(args.config)
    tts_settings = settings.get("tts", {})

    voice_id = tts_settings.get("voice_id")
    if not voice_id:
        raise ValueError("voice_id가 설정되지 않았습니다. settings.json의 tts.voice_id를 확인하세요.")
    model_id = tts_settings.get("model_id", "eleven_v3")

    speed = args.speed or tts_settings.get("speed", 1.0)
    stability = args.stability or tts_settings.get("stability", 0.5)
    similarity_boost = args.similarity_boost or tts_settings.get("similarity_boost", 0.75)

    # 텍스트 읽기
    with open(args.input_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    print(f"📝 텍스트 길이: {len(text)}자")
    print(f"🎤 voice_id: {voice_id}")
    print(f"⚙️ 설정: speed={speed}, stability={stability}, similarity_boost={similarity_boost}")
    print(f"📦 청크 크기: {MAX_CHUNK_CHARS}자")

    # 크레딧 체크 (--check-credit 옵션 줄 때만)
    if args.check_credit:
        if not check_credit(len(text)):
            print("중단합니다.")
            return

    # TTS 생성 (청크 분할 적용)
    output_dir = Path(args.output_dir)
    generate_tts_chunked(
        text,
        output_dir,
        voice_id=voice_id,
        model_id=model_id,
        speed=speed,
        stability=stability,
        similarity_boost=similarity_boost
    )

    print("✓ 완료!")


if __name__ == "__main__":
    main()
