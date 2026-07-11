#!/usr/bin/env python3
"""
캐릭터 턴어라운드 시트 생성 — characters.json 을 읽어 인물별
정면·3/4·측면·후면 4뷰(흰 배경, 텍스트 0) 시트를 생성한다.

검증된 일관성 앵커: trait-lock(특히 build=키/체형/연령) + anchorProp + 문화앵커(STYLE).

Usage:
    python3 scripts/assets/turnaround.py <project_dir> [--only id1,id2] [--dry-run]

flat 인물  → assets/characters/<id>_turnaround.png
variant 인물 → assets/characters/<id>_<variant>_turnaround.png (각 variant마다)
characters.json의 turnaround 경로가 이미 파일로 존재하면 스킵(--force로 재생성).
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


def turnaround_prompt(lock, negatives, style, anchor=None):
    neg_extra = (" " + ", ".join(negatives) + ".") if negatives else ""
    anchor_extra = (
        f" Signature identifying feature — must be clearly visible in ALL four views "
        f"including the back view: {anchor}." if anchor else ""
    )
    return (
        f"Character turnaround model sheet of ONE single {lock}, "
        f"four views in a row: front, 3/4, side, back. "
        f"Plain pure white background. No labels, no swatches. "
        f"SAME identical person across all four views.{anchor_extra}{neg_extra} "
        f"{style['preset']} {style.get('negative', '')}"
    ).strip()


def jobs_for_char(cid, char):
    """(out_rel, lock, negatives, anchor) 목록. flat=1개, variant=variant수만큼."""
    anchor = char.get("anchorProp")
    if "variants" in char:
        out = []
        for v, vd in char["variants"].items():
            rel = vd.get("turnaround") or f"assets/characters/{cid}_{v}_turnaround.png"
            out.append((rel, vd["lock"], vd.get("negatives", char.get("negatives", [])),
                        vd.get("anchorProp", anchor)))
        return out
    rel = char.get("turnaround") or f"assets/characters/{cid}_turnaround.png"
    return [(rel, char["lock"], char.get("negatives", []), anchor)]


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
    characters = json.loads((project_dir / "characters.json").read_text())
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None

    tasks = []
    for cid, char in characters.items():
        if cid.startswith("_") or not isinstance(char, dict):
            continue
        if only and cid not in only:
            continue
        for rel, lock, negs, anchor in jobs_for_char(cid, char):
            tasks.append((cid, rel, lock, negs, anchor))

    key = find_env_key(project_dir)
    env = dict(os.environ)
    if key:
        env["GEMINI_API"] = key
    conc = args.concurrency or int(style.get("max_concurrent", 5))

    def run(t):
        cid, rel, lock, negs, anchor = t
        out = (project_dir / rel)
        if out.exists() and not args.force and not args.dry_run:
            return cid, rel, "SKIP(exists)"
        prompt = turnaround_prompt(lock, negs, style, anchor)
        out.parent.mkdir(parents=True, exist_ok=True)
        pf = out.with_suffix(".prompt.txt")
        pf.write_text(prompt, encoding="utf-8")
        if args.dry_run:
            return cid, rel, "DRY"
        r = subprocess.run(["python3", str(GEN), str(pf), str(out)], capture_output=True, text=True, env=env)
        return cid, rel, ("OK" if (out.exists() and r.returncode == 0) else "FAIL: " + (r.stderr or r.stdout)[-200:])

    with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
        results = list(ex.map(run, tasks))
    for cid, rel, status in results:
        print(f"[{cid}] {rel} -> {status}")
    ok = sum(1 for _, _, s in results if s == "OK")
    print(f"\n턴어라운드: OK {ok} / 전체 {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
