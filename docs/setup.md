# 셋업 가이드 (프리랜서 온보딩)

썰/야담 내러티브 유튜브 자동화 파이프라인. **Claude Code에서 "야담 영상 만들어줘" 한마디로**
대본→캐릭터/배경 asset→스토리보드→씬이미지→TTS→CapCut 드래프트→업로드까지 진행된다.
기본 경로(flow 이미지 + Vrew TTS + CapCut 렌더)는 **API 키·과금이 전혀 필요 없다.**

## 0. 요구 사항

| 항목 | 용도 | 비고 |
|---|---|---|
| macOS + Chrome | flow 이미지 생성 (웹세션) | 버너 구글 계정 권장 |
| Python 3.10+ | 파이프라인 스크립트 | |
| ffmpeg | 오디오 처리 | `brew install ffmpeg` |
| [Vrew](https://vrew.ai) | TTS (반수동, 무료) | 데스크톱 앱 |
| CapCut 데스크톱 | 렌더/마무리 편집 | `~/Movies/CapCut/...` 경로에 드래프트 생성됨 |
| Claude Code | 오케스트레이션 (story-pd 스킬) | |

## 1. 설치

```bash
git clone https://github.com/nossssi/gogogo2-youtube.git
cd gogogo2-youtube

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

brew install ffmpeg            # 없다면

cp .env.example .env           # 기본 경로만 쓰면 키를 채울 필요 없음
```

선택 — 자막 타이밍 정밀 모드용 whisper (없어도 음절 비례 폴백으로 동작):
```bash
.venv/bin/pip install openai-whisper
```

## 2. 이미지 엔진 (flow — 무료, 기본)

labs.google Flow 웹세션으로 Nano Banana Pro 이미지를 생성한다. **작업 전마다 데몬이 떠 있어야 한다.**

1. Chrome에서 `chrome://extensions` → 개발자 모드 → "압축해제된 확장 프로그램 로드" → `scripts/image/flow_extension/` 선택
2. 버너 구글 계정으로 [labs.google/fx/ko/tools/flow](https://labs.google/fx/ko/tools/flow) 로그인, 탭 유지
3. 데몬 상주: `python3 scripts/image/flow_token_server.py`
4. 확장 아이콘 → Connect (토큰이 `~/.flow-proxy/token.json`에 저장됨)

상세(멀티 계정 레인, reCAPTCHA 브리지 등): [docs/flow-image.md](flow-image.md)

> 유료 대안: `channels/{채널}/config/settings.json`에서 `image.engine="gemini"` + `.env`에
> `GEMINI_API_KEY` 등록 시에만 Gemini API 호출. **자동 폴백 없음** — 실수 과금 방지를 위해
> flow가 깨져도 gemini로 몰래 넘어가지 않는다.

## 3. 사용법

Claude Code를 레포 루트에서 열고:

```
야담 영상 만들어줘
```

story-pd 스킬이 파일 존재 기반 상태머신으로 단계를 자동 감지해 진행한다.
사람이 개입하는 지점(게이트)만 알면 된다:

| 게이트 | 할 일 |
|---|---|
| SCRIPT (대화) | 소재·컨셉·아웃라인을 Claude와 함께 확정 |
| ASSET 검수 | 생성된 캐릭터 턴어라운드/배경을 보고 OK |
| TTS (Vrew) | `{P}/vrew/vrew_script*.txt`를 Vrew에서 낭독 → 음성 mp3 + SRT를 `{P}/vrew/`에 저장 |
| RENDER 후 | CapCut을 열면 드래프트가 떠 있음 → 마무리 편집 → mp4를 `{P}/output/`에 내보내기 |

`{P}` = `channels/{채널}/projects/{프로젝트}`.
참고용 완성 프로젝트 산출물(텍스트만): `channels/yadam/projects/소금장수/`

## 4. 업로드 (선택 — 업로드 담당자만)

```bash
# 최초 1회: Google Cloud Console에서 OAuth 클라이언트(데스크톱) 생성 →
# client_secret.json을 channels/{채널}/config/youtube-api/ 에 저장 후
.venv/bin/python scripts/upload/auth.py --channel {채널}

# 매 업로드 (비공개 업로드)
.venv/bin/python scripts/upload/upload.py --project {프로젝트} --channel {채널}
```

`youtube-api/` 폴더는 통째로 gitignore — **시크릿·토큰을 절대 커밋하지 말 것.**

## 5. git 규칙 (여럿이 한 채널을 굴릴 때)

- **커밋되는 것**: 스킬(`.claude/skills/`), 스크립트, 채널 config, `research/topic_log.json`(소재 대장), refs/·proposal_*.md
- **커밋 안 되는 것(로컬 전용)**: `channels/*/projects/`(각자 작업물·미디어), `.env`, 토큰, scan 리포트
- **소재 중복 방지 절차**: 작업 시작 전 `git pull` → 소재 확정(CONCEPT ③) 시 `topic_log.json` 커밋+push.
  topic_log가 공유 안 되면 다른 사람과 같은 소재를 만들게 된다.
