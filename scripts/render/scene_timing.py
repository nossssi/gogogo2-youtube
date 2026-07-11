#!/usr/bin/env python3
"""
씬 → 오디오 타이밍 매핑 → 렌더용 storyboard.json 생성.

내러티브 파이프라인은 storyboard(25씬 authored 비트)를 오디오보다 먼저 만들기 때문에,
TTS 후 각 씬을 자막 타임라인(subtitle.srt)에 매핑하는 단계가 필요하다. (autoworker의
map_timestamps에 해당하는, story 파이프라인의 빠진 조각.)

두 가지 모드:
1) --emit-sentence-map: sentences.json + subtitle.srt 로 문장별 자막 큐 범위를 계산해
   {V}/sentence_cue_map.json 출력. (기계적 — PD가 씬↔문장 매핑을 authored 할 때 참고.)
2) 기본: 프로젝트 storyboard.json 의 각 씬에 있는 "sentences":[a,b] (0-based 문장 범위)를
   읽어 문장→큐 변환 후 {V}/storyboard.json (렌더용, subtitle_range 포함) 출력.
   씬에 "sentences"가 없으면 전체 자막을 씬 수로 균등 분배(폴백, 동기 느슨).

문장→큐 매핑 2단계:
- 정밀 모드: split_long_cues.py --apply 가 sentences.json에 기록한 문장별 cue_range
  (whisper 실측 + 문장 경계 스냅 후 배속)를 그대로 쓴다. settings.cue_count가 현재
  subtitle.srt 큐 수와 일치할 때만 신뢰(불일치 = 다른 시점 산출물 → 비례 폴백).
- 비례 모드(폴백): 대본 문장의 누적 글자 위치를 자막 글자 공간으로 비례 매핑.

Usage:
    python3 scripts/render/scene_timing.py <project_dir> --emit-sentence-map
    python3 scripts/render/scene_timing.py <project_dir>          # 렌더 storyboard 생성
"""
import argparse, json, re, sys, pathlib


def parse_srt(path):
    txt = pathlib.Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    cues = []
    def t(s):
        s = s.strip().replace(",", "."); h, m, rest = s.split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)
    for blk in re.split(r"\n\s*\n", txt.strip()):
        ls = [l for l in blk.splitlines() if l.strip()]
        if len(ls) < 3 or "-->" not in ls[1]:
            continue
        a, b = ls[1].split("-->")
        cues.append({"start": t(a), "end": t(b), "text": "".join(ls[2:])})
    return cues


def norm(s):
    return re.sub(r"\s+", "", re.sub(r"[^\w가-힣]", "", s))


def sentence_cue_ranges(sentences, cues):
    """각 문장을 덮는 자막 큐 범위 [first,last] (1-based) + 타이밍.

    자막(cue) 텍스트가 대본 문장과 정확히 일치하지 않아도(특히 Vrew에서 줄여 8~10%
    짧아지는 경우) 문장의 누적 글자 위치를 자막 글자 공간으로 비례 축소해 매핑한다.
    그리디 누적 매칭은 자막이 짧으면 큐를 먼저 소진해 꼬리 문장들이 마지막 큐로
    붕괴하는데, 비례 매핑은 단조·전체 커버를 보장하고 붕괴가 없다."""
    cue_cum = [0]
    for c in cues:
        cue_cum.append(cue_cum[-1] + len(norm(c["text"])))
    total_cue = cue_cum[-1] or 1
    sent_lens = [max(1, len(norm(s["text"]))) for s in sentences]
    total_sent = sum(sent_lens) or 1
    R = total_cue / total_sent

    def cue_at(char_pos):
        for i in range(len(cues)):
            if char_pos < cue_cum[i + 1]:
                return i
        return len(cues) - 1

    out = []
    spos = 0
    for s, L in zip(sentences, sent_lens):
        first = cue_at(spos * R)
        last = max(first, cue_at((spos + L) * R - 1e-9))
        out.append({"idx": s["idx"], "cue_first": first + 1, "cue_last": last + 1,
                    "start": cues[first]["start"], "end": cues[last]["end"]})
        spos += L
    return out


def exact_sentence_ranges(meta, sentences, cues):
    """split_long_cues --apply가 기록한 문장별 cue_range(실측)를 그대로 사용.

    조건: 모든 문장에 cue_range 키 존재 + settings.cue_count == 현재 큐 수.
    cue_range가 null인 문장(Vrew에서 삭제됨)은 이웃 실측으로 보정 —
    시작은 다음 문장의 첫 큐, 끝은 이전 문장의 마지막 큐 (0폭)."""
    if meta.get("cue_count") != len(cues):
        return None
    if not sentences or not all("cue_range" in s for s in sentences):
        return None
    rs = [s["cue_range"] for s in sentences]
    if not any(rs):
        return None
    n = len(sentences)
    out = []
    for i, s in enumerate(sentences):
        r = rs[i]
        if r:
            first, last = r
        else:
            first = next((rs[j][0] for j in range(i + 1, n) if rs[j]), len(cues))
            last = next((rs[j][1] for j in range(i - 1, -1, -1) if rs[j]), 1)
        out.append({"idx": s["idx"], "cue_first": first, "cue_last": last,
                    "start": cues[first - 1]["start"], "end": cues[last - 1]["end"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--video-subdir", default="_video")
    ap.add_argument("--emit-sentence-map", action="store_true")
    args = ap.parse_args()

    P = args.project_dir.resolve()
    V = P / args.video_subdir
    raw = json.loads((V / "sentences.json").read_text())
    if isinstance(raw, dict) and "sentences" in raw:
        meta, sents = raw.get("settings", {}), raw["sentences"]
    else:
        meta, sents = {}, raw
    cues = parse_srt(V / "subtitle.srt")

    ranges = exact_sentence_ranges(meta, sents, cues)
    if ranges:
        print(f"[문장→큐 매핑] 정밀 모드 (split_long_cues 실측 cue_range, {len(cues)}큐)")
    else:
        if meta.get("cue_count") is not None and meta.get("cue_count") != len(cues):
            print(f"⚠️ sentences.json cue_count({meta['cue_count']}) ≠ subtitle.srt 큐 수({len(cues)}) — "
                  f"다른 시점 산출물. split_long_cues --apply 재실행 권장. 비례 매핑으로 폴백.")
        else:
            print("[문장→큐 매핑] 비례 모드 (실측 cue_range 없음 — split_long_cues --apply 후 정밀 모드 가능)")
        ranges = sentence_cue_ranges(sents, cues)

    if args.emit_sentence_map:
        json.dump({"per_sentence": ranges}, open(V / "sentence_cue_map.json", "w"), ensure_ascii=False, indent=2)
        print(f"sentence_cue_map.json: {len(ranges)}문장 / {len(cues)}큐")
        return 0

    # 렌더용 storyboard.json 생성 — authored scene→sentence 매핑은 소스 storyboard.json에 있다
    board = json.loads((P / "storyboard.json").read_text())
    scenes_src = board["scenes"] if isinstance(board, dict) else board
    n = len(scenes_src)
    by_idx = {r["idx"]: r for r in ranges}

    render_scenes = []
    fallback_scenes = []
    for i, sc in enumerate(scenes_src):
        sid = sc.get("id", i + 1)
        sent = sc.get("sentences")
        if sent and by_idx:
            a, b = sent[0], sent[-1]
            first = by_idx.get(a, ranges[0])["cue_first"]
            last = by_idx.get(b, ranges[-1])["cue_last"]
        else:  # 폴백: 자막 큐를 씬 수로 균등 분배
            fallback_scenes.append(sid)
            first = round(i * len(cues) / n) + 1
            last = round((i + 1) * len(cues) / n)
        render_scenes.append({
            "id": sid,
            "image_path": f"../scenes/scene_{sid:02d}.png",
            "description": sc.get("narration", sc.get("description", "")),
            "subtitle_range": [first, max(first, last)],
        })
    json.dump({"scenes": render_scenes}, open(V / "storyboard.json", "w"), ensure_ascii=False, indent=2)
    print(f"렌더 storyboard.json: {n}씬, 큐범위 {render_scenes[0]['subtitle_range']}..{render_scenes[-1]['subtitle_range']}")

    # 경계 검수 리포트 — 씬별 첫/끝 큐 텍스트. PD가 "씬의 첫 큐 = 그 씬 narration의 첫 문장"인지 확인한다.
    def fmt_t(s):
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"
    print("\n[경계 검수] 씬별 첫 큐 … 끝 큐 (어긋난 씬은 storyboard.json의 sentences 수정 후 재실행):")
    for rs in render_scenes:
        a, b = rs["subtitle_range"]
        ca, cb = cues[a - 1], cues[b - 1]
        head = ca["text"][:24]
        tail = cb["text"][-24:] if b != a else ""
        mark = " ★폴백" if rs["id"] in fallback_scenes else ""
        print(f"  씬{rs['id']:>2} [{fmt_t(ca['start'])}~{fmt_t(cb['end'])}] {head}{' … ' + tail if tail else ''}{mark}")

    if fallback_scenes:
        print(f"\n⚠️  경고: 씬 {fallback_scenes} 에 sentences가 없어 균등분배 폴백 사용 —")
        print("    씬 경계가 서사와 무관하게 잘립니다(이미지가 자막 중간에 걸림). sentences를 채우고 재실행하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
