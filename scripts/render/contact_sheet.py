#!/usr/bin/env python3
"""이미지 폴더 → 검수용 contact sheet(그리드 몽타주) PNG.

Remotion 의존 없이 Pillow만으로 만든다. SCENE_IMG / ASSET_GEN 검수 게이트에서
씬 이미지·턴어라운드를 한 장으로 훑어볼 때 사용.

Usage:
    # 프로젝트 scenes/ 검수 (기본)
    python3 scripts/render/contact_sheet.py --channel yadam --project 소금장수

    # 임의 폴더 (asset 검수 등)
    python3 scripts/render/contact_sheet.py --dir channels/yadam/projects/소금장수/assets/characters

출력: {대상 폴더}/_contact_sheet.png (--out으로 변경 가능)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EXTS = {".png", ".jpg", ".jpeg", ".webp"}
LABEL_H = 28

# macOS 한글 폰트 → 실패 시 PIL 기본 폰트
_FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
]


def _load_font(size: int = 16):
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_contact_sheet(src_dir: Path, out_path: Path | None, cols: int, thumb_width: int) -> Path:
    images = sorted(p for p in src_dir.iterdir()
                    if p.suffix.lower() in EXTS and not p.name.startswith("_"))
    if not images:
        raise FileNotFoundError(f"이미지 없음: {src_dir}")

    font = _load_font()
    thumbs = []
    for p in images:
        with Image.open(p) as im:
            im = im.convert("RGB")
            h = max(1, round(im.height * thumb_width / im.width))
            thumbs.append((p.stem, im.resize((thumb_width, h), Image.LANCZOS)))

    cols = max(1, min(cols, len(thumbs)))
    rows = -(-len(thumbs) // cols)
    cell_h = max(t.height for _, t in thumbs) + LABEL_H
    sheet = Image.new("RGB", (cols * thumb_width, rows * cell_h), "#1a1a1a")
    draw = ImageDraw.Draw(sheet)

    for i, (label, thumb) in enumerate(thumbs):
        x = (i % cols) * thumb_width
        y = (i // cols) * cell_h
        sheet.paste(thumb, (x, y))
        draw.text((x + 6, y + cell_h - LABEL_H + 5), label, fill="#e8e8e8", font=font)

    out_path = out_path or (src_dir / "_contact_sheet.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="이미지 폴더 → 검수용 contact sheet")
    parser.add_argument("--channel", help="채널 이름 (--project와 함께: {P}/scenes/ 대상)")
    parser.add_argument("--project", help="프로젝트 이름")
    parser.add_argument("--dir", help="임의 이미지 폴더 (channel/project 대신)")
    parser.add_argument("--out", help="출력 경로. 기본 {대상 폴더}/_contact_sheet.png")
    parser.add_argument("--cols", type=int, default=6, help="그리드 열 수")
    parser.add_argument("--thumb-width", type=int, default=360, help="썸네일 폭 px")
    args = parser.parse_args()

    if args.dir:
        src_dir = Path(args.dir)
    elif args.channel and args.project:
        src_dir = ROOT / "channels" / args.channel / "projects" / args.project / "scenes"
    else:
        parser.error("--dir 또는 --channel+--project 필요")

    if not src_dir.is_dir():
        print(f"[ERROR] 폴더 없음: {src_dir}", file=sys.stderr)
        return 1

    try:
        sheet = build_contact_sheet(src_dir, Path(args.out) if args.out else None,
                                    args.cols, args.thumb_width)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[INFO] contact sheet: {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
