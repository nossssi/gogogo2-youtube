"""워치리스트 채널의 최근 영상을 스캔해 소재 트렌드 리포트를 만든다.

사용법:
    python3 scripts/research/scan_channels.py --channel yadam [--days 30] [--limit 15]
    python3 scripts/research/scan_channels.py --watchlist 경로.json --out-dir 경로   # 테스트/단독 실행

입력:
    channels/{채널}/config/watchlist.json
    { "defaults": {"days":30, "limit_per_channel":15, "min_minutes":10},
      "channels": [{"handle":"@핸들", "name":"표시명", "note":"왜 추적하나"}, ...] }
    (handle 대신 "url"로 채널 주소를 직접 줘도 된다)

출력:
    channels/{채널}/research/scan_YYYYMMDD.json / .md  (조회수/일 정렬 — 소재 트렌드용)

yt-dlp flat-playlist만 사용 — 영상 다운로드 없음, API 키 불필요.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def videos_tab_url(entry):
    """워치리스트 항목 → 채널 /videos 탭 URL (쇼츠 제외됨)."""
    url = (entry.get("url") or "").rstrip("/")
    if not url:
        handle = entry.get("handle", "").strip()
        if not handle:
            raise ValueError(f"handle 또는 url이 필요합니다: {entry}")
        if not handle.startswith("@"):
            handle = "@" + handle
        url = f"https://www.youtube.com/{handle}"
    if not url.endswith("/videos"):
        url += "/videos"
    return url


def run_ytdlp_flat(url, limit):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--extractor-args", "youtubetab:approximate_date",
        "--playlist-items", f"1:{limit}",
        "-J",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()
        raise RuntimeError(tail[-1] if tail else "yt-dlp 실패")
    data = json.loads(result.stdout)
    return data.get("entries") or [], data.get("channel") or data.get("title") or ""


def fmt_duration(sec):
    if not sec:
        return "?"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_upload_date(entry):
    """approximate_date 옵션은 timestamp(epoch)로 준다. upload_date(YYYYMMDD)는 폴백."""
    ts = entry.get("timestamp")
    if ts:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date()
    s = entry.get("upload_date")
    if not s or len(str(s)) != 8:
        return None
    try:
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def scan_one(entry, days, limit, min_minutes, today):
    """채널 하나 스캔 → (rows, error|None)."""
    name = entry.get("name") or entry.get("handle") or entry.get("url")
    try:
        url = videos_tab_url(entry)
        entries, channel_title = run_ytdlp_flat(url, limit)
    except Exception as e:
        return name, [], f"{name}: {e}"
    rows = []
    for e in entries:
        dur = e.get("duration") or 0
        if dur and dur < min_minutes * 60:
            continue
        up = parse_upload_date(e)
        days_ago = (today - up).days if up else None
        if days_ago is not None and days_ago > days:
            continue
        views = e.get("view_count")
        vpd = None
        if views is not None and days_ago is not None:
            vpd = round(views / max(days_ago, 1))
        rows.append({
            "channel": channel_title or name,
            "watch_name": name,
            "note": entry.get("note", ""),
            "id": e.get("id"),
            "url": f"https://www.youtube.com/watch?v={e.get('id')}",
            "title": e.get("title", ""),
            "duration": dur,
            "duration_str": fmt_duration(dur),
            "views": views,
            "days_ago": days_ago,
            "views_per_day": vpd,
        })
    return name, rows, None


def scan(watchlist, days, limit, min_minutes, today, workers=6):
    """전체 워치리스트 병렬 스캔 (채널당 yt-dlp 1회 — 66채널 기준 1~2분)."""
    import concurrent.futures as cf
    rows, errors = [], []
    channels = watchlist.get("channels", [])
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for name, ch_rows, err in pool.map(
            lambda e: scan_one(e, days, limit, min_minutes, today), channels
        ):
            if err:
                errors.append(err)
                print(f"  ✗ {err}")
            else:
                rows.extend(ch_rows)
                print(f"  ✓ {name}: 최근 {days}일 내 {len(ch_rows)}편")
    rows.sort(key=lambda r: (r["views_per_day"] is None, -(r["views_per_day"] or r["views"] or 0)))
    return rows, errors


def load_referenced_ids(out_dir):
    """소재 대장(topic_log.json)에서 이미 참고한 영상 id 집합."""
    path = os.path.join(out_dir, "topic_log.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            log = json.load(f)
        return {vid for e in log.get("entries", []) for vid in e.get("refs", [])}
    except (json.JSONDecodeError, TypeError):
        return set()


def recent_motifs(out_dir, n=3):
    """소재 대장의 최근 n편 감정축·모티프 (리포트 머리에 표시 — 중복 회피용)."""
    path = os.path.join(out_dir, "topic_log.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            log = json.load(f)
        return log.get("entries", [])[-n:]
    except (json.JSONDecodeError, TypeError):
        return []


def build_md(rows, errors, days, today, referenced, recents):
    lines = [f"# 워치리스트 스캔 — {today.isoformat()} (최근 {days}일)", ""]
    lines.append("소재 트렌드 리포트. **조회수/일** 순 정렬 — 위쪽이 지금 터지는 소재. 여기서 CONCEPT 소재 후보를 고른다.")
    if recents:
        lines.append("")
        lines.append("**최근 제작 편** (감정축·모티프 중복 회피 — topic_log.json):")
        for e in recents:
            motifs = "·".join(e.get("motifs", []))
            lines.append(f"- {e.get('date', '?')} {e.get('project', '?')} — {e.get('emotion', '?')} / {motifs}")
    lines.append("")
    lines.append("| # | 참고 | 조회수/일 | 조회수 | 경과 | 길이 | 채널 | 제목 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        used = "✓" if r["id"] in referenced else ""
        vpd = f"{r['views_per_day']:,}" if r["views_per_day"] is not None else "?"
        views = f"{r['views']:,}" if r["views"] is not None else "?"
        ago = f"{r['days_ago']}일" if r["days_ago"] is not None else "?"
        lines.append(f"| {i} | {used} | {vpd} | {views} | {ago} | {r['duration_str']} | {r['channel']} | [{r['title']}]({r['url']}) |")
    if referenced:
        lines.append("")
        lines.append("✓ = 이전 편에서 이미 참고한 영상 (topic_log.json refs)")
    if errors:
        lines += ["", "## 스캔 실패", ""] + [f"- {e}" for e in errors]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="워치리스트 채널 최근 영상 스캔")
    parser.add_argument("--channel", help="채널 폴더명 (channels/{채널}/config/watchlist.json 사용)")
    parser.add_argument("--watchlist", help="watchlist.json 경로 직접 지정 (--channel 대신)")
    parser.add_argument("--out-dir", help="출력 폴더 (기본: channels/{채널}/research)")
    parser.add_argument("--days", type=int, help="최근 N일 (기본: watchlist defaults 또는 30)")
    parser.add_argument("--limit", type=int, help="채널당 최신 N편 조회 (기본: 15)")
    parser.add_argument("--min-minutes", type=int, help="이 길이 미만 영상 제외 (기본: 10)")
    args = parser.parse_args()

    if args.watchlist:
        wl_path = args.watchlist
        out_dir = args.out_dir or os.path.dirname(os.path.abspath(wl_path))
    elif args.channel:
        wl_path = os.path.join(ROOT, "channels", args.channel, "config", "watchlist.json")
        out_dir = args.out_dir or os.path.join(ROOT, "channels", args.channel, "research")
    else:
        parser.error("--channel 또는 --watchlist 필요")

    if not os.path.exists(wl_path):
        print(f"워치리스트 없음: {wl_path}")
        sys.exit(1)
    with open(wl_path, encoding="utf-8") as f:
        watchlist = json.load(f)
    if not watchlist.get("channels"):
        print(f"워치리스트에 채널이 없습니다. {wl_path} 의 channels[]를 채워주세요.")
        sys.exit(1)

    defaults = watchlist.get("defaults", {})
    days = args.days or defaults.get("days", 30)
    limit = args.limit or defaults.get("limit_per_channel", 15)
    min_minutes = args.min_minutes if args.min_minutes is not None else defaults.get("min_minutes", 10)
    today = datetime.date.today()

    print(f"스캔: 채널 {len(watchlist['channels'])}개, 최근 {days}일, 채널당 최신 {limit}편, {min_minutes}분 미만 제외")
    rows, errors = scan(watchlist, days, limit, min_minutes, today)

    referenced = load_referenced_ids(out_dir)
    recents = recent_motifs(out_dir)
    for r in rows:
        r["referenced"] = r["id"] in referenced

    os.makedirs(out_dir, exist_ok=True)
    stamp = today.strftime("%Y%m%d")
    json_path = os.path.join(out_dir, f"scan_{stamp}.json")
    md_path = os.path.join(out_dir, f"scan_{stamp}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"date": today.isoformat(), "days": days, "rows": rows, "errors": errors}, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_md(rows, errors, days, today, referenced, recents))

    print(f"\n✓ {len(rows)}편 → {os.path.relpath(md_path, ROOT)}")
