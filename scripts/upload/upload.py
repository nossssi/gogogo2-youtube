"""
YouTube 업로드 스크립트.

프로젝트의 영상을 YouTube에 비공개로 업로드.
제목/설명은 output/youtube.md(우선) 또는 {P}/meta.txt에서 자동 추출하거나 인자로 전달.

사용법:
  .venv/bin/python scripts/upload/upload.py \
    --project 중고차-몰락 \
    [--title "제목"] \
    [--description "설명"] \
    [--tags "태그1,태그2"] \
    [--thumbnail path/to/thumb.png] \
    [--privacy private|unlisted|public]
"""

import argparse
import json
import re
import sys
from pathlib import Path

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_resolver import resolve_project_dir

VALID_PRIVACY = ("private", "unlisted", "public")


def load_credentials(channel_name: str) -> Credentials:
    """채널의 OAuth 토큰을 로드하고 필요시 갱신."""
    channel_dir = ROOT / "channels" / channel_name
    token_path = channel_dir / "config" / "youtube-api" / "token.json"

    if not token_path.exists():
        print(f"[ERROR] 토큰 없음: {token_path}")
        print(f"[ERROR] 먼저 인증을 실행하세요:")
        print(f"  .venv/bin/python scripts/upload/auth.py --channel \"{channel_name}\"")
        sys.exit(1)

    token_data = json.loads(token_path.read_text())
    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data.get("scopes"),
    )

    if creds.expired and creds.refresh_token:
        print("[INFO] 토큰 갱신 중...")
        creds.refresh(google.auth.transport.requests.Request())
        token_data["token"] = creds.token
        token_path.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
        print("[OK] 토큰 갱신 완료")

    return creds


def find_video_file(project_dir: Path) -> Path:
    """프로젝트에서 업로드할 영상 파일을 찾음."""
    output_dir = project_dir / "output"
    mp4_files = sorted(output_dir.glob("*.mp4"))

    if not mp4_files:
        print("[ERROR] 업로드할 영상 파일을 찾을 수 없습니다.")
        print(f"[ERROR] 확인 경로: {output_dir}")
        sys.exit(1)

    if len(mp4_files) > 1:
        print(f"[WARN] output/에 mp4가 {len(mp4_files)}개 있어 첫 번째를 사용합니다: {mp4_files[0].name}")

    return mp4_files[0]


def extract_metadata_from_youtube_md(project_dir: Path) -> dict:
    """output/youtube.md에서 제목, 설명, 태그를 추출."""
    youtube_md = project_dir / "output" / "youtube.md"
    metadata = {"title": "", "description": "", "tags": [], "pinned_comment": ""}

    if not youtube_md.exists():
        return metadata

    content = youtube_md.read_text()

    # 섹션별 파싱
    sections = re.split(r"\n## ", content)
    for section in sections:
        if section.startswith("제목"):
            lines = section.split("\n", 1)
            if len(lines) > 1:
                metadata["title"] = lines[1].strip()

        elif section.startswith("설명글"):
            lines = section.split("\n", 1)
            if len(lines) > 1:
                metadata["description"] = lines[1].strip()

        elif section.startswith("태그"):
            lines = section.split("\n", 1)
            if len(lines) > 1:
                raw = lines[1].strip()
                # #태그, #태그 또는 태그, 태그 형식 모두 지원
                tags = [t.strip().lstrip("#") for t in raw.split(",") if t.strip()]
                metadata["tags"] = tags

        elif section.startswith("고정 댓글"):
            lines = section.split("\n", 1)
            if len(lines) > 1:
                metadata["pinned_comment"] = lines[1].strip()

    return metadata


def extract_metadata_from_meta_txt(project_dir: Path) -> dict:
    """{P}/meta.txt에서 제목/설명/태그를 추출 (youtube.md 없을 때 폴백).

    meta.txt 규약: [제목] / [썸네일 문구] / [설명문](해시태그 줄 포함) / [제작 메모]
    """
    meta_path = project_dir / "meta.txt"
    metadata = {"title": "", "description": "", "tags": [], "pinned_comment": ""}

    if not meta_path.exists():
        return metadata

    content = meta_path.read_text(encoding="utf-8")
    sections = {}
    for m in re.finditer(r"\[([^\]]+)\]\n(.*?)(?=\n\[|\Z)", content, re.DOTALL):
        sections[m.group(1).strip()] = m.group(2).strip()

    metadata["title"] = sections.get("제목", "").splitlines()[0].strip() if sections.get("제목") else ""
    desc = sections.get("설명문", "")
    metadata["description"] = desc
    metadata["tags"] = re.findall(r"#([\w가-힣]+)", desc)

    return metadata


def get_channel_from_workflow(project_dir: Path) -> str:
    """workflow.json에서 채널명을 읽음."""
    workflow_path = project_dir / "workflow.json"
    if workflow_path.exists():
        data = json.loads(workflow_path.read_text())
        return data.get("channel", "")
    return ""


def upload_video(
    creds: Credentials,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    thumbnail_path: Path | None = None,
) -> dict:
    """YouTube에 영상 업로드."""
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    print(f"[INFO] 업로드 시작: {video_path.name}")
    print(f"[INFO] 제목: {title}")
    print(f"[INFO] 공개상태: {privacy}")
    print(f"[INFO] 파일 크기: {video_path.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    import time

    response = None
    retry_count = 0
    max_retries = 10
    while response is None:
        try:
            status, response = request.next_chunk(num_retries=5)
            if status:
                pct = int(status.progress() * 100)
                print(f"  업로드 중... {pct}%")
            retry_count = 0
        except Exception as e:
            error_name = type(e).__name__
            retry_count += 1
            if retry_count > max_retries:
                raise
            wait = min(2 ** retry_count * 5, 120)
            print(f"  [WARN] {error_name}: {e}")
            print(f"  [WARN] {wait}초 후 재시도... ({retry_count}/{max_retries})")
            time.sleep(wait)

    video_id = response["id"]
    print()
    print(f"[OK] 업로드 완료!")
    print(f"[OK] Video ID: {video_id}")
    print(f"[OK] URL: https://studio.youtube.com/video/{video_id}/edit")

    # 썸네일 업로드 (2MB 초과 시 자동 압축)
    if thumbnail_path and thumbnail_path.exists():
        upload_thumb = thumbnail_path
        if thumbnail_path.stat().st_size > 2_000_000:
            try:
                from PIL import Image
                import io
                img = Image.open(thumbnail_path)
                # JPEG로 변환하여 압축
                compressed = thumbnail_path.parent / f"{thumbnail_path.stem}_compressed.jpg"
                quality = 90
                while quality >= 30:
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=quality)
                    if buf.tell() <= 2_000_000:
                        with open(compressed, "wb") as f:
                            f.write(buf.getvalue())
                        print(f"[INFO] 썸네일 압축: {thumbnail_path.stat().st_size // 1024}KB → {compressed.stat().st_size // 1024}KB")
                        upload_thumb = compressed
                        break
                    quality -= 10
            except ImportError:
                print("[WARN] Pillow 미설치 — 썸네일 압축 건너뜀")
        print(f"[INFO] 썸네일 업로드 중: {upload_thumb.name}")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(upload_thumb)),
        ).execute()
        print(f"[OK] 썸네일 설정 완료")

    return response


def save_upload_result(project_dir: Path, response: dict, privacy: str) -> None:
    """업로드 결과를 프로젝트에 저장."""
    result = {
        "video_id": response["id"],
        "title": response["snippet"]["title"],
        "url": f"https://youtu.be/{response['id']}",
        "studio_url": f"https://studio.youtube.com/video/{response['id']}/edit",
        "privacy": privacy,
        "uploaded_at": response["snippet"]["publishedAt"],
    }
    result_path = project_dir / "output" / "upload_result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"[OK] 결과 저장: {result_path}")


def main():
    parser = argparse.ArgumentParser(description="YouTube 영상 업로드")
    parser.add_argument("--project", required=True, help="프로젝트명 (channels/{채널}/projects/ 하위 폴더명)")
    parser.add_argument("--title", help="영상 제목 (미지정시 youtube.md/meta.txt에서 추출)")
    parser.add_argument("--description", default="", help="영상 설명")
    parser.add_argument("--tags", default="", help="태그 (쉼표 구분)")
    parser.add_argument("--thumbnail", help="썸네일 이미지 경로")
    parser.add_argument("--privacy", default="private", choices=VALID_PRIVACY, help="공개 상태 (기본: private)")
    parser.add_argument("--video", help="영상 파일 경로 (미지정시 자동 탐색)")
    parser.add_argument("--channel", help="채널명 (미지정시 workflow.json에서 추출)")
    args = parser.parse_args()

    # 프로젝트 경로
    try:
        project_dir = resolve_project_dir(args.project, args.channel)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    if not project_dir.exists():
        print(f"[ERROR] 프로젝트 없음: {project_dir}")
        sys.exit(1)

    # 채널 결정
    channel = args.channel or get_channel_from_workflow(project_dir)
    if not channel:
        print("[ERROR] 채널을 지정하세요 (--channel 또는 workflow.json)")
        sys.exit(1)

    # 영상 파일
    if args.video:
        video_path = Path(args.video)
        if not video_path.is_absolute():
            video_path = ROOT / video_path
    else:
        video_path = find_video_file(project_dir)

    print(f"[INFO] 채널: {channel}")
    print(f"[INFO] 프로젝트: {args.project}")
    print(f"[INFO] 영상: {video_path}")
    print()

    # 메타데이터: youtube.md 우선, 없으면 concept.md 폴백
    yt_meta = extract_metadata_from_youtube_md(project_dir)
    concept_meta = extract_metadata_from_meta_txt(project_dir)

    title = args.title or yt_meta["title"] or concept_meta["title"]
    if not title:
        print("[ERROR] 제목을 지정하세요 (--title 또는 youtube.md/meta.txt)")
        sys.exit(1)

    description = args.description or yt_meta["description"] or concept_meta["description"]
    tags_from_arg = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    tags = tags_from_arg or yt_meta["tags"] or concept_meta.get("tags", [])

    # 썸네일: 인자 > output/thumbnails/ 자동 탐색
    thumbnail_path = None
    if args.thumbnail:
        thumbnail_path = Path(args.thumbnail)
        if not thumbnail_path.is_absolute():
            thumbnail_path = ROOT / thumbnail_path
    else:
        thumb_dir = project_dir / "output" / "thumbnails"
        if thumb_dir.exists():
            thumbs = sorted(thumb_dir.glob("*.png")) + sorted(thumb_dir.glob("*.jpg"))
            if thumbs:
                thumbnail_path = thumbs[0]

    # 인증
    creds = load_credentials(channel)

    # 업로드
    response = upload_video(
        creds=creds,
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy=args.privacy,
        thumbnail_path=thumbnail_path,
    )

    # 결과 저장
    save_upload_result(project_dir, response, args.privacy)


if __name__ == "__main__":
    main()
