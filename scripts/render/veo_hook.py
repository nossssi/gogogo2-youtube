#!/usr/bin/env python3
"""
VEO_HOOK — 훅 인트로 립싱크 클립 자동화 (SCENE_TIMING 후, RENDER 전).

씬1 이미지를 시작 프레임으로 Veo i2v 8초 립싱크 클립을 생성하고,
렌더 storyboard(`{V}/storyboard.json`) 씬1에 `video_path`를 주입한다.

엔진 (settings.json image.veo.engine, 기본 gemini):
  - gemini: Gemini API predictLongRunning (⚠️유료, GEMINI_API_KEY — 데몬 불필요, 기본)
            모델 기본 veo-3.1-fast-generate-preview, 1080p, 8초, 네이티브 오디오(대사 포함)
  - flow:   labs.google 웹세션 (flow_veo.py — 데몬 :포트 + Chrome 로그인 필요, ~20크레딧/8초)

실패해도 프롬프트/매니페스트 파일은 항상 남으므로 수동 재시도 가능:
  {V}/veo_hook.json 의 manual_cmd 를 그대로 실행하면 된다.

동작:
  1) 훅 대사 추출 — script.txt 앞부분의 첫 따옴표 대사 (playbook "대사 선행" 전제)
  2) {V}/veo_hook_prompt.txt 생성(이미 있으면 그대로 사용 — PD가 다듬은 뒤 재실행 지원)
  3) {V}/veo_hook.json 매니페스트 기록 (시작 프레임·프롬프트·수동 커맨드 — 항상)
  4) Veo 생성 → {V}/veo_hook_scene01.mp4 (이미 있으면 건너뜀 — 과금 보호, --force로 재생성)
  5) {V}/storyboard.json 씬1에 "video_path" 주입 (capcut_export가 스틸 대신 클립으로 싣는다)

Usage:
    python3 scripts/render/veo_hook.py <project_dir> [--prompt-only] [--force]
        [--engine gemini|flow] [--model MODEL] [--duration 8] [--config settings.json]
"""
import argparse
import base64
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "image"))
from generate_image import find_env_key  # noqa: E402

OUT_NAME = "veo_hook_scene01.mp4"
PROMPT_NAME = "veo_hook_prompt.txt"
MANIFEST_NAME = "veo_hook.json"

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
POLL_INTERVAL = 10.0
POLL_TIMEOUT = 900.0

PROMPT_TEMPLATE = """Animate this Korean webtoon-style illustration.
{scene_desc}

The character at the center of the frame slowly begins to speak in Korean — a natural voice \
matching the character's age and mood, lips synced precisely to the words:
"{dialogue}"

Camera holds on the face, slowly pushing in. Subtle ambient motion only.

Audio: quiet ambient sound and the Korean dialogue only. No background music.
Strictly no subtitles, no captions, no on-screen text of any kind.
Keep the original 2D Korean webtoon illustration art style — do not make it photorealistic.
"""


def extract_dialogue(script_path: pathlib.Path) -> str | None:
    """대본 앞부분에서 첫 따옴표 대사 추출 (곧은/굽은 따옴표 모두)."""
    if not script_path.exists():
        return None
    head = script_path.read_text(encoding="utf-8")[:800]
    m = re.search(r'[“"]([^”"]{2,80}?)[”"]', head)
    return m.group(1).strip() if m else None


def scene1_desc(project: pathlib.Path) -> tuple[int, str]:
    """소스 storyboard 씬1의 (id, visual_desc — {id} placeholder를 lock으로 치환)."""
    board = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    scenes = board["scenes"] if isinstance(board, dict) else board
    sc = scenes[0]
    desc = sc.get("visual_desc", "")
    chars_path = project / "characters.json"
    if chars_path.exists():
        chars = json.loads(chars_path.read_text(encoding="utf-8"))
        for cid, c in (chars.items() if isinstance(chars, dict) else []):
            if cid.startswith("_") or not isinstance(c, dict):
                continue
            lock = c.get("lock")
            if not lock and isinstance(c.get("variants"), dict):
                dv = c["variants"].get(c.get("default_variant")) or next(iter(c["variants"].values()), {})
                lock = (dv or {}).get("lock")
            desc = desc.replace("{" + cid + "}", lock or c.get("name") or cid)
    return sc.get("id", 1), desc


def start_frame_path(project: pathlib.Path, video_dir: pathlib.Path, scene_id: int) -> pathlib.Path | None:
    """씬1 시작 프레임: 렌더 storyboard의 image_path 우선, 없으면 scenes/ 규약 경로."""
    rb = video_dir / "storyboard.json"
    if rb.exists():
        scenes = json.loads(rb.read_text(encoding="utf-8")).get("scenes", [])
        if scenes:
            p = (video_dir / scenes[0].get("image_path", "")).resolve()
            if p.exists():
                return p
    p = project / "scenes" / f"scene_{scene_id:02d}.png"
    return p if p.exists() else None


def inject_video_path(video_dir: pathlib.Path) -> bool:
    """렌더 storyboard 씬1에 video_path 주입. 렌더 storyboard가 아직 없으면 False."""
    rb = video_dir / "storyboard.json"
    if not rb.exists():
        return False
    data = json.loads(rb.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    if not scenes:
        return False
    if scenes[0].get("video_path") != OUT_NAME:
        scenes[0]["video_path"] = OUT_NAME
        json.dump(data, open(rb, "w"), ensure_ascii=False, indent=2)
    return True


# ---------------- gemini(Veo API) 백엔드 ----------------

def _api(url: str, key: str, body: dict | None = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def veo_gemini(prompt: str, frame: pathlib.Path, out_path: pathlib.Path, key: str,
               model: str, ratio: str, resolution: str, duration: int) -> int:
    """Gemini API Veo i2v: predictLongRunning → 폴링 → URI 다운로드. 성공 0."""
    b64 = base64.b64encode(frame.read_bytes()).decode()
    mime = "image/png" if frame.suffix.lower() == ".png" else "image/jpeg"
    # durationSeconds는 정수여야 한다(문자열이면 400) — 2026-07-19 실측
    params = {"aspectRatio": ratio, "resolution": resolution, "durationSeconds": int(duration)}
    inst = {"prompt": prompt, "image": {"bytesBase64Encoded": b64, "mimeType": mime}}
    try:
        data = _api(f"{API_BASE}/models/{model}:predictLongRunning", key,
                    {"instances": [inst], "parameters": params})
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} from Veo API: {e.read().decode(errors='replace')[:600]}", file=sys.stderr)
        return 1
    op_name = data.get("name")
    if not op_name:
        print(f"error: 생성 시작 응답에 operation name 없음: {json.dumps(data)[:400]}", file=sys.stderr)
        return 1

    print(f"  생성 시작 op={op_name[:60]}... 폴링 중", file=sys.stderr)
    deadline = time.time() + POLL_TIMEOUT
    op = {}
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            op = _api(f"{API_BASE}/{op_name}", key)
        except urllib.error.HTTPError as e:
            print(f"  폴링 HTTP {e.code} — 재시도", file=sys.stderr)
            continue
        if op.get("done"):
            break
        print("  ... 생성 중", file=sys.stderr)
    if not op.get("done"):
        print(f"error: 폴링 타임아웃({int(POLL_TIMEOUT)}s)", file=sys.stderr)
        return 1
    if op.get("error"):
        print(f"error: Veo 생성 실패: {json.dumps(op['error'], ensure_ascii=False)[:600]}", file=sys.stderr)
        return 1

    samples = (((op.get("response") or {}).get("generateVideoResponse") or {})
               .get("generatedSamples") or [])
    uri = (samples[0].get("video") or {}).get("uri") if samples else None
    if not uri:
        print(f"error: 응답에 video.uri 없음: {json.dumps(op, ensure_ascii=False)[:600]}", file=sys.stderr)
        return 1

    req = urllib.request.Request(uri, headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            buf = resp.read()
    except urllib.error.HTTPError:
        sep = "&" if "?" in uri else "?"
        with urllib.request.urlopen(f"{uri}{sep}key={key}", timeout=300) as resp:
            buf = resp.read()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf)
    print(f"saved {out_path}  ({out_path.stat().st_size} bytes)  [gemini/{model} {duration}s {resolution}]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path, default=None,
                    help="settings.json 경로 (기본: {P}/../../config/settings.json)")
    ap.add_argument("--prompt-only", action="store_true", help="무료: 프롬프트·매니페스트만 생성")
    ap.add_argument("--force", action="store_true", help="mp4가 있어도 재생성 (⚠️과금 재발생)")
    ap.add_argument("--engine", default=None, choices=["gemini", "flow"],
                    help="기본: settings image.veo.engine → gemini")
    ap.add_argument("--model", default=None)
    ap.add_argument("--duration", type=int, default=8, choices=[4, 6, 8], help="gemini 전용 (기본 8초)")
    ap.add_argument("--resolution", default=None, help="gemini 전용 (기본 settings → 1080p)")
    ap.add_argument("--ports", default=None, help="flow 전용: 유료 레인 포트(쉼표구분)")
    ap.add_argument("--video-subdir", default="_video")
    args = ap.parse_args()

    P = args.project_dir.resolve()
    V = P / args.video_subdir
    V.mkdir(parents=True, exist_ok=True)

    # settings: image.veo (channels/{ch}/projects/{proj} 관례 → 채널 config)
    cfg_path = args.config or (P.parents[1] / "config" / "settings.json")
    veo_cfg = {}
    if cfg_path and cfg_path.exists():
        veo_cfg = (json.loads(cfg_path.read_text(encoding="utf-8")).get("image") or {}).get("veo") or {}
    engine = args.engine or veo_cfg.get("engine") or "gemini"
    ratio = veo_cfg.get("ratio") or "16:9"
    resolution = args.resolution or veo_cfg.get("resolution") or "1080p"
    flow_cfg = veo_cfg.get("flow") or {}
    if engine == "gemini":
        model = args.model or veo_cfg.get("model") or "veo-3.1-fast-generate-preview"
    else:
        model = args.model or flow_cfg.get("model") or "veo-fast"
    ports = ([int(x) for x in str(args.ports).split(",") if x.strip()] if args.ports
             else list(flow_cfg.get("ports") or [3849]))

    # 1) 소재 수집: 씬1 desc + 훅 대사 + 시작 프레임
    try:
        scene_id, desc = scene1_desc(P)
    except (OSError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"error: storyboard.json 읽기 실패: {e}", file=sys.stderr)
        return 2
    dialogue = extract_dialogue(P / "script.txt")
    if not dialogue:
        print("error: script.txt 앞 800자에서 따옴표 대사를 찾지 못함 — playbook '대사 선행' 위반이거나 "
              "대본 없음. 프롬프트를 수동 작성 후 재실행.", file=sys.stderr)
        return 2
    frame = start_frame_path(P, V, scene_id)

    # 2) 프롬프트: 있으면 존중, 없으면 템플릿 생성
    prompt_path = V / PROMPT_NAME
    if not prompt_path.exists():
        prompt_path.write_text(PROMPT_TEMPLATE.format(scene_desc=desc.strip(), dialogue=dialogue),
                               encoding="utf-8")
        print(f"프롬프트 생성: {prompt_path}")
    else:
        print(f"프롬프트 재사용: {prompt_path}")

    # 3) 매니페스트 (항상 기록 — 수동 폴백의 근거 파일)
    out_path = V / OUT_NAME
    if engine == "gemini":
        manual = f"python3 scripts/render/veo_hook.py '{P}' --force --engine gemini --model {model}"
    else:
        manual = (f"python3 scripts/image/flow_veo.py '{V / PROMPT_NAME}' '{out_path}' "
                  f"'{frame}' --model {model} --ratio {ratio} --ports {','.join(map(str, ports))}")
    manifest = {
        "engine": engine,
        "start_frame": str(frame) if frame else None,
        "prompt_file": PROMPT_NAME,
        "dialogue": dialogue,
        "model": model, "ratio": ratio,
        "resolution": resolution if engine == "gemini" else None,
        "duration": args.duration if engine == "gemini" else 8,
        "output": OUT_NAME,
        "manual_cmd": manual,
        "status": "pending",
    }

    def save(status: str) -> None:
        manifest["status"] = status
        json.dump(manifest, open(V / MANIFEST_NAME, "w"), ensure_ascii=False, indent=2)

    if frame is None:
        save("no_start_frame")
        print("error: 씬1 시작 프레임 이미지를 찾지 못함 (scenes/ 비었나?) — 매니페스트만 기록.", file=sys.stderr)
        return 1
    if args.prompt_only:
        save("prompt_ready")
        print("--prompt-only: 생성 생략. 매니페스트 기록 완료.")
        return 0

    # 4) 생성 (mp4 있으면 건너뜀 — 재실행 시 과금 보호)
    if out_path.exists() and not args.force:
        print(f"클립 존재 — 생성 건너뜀: {out_path}")
    else:
        prompt = prompt_path.read_text(encoding="utf-8")
        if engine == "gemini":
            key = find_env_key(P, "GEMINI_API", "GEMINI_API_KEY", "GOOGLE_API_KEY")
            if not key:
                save("failed")
                print("error: GEMINI_API_KEY 없음 (.env) — 매니페스트의 manual_cmd로 재시도.", file=sys.stderr)
                return 1
            print(f"⚠️ Veo 생성 시작 (유료 API, {model}, {args.duration}s, {resolution})")
            rc = veo_gemini(prompt, frame, out_path, key, model, ratio, resolution, args.duration)
        else:
            try:
                from flow_veo import run as flow_run
            except ImportError as e:
                save("failed")
                print(f"error: flow_veo import 실패: {e}", file=sys.stderr)
                return 1
            print(f"⚠️ Veo 생성 시작 (flow 유료 ~20크레딧, 레인 {ports}, {model})")
            rc = flow_run(prompt, out_path, frame, model=model, ratio=ratio, ports=ports)
        if rc != 0 or not out_path.exists():
            save("failed")
            print(f"생성 실패(rc={rc}) — 매니페스트의 manual_cmd로 수동 재시도 가능. "
                  f"RENDER는 씬1 스틸 폴백으로 진행해도 됨.", file=sys.stderr)
            return 1

    # 5) 렌더 storyboard 주입
    if inject_video_path(V):
        save("injected")
        print(f"완료: 렌더 storyboard 씬1 ← video_path={OUT_NAME}")
    else:
        save("generated_not_injected")
        print("클립은 준비됐으나 렌더 storyboard(_video/storyboard.json)가 없어 주입 보류 — "
              "SCENE_TIMING 후 재실행하면 주입만 수행.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
