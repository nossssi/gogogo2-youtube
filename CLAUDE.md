# autoworker-story

썰/스토리 야담 유튜브 **내러티브** 자동화 파이프라인.
정보성 채널(마스코트 1개, `autoworker-youtube`)과 달리 **주연·조연 캐릭터 + 배경 asset**이 등장한다.
`autoworker-youtube`는 **코드 참조만** 하고(fork 아님), 검증된 조각만 이식했다.

## 핵심 원칙 (빈밥상 실증으로 검증됨)

캐릭터 일관성 3종 세트:
1. **턴어라운드 ref** — 인물당 1장(정면·3/4·측면·후면, 흰 배경, 텍스트 0).
2. **trait-lock 텍스트** — `physical{age,build,hair,eyes,uniqueFeatures}` + `negatives`. 특히 **`build`(키/체형/연령)가 필수** (없으면 다 성인으로 드리프트). hex 색은 약하니 말로.
3. **씬별 cast** — 씬마다 등장 인물 id만 골라 그 턴어라운드 ref만 첨부(전부 X, 최대 5장).

- **인물마다 식별 앵커 1개 필수** (`anchorProp` + lock 문장에 포함) — 실루엣/착용 소품/시그니처 색/큰 머리·얼굴 특징 중 하나, 캐스트 내 축·색 중복 금지. 동물·신령 등 비인간 인물은 얼굴 잠금이 약하므로 몸에 두른 착용 소품(발목에 맨 색 끈, 목에 건 방울 등)이 얼굴보다 강한 앵커.
- **문화·시대 앵커는 STYLE 프리셋에 박는다** — ref 없는 씬(군중·빈 배경)은 텍스트 앵커가 유일한 방어선. 없으면 서양 판타지로 드리프트. `"Ghibli/anime"` 금지 → `"Korean webtoon/manhwa"`.

## 워크플로우 (story-pd 스킬 상태머신)

```
SCRIPT → ASSET_GEN(★검수 게이트) → STORYBOARD → SCENE_IMG → TTS → RENDER → UPLOAD
```

파일 존재 기반 상태 감지. 프로젝트 경로 `{P}` = `channels/{채널}/projects/{프로젝트}`.

**SCRIPT 서브 상태머신** (`{S}` = `{P}/_script`, 주력 = 장편 3~4만자 단일 대하 서사):
```
WATCHLIST(1회) → SCAN(소재 트렌드) → CONCEPT(★대화: 레퍼런스 1편 분석+확정 브리프) → OUTLINE(★대화: 장 설계+복선 장부+레지스트리 초안)
→ DRAFT(2~3장 배치 순차 집필+bible+레지스트리 동기화) → REVIEW(validate_script.py+체크리스트) → script.txt+meta.txt
```
- 대본 공식(playbook) = story-pd `prompts/script-guide.md` — **매 편 벤치마킹 안 함**, 공식 버전 그대로 적용. 개정은 딥 벤치마킹(`benchmark-guide.md`) 제안 → 사용자 승인 시에만 (`playbook-history.md`에 기록).
- **별도 인물 추출 단계 없음 (레지스트리 생애주기)** — characters/locations.json은 OUTLINE에서 서사 필드로 태어나고, DRAFT 중 동기화되고, ASSET_GEN 진입 시 시각 필드(영문 lock·negatives)를 완성한다.

**RENDER = CapCut export 전용 (자동 mp4 렌더 없음)** — `capcut_export.py`가 `{V}` 산출물로 CapCut 드래프트 생성(성공 시 `{P}/output/capcut_draft.json` 마커) → 사람이 CapCut에서 마무리 편집 → `{P}/output/`에 mp4 내보내기 → UPLOAD(upload.py가 output/의 mp4를 집는다).

**TTS 반수동(Vrew) 모드** — `settings.json tts.engine: "vrew"`. `ingest_vrew.py --export-script`로 대본 내보내기(**1만자 한도 초과 시 `vrew_script_partNN.txt` 분할** — 파트별 낭독 후 `narration_NN.mp3/srt`로 저장, ingest가 샘플 정확도로 병합) → 사용자가 Vrew에서 음성+SRT 제작 → `{P}/vrew/`에 넣고 `ingest_vrew.py` 실행 → `audio.mp3`/`subtitle.srt`/`sentences.json` 생성 (ElevenLabs·alignment·무음압축 건너뜀) → **`split_long_cues.py --apply`로 자막 정형화** (①문장 경계 스냅: 문장 경계를 걸친 큐를 경계에서 분할 — 씬 경계=큐 경계 보장, ②20자 초과 분할; whisper 단어 실측, 폴백=음절 비례; --apply가 sentences.json에 문장별 실측 cue_range 기록; 반드시 scene_timing 전) → `scene_timing.py`부터 동일 (실측 cue_range가 있으면 정밀 모드, 없으면 비례 폴백).

## 폴더 구조

```
channels/{채널}/config/{style.json, settings.json, workflow.json, profile.md, watchlist.json}
channels/{채널}/research/           # scan_*.md 소재 리포트, topic_log.json 소재 대장(모티프 중복 회피), refs/ 딥 벤치마킹, proposal_*.md 공식 개정 제안
channels/{채널}/projects/{프로젝트}/
  _script/                          # concept.md, outline.md, chapters/, bible.md
  script.txt  meta.txt
  characters.json   locations.json
  assets/characters/<id>[_<variant>]_turnaround.png
  assets/locations/<id>_sheet.png
  storyboard.json
  scenes/scene_NN.png
  audio/  render/
scripts/
  research/scan_channels.py    # watchlist 채널 최근 영상 스캔 → 조회수/일 소재 리포트 (yt-dlp, 무료)
  research/collect_refs.py     # 영상 자막·댓글·메타 수집 (--benchmark=공식 개정용 / --project)
  script/validate_script.py    # 대본 제약 기계 검증 (분량·숫자·영어·20자 호흡·문어체)
  image/generate_image.py      # 엔진 디스패처. flow=Nano Banana+2K 업스케일(무료 기본) / gemini=Nano Banana Pro API(유료)
  assets/turnaround.py         # characters.json → 턴어라운드
  assets/background.py         # locations.json → 배경 시트
  storyboard/build.py          # characters+locations+storyboard.json → 씬 이미지
  render/capcut_export.py      # {V} 산출물 → CapCut 드래프트 (렌더는 CapCut에서 사람이 마무리)
  render/scene_timing.py       # 씬→자막 큐 타이밍 매핑 (렌더용 storyboard 생성)
  render/contact_sheet.py      # 검수용 그리드 몽타주 (PIL, scenes/·assets/ 공용)
  tts/  upload/                # autoworker에서 이식 (upload: OAuth 인증 + 비공개 업로드, 자족)
```

## 스키마

**characters.json** — id별 레지스트리. 같은 인물의 나이/상태 변화는 `variants`, 변신·환생은 새 id + 공유 `anchorProp`.
**locations.json** — 재등장 장소만 시트 ref.
**storyboard.json** — 씬: `{id, act, narration, cast[], location, visual_desc, image_prompt, image, status}`. cast는 `"id"` 또는 `"id:variant"`.

## 이미지 생성 규칙 (build.py)

- 프롬프트 = `visual_desc`({id}→variant별 trait-lock 치환) + 채널 `style.json`(STYLE+문화앵커+NEG)
- refs = cast별 turnaround + location.sheet → 최대 5장, cast 우선
- 모델(flow 기본): Nano Banana(NARWHAL) + 2K 업스케일, 동시성 ~5 — banana-pro와 일관성 동급이면서 일일 쿼터 ~10배(A/B 실측 2026-07). `settings.json image.flow.model`로 변경

## 이미지 엔진 (flow=무료 / gemini=유료)

`settings.json image.engine`로 분기(**기본 `flow`, 미설정 시에도 `flow`**). `generate_image.py`가 이 값을 읽어 자동 라우팅 — 호출부(turnaround/background/build) 무관.
- **flow**(무료, 기본): labs.google Flow 웹세션(버너 구글 로그인)으로 Nano Banana(NARWHAL) 생성 + `upsampleImage` 2K 업스케일(실패 시 원본 폴백). **상주 데몬 + Chrome Flow 탭 로그인 필요**(reCAPTCHA 브리지, 반수동). 셋업: `docs/flow-image.md`.
- **gemini**(유료, 명시 opt-in 전용): `settings.json image.engine="gemini"`로 **직접 지정 + `.env`에 `GEMINI_API_KEY` 등록**했을 때만 API 호출. **자동 폴백 없음** — flow가 깨져도 gemini로 몰래 넘어가지 않고 에러를 낸다(실수 과금 방지). 키 없이 gemini 지정 시 안내 메시지 후 종료.

## 환경

- API 키: 루트 `.env`의 `GEMINI_API_KEY` (gemini 엔진 전용).
- `generate_image.py`는 상위 폴더로 올라가며 `.env`(키)와 `config/settings.json`·`config/style.json`(엔진·비율)을 찾는다.
- flow 엔진: `python3 scripts/image/flow_token_server.py` 상주 + Chrome 확장(`scripts/image/flow_extension/`) Connect. 토큰은 `~/.flow-proxy/token.json`.
