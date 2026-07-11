#!/usr/bin/env python3
"""
SRT 자막을 30fps 프레임 경계에 맞춰 정렬

규칙:
- 시작 시간: 이전 자막 끝과 동일 (연속성 보장)
- 끝 시간: 가장 가까운 프레임 경계로 스냅
- 최소 1프레임(33ms) 보장
"""

import re
from pathlib import Path


def parse_timestamp(ts: str) -> int:
    """SRT 타임스탬프를 ms로 변환"""
    match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', ts)
    if not match:
        raise ValueError(f"Invalid timestamp: {ts}")
    h, m, s, ms = map(int, match.groups())
    return h * 3600000 + m * 60000 + s * 1000 + ms


def format_timestamp(ms: int) -> str:
    """ms를 SRT 타임스탬프로 변환"""
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_part = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"


def snap_to_frame(ms: int, fps: int = 30) -> int:
    """ms를 가장 가까운 프레임 경계로 스냅"""
    frame = round(ms * fps / 1000)
    return round(frame * 1000 / fps)


def parse_srt(content: str) -> list[dict]:
    """SRT 파일 파싱"""
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)

    subtitles = []
    for match in matches:
        subtitles.append({
            'index': int(match[0]),
            'start': parse_timestamp(match[1]),
            'end': parse_timestamp(match[2]),
            'text': match[3].strip()
        })
    return subtitles


def align_subtitles(subtitles: list[dict], fps: int = 30) -> list[dict]:
    """자막 시간을 프레임 경계에 정렬 (연속성 보장)"""
    aligned = []
    prev_end_ms = 0

    for i, sub in enumerate(subtitles):
        # 시작 시간: 이전 자막 끝과 동일 (첫 자막은 스냅)
        if i == 0:
            new_start = snap_to_frame(sub['start'], fps)
        else:
            new_start = prev_end_ms

        # 끝 시간: 프레임 경계로 스냅
        new_end = snap_to_frame(sub['end'], fps)

        # 최소 1프레임 길이 보장
        if new_end <= new_start:
            new_end = new_start + 33

        prev_end_ms = new_end

        aligned.append({
            'index': sub['index'],
            'start': new_start,
            'end': new_end,
            'text': sub['text']
        })

    return aligned


def format_srt(subtitles: list[dict]) -> str:
    """자막을 SRT 형식으로 출력"""
    lines = []
    for sub in subtitles:
        lines.append(f"{sub['index']}")
        lines.append(f"{format_timestamp(sub['start'])} --> {format_timestamp(sub['end'])}")
        lines.append(sub['text'])
        lines.append("")
    return '\n'.join(lines)


def snap_srt_to_frames(
    input_path: str | Path,
    output_path: str | Path,
    fps: int = 30
) -> int:
    """
    SRT 파일을 프레임 경계에 맞춰 정렬

    Returns:
        처리된 자막 개수
    """
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    subtitles = parse_srt(content)
    aligned = align_subtitles(subtitles, fps)

    with open(output_path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(format_srt(aligned))

    print(f"✓ 프레임 스냅 완료: {output_path} ({len(subtitles)}개 자막)")
    return len(subtitles)


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

    parser = argparse.ArgumentParser(description="SRT를 프레임 경계에 정렬")
    parser.add_argument("input_path", help="입력 SRT 파일")
    parser.add_argument("output_path", nargs="?", help="출력 SRT 파일 (기본: *_snapped.srt)")
    parser.add_argument("--config", help="설정 파일 경로 (settings.json)")
    parser.add_argument("--fps", type=int, help="프레임레이트 (기본: 30)")

    args = parser.parse_args()

    # 설정 로드 (config 파일 → CLI 인자로 오버라이드)
    settings = load_settings(args.config)
    subtitle_settings = settings.get("subtitle", {})

    fps = args.fps or subtitle_settings.get("fps", 30)

    input_path = Path(args.input_path)
    output_path = args.output_path or input_path.with_stem(input_path.stem + '_snapped')

    snap_srt_to_frames(input_path, output_path, fps)


if __name__ == '__main__':
    main()
