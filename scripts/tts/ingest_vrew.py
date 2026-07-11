#!/usr/bin/env python3
"""
Vrew 반수동 모드 — 사용자가 Vrew에서 뽑은 음성+SRT를 파이프라인 산출물로 변환.

정책: **단일 나레이션** — 대사 포함 전체를 나레이터 한 명이 읽는다. (대본 원천 = script.txt)

흐름:
    1) --export-script 로 {P}/vrew/vrew_script.txt 생성 (= script.txt).
       **Vrew 붙여넣기 한도(기본 9,800자, 공백 포함) 초과 시 문단 경계에서
       vrew_script_part01.txt, part02… 로 자동 분할** — 파트마다 별도 Vrew 프로젝트로
       낭독하고(같은 보이스·같은 속도), 내보내기 파일명에 파트 번호를 붙인다
       (예: narration_01.mp3 + narration_01.srt).
    2) 사용자가 Vrew에서 음성/자막 내보내기 → {P}/vrew/ 에 저장 (여러 파트 가능)
    3) 본 스크립트 실행 → {V}/audio.mp3, {V}/subtitle.srt(프레임 스냅), {V}/sentences.json
       여러 파트면 이름순으로 짝지어 오디오를 병합(WAV 샘플 정확도로 오프셋 계산)하고
       SRT를 파트별 프레임 스냅 후 오프셋 이어붙인다.
    4) 이후는 기존과 동일: split_long_cues → scene_timing.py → render

alignment.json / 무음압축 단계는 건너뛴다 (Vrew 결과물이 이미 싱크·페이싱 완료).
여기서 만드는 sentences.json의 문장↔자막 매핑(그리디 누적)과 words 타이밍은 잠정치 —
다음 단계 split_long_cues.py --apply 가 문장 경계 스냅 + whisper 실측으로
cue_range/start/end/words 를 확정 기록한다(scene_timing 정밀 모드의 근거).
(문장을 통째로 지우거나 새로 쓰면 storyboard의 sentences 범위가 밀리니 금지.)

Usage:
    python3 scripts/tts/ingest_vrew.py <project_dir> --export-script
    python3 scripts/tts/ingest_vrew.py <project_dir> [--config settings.json]
"""
import argparse
import json
import re
import subprocess
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from init_sentences import split_into_sentences
from align_to_frames import parse_srt as parse_srt_frames, align_subtitles, format_srt, snap_to_frame

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac")


def load_spoken_text(project_dir: pathlib.Path) -> str:
    """발화 텍스트 = script.txt. (vrew 모드는 단일 나레이션 — 화자 분리 없음)"""
    return (project_dir / "script.txt").read_text(encoding="utf-8").strip()


def split_for_vrew(text: str, limit: int) -> list[str]:
    """Vrew 붙여넣기 한도(공백 포함 글자수)에 맞춰 문단 경계에서 분할.

    문단(빈 줄 구분)을 순서대로 채우다 한도를 넘기 전에 끊는다.
    문단 하나가 한도를 넘으면 문장 경계에서 쪼갠다."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    for p in paras:
        if len(p) <= limit:
            units.append(p)
        else:  # 초장 문단 — 문장 경계로 세분
            buf = ""
            for sent in split_into_sentences(p):
                if buf and len(buf) + len(sent) + 1 > limit:
                    units.append(buf)
                    buf = sent
                else:
                    buf = (buf + " " + sent).strip()
            if buf:
                units.append(buf)

    parts, buf = [], ""
    for u in units:
        if buf and len(buf) + len(u) + 2 > limit:
            parts.append(buf)
            buf = u
        else:
            buf = (buf + "\n\n" + u).strip()
    if buf:
        parts.append(buf)
    return parts


def export_script(project_dir: pathlib.Path, paste_limit: int = 9800) -> int:
    """Vrew에 붙여넣을 대본 생성 (나레이터 보이스 하나로 전체 낭독).

    Vrew 한도(공백 포함 ~1만자) 초과 시 문단 경계에서 파트 파일로 분할."""
    vrew_dir = project_dir / "vrew"
    vrew_dir.mkdir(exist_ok=True)

    text = load_spoken_text(project_dir)
    script_path = vrew_dir / "vrew_script.txt"
    script_path.write_text(text + "\n", encoding="utf-8")

    for old in vrew_dir.glob("vrew_script_part*.txt"):
        old.unlink()

    if len(text) <= paste_limit:
        print(f"✓ {script_path}  ({len(text):,}자 — Vrew에 통째로 붙여넣고 나레이터 보이스 하나로 낭독)")
        print(f"\nVrew에서 음성(mp3/wav)과 자막(srt)을 내보내 {vrew_dir}/ 에 넣은 뒤,")
        print(f"  python3 scripts/tts/ingest_vrew.py {project_dir}")
        return 0

    parts = split_for_vrew(text, paste_limit)
    print(f"✓ {script_path}  (전체 {len(text):,}자 — Vrew 한도 {paste_limit:,}자 초과 → {len(parts)}개 파트로 분할)")
    for i, part in enumerate(parts, 1):
        pp = vrew_dir / f"vrew_script_part{i:02d}.txt"
        pp.write_text(part + "\n", encoding="utf-8")
        print(f"  ✓ {pp.name}  ({len(part):,}자)")
    print(f"""
파트별 Vrew 낭독 안내 (총 {len(parts)}개, 반드시 같은 보이스·같은 속도로):
  1. 파트마다 별도 Vrew 프로젝트를 만들어 vrew_script_partNN.txt 내용을 붙여넣기
  2. 내보내기 파일명에 파트 번호를 붙여 {vrew_dir}/ 에 저장 —
     예: narration_01.mp3 + narration_01.srt, narration_02.mp3 + narration_02.srt …
     (이름순 정렬로 오디오↔SRT를 짝짓고 파트를 이어 붙이므로 번호가 순서다)
  3. 완료 후: python3 scripts/tts/ingest_vrew.py {project_dir}""")
    return 0


def find_inputs(vrew_dir: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """{P}/vrew/ 에서 오디오·SRT를 찾는다 — N쌍(멀티 파트) 허용, 이름순 짝."""
    audios = sorted(p for p in vrew_dir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    srts = sorted(vrew_dir.glob("*.srt"))
    if not audios or len(audios) != len(srts):
        raise SystemExit(
            f"✗ {vrew_dir} 에 오디오 {len(audios)}개, SRT {len(srts)}개 — 같은 수의 쌍이어야 합니다.\n"
            f"  오디오: {[p.name for p in audios]}\n  SRT: {[p.name for p in srts]}"
        )
    return audios, srts


def ffprobe_duration(path: pathlib.Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(probe.stdout.strip())


def run_ffmpeg(args: list[str], what: str):
    r = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"✗ ffmpeg {what} 실패: {r.stderr[-500:]}")


def transcode_audio(srcs: list[pathlib.Path], dst: pathlib.Path) -> tuple[float, list[float]]:
    """오디오(1개 이상)를 병합해 mp3로 변환. returns (총 길이초, 파트별 시작 오프셋초).

    멀티 파트는 WAV로 통일 후 이어 붙인다 — 오프셋이 샘플 정확도로 계산되어
    파트별 SRT 시프트가 실제 오디오 위치와 일치한다."""
    if len(srcs) == 1:
        run_ffmpeg(["-i", str(srcs[0]), "-codec:a", "libmp3lame", "-qscale:a", "2", str(dst)], "변환")
        return ffprobe_duration(dst), [0.0]

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdir = pathlib.Path(td)
        wavs, offsets, acc = [], [], 0.0
        for i, src in enumerate(srcs):
            w = tdir / f"part{i:02d}.wav"
            run_ffmpeg(["-i", str(src), "-ar", "44100", "-ac", "2",
                        "-c:a", "pcm_s16le", str(w)], f"wav 변환({src.name})")
            offsets.append(acc)
            acc += ffprobe_duration(w)
            wavs.append(w)
        lst = tdir / "list.txt"
        lst.write_text("".join(f"file '{w}'\n" for w in wavs), encoding="utf-8")
        merged = tdir / "merged.wav"
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(merged)], "병합")
        run_ffmpeg(["-i", str(merged), "-codec:a", "libmp3lame", "-qscale:a", "2", str(dst)], "mp3 인코딩")
    return ffprobe_duration(dst), offsets


def norm(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w가-힣]", "", s))


def build_sentences(text: str, cues: list[dict], max_chars: int) -> dict:
    """대본 문장을 자막 큐에 매핑해 sentences.json 구조 생성.

    타이밍은 문장을 덮는 큐 범위의 [첫 큐 start, 마지막 큐 end].
    words는 문장 구간 안에서 글자 수 비례로 보간 (하위 단계 호환용).
    """
    sentences = split_into_sentences(text)
    ci = 0
    out = []
    for idx, sent_text in enumerate(sentences):
        target = norm(sent_text)
        acc = ""
        first = min(ci, len(cues) - 1)
        while ci < len(cues) and len(acc) < len(target):
            acc += norm(cues[ci]["text"])
            ci += 1
        last = max(first, ci - 1)
        start, end = cues[first]["start"], cues[last]["end"]

        words = []
        tokens = sent_text.split()
        total_chars = sum(len(t) for t in tokens) or 1
        cursor = start
        for t in tokens:
            w_dur = (end - start) * len(t) / total_chars
            words.append({"word": t, "start": round(cursor, 3), "end": round(cursor + w_dur, 3)})
            cursor += w_dur

        out.append({
            "idx": idx,
            "text": sent_text,
            "chars": len(sent_text.replace(" ", "")),
            "needs_split": False,  # 자막 분할은 Vrew 클립이 이미 결정
            "words": words,
        })

    if ci < len(cues):
        print(f"⚠️ 대본 문장에 매핑되지 않은 자막 큐 {len(cues) - ci}개 (마지막 문장에 흡수 안 됨)")
    return {"settings": {"max_chars": max_chars, "source": "vrew"}, "sentences": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--config", help="settings.json 경로 (fps, max_chars)")
    ap.add_argument("--video-subdir", default="_video")
    ap.add_argument("--export-script", action="store_true", help="Vrew용 대본만 생성하고 종료")
    args = ap.parse_args()

    P = args.project_dir.resolve()
    settings = {}
    if args.config and pathlib.Path(args.config).exists():
        settings = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    fps = settings.get("subtitle", {}).get("fps", 30)
    max_chars = settings.get("subtitle", {}).get("max_chars", 20)
    paste_limit = settings.get("tts", {}).get("vrew_paste_limit", 9800)

    if args.export_script:
        return export_script(P, paste_limit)

    audios, srts = find_inputs(P / "vrew")
    V = P / args.video_subdir
    V.mkdir(parents=True, exist_ok=True)
    if len(audios) == 1:
        print(f"🎬 Vrew 모드: {audios[0].name} + {srts[0].name}")
    else:
        print(f"🎬 Vrew 모드 (멀티 파트 {len(audios)}쌍, 이름순 병합):")
        for a, s in zip(audios, srts):
            print(f"    {a.name}  ↔  {s.name}")

    # 1) 오디오 → {V}/audio.mp3 (무음압축 없음 — Vrew에서 페이싱 완료; 멀티 파트는 병합)
    audio_dur, offsets = transcode_audio(audios, V / "audio.mp3")
    print(f"✓ audio.mp3 ({audio_dur:.1f}초{f', 파트 경계 {[round(o,1) for o in offsets[1:]]}초' if len(offsets) > 1 else ''})")

    # 2) SRT → 파트별 프레임 스냅 → 오프셋 이어붙임 → {V}/subtitle.srt
    #    (스냅을 파트 안에서만 하고 파트 사이 무음 간격은 보존한다)
    aligned = []
    for off, srt_src in zip(offsets, srts):
        part = align_subtitles(parse_srt_frames(srt_src.read_text(encoding="utf-8-sig")), fps)
        off_ms = snap_to_frame(round(off * 1000), fps)
        for s in part:
            s["start"] += off_ms
            s["end"] += off_ms
        aligned.extend(part)
    for i, s in enumerate(aligned):
        s["index"] = i + 1
    (V / "subtitle.srt").write_text(format_srt(aligned), encoding="utf-8-sig", newline="\r\n")
    srt_end = aligned[-1]["end"] / 1000
    print(f"✓ subtitle.srt ({len(aligned)}큐, {fps}fps 스냅, 끝 {srt_end:.1f}초)")
    if abs(audio_dur - srt_end) > 3.0:
        print(f"⚠️ 오디오({audio_dur:.1f}초)와 자막 끝({srt_end:.1f}초) 차이가 큼 — 내보내기 짝이 맞는지 확인")

    # 자막 줄 길이 검사 — vrew 모드는 자막 분할이 없어 Vrew 클립이 곧 자막 줄
    long_cues = [(i + 1, s["text"]) for i, s in enumerate(aligned)
                 if len(s["text"].replace(" ", "")) > max_chars]
    if long_cues:
        print(f"ℹ️ {max_chars}자 초과 자막 {len(long_cues)}개 — 다음 단계 split_long_cues.py가 자동 분할합니다.")

    # 3) 대본 문장 ↔ 큐 매핑 → {V}/sentences.json
    text = load_spoken_text(P)
    cues = [{"start": s["start"] / 1000, "end": s["end"] / 1000, "text": s["text"]} for s in aligned]

    # 대본↔자막 총량 대조 — Vrew에서 문장이 삭제/추가되면 매핑 전체가 밀린다
    script_chars, cue_chars = len(norm(text)), sum(len(norm(c["text"])) for c in cues)
    if script_chars and abs(script_chars - cue_chars) / script_chars > 0.03:
        print(f"⚠️ 대본({script_chars}자)과 자막({cue_chars}자) 글자 수 차이 "
              f"{abs(script_chars - cue_chars) / script_chars:.0%} — Vrew에서 문장을 삭제/추가했다면 "
              f"씬 타이밍이 밀림. script.txt를 실제 낭독 내용과 맞춘 뒤 재실행 권장.")

    result = build_sentences(text, cues, max_chars)
    (V / "sentences.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ sentences.json ({len(result['sentences'])}문장 / {len(cues)}큐)")

    print("\n다음 단계:")
    print(f"  python3 scripts/tts/split_long_cues.py {P} --config <settings.json> --apply   # 긴 자막 자동 분할")
    print(f"  python3 scripts/render/scene_timing.py {P}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
