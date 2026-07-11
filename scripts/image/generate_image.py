#!/usr/bin/env python3
"""
Generate an image with Google Gemini (nano-banana / nano-banana-pro).

Usage:
    GEMINI_API=xxx ./generate-image.py <prompt_file> <out.png> [ref1.png ref2.png ...]
    GEMINI_API=xxx ./generate-image.py --model gemini-2.5-flash-image-preview <prompt_file> <out.png> [refs...]

Defaults:
    model: gemini-3-pro-image  (Nano Banana Pro 정식판 · 2K output · multimodal refs)
    timeout: 600s

Reference images are sent as inline parts BEFORE the text prompt — Gemini reads them
as visual style/character locks. The prompt text comes last so it conditions on the refs.

Output: writes the first image bytes from the response to <out.png>.
Exits non-zero on API error or no image in response (prints first 2KB of body to stderr).
"""

import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def img_part(path: pathlib.Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": data}}


def find_env_key(start: pathlib.Path, *names: str) -> str | None:
    """Walk up from `start` looking for a .env file, return first matching key."""
    cur = start.resolve()
    for _ in range(6):
        env = cur / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                for name in names:
                    if line.startswith(f"{name}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_config(start: pathlib.Path, filename: str) -> dict | None:
    """Walk up from `start` looking for a sibling `config/<filename>` (채널 config)."""
    cur = start.resolve()
    for _ in range(8):
        cfg = cur / "config" / filename
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def resolve_engine(prompt_file: pathlib.Path, cli_engine: str | None) -> str:
    """엔진 결정: --engine > IMAGE_ENGINE env > settings.json image.engine > 'flow'.

    기본값은 무료 'flow'. gemini(유료 API)는 **settings.json image.engine="gemini"로
    명시했을 때만** 쓴다 — 설정 누락/오독 시 실수로 과금되지 않게, 그리고 flow가 깨져도
    자동으로 gemini로 넘어가지 않는다(자동 폴백 없음, 사용자 명시 opt-in 전용)."""
    if cli_engine:
        return cli_engine
    env_engine = os.environ.get("IMAGE_ENGINE")
    if env_engine:
        return env_engine
    settings = find_config(prompt_file.parent, "settings.json") or {}
    return (settings.get("image") or {}).get("engine") or "flow"


def run_flow(args) -> int:
    """Flow(labs.google 웹세션) 무료 경로. settings.json image.flow + style.json 에서 설정 해석."""
    import flow_client  # 지역 import: gemini 경로엔 불필요

    settings = find_config(args.prompt_file.parent, "settings.json") or {}
    flow_cfg = (settings.get("image") or {}).get("flow") or {}
    style = find_config(args.prompt_file.parent, "style.json") or {}
    model = flow_cfg.get("model", "banana-pro")
    ratio = flow_cfg.get("ratio") or style.get("aspect_ratio") or "16:9"
    # 멀티계정 레인: image.flow.ports(리스트) 우선, 없으면 image.flow.port(단일), env FLOW_PORTS 오버라이드
    env_ports = os.environ.get("FLOW_PORTS")
    if env_ports:
        ports = [int(x) for x in env_ports.split(",") if x.strip()]
    elif isinstance(flow_cfg.get("ports"), list) and flow_cfg["ports"]:
        ports = [int(p) for p in flow_cfg["ports"]]
    else:
        ports = [int(flow_cfg.get("port", 3847))]

    prompt = args.prompt_file.read_text(encoding="utf-8")
    return flow_client.run(prompt, args.out_path, list(args.refs),
                           model=model, ratio=ratio, ports=ports)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="gemini-3-pro-image",
                   help="Gemini image model (default: gemini-3-pro-image · Nano Banana Pro GA)")
    p.add_argument("--engine", default=None, choices=["gemini", "flow"],
                   help="이미지 엔진. 미지정 시 IMAGE_ENGINE env → settings.json image.engine → 'flow'(무료 기본).")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("prompt_file", type=pathlib.Path)
    p.add_argument("out_path", type=pathlib.Path)
    p.add_argument("refs", nargs="*", type=pathlib.Path, help="Optional reference images")
    args = p.parse_args()

    if not args.prompt_file.exists():
        print(f"error: prompt file not found: {args.prompt_file}", file=sys.stderr)
        return 2
    for r in args.refs:
        if not r.exists():
            print(f"error: ref image not found: {r}", file=sys.stderr)
            return 2

    # 엔진 디스패치: flow(무료 웹세션) vs gemini(유료 API). 호출부는 이 파일만 부른다.
    engine = resolve_engine(args.prompt_file, args.engine)
    if engine == "flow":
        return run_flow(args)

    key = (
        os.environ.get("GEMINI_API")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or find_env_key(args.prompt_file.parent, "GEMINI_API", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    if not key:
        print("error: engine=gemini(유료)로 설정됐지만 GEMINI_API_KEY가 없습니다.\n"
              "  무료로 쓰려면 settings.json image.engine=\"flow\"(기본)로 두세요.\n"
              "  gemini를 쓰려면 루트 .env에 GEMINI_API_KEY=... 등록 후 다시 실행하세요.",
              file=sys.stderr)
        return 2

    prompt = args.prompt_file.read_text(encoding="utf-8")
    parts = [img_part(r) for r in args.refs] + [{"text": prompt}]
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{args.model}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"HTTP {e.code} from Gemini:", file=sys.stderr)
        print(body_text[:2000], file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 1

    # Find first image part in candidates
    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                args.out_path.parent.mkdir(parents=True, exist_ok=True)
                args.out_path.write_bytes(base64.b64decode(inline["data"]))
                print(f"saved {args.out_path}  ({args.out_path.stat().st_size} bytes)")
                return 0

    # No image — usually safety block or text-only response
    print("no image in response. body preview:", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False)[:2000], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
