#!/usr/bin/env python3
"""
씬 이미지 일괄 생성 — characters.json + locations.json + storyboard.json 을 읽어
씬별 cast(+location) ref를 골라 첨부하고 Nano Banana Pro로 생성한다.

빈밥상 build_storyboard.py의 검증된 방식(씬별 cast ref만 첨부 + trait-lock 치환 +
STYLE 문화앵커 append)을 프로젝트/채널 무관하게 일반화한 것.

Usage:
    python3 scripts/storyboard/build.py <project_dir> [--only 1,2,3] [--dry-run] [--concurrency N]

project_dir = channels/<채널>/projects/<프로젝트>  (characters.json/locations.json/storyboard.json 위치)
채널 config(style.json)은 project_dir 상위(../../config/style.json)에서 자동 로드.

입력(소스, 보존):  storyboard.json  { "scenes": [ {id, act, narration, cast[], location, visual_desc}, ... ] }
출력:              storyboard.built.json  (각 씬에 image_prompt / image / status 추가)
                   scenes/scene_NN.png,  scenes/_pNN.txt (프롬프트)

cast 토큰: "id" 또는 "id:variant". visual_desc의 {id}(base id)는 해당 인물 lock 문장으로 치환.
refs: cast turnaround(순서대로) + location.sheet(존재 시) → style.max_refs 로 캡, cast 우선.
"""
import argparse
import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE.parent / "image" / "generate_image.py"


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_env_key(start: pathlib.Path, name: str = "GEMINI_API_KEY") -> str | None:
    cur = start.resolve()
    for _ in range(6):
        env = cur / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def resolve_cast(token: str, characters: dict) -> dict:
    """cast 토큰("id" | "id:variant") → {base_id, lock, turnaround(상대경로)}."""
    base, _, variant = token.partition(":")
    char = characters.get(base)
    if not char:
        raise KeyError(f"characters.json에 없는 인물: {base!r} (씬 cast={token!r})")
    if "variants" in char:
        v = variant or char.get("default_variant")
        if not v:
            raise KeyError(f"{base!r}는 variant 인물인데 variant 미지정이고 default_variant 없음")
        vd = char["variants"].get(v)
        if not vd:
            raise KeyError(f"{base!r}에 variant {v!r} 없음")
        return {"base": base, "lock": vd["lock"], "turnaround": vd.get("turnaround")}
    return {"base": base, "lock": char["lock"], "turnaround": char.get("turnaround")}


def build_scene(scene, characters, locations, style, project_dir):
    """씬 하나 → (prompt_text, ref_paths[])."""
    desc = scene["visual_desc"]
    cast_tokens = scene.get("cast") or []
    ref_paths = []

    # cast: lock 치환 + turnaround ref
    for token in cast_tokens:
        r = resolve_cast(token, characters)
        desc = desc.replace("{" + r["base"] + "}", r["lock"])
        if r["turnaround"]:
            p = (project_dir / r["turnaround"]).resolve()
            if p.exists():
                ref_paths.append(str(p))

    # 남은 미치환 {id} 안전망 (cast에 없지만 desc에 등장 시 lock만 주입, ref 없이)
    for cid, char in characters.items():
        tok = "{" + cid + "}"
        if tok in desc:
            lock = char.get("lock") or (char.get("variants", {}).get(char.get("default_variant", ""), {}) or {}).get("lock", cid)
            desc = desc.replace(tok, lock)

    # location sheet (존재할 때만, cast 다음 순위)
    loc = scene.get("location")
    if loc and loc in locations:
        sheet = locations[loc].get("sheet")
        if sheet:
            sp = (project_dir / sheet).resolve()
            if sp.exists():
                ref_paths.append(str(sp))

    # max_refs 캡 (cast 우선 — 리스트 앞쪽이 cast)
    max_refs = int(style.get("max_refs", 5))
    ref_paths = ref_paths[:max_refs]

    prompt = f"{desc.strip()} {style['preset']} {style.get('negative', '')}".strip()
    return prompt, ref_paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--only", default="", help="생성할 씬 id 목록 (쉼표구분). 미지정 시 전체.")
    ap.add_argument("--dry-run", action="store_true", help="프롬프트/ref만 출력, 이미지 생성 안 함.")
    ap.add_argument("--concurrency", type=int, default=0, help="동시 생성 수 (0=style.max_concurrent, flow면 레인 수로 캡).")
    ap.add_argument("--force", action="store_true", help="체크포인트(OK+PNG 존재) 씬도 재생성.")
    args = ap.parse_args()

    project_dir = args.project_dir.resolve()
    style_path = project_dir.parent.parent / "config" / "style.json"
    for pth, label in [(style_path, "style.json"),
                       (project_dir / "characters.json", "characters.json"),
                       (project_dir / "storyboard.json", "storyboard.json")]:
        if not pth.exists():
            print(f"error: {label} 없음: {pth}", file=sys.stderr)
            return 2

    style = load_json(style_path)
    characters = load_json(project_dir / "characters.json")
    lp = project_dir / "locations.json"
    locations = load_json(lp) if lp.exists() else {}
    storyboard = load_json(project_dir / "storyboard.json")
    scenes = storyboard["scenes"] if isinstance(storyboard, dict) else storyboard

    all_scenes = scenes
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None
    if only:
        scenes = [s for s in scenes if s["id"] in only]

    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)

    # 체크포인트: 기존 built.json에서 OK이고 PNG가 실재하는 씬은 스킵 (--force로 무시)
    out_json = project_dir / "storyboard.built.json"
    prev = {}
    if out_json.exists():
        try:
            prev = {s["id"]: s for s in load_json(out_json).get("scenes", [])}
        except Exception:
            prev = {}

    def done(sid):
        rec = prev.get(sid)
        return bool(rec and rec.get("status") == "OK"
                    and (scenes_dir / f"scene_{sid:02d}.png").exists())

    if not args.force and not args.dry_run:
        skipped = [s["id"] for s in scenes if done(s["id"])]
        scenes = [s for s in scenes if not done(s["id"])]
        if skipped:
            print(f"체크포인트 스킵 {len(skipped)}씬 (OK+PNG 존재). --force로 재생성 가능.")

    key = find_env_key(project_dir)
    env = dict(os.environ)
    if key:
        env["GEMINI_API"] = key

    conc = args.concurrency or int(style.get("max_concurrent", 5))
    # flow 엔진이면 레인(포트) 수 이상의 동시성은 "모든 레인이 사용 중" 즉시 실패만 낳는다 — 자동 캡
    try:
        img = load_json(project_dir.parent.parent / "config" / "settings.json").get("image", {})
        if img.get("engine", "flow") == "flow":
            flow = img.get("flow", {})
            lanes = len(flow.get("ports") or ([flow["port"]] if flow.get("port") else [])) or 1
            if conc > lanes:
                print(f"flow 레인 {lanes}개 — 동시성 {conc}→{lanes}로 자동 캡")
                conc = lanes
    except Exception:
        pass
    built = []

    def run(scene):
        sid = scene["id"]
        try:
            prompt, refs = build_scene(scene, characters, locations, style, project_dir)
        except KeyError as e:
            return {**scene, "status": f"FAIL(build): {e}"}
        pf = scenes_dir / f"_p{sid:02d}.txt"
        pf.write_text(prompt, encoding="utf-8")
        out = scenes_dir / f"scene_{sid:02d}.png"
        rec = {**scene, "image_prompt": prompt, "image": f"scenes/scene_{sid:02d}.png"}
        if args.dry_run:
            rec["status"] = f"DRY (refs={len(refs)})"
            return rec
        cmd = ["python3", str(GEN), str(pf), str(out)] + refs
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        ok = out.exists() and r.returncode == 0
        rec["status"] = "OK" if ok else "FAIL: " + (r.stderr or r.stdout)[-300:]
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
        for rec in ex.map(run, scenes):
            built.append(rec)
            print(f"[{rec['id']:02d}] {rec.get('act',''):5} cast={rec.get('cast')} loc={rec.get('location')} refs->{rec['status']}")

    # 병합 저장: 이번에 돌린 씬은 새 결과, 안 돌린 씬은 기존 기록 유지 (--only가 체크포인트를 지우지 않게)
    new_by_id = {s["id"]: s for s in built}
    merged = [new_by_id.get(s["id"]) or prev.get(s["id"]) or dict(s) for s in all_scenes]
    json.dump({"scenes": merged}, open(out_json, "w"), ensure_ascii=False, indent=2)
    ok = sum(1 for s in merged if s.get("status") == "OK")
    dry = sum(1 for s in merged if str(s.get("status", "")).startswith("DRY"))
    print(f"\n완료(전체 기준): OK {ok} / DRY {dry} / 전체 {len(merged)} (이번 실행 {len(built)}씬)  → {out_json.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
