#!/usr/bin/env python3
"""
Flow 멀티계정 런처/모니터 — N개 레인(계정) 데몬을 한 번에 띄우고 상태를 보여준다.

각 레인 = (Chrome 프로필 1개 + 버너 계정 1개 + 데몬 포트 1개).
클라이언트(flow_client)는 놀고있는 레인을 임대해 병렬로 이미지를 뽑는다 → 계정 수만큼 처리량↑ / 쿼터↑.

Usage:
    # 3개 레인(포트 3847,3848,3849) 데몬 기동 + 상태 모니터 (배치 도는 동안 켜둠)
    python3 scripts/image/flow_multi.py --count 3

    # 특정 포트들로
    python3 scripts/image/flow_multi.py --ports 3847,3848,3849

    # 데몬 안 띄우고 상태만
    python3 scripts/image/flow_multi.py --ports 3847,3848 --status-only

레인마다 Chrome 프로필에서 할 일(최초 1회):
  1) 새 Chrome 프로필 생성(우상단 프로필 → 추가) 후 그 프로필에서 버너 구글 계정 로그인
  2) chrome://extensions → 개발자 모드 → flow_extension 로드
  3) 확장 팝업에서 '레인 포트'를 이 프로필용 포트(3847/3848/...)로 설정
  4) labs.google/fx/tools/flow 열고 로그인 → 확장 Connect
  5) 그 프로필의 Flow 탭은 배치 도는 동안 열어둘 것

settings.json 예: "image": {"engine":"flow", "flow": {"ports":[3847,3848,3849], ...}}
"""
import argparse
import json
import pathlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DAEMON = HERE / "flow_token_server.py"


def status(port: int) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=3) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError):
        return {"connected": False, "message": "데몬 미기동", "busy": None, "_down": True}


def print_status(ports: list[int]) -> None:
    line = []
    for p in ports:
        s = status(p)
        if s.get("_down"):
            mark = "⛔ 미기동"
        elif s.get("connected"):
            mark = "🟢 연결" + ("·작업중" if s.get("busy") else "·대기")
        else:
            mark = "🟡 미연결(Connect 필요)"
        line.append(f"[{p}] {mark}")
    print("  " + "   ".join(line), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=0, help="레인 개수(포트 base부터 연속). --ports와 택1")
    ap.add_argument("--base-port", type=int, default=3847)
    ap.add_argument("--ports", default="", help="포트 목록(쉼표). 예: 3847,3848,3849")
    ap.add_argument("--status-only", action="store_true", help="데몬 안 띄우고 상태만 반복 출력")
    args = ap.parse_args()

    if args.ports:
        ports = [int(x) for x in args.ports.split(",") if x.strip()]
    elif args.count:
        ports = [args.base_port + i for i in range(args.count)]
    else:
        print("--count 또는 --ports 필요", file=sys.stderr)
        return 2

    procs = []
    if not args.status_only:
        for p in ports:
            proc = subprocess.Popen([sys.executable, str(DAEMON), "--port", str(p)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append(proc)
        time.sleep(1.5)

    print(f"Flow 멀티레인: {ports}")
    print("각 레인의 Chrome 프로필에서 확장 팝업 포트를 해당 포트로 맞추고 Connect 하세요.")
    print("settings.json image.flow.ports 도 이 목록으로 설정하면 병렬 생성됩니다.\n")

    def cleanup(*_):
        for pr in procs:
            pr.terminate()
        print("\n레인 종료")
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            print_status(ports)
            time.sleep(5)
    except KeyboardInterrupt:
        cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
