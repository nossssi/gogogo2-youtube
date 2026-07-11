"""프로젝트 디렉토리 해석 모듈.

모든 Python 스크립트가 공유하는 프로젝트 경로 해석 함수.

해석 우선순위:
1. --channel 명시 → ROOT/channels/{channel}/projects/{project}
2. 미명시 → channels/*/projects/ 전체 스캔하여 매칭
3. 폴백 → 레거시 ROOT/projects/{project}
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def resolve_project_dir(project: str, channel: str | None = None) -> Path:
    """프로젝트 디렉토리 경로를 해석한다.

    Args:
        project: 프로젝트 폴더명
        channel: 채널명 (None이면 자동 스캔)

    Returns:
        프로젝트 디렉토리 Path

    Raises:
        FileNotFoundError: 프로젝트를 찾을 수 없을 때
    """
    # 1. 채널 명시
    if channel:
        return ROOT / "channels" / channel / "projects" / project

    # 2. channels/*/projects/ 스캔
    channels_dir = ROOT / "channels"
    if channels_dir.exists():
        matches = list(channels_dir.glob(f"*/projects/{project}"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            channels = [m.parent.parent.name for m in matches]
            raise FileNotFoundError(
                f"프로젝트 '{project}'가 여러 채널에 존재합니다: {channels}. "
                f"--channel로 채널을 명시하세요."
            )

    # 3. 레거시 폴백
    legacy = ROOT / "projects" / project
    if legacy.exists():
        return legacy

    raise FileNotFoundError(
        f"프로젝트 '{project}'를 찾을 수 없습니다. "
        f"channels/*/projects/ 및 projects/ 모두 확인했습니다."
    )


def scan_video_id_map(channel: str) -> dict[str, Path]:
    """채널의 모든 프로젝트(archive + 진행 중)를 스캔해 video_id → project_dir 매핑 반환.

    각 프로젝트의 output/upload_result.json에서 video_id를 읽어 dict 구성.
    upload_result.json이 없거나 video_id가 비어 있으면 스킵.
    """
    result: dict[str, Path] = {}
    base = ROOT / "channels" / channel / "projects"
    if not base.exists():
        return result

    scan_dirs = [base]
    archive = base / "_archive"
    if archive.exists():
        scan_dirs.append(archive)

    for scan_dir in scan_dirs:
        for project_dir in scan_dir.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith("_"):
                continue
            upload_result = project_dir / "output" / "upload_result.json"
            if not upload_result.exists():
                continue
            try:
                data = json.loads(upload_result.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            video_id = data.get("video_id")
            if video_id:
                result[video_id] = project_dir

    return result
