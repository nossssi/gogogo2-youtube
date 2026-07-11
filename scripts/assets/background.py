#!/usr/bin/env python3
"""
배경(location) 시트 생성 — locations.json 을 읽어 재등장 장소별
establishing 배경 시트(인물 없음)를 생성한다. 같은 장소가 씬마다 드리프트하는 것 방지.

Usage:
    python3 scripts/assets/background.py <project_dir> [--only id1,id2] [--dry-run] [--force]

→ assets/locations/<id>_sheet.png  (locations.json의 sheet 경로)
sheet 파일이 이미 존재하면 스킵(--force로 재생성).
"""
import argparse, concurrent.futures, json, os, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE.parent / "image" / "generate_image.py"


def find_env_key(start, name="GEMINI_API_KEY"):
    cur = pathlib.Path(start).resolve()
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


def background_prompt(desc, style):
    return (
        f"{desc}. Environment / location establishing reference sheet, wide shot, "
        f"NO people, NO characters, empty scene. "
        f"{style['preset']} {style.get('negative', '')}"
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=pathlib.Path)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--concurrency", type=int, default=0)
    args = ap.parse_args()

    project_dir = args.project_dir.resolve()
    style = json.loads((project_dir.parent.parent / "config" / "style.json").read_text())
    lp = project_dir / "locations.json"
    if not lp.exists():
        print(f"locations.json 없음 — 생성할 배경 없음: {lp}")
        return 0
    locations = json.loads(lp.read_text())
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None

    tasks = []
    for lid, loc in locations.items():
        if lid.startswith("_") or not isinstance(loc, dict):
            continue
        if only and lid not in only:
            continue
        rel = loc.get("sheet") or f"assets/locations/{lid}_sheet.png"
        tasks.append((lid, rel, loc.get("desc", lid)))

    key = find_env_key(project_dir)
    env = dict(os.environ)
    if key:
        env["GEMINI_API"] = key
    conc = args.concurrency or int(style.get("max_concurrent", 5))

    def run(t):
        lid, rel, desc = t
        out = project_dir / rel
        if out.exists() and not args.force and not args.dry_run:
            return lid, rel, "SKIP(exists)"
        prompt = background_prompt(desc, style)
        out.parent.mkdir(parents=True, exist_ok=True)
        pf = out.with_suffix(".prompt.txt")
        pf.write_text(prompt, encoding="utf-8")
        if args.dry_run:
            return lid, rel, "DRY"
        r = subprocess.run(["python3", str(GEN), str(pf), str(out)], capture_output=True, text=True, env=env)
        return lid, rel, ("OK" if (out.exists() and r.returncode == 0) else "FAIL: " + (r.stderr or r.stdout)[-200:])

    with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
        results = list(ex.map(run, tasks))
    for lid, rel, status in results:
        print(f"[{lid}] {rel} -> {status}")
    ok = sum(1 for _, _, s in results if s == "OK")
    print(f"\n배경 시트: OK {ok} / 전체 {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
