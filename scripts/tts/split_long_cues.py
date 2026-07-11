#!/usr/bin/env python3
"""
Vrew 자막 큐 정형화 (반수동 모드 후처리) — 두 패스:

패스 0) 문장 경계 스냅 — 큐 하나가 대본 문장 경계를 걸치면(짧은 문장들이 한 클립에
    합쳐진 경우 등) 그 경계에서 큐를 분할한다. Vrew는 자막에서 문장부호를 지우므로
    경계 위치는 대본(sentences.json)↔자막의 비공백 글자 정렬로 찾는다(텍스트 동일 시
    항등, 다르면 difflib 블록+선형보간 — Vrew에서 표기를 줄여도 위치 보존).
    이 패스 덕에 씬 경계(storyboard sentences)가 항상 큐 경계와 일치한다.
패스 1) 길이 분할 — 비공백 글자수 > max_chars 인 큐를 어절 경계에서 균등 분할
    (쉼표 등 구두점 경계 우선).

타이밍 근거 2단계 (두 패스 공통):
    1) whisper — {V}/whisper/audio.json (openai-whisper --word_timestamps True)의
       단어별 실측 시각으로 분할점을 찍는다. 큐 구간 안의 인식 글자수가 원문과
       25% 이상 어긋나면 그 큐는 신뢰하지 않고 2)로.
    2) ratio — 큐 길이를 비공백 음절 수 비례로 나눈다 (오차 ±0.2초 수준).
    새 경계는 fps 프레임 그리드에 스냅, 조각당 최소 10프레임 보장.

출력:
    {V}/subtitle.split.srt   적용본(스냅+분할) — 검수 후 subtitle.srt로 교체
    {V}/split_report.json    {"sentence_snap": [...], "long_split": [...]} + 문장별 큐 범위
    --apply 시 추가로:
      {V}/subtitle.srt 교체 + {V}/sentences.json에 문장별 실측 큐 범위 기록
      (cue_range/start/end/words 갱신, settings.cue_count) → scene_timing이 비례 추정
      대신 이 실측 매핑을 쓴다(정밀 모드).

Usage:
    python3 scripts/tts/split_long_cues.py <project_dir> [--config settings.json] [--apply]
"""
import argparse
import bisect
import difflib
import json
import math
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from align_to_frames import parse_srt, format_srt, snap_to_frame


def norm(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w가-힣]", "", s))


def run_whisper(audio: pathlib.Path, out_dir: pathlib.Path, model: str = "medium") -> pathlib.Path:
    """whisper CLI로 단어 타임스탬프 생성 (있으면 재사용)."""
    j = out_dir / (audio.stem + ".json")
    if j.exists():
        if j.stat().st_mtime >= audio.stat().st_mtime:
            return j
        print(f"♻️  whisper 캐시가 오디오보다 오래됨 — 재실행 ({j.name})")
        j.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"⏳ whisper {model} 실행 중 ({audio.name}) — 수 분 걸립니다…")
    r = subprocess.run(
        ["whisper", str(audio), "--model", model, "--language", "ko",
         "--word_timestamps", "True", "--output_format", "json",
         "--output_dir", str(out_dir)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not j.exists():
        print(f"⚠️ whisper 실패 — ratio 폴백만 사용: {r.stderr[-300:]}")
        return None
    return j


def load_words(whisper_json: pathlib.Path) -> list[dict]:
    """whisper JSON → [{start, end, chars}] (비공백 글자수)."""
    data = json.loads(whisper_json.read_text(encoding="utf-8"))
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            c = norm(w["word"])
            if c:
                words.append({"start": w["start"], "end": w["end"], "chars": len(c)})
    return words


def chunk_text(text: str, max_chars: int) -> list[str]:
    """어절 경계 분할 — 쉼표 등 구두점 뒤를 우선하되 조각 균형 유지.

    n조각 연속 분할 전수 탐색(토큰 수가 작아 부담 없음):
    비용 = Σ(조각길이-목표)² − 구두점 경계 보너스. 초과 조각이 생기면 n을 늘린다.
    """
    tokens = text.split()
    lens = [len(t) for t in tokens]
    total = sum(lens)
    n = max(2, math.ceil(total / max_chars))
    PUNCT_BONUS = -(max_chars ** 2)  # 구두점 경계 1개 ≈ 상당한 불균형까지 감수

    def solve(n: int):
        target = total / n
        best = {}  # (start_idx, chunks_left) -> (cost, split_list)

        def rec(i: int, left: int):
            if (i, left) in best:
                return best[(i, left)]
            if left == 1:
                size = sum(lens[i:])
                cost = float("inf") if size > max_chars else (size - target) ** 2
                best[(i, left)] = (cost, [])
                return best[(i, left)]
            res = (float("inf"), None)
            size = 0
            for j in range(i, len(tokens) - left + 1):
                size += lens[j]
                if size > max_chars:
                    break
                sub_cost, sub_splits = rec(j + 1, left - 1)
                cost = (size - target) ** 2 + sub_cost
                if tokens[j][-1] in ",!?…":
                    cost += PUNCT_BONUS
                if cost < res[0]:
                    res = (cost, [j + 1] + sub_splits)
            best[(i, left)] = res
            return res

        cost, splits = rec(0, n)
        return (splits if cost != float("inf") else None)

    while n <= len(tokens):
        splits = solve(n)
        if splits is not None:
            chunks, prev = [], 0
            for s in splits + [len(tokens)]:
                chunks.append(" ".join(tokens[prev:s]))
                prev = s
            return chunks
        n += 1
    return tokens  # 모든 어절이 초장 — 어절 단위로라도 반환


def build_offset_map(S: str, C: str):
    """대본 norm-공간 오프셋 → 자막 norm-공간 오프셋 함수.

    동일하면 항등. 다르면(Vrew에서 표기 축약/수정) difflib 일치 블록을 앵커로
    삼고 블록 사이는 선형보간 — 편집이 없는 구간의 경계는 정확히, 편집 구간
    안의 경계는 근사로 매핑된다(이후 어절 경계 스냅이 오차를 흡수)."""
    if S == C:
        return lambda p: float(p)
    sm = difflib.SequenceMatcher(None, S, C, autojunk=False)
    pts = [(0, 0)]
    for a, b, size in sm.get_matching_blocks():
        for p in ((a, b), (a + size, b + size)):
            if p[0] > pts[-1][0] and p[1] >= pts[-1][1]:
                pts.append(p)
    if pts[-1] != (len(S), len(C)):
        pts.append((len(S), len(C)))
    xs = [p[0] for p in pts]

    def f(p):
        i = bisect.bisect_right(xs, p) - 1
        if i >= len(pts) - 1:
            return float(pts[-1][1])
        a0, b0 = pts[i]
        a1, b1 = pts[i + 1]
        if a1 == a0:
            return float(b0)
        return b0 + (p - a0) * (b1 - b0) / (a1 - a0)

    return f


def snap_sentence_bounds(subs: list[dict], sentences: list[dict],
                         words: list[dict], fps: int):
    """패스 0 — 문장 경계가 큐 내부에 떨어지면 그 자리에서 큐를 분할.

    returns (새 큐 리스트, bounds, 리포트)
      bounds: 각 문장 끝의 자막 norm-공간 오프셋(float, 문장 수만큼).
              이후 최종 큐→문장 배속(sentence_cue_assign)에 쓴다.
    """
    S_parts = [norm(s["text"]) for s in sentences]
    fmap = build_offset_map("".join(S_parts), "".join(norm(s["text"]) for s in subs))
    bounds, acc = [], 0
    for part in S_parts:
        acc += len(part)
        bounds.append(fmap(acc))

    min_ms = round(10 * 1000 / fps)
    out, report = [], []
    cpos = 0
    for sub in subs:
        text = sub["text"].replace("\n", " ").strip()
        cn = len(norm(text))
        c0 = cpos
        cpos += cn
        inner = [b - c0 for b in bounds[:-1] if c0 < b < c0 + cn]
        if not inner or cn == 0:
            out.append(dict(sub))
            continue

        # 경계 목표(비공백 위치)마다 가장 가까운 어절 경계 선택 — 양 끝이 최근접이면 분할 불필요
        tokens = text.split()
        cand, a = [0], 0
        for t in tokens:
            a += len(norm(t))
            cand.append(a)
        picks = []  # (norm위치, 토큰 경계 index)
        for d in sorted(inner):
            j = min(range(len(cand)), key=lambda i: (abs(cand[i] - d), i))
            if 0 < j < len(tokens) and all(j != pj for _, pj in picks):
                picks.append((cand[j], j))
        if not picks:
            out.append(dict(sub))
            continue

        dur = sub["end"] - sub["start"]
        min_local = max(1, min(min_ms, dur // (len(picks) + 1)))
        engine = "whisper"
        t0, t1 = sub["start"] / 1000, sub["end"] / 1000
        bounds_ms, prev_ms = [], sub["start"]
        for i, (p, _) in enumerate(picks):
            b = whisper_boundary(words, t0, t1, p, cn) if words else None
            if b is None:
                engine = "ratio"
                b = t0 + (t1 - t0) * p / cn
            ms = snap_to_frame(round(b * 1000), fps)
            ms = max(prev_ms + min_local, min(ms, sub["end"] - min_local * (len(picks) - i)))
            bounds_ms.append(ms)
            prev_ms = ms

        edges_tok = [0] + [j for _, j in picks] + [len(tokens)]
        edges_ms = [sub["start"]] + bounds_ms + [sub["end"]]
        pieces = []
        for i in range(len(edges_tok) - 1):
            piece = {"start": edges_ms[i], "end": edges_ms[i + 1],
                     "text": " ".join(tokens[edges_tok[i]:edges_tok[i + 1]])}
            out.append(piece)
            pieces.append(piece)
        report.append({
            "orig_index": sub["index"], "engine": engine,
            "before": {"start": sub["start"], "end": sub["end"], "text": text, "chars": cn},
            "after": [{"start": p["start"], "end": p["end"], "text": p["text"],
                       "chars": len(norm(p["text"]))} for p in pieces],
        })
    for i, s in enumerate(out):
        s["index"] = i + 1
    return out, bounds, report


def sentence_cue_assign(final_subs: list[dict], bounds: list[float]) -> list[int]:
    """최종 큐 각각을 문장 idx에 배속 — 큐의 norm-글자 중앙 위치가 속한 문장."""
    tags, cpos = [], 0
    for sub in final_subs:
        cn = len(norm(sub["text"])) or 1
        mid = cpos + cn / 2
        tags.append(min(bisect.bisect_left(bounds, mid), len(bounds) - 1))
        cpos += cn
    return tags


def whisper_boundary(words: list[dict], cue_start: float, cue_end: float,
                     char_pos: int, cue_chars: int):
    """큐 구간 안 whisper 단어들로 char_pos(비공백 누적 위치)의 실측 시각을 찾는다."""
    inside = [w for w in words if w["end"] > cue_start + 0.02 and w["start"] < cue_end - 0.02]
    got = sum(w["chars"] for w in inside)
    if not inside or cue_chars == 0 or abs(got - cue_chars) / cue_chars > 0.25:
        return None  # 인식 불량 → ratio 폴백
    # 인식 글자수 기준으로 위치 재비례 (원문과 총량이 조금 달라도 위치는 보존됨)
    pos = char_pos * got / cue_chars
    acc = 0
    for w in inside:
        if acc + w["chars"] >= pos:
            frac = (pos - acc) / w["chars"]
            return w["start"] + (w["end"] - w["start"]) * frac
        acc += w["chars"]
    return inside[-1]["end"]


def split_cues(subs: list[dict], words: list[dict], max_chars: int, fps: int):
    """분할 적용. returns (새 큐 리스트, 리포트)."""
    min_ms = round(10 * 1000 / fps)  # 조각당 최소 10프레임
    out, report = [], []
    for sub in subs:
        text = sub["text"].replace("\n", " ").strip()
        chars = len(text.replace(" ", ""))
        if chars <= max_chars:
            out.append(dict(sub))
            continue

        chunks = chunk_text(text, max_chars)
        t0, t1 = sub["start"] / 1000, sub["end"] / 1000

        # 조각 경계의 비공백 누적 위치들
        positions, acc = [], 0
        for c in chunks[:-1]:
            acc += len(c.replace(" ", ""))
            positions.append(acc)

        engine = "whisper"
        bounds_ms = []
        prev_ms = sub["start"]
        for i, p in enumerate(positions):
            b = whisper_boundary(words, t0, t1, p, chars) if words else None
            if b is None:
                engine = "ratio"
                b = t0 + (t1 - t0) * p / chars
            ms = snap_to_frame(round(b * 1000), fps)
            ms = max(prev_ms + min_ms, min(ms, sub["end"] - min_ms * (len(positions) - i)))
            bounds_ms.append(ms)
            prev_ms = ms

        edges = [sub["start"]] + bounds_ms + [sub["end"]]
        pieces = []
        for i, c in enumerate(chunks):
            piece = {"start": edges[i], "end": edges[i + 1], "text": c}
            out.append(piece)
            pieces.append(piece)
        report.append({
            "orig_index": sub["index"], "engine": engine,
            "before": {"start": sub["start"], "end": sub["end"], "text": text, "chars": chars},
            "after": [{"start": p["start"], "end": p["end"], "text": p["text"],
                       "chars": len(p["text"].replace(" ", ""))} for p in pieces],
        })
    for i, s in enumerate(out):
        s["index"] = i + 1
    return out, report


def update_sentences_json(sent_path: pathlib.Path, sent_data: dict,
                          final_subs: list[dict], tags: list[int],
                          snap_stats: dict) -> list[int]:
    """--apply 시 sentences.json에 문장별 실측 큐 범위·타이밍 기록. returns 큐 없는 문장 idx들."""
    ranges = {}
    for k, t in enumerate(tags, start=1):
        if t not in ranges:
            ranges[t] = [k, k]
        else:
            ranges[t][1] = k

    missing = []
    for s in sent_data["sentences"]:
        r = ranges.get(s["idx"])
        s["cue_range"] = r
        if not r:
            missing.append(s["idx"])
            continue
        start = final_subs[r[0] - 1]["start"] / 1000
        end = final_subs[r[1] - 1]["end"] / 1000
        s["start"], s["end"] = round(start, 3), round(end, 3)
        tokens = s["text"].split()
        total = sum(len(t) for t in tokens) or 1
        cur, ws = start, []
        for t in tokens:
            d = (end - start) * len(t) / total
            ws.append({"word": t, "start": round(cur, 3), "end": round(cur + d, 3)})
            cur += d
        s["words"] = ws

    sent_data.setdefault("settings", {})
    sent_data["settings"]["cue_count"] = len(final_subs)
    sent_data["settings"]["sentence_snap"] = snap_stats
    sent_path.write_text(json.dumps(sent_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--config", help="settings.json 경로 (fps, max_chars)")
    ap.add_argument("--video-subdir", default="_video")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--no-whisper", action="store_true", help="ratio 분배만 사용")
    ap.add_argument("--no-snap", action="store_true", help="문장 경계 스냅(패스 0) 생략")
    ap.add_argument("--apply", action="store_true", help="subtitle.srt 교체 + sentences.json에 큐 범위 기록")
    args = ap.parse_args()

    settings = {}
    if args.config and pathlib.Path(args.config).exists():
        settings = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    fps = settings.get("subtitle", {}).get("fps", 30)
    max_chars = settings.get("subtitle", {}).get("max_chars", 20)

    V = args.project_dir.resolve() / args.video_subdir
    srt_path = V / "subtitle.srt"
    subs = parse_srt(srt_path.read_text(encoding="utf-8-sig"))

    sent_path = V / "sentences.json"
    sent_data = None
    if not args.no_snap:
        if sent_path.exists():
            sent_data = json.loads(sent_path.read_text(encoding="utf-8"))
            if not isinstance(sent_data, dict):
                sent_data = {"settings": {}, "sentences": sent_data}
        else:
            print("⚠️ sentences.json 없음 — 문장 경계 스냅 건너뜀 (ingest_vrew를 먼저 실행하세요)")

    words = []
    if not args.no_whisper:
        wj = run_whisper(V / "audio.mp3", V / "whisper", args.model)
        if wj:
            words = load_words(wj)
            print(f"✓ whisper 단어 {len(words)}개 로드")

    # 패스 0 — 문장 경계 스냅
    bounds, snap_report = None, []
    if sent_data:
        subs, bounds, snap_report = snap_sentence_bounds(subs, sent_data["sentences"], words, fps)
        if snap_report:
            print(f"✂️  문장 경계를 걸친 큐 {len(snap_report)}개를 경계에서 분할:")
            for r in snap_report:
                print(f"    큐{r['orig_index']} [{r['engine']}] {r['before']['text'][:36]!r} → {len(r['after'])}조각")
        else:
            print("✓ 문장 경계 스냅: 모든 문장 경계가 이미 큐 경계와 일치")

    # 패스 1 — 길이 분할
    new_subs, report = split_cues(subs, words, max_chars, fps)
    n_w = sum(1 for r in report if r["engine"] == "whisper")
    n_r = sum(1 for r in report if r["engine"] == "ratio")

    # 최종 큐 → 문장 배속 (스냅을 돌린 경우에만 가능)
    tags, missing_preview = None, []
    if bounds is not None:
        tags = sentence_cue_assign(new_subs, bounds)
        if tags != sorted(tags):
            print("⚠️ 큐→문장 배속이 단조가 아님 — 대본과 자막 순서가 다릅니다. 결과 검수 필요.")
        present = set(tags)
        missing_preview = [s["idx"] for s in sent_data["sentences"] if s["idx"] not in present]
        if missing_preview:
            print(f"⚠️ 자막 큐가 하나도 배속되지 않은 문장 {len(missing_preview)}개: {missing_preview[:10]}"
                  f"{' …' if len(missing_preview) > 10 else ''} — Vrew에서 문장이 삭제된 듯. 씬 경계는 이웃 문장으로 보정됩니다.")

    (V / "subtitle.split.srt").write_text(format_srt(new_subs), encoding="utf-8-sig", newline="\r\n")
    (V / "split_report.json").write_text(json.dumps(
        {"sentence_snap": snap_report, "long_split": report},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 최종 {len(new_subs)}큐 (문장스냅 {len(snap_report)}개 · 20자분할 {len(report)}개: whisper {n_w}, ratio {n_r})")
    print(f"✓ {V/'subtitle.split.srt'}\n✓ {V/'split_report.json'}")

    if args.apply:
        srt_path.write_text(format_srt(new_subs), encoding="utf-8-sig", newline="\r\n")
        print(f"✓ subtitle.srt 교체 완료")
        if tags is not None:
            snap_stats = {"splits": len(snap_report),
                          "engines": sorted({r["engine"] for r in snap_report})}
            update_sentences_json(sent_path, sent_data, new_subs, tags, snap_stats)
            print(f"✓ sentences.json 갱신 — 문장별 cue_range/start/end 실측 기록 "
                  f"(scene_timing이 정밀 모드로 동작)")
    else:
        print("  검수 후 적용: --apply 재실행 또는 subtitle.split.srt를 subtitle.srt로 복사")
    return 0


if __name__ == "__main__":
    sys.exit(main())
