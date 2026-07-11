"""
YouTube OAuth2 인증 스크립트.

최초 1회 실행하면 브라우저가 열리고 Google 로그인 후 토큰이 저장됨.
이후에는 자동 갱신되므로 다시 실행할 필요 없음.

사용법:
  .venv/bin/python scripts/upload/auth.py --channel "메인경제채널"

사전 준비:
  1. Google Cloud Console → API 및 서비스 → YouTube Data API v3 활성화
  2. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
  3. JSON 다운로드 → channels/{채널}/config/youtube-api/client_secret.json 으로 저장
"""

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

ROOT = Path(__file__).resolve().parents[2]


def get_channel_dir(channel_name: str) -> Path:
    channel_dir = ROOT / "channels" / channel_name
    if not channel_dir.exists():
        print(f"[ERROR] 채널 디렉토리 없음: {channel_dir}")
        sys.exit(1)
    return channel_dir


def authenticate(channel_name: str) -> None:
    channel_dir = get_channel_dir(channel_name)
    client_secret = channel_dir / "config" / "youtube-api" / "client_secret.json"
    token_path = channel_dir / "config" / "youtube-api" / "token.json"

    if not client_secret.exists():
        print(f"[ERROR] OAuth 클라이언트 시크릿 파일 없음: {client_secret}")
        print()
        print("=== 설정 방법 ===")
        print("1. Google Cloud Console (https://console.cloud.google.com) 접속")
        print("2. API 및 서비스 → 사용자 인증 정보")
        print("3. OAuth 2.0 클라이언트 ID 생성 (애플리케이션 유형: 데스크톱 앱)")
        print("4. JSON 다운로드")
        print(f"5. 파일을 여기에 저장: {client_secret}")
        sys.exit(1)

    if token_path.exists():
        print(f"[INFO] 토큰이 이미 존재합니다: {token_path}")
        print("[INFO] 재인증하려면 토큰 파일을 삭제 후 다시 실행하세요.")
        return

    print(f"[INFO] 브라우저에서 Google 로그인 창이 열립니다...")
    print(f"[INFO] 채널: {channel_name}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    credentials = flow.run_local_server(port=0)

    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    token_path.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
    print(f"[OK] 토큰 저장 완료: {token_path}")
    print("[OK] 이후 업로드 시 자동으로 사용됩니다.")


def main():
    parser = argparse.ArgumentParser(description="YouTube OAuth2 인증")
    parser.add_argument("--channel", required=True, help="채널 이름 (channels/ 하위 폴더명)")
    args = parser.parse_args()
    authenticate(args.channel)


if __name__ == "__main__":
    main()
