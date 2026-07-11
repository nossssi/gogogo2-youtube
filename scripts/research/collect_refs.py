"""YouTube 레퍼런스 영상 수집 (autoworker-youtube collect.py 이식).

사용법:
    # 딥 벤치마킹용 (채널 공용 — 공식 개정 재료)
    python3 scripts/research/collect_refs.py --channel yadam --benchmark URL1 URL2 ...
    # 프로젝트용 (특정 편의 참고자료)
    python3 scripts/research/collect_refs.py --channel yadam --project 프로젝트명 URL1 ...

출력:
    {목적지}/refs/{번호}/  (benchmark → channels/{채널}/research/refs/,
                           project   → channels/{채널}/projects/{프로젝트}/_refs/)
    ├── meta.md          ← 제목·조회수·구독자·업로드일 + 댓글 TOP 10
    ├── transcript.txt   ← 한국어 자막 (= 대본 전문)
    └── thumbnail.webp
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ytdlp_bin():
    venv = os.path.join(ROOT, ".venv", "bin", "yt-dlp")
    return venv if os.path.exists(venv) else "yt-dlp"


def run_ytdlp_cmd(cmd):
    """--remote-components 미지원 yt-dlp면 그 옵션을 빼고 재시도."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 and "remote-components" in (result.stderr or ""):
        cmd = [c for i, c in enumerate(cmd) if c != "--remote-components" and (i == 0 or cmd[i - 1] != "--remote-components")]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return result


def next_ref_id(ref_dir):
    os.makedirs(ref_dir, exist_ok=True)
    existing = [d for d in os.listdir(ref_dir) if d.isdigit()]
    if not existing:
        return "001"
    return f"{max(int(d) for d in existing) + 1:03d}"


def run_ytdlp(url, output_dir):
    """영상 메타데이터 + 썸네일 + 자막."""
    cmd = [
        ytdlp_bin(),
        "--skip-download",
        "--write-thumbnail",
        "--write-auto-sub",
        "--sub-lang", "ko",
        "--sub-format", "json3",
        "--print-json",
        "--remote-components", "ejs:github",
        "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
        url,
    ]
    result = run_ytdlp_cmd(cmd)
    if result.returncode != 0:
        if "429" in result.stderr or "subtitle" in result.stderr.lower():
            print("  자막 다운로드 실패, 자막 없이 재시도...")
            cmd_no_sub = [c for c in cmd if c not in ("--write-auto-sub", "--sub-lang", "ko", "--sub-format", "json3")]
            result = run_ytdlp_cmd(cmd_no_sub)
        if result.returncode != 0:
            print(f"yt-dlp 에러: {result.stderr}")
            sys.exit(1)
    return json.loads(result.stdout)


def fetch_comments(url):
    """댓글 TOP 10."""
    cmd = [
        ytdlp_bin(),
        "--skip-download",
        "--write-comments",
        "--no-write-info-json",
        "--extractor-args", "youtube:comment_sort=top;max_comments=10",
        "--print-json",
        "--remote-components", "ejs:github",
        url,
    ]
    result = run_ytdlp_cmd(cmd)
    if result.returncode != 0:
        return []
    data = json.loads(result.stdout)
    return (data.get("comments") or [])[:10]


def parse_json3(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        subs = json.load(f)
    segments = []
    for event in subs.get("events", []):
        segs = event.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if text and text != "\n":
            segments.append(text)
    return " ".join(segments)


def parse_transcript(output_dir):
    for f in os.listdir(output_dir):
        if f.endswith(".ko.json3"):
            return parse_json3(os.path.join(output_dir, f))
    return None


def build_meta_md(info, comments):
    ud = info.get("upload_date", "")
    upload_date = f"{ud[:4]}-{ud[4:6]}-{ud[6:8]}" if len(ud) == 8 else ud

    subs = info.get("channel_follower_count") or 0
    subs_str = f"{subs / 10000:.0f}만" if subs >= 10000 else f"{subs:,}"

    comment_rows = ""
    for i, c in enumerate(comments, 1):
        likes = c.get("like_count", 0) or 0
        text = (c.get("text", "") or "").replace("\n", " ").replace("|", "\\|")
        comment_rows += f"| {i} | {likes:,} | {text} |\n"

    comment_count = info.get("comment_count", "N/A")
    if isinstance(comment_count, int):
        comment_count = f"{comment_count:,}"

    return f"""# {info.get('title', '')}

## 기본 정보
- **URL**: https://www.youtube.com/watch?v={info.get('id', '')}
- **채널명**: {info.get('channel', '')}
- **구독자수**: {subs_str}
- **조회수**: {info.get('view_count', 0):,}
- **업로드일**: {upload_date}
- **영상 길이**: {info.get('duration_string', '')}
- **댓글 수**: {comment_count}
- **좋아요 수**: {info.get('like_count') or 0:,}

## 썸네일
![thumbnail](thumbnail.webp)

---

## 댓글 (추천순 TOP 10)

| 순위 | 좋아요 | 댓글 |
|------|--------|------|
{comment_rows}"""


def cleanup(output_dir):
    for f_name in os.listdir(output_dir):
        if f_name.endswith(".webp") and f_name != "thumbnail.webp":
            shutil.copy(os.path.join(output_dir, f_name), os.path.join(output_dir, "thumbnail.webp"))
            os.remove(os.path.join(output_dir, f_name))
            break
    for f_name in os.listdir(output_dir):
        if f_name.endswith(".json3") or f_name.endswith(".info.json"):
            os.remove(os.path.join(output_dir, f_name))


def collect(url, ref_dir, ref_id):
    output_dir = os.path.join(ref_dir, ref_id)
    os.makedirs(output_dir, exist_ok=True)

    print("\n[1/5] 영상 정보 수집 중...")
    info = run_ytdlp(url, output_dir)
    print(f"       → {info.get('title', '(제목 없음)')}")

    print("[2/5] 댓글 수집 중...")
    comments = fetch_comments(url)
    print(f"       → {len(comments)}개 수집")

    print("[3/5] meta.md 생성 중...")
    with open(os.path.join(output_dir, "meta.md"), "w", encoding="utf-8") as f:
        f.write(build_meta_md(info, comments))

    print("[4/5] 자막 파싱 중...")
    ko_text = parse_transcript(output_dir)
    with open(os.path.join(output_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(ko_text or "(자막 없음)")
    print(f"       → {'transcript.txt 저장' if ko_text else '자막 없음'}")

    print("[5/5] 정리 중...")
    cleanup(output_dir)

    rel_path = os.path.relpath(output_dir, ROOT)
    print(f"\n✓ 완료! → {rel_path}/")
    for f_name in sorted(os.listdir(output_dir)):
        size = os.path.getsize(os.path.join(output_dir, f_name))
        print(f"  {f_name} ({size:,} bytes)")


def detect_channel():
    ch_root = os.path.join(ROOT, "channels")
    chans = [d for d in os.listdir(ch_root) if os.path.isdir(os.path.join(ch_root, d)) and not d.startswith("_")]
    if len(chans) == 1:
        return chans[0]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube 레퍼런스 영상 수집")
    parser.add_argument("--channel", default=None, help="채널 폴더명 (미지정 시 1개면 자동)")
    parser.add_argument("--project", default=None, help="프로젝트명 → projects/{프로젝트}/_refs/에 저장")
    parser.add_argument("--benchmark", action="store_true", help="channels/{채널}/research/refs/에 저장 (공식 개정용)")
    parser.add_argument("urls", nargs="+", help="YouTube URL 목록")
    args = parser.parse_args()

    channel = args.channel or detect_channel()
    if not channel:
        print("--channel을 지정해주세요 (channels/에 채널이 여러 개).")
        sys.exit(1)

    if args.benchmark:
        ref_dir = os.path.join(ROOT, "channels", channel, "research", "refs")
    elif args.project:
        ref_dir = os.path.join(ROOT, "channels", channel, "projects", args.project, "_refs")
    else:
        print("--benchmark 또는 --project 중 하나를 지정해주세요.")
        sys.exit(1)

    print(f"수집 대상: {len(args.urls)}개 → {os.path.relpath(ref_dir, ROOT)}/\n{'=' * 40}")
    for i, url in enumerate(args.urls, 1):
        ref_id = next_ref_id(ref_dir)
        print(f"\n[{i}/{len(args.urls)}] refs/{ref_id}/")
        collect(url, ref_dir, ref_id)

    print(f"\n{'=' * 40}\n전체 완료! {os.path.relpath(ref_dir, ROOT)}/ 를 확인하세요.")
