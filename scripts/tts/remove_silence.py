#!/usr/bin/env python3
"""
무음 구간 압축 스크립트

설정된 임계값 이상의 무음 구간을 목표 길이로 압축합니다.
MP3와 SRT 파일 모두 처리합니다.
"""

import subprocess
import numpy as np
import re
import os
import tempfile
from pathlib import Path


def load_audio(mp3_path: str | Path) -> tuple[np.ndarray, int]:
    """MP3를 로드하여 numpy 배열로 변환 (ffmpeg 사용)"""
    import wave

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name

    # MP3 -> WAV 변환
    subprocess.run([
        'ffmpeg', '-y', '-i', str(mp3_path),
        '-ar', '44100', '-ac', '1', '-f', 'wav', tmp_path
    ], capture_output=True)

    with wave.open(tmp_path, 'rb') as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        audio_data = wf.readframes(n_frames)
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        audio = audio / 32768.0  # Normalize to [-1, 1]

    os.unlink(tmp_path)
    return audio, sample_rate


def save_audio(audio: np.ndarray, sample_rate: int, output_path: str | Path):
    """numpy 배열을 MP3로 저장"""
    import wave

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name

    # numpy -> WAV
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(tmp_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    # WAV -> MP3
    subprocess.run([
        'ffmpeg', '-y', '-i', tmp_path,
        '-codec:a', 'libmp3lame', '-qscale:a', '2', str(output_path)
    ], capture_output=True)

    os.unlink(tmp_path)


def detect_silences(
    audio: np.ndarray,
    sample_rate: int,
    silence_thresh_db: float = -50,
    min_silence_sec: float = 0.5
) -> list[tuple[float, float]]:
    """
    무음 구간 감지

    Returns:
        [(start_sec, end_sec), ...] 형태의 무음 구간 리스트
    """
    window_size = int(sample_rate * 0.02)  # 20ms 윈도우
    hop_size = window_size // 2

    silences = []
    in_silence = False
    silence_start = 0

    threshold = 10 ** (silence_thresh_db / 20)  # dB to amplitude

    for i in range(0, len(audio) - window_size, hop_size):
        window = audio[i:i + window_size]
        rms = np.sqrt(np.mean(window ** 2))

        current_time = i / sample_rate

        if rms < threshold:
            if not in_silence:
                in_silence = True
                silence_start = current_time
        else:
            if in_silence:
                silence_end = current_time
                silence_duration = silence_end - silence_start
                if silence_duration >= min_silence_sec:
                    silences.append((silence_start, silence_end))
                in_silence = False

    # 마지막 무음 구간 처리
    if in_silence:
        silence_end = len(audio) / sample_rate
        silence_duration = silence_end - silence_start
        if silence_duration >= min_silence_sec:
            silences.append((silence_start, silence_end))

    return silences


def compress_silences(
    audio: np.ndarray,
    sample_rate: int,
    silences: list[tuple[float, float]],
    target_silence_sec: float = 0.2
) -> tuple[np.ndarray, list, list]:
    """
    무음 구간을 압축하고 시간 매핑 정보를 반환

    Returns:
        (압축된 오디오, 조정 정보 리스트, 무음 처리 정보 리스트)
    """
    if not silences:
        return audio, [], []

    result_parts = []
    adjustments = []
    silence_info = []
    prev_end = 0
    total_removed = 0

    for start, end in silences:
        original_duration = end - start
        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)

        # 무음 앞부분 추가
        result_parts.append(audio[prev_end:start_sample])

        # 무음 압축
        new_duration = target_silence_sec
        target_samples = int(new_duration * sample_rate)
        result_parts.append(audio[start_sample:start_sample + target_samples])
        removed = original_duration - new_duration

        silence_info.append((start, end, original_duration, new_duration))
        total_removed += removed
        adjustments.append((end, total_removed))
        prev_end = end_sample

    # 마지막 부분 추가
    result_parts.append(audio[prev_end:])

    return np.concatenate(result_parts), adjustments, silence_info


def create_time_adjuster(silence_info: list, adjustments: list):
    """시간 조정 함수 생성"""
    def adjust_time(original_sec: float) -> float:
        if not adjustments:
            return original_sec

        adjusted = original_sec
        for i, (boundary, cumulative_removed) in enumerate(adjustments):
            if original_sec >= boundary:
                adjusted = original_sec - cumulative_removed
            else:
                prev_removed = adjustments[i-1][1] if i > 0 else 0
                start, end, orig_dur, new_dur = silence_info[i]
                if original_sec >= start:
                    into_silence = original_sec - start
                    if into_silence <= new_dur:
                        adjusted = (start - prev_removed) + into_silence
                    else:
                        adjusted = (start - prev_removed) + new_dur
                else:
                    adjusted = original_sec - prev_removed
                break

        return max(0, adjusted)

    return adjust_time


def parse_srt_time(time_str: str) -> float:
    """SRT 시간 문자열을 초로 변환"""
    match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_str)
    if match:
        h, m, s, ms = map(int, match.groups())
        return h * 3600 + m * 60 + s + ms / 1000
    return 0


def format_srt_time(seconds: float) -> str:
    """초를 SRT 시간 형식으로 변환"""
    seconds = max(0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def adjust_srt(input_path: str | Path, output_path: str | Path, adjust_time_func):
    """SRT 파일의 타임스탬프를 조정"""
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    pattern = r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})'

    def replace_times(match):
        start = parse_srt_time(match.group(1))
        end = parse_srt_time(match.group(2))
        new_start = adjust_time_func(start)
        new_end = adjust_time_func(end)
        return f"{format_srt_time(new_start)} --> {format_srt_time(new_end)}"

    adjusted_content = re.sub(pattern, replace_times, content)

    with open(output_path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(adjusted_content)


def process_silence(
    input_mp3: str | Path,
    input_srt: str | Path,
    output_mp3: str | Path,
    output_srt: str | Path,
    min_silence: float = 0.8,
    target_silence: float = 0.2,
    silence_thresh_db: float = -50
) -> dict:
    """
    무음 구간을 압축하고 SRT를 조정합니다.

    Returns:
        {"original_duration": float, "new_duration": float, "saved": float, "silence_count": int}
    """
    import shutil

    print("오디오 파일 로드 중...")
    audio, sample_rate = load_audio(input_mp3)
    original_duration = len(audio) / sample_rate
    print(f"원본 길이: {original_duration:.2f}초")

    print(f"무음 구간 감지 중 ({min_silence}초 이상)...")
    silences = detect_silences(audio, sample_rate, silence_thresh_db, min_silence)

    if not silences:
        print("감지된 무음 구간 없음. 원본 파일 복사.")
        shutil.copy(input_mp3, output_mp3)
        shutil.copy(input_srt, output_srt)
        return {
            "original_duration": original_duration,
            "new_duration": original_duration,
            "saved": 0,
            "silence_count": 0
        }

    print(f"감지된 무음 구간: {len(silences)}개 → {target_silence}초로 압축")

    compressed_audio, adjustments, silence_info = compress_silences(
        audio, sample_rate, silences, target_silence
    )

    new_duration = len(compressed_audio) / sample_rate
    saved = original_duration - new_duration
    print(f"압축 후 길이: {new_duration:.2f}초 ({saved:.2f}초 단축)")

    print(f"MP3 저장 중: {output_mp3}")
    save_audio(compressed_audio, sample_rate, output_mp3)

    print(f"SRT 조정 중: {output_srt}")
    adjust_time_func = create_time_adjuster(silence_info, adjustments)
    adjust_srt(input_srt, output_srt, adjust_time_func)

    return {
        "original_duration": original_duration,
        "new_duration": new_duration,
        "saved": saved,
        "silence_count": len(silences)
    }


def load_settings(config_path: str | Path | None) -> dict:
    """settings.json에서 설정 로드"""
    import json
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    """CLI 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="무음 구간 압축")
    parser.add_argument("input_mp3", help="입력 MP3 파일")
    parser.add_argument("input_srt", help="입력 SRT 파일")
    parser.add_argument("output_mp3", help="출력 MP3 파일")
    parser.add_argument("output_srt", help="출력 SRT 파일")
    parser.add_argument("--config", help="설정 파일 경로 (settings.json)")
    parser.add_argument("--min-silence", type=float, help="최소 무음 길이 (초)")
    parser.add_argument("--target-silence", type=float, help="목표 무음 길이 (초)")
    parser.add_argument("--silence-thresh", type=float, help="무음 임계값 (dB)")

    args = parser.parse_args()

    # 설정 로드 (config 파일 → CLI 인자로 오버라이드)
    settings = load_settings(args.config)
    silence_settings = settings.get("silence", {})

    min_silence = args.min_silence or silence_settings.get("min_silence", 0.8)
    target_silence = args.target_silence or silence_settings.get("target_silence", 0.2)
    silence_thresh = args.silence_thresh or silence_settings.get("silence_thresh_db", -50)

    result = process_silence(
        args.input_mp3,
        args.input_srt,
        args.output_mp3,
        args.output_srt,
        min_silence,
        target_silence,
        silence_thresh
    )

    print(f"\n✓ 완료! {result['saved']:.2f}초 단축됨")


if __name__ == "__main__":
    main()
