#!/usr/bin/env python3
"""
Flow Veo 비디오 생성 클라이언트 — labs.google Flow 내부 API(aisandbox-pa)로 i2v/t2v.

⚠️ 유료 크레딧 소모 (Google AI Pro 구독 계정). 이미지(flow_client)와 달리 무료가 아님.
   Fast 8초 클립당 ~20크레딧(변동 가능) — 훅 인트로 영상화 전용으로 아껴 쓸 것.

흐름:
  [i2v] uploadImage(시작 프레임 → mediaId)
  → video:batchAsyncGenerateVideoReferenceImages (reCAPTCHA action=VIDEO_GENERATION)
  → video:batchCheckAsyncVideoGenerationStatus 5초 폴링 (최대 10분)
  → labs.google tRPC media.getMediaUrlRedirect 로 다운로드 (세션쿠키 인증)

단독 실행:
    python3 scripts/image/flow_veo.py <prompt_file> <out.mp4> [start_frame.png] \
        [--model veo-fast] [--ratio 16:9] [--ports 3849]

의존성: 표준 라이브러리만. flow_token_server 데몬 + Chrome Flow 탭 + 확장 필요 (flow_client와 동일).
wire 계약 출처: liorium/flow-proxy scripts/generate-video.mjs (MIT, 2026-04 기준).
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from flow_client import (  # noqa: E402
    ENDPOINT_BASE, FlowError, _post, _rand_seed, _uuid4,
    acquire_lane, release_lane, upload_ref,
)

RECAPTCHA_ACTION = "VIDEO_GENERATION"
POLL_INTERVAL = 5.0
POLL_TIMEOUT = 600.0
DOWNLOAD_URL = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect"
SESSION_COOKIE_NAME = "__Secure-next-auth.session-token"

# videoModelKey: t2v는 referenceImages 없이, r2v(i2v)는 시작 프레임 mediaId 첨부
MODELS = {
    "veo-fast":     {"key": "veo_3_1_r2v_fast_landscape", "endpoint": "video:batchAsyncGenerateVideoReferenceImages", "i2v": True},
    "veo-fast-t2v": {"key": "veo_3_1_t2v_fast",           "endpoint": "video:batchAsyncGenerateVideoText",            "i2v": False},
}
ASPECT_MAP = {
    "16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "1:1": "VIDEO_ASPECT_RATIO_SQUARE",
}

STATUS_OK = {"MEDIA_GENERATION_STATUS_SUCCESSFUL", "MEDIA_GENERATION_STATUS_COMPLETE",
             "MEDIA_GENERATION_STATUS_SUCCEEDED"}
STATUS_FAIL = {"MEDIA_GENERATION_STATUS_FAILED", "MEDIA_GENERATION_STATUS_CANCELLED"}


def daemon_session(port: int) -> tuple[str, str | None, str | None]:
    """데몬에서 access token + projectId + sessionCookie 획득."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/token", timeout=20) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise FlowError(f"토큰 없음: {e.read().decode(errors='replace')}. 확장에서 Connect 했는지 확인.") from e
    except urllib.error.URLError as e:
        raise FlowError(f"토큰 데몬(:{port})에 연결 실패 — 먼저 실행: "
                        f"python3 scripts/image/flow_token_server.py --port {port}") from e
    return data["accessToken"], data.get("projectId"), data.get("sessionCookie")


def daemon_recaptcha_video(port: int) -> str:
    """VIDEO_GENERATION 액션으로 reCAPTCHA 토큰 획득."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/get-recaptcha",
            data=json.dumps({"action": RECAPTCHA_ACTION}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise FlowError(f"reCAPTCHA 요청 실패(데몬 :{port}): {e}") from e
    if data.get("error"):
        raise FlowError(data["error"])
    return data["token"]


def start_generation(prompt: str, start_media_id: str | None, token: str, project_id: str,
                     recaptcha: str, model: str, ratio: str, seed: int | None) -> str:
    m = MODELS[model]
    request: dict = {
        "aspectRatio": ASPECT_MAP.get(ratio, "VIDEO_ASPECT_RATIO_LANDSCAPE"),
        "seed": seed if seed is not None else _rand_seed(),
        "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
        "videoModelKey": m["key"],
        "metadata": {},
    }
    if m["i2v"]:
        if not start_media_id:
            raise FlowError(f"모델 {model}(i2v)은 시작 프레임 이미지가 필요")
        request["referenceImages"] = [{"mediaId": start_media_id, "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"}]
    payload = {
        "mediaGenerationContext": {"batchId": _uuid4()},
        "clientContext": {
            "projectId": project_id,
            "tool": "PINHOLE",
            "userPaygateTier": "PAYGATE_TIER_ONE",
            "sessionId": ";" + str(int(time.time() * 1000)),
            "recaptchaContext": {"token": recaptcha, "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
        },
        "requests": [request],
        "useV2ModelConfig": True,
    }
    data = _post(f"{ENDPOINT_BASE}/{m['endpoint']}", payload, token=token, timeout=120)
    media = data.get("media") or []
    if not media or not media[0].get("name"):
        raise FlowError(f"생성 시작 응답에 mediaId 없음: {json.dumps(data)[:500]}")
    return media[0]["name"]


def poll_until_done(media_id: str, token: str, project_id: str) -> None:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        data = _post(f"{ENDPOINT_BASE}/video:batchCheckAsyncVideoGenerationStatus",
                     {"media": [{"name": media_id, "projectId": project_id}]},
                     token=token, timeout=60)
        status = ""
        for item in data.get("media") or []:
            if item.get("name") == media_id:
                status = (((item.get("mediaMetadata") or {}).get("mediaStatus") or {})
                          .get("mediaGenerationStatus") or "")
                break
        if status in STATUS_OK:
            return
        if status in STATUS_FAIL:
            raise FlowError(f"생성 실패: {status}")
        print(f"  ... {status or 'PENDING'}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)
    raise FlowError(f"폴링 타임아웃({int(POLL_TIMEOUT)}s): mediaId={media_id}")


def download_video(media_id: str, session_cookie: str) -> bytes:
    """labs.google tRPC redirect → 서명 GCS URL → mp4. 완료 직후 404/409는 정상(재시도)."""
    url = f"{DOWNLOAD_URL}?name={urllib.parse.quote(media_id)}"
    delays = [0, 2, 4, 7, 10]
    last = None
    for d in delays:
        if d:
            time.sleep(d)
        req = urllib.request.Request(url, headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:  # 302 자동 추적
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (404, 409, 425, 429, 500, 502, 503, 504):
                raise FlowError(f"다운로드 HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    raise FlowError(f"다운로드 재시도 소진: {last}")


def run(prompt: str, out_path: pathlib.Path, start_frame: pathlib.Path | None,
        model: str = "veo-fast", ratio: str = "16:9", ports: list[int] | int = 3849,
        seed: int | None = None, max_retries: int = 2) -> int:
    """veo 경로 진입점. 성공 0, 실패 비0. ⚠️ 호출당 유료 크레딧 소모."""
    port_list = [ports] if isinstance(ports, int) else list(ports)
    try:
        port = acquire_lane(port_list)
    except FlowError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        return _run_on_port(prompt, out_path, start_frame, model, ratio, port, seed, max_retries)
    finally:
        release_lane(port)


def _run_on_port(prompt: str, out_path: pathlib.Path, start_frame: pathlib.Path | None,
                 model: str, ratio: str, port: int, seed: int | None, max_retries: int) -> int:
    try:
        token, project_id, session_cookie = daemon_session(port)
    except FlowError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not project_id:
        print(f"error: projectId 미설정 — curl -X POST localhost:{port}/set-project "
              "-d '{\"projectId\":\"<UUID>\"}'", file=sys.stderr)
        return 2
    if not session_cookie:
        print("error: sessionCookie 없음 — 확장에서 Reconnect 후 재시도 (다운로드에 필요)", file=sys.stderr)
        return 2

    start_media_id = None
    if MODELS[model]["i2v"]:
        try:
            start_media_id = upload_ref(start_frame, token, project_id, port)
        except (FlowError, urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            print(f"error: 시작 프레임 업로드 실패: {e}", file=sys.stderr)
            return 1

    backoff = 10
    for attempt in range(1, max_retries + 1):
        try:
            recaptcha = daemon_recaptcha_video(port)
            t0 = time.time()
            media_id = start_generation(prompt, start_media_id, token, project_id,
                                        recaptcha, model, ratio, seed)
            print(f"  생성 시작 mediaId={media_id[:40]}... 폴링 중", file=sys.stderr)
            poll_until_done(media_id, token, project_id)
            buf = download_video(media_id, session_cookie)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(buf)
            print(f"saved {out_path}  ({out_path.stat().st_size} bytes, {time.time()-t0:.0f}s)  [flow/{model}]")
            return 0
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < max_retries:
                print(f"429 rate limit — {backoff}s 후 재시도 ({attempt}/{max_retries})", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"HTTP {e.code} from Flow: {body[:800]}", file=sys.stderr)
            return 1
        except FlowError as e:
            # 생성이 시작된 뒤의 실패는 크레딧이 이미 소모됐을 수 있어 자동 재시도하지 않음
            print(f"error: {e}", file=sys.stderr)
            return 1
        except (urllib.error.URLError, OSError) as e:
            print(f"network error: {e}", file=sys.stderr)
            return 1
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt_file", type=pathlib.Path)
    ap.add_argument("out_path", type=pathlib.Path)
    ap.add_argument("start_frame", nargs="?", type=pathlib.Path, default=None)
    ap.add_argument("--model", default="veo-fast", choices=sorted(MODELS))
    ap.add_argument("--ratio", default="16:9")
    ap.add_argument("--ports", default="3849", help="유료 계정 레인 포트(들). 쉼표구분")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    ports = [int(x) for x in str(args.ports).split(",") if x.strip()]

    if not args.prompt_file.exists():
        print(f"error: prompt file not found: {args.prompt_file}", file=sys.stderr)
        return 2
    if MODELS[args.model]["i2v"] and (not args.start_frame or not args.start_frame.exists()):
        print(f"error: i2v 모델은 시작 프레임 필요: {args.start_frame}", file=sys.stderr)
        return 2

    prompt = args.prompt_file.read_text(encoding="utf-8")
    return run(prompt, args.out_path, args.start_frame,
               model=args.model, ratio=args.ratio, ports=ports, seed=args.seed)


if __name__ == "__main__":
    sys.exit(main())
