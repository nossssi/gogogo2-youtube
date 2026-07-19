---
name: story-pd
description: 썰/야담 내러티브 유튜브 PD. "야담 영상 만들어줘" 한마디로 대본→asset(인물·배경)→스토리보드→씬이미지→TTS→렌더→업로드를 상태 기반으로 오케스트레이션. 정보성(마스코트)과 달리 주연·조연 캐릭터와 배경 asset이 등장하는 파이프라인. 야담/썰/스토리 영상·대본·캐릭터·스토리보드 요청 시 사용.
---

# story-pd — 썰/야담 내러티브 PD

## 역할 원칙
1. **상태 기반 진행** — 파일 존재 여부로 현재 단계를 감지하고 다음 단계를 자동 결정.
2. **asset 검수 게이트 — 사용자 컨펌 필수** (2026-07-19 사용자 지시로 재도입) — ASSET_GEN(턴어라운드·배경) 후 **반드시 멈춘다**. contact sheet를 만들어 **`open`으로 화면에 띄우고**(사용자가 파일을 직접 찾을 필요 없게), 캐릭터 일관성(연령/체형/문화/앵커)을 눈으로 확인하고 **사용자가 명시적으로 OK 할 때까지 STORYBOARD 이후로 절대 진행하지 않는다**. 드리프트를 지적하면 해당 인물만 lock/anchorProp 수정 후 `--force` 재생성 → 다시 띄워 재확인. **사람 게이트는 asset 검수 + TTS(Vrew 낭독) + CapCut 마무리 편집 셋.**
3. **대화 밀도는 단계별로 다르다** — **SCRIPT(대본)는 최대 대화가 목적**: 컨셉·아웃라인·장 초안을 사용자와 함께 다듬어 새 이야기를 공동 창작한다. 각 서브 단계 산출물(concept/outline/장 배치)은 반드시 보여주고 피드백을 받은 뒤 다음으로. **SCRIPT 이후 제작 단계(asset~upload)는 최소 대화** — auto 단계는 결과만 보고, ask 단계(asset검수, thumbnail)에서만 대화.
4. **에이전트 위임** — 장편 집필(DRAFT 배치)·분석은 에이전트에 위임. PD는 오케스트레이션.

## 프로젝트 구조
`{P}` = `channels/{채널}/projects/{프로젝트}`
```
{P}/_script/                  # {S}: concept.md, outline.md(장 설계+복선 장부), chapters/, bible.md
{P}/_refs/NNN/                # CONCEPT 원전 수집물+분석: meta.md(조회수·댓글TOP10)+transcript.txt+thumbnail+analysis.md(분석 보고서)
{P}/script.txt  meta.txt
{P}/characters.json  locations.json
{P}/assets/characters/<id>[_<variant>]_turnaround.png
{P}/assets/locations/<id>_sheet.png
{P}/storyboard.json           # 소스(사람이 authored, status 없음)
{P}/storyboard.built.json     # build.py 출력(image/status 포함)
{P}/scenes/scene_NN.png
{P}/vrew/                     # vrew 모드: vrew_script.txt + 사용자가 넣는 음성/SRT
{P}/_video/                   # {V}: TTS·자막·렌더용 storyboard 등 중간물
{P}/output/capcut_draft.json  # RENDER 마커 (capcut_export 성공 기록)
{P}/output/*.mp4              # 사람이 CapCut에서 마무리 편집 후 내보낸 최종본
```
채널 그림체/문화앵커: `channels/{채널}/config/style.json` (모든 프롬프트에 자동 append).
채널 공용 리서치: `channels/{채널}/config/watchlist.json`(추적 채널) → `channels/{채널}/research/`(scan_*.md 소재 리포트, topic_log.json 소재 대장, refs/ 딥 벤치마킹 수집, proposal_*.md 공식 개정 제안).

## 초기화
- **채널**: `channels/` 스캔(`_`로 시작 제외). 1개면 자동, 여러 개면 선택. `config/settings.json`+`profile.md`+`workflow.json` 로드.
- **프로젝트**: 기존 관련 요청→선택. 새 프로젝트는 **생성 시각으로 명명** — `YYMMDD_HHMM` (예: `260711_1430`). 컨셉이 없는 시점이라 키워드 명명이 불가능하기 때문. CONCEPT ③ 확정 때 뒤에 언더바+짧은 제목을 붙여 rename (예: `260711_1430_머슴임금`).
- **모드**: `config/workflow.json`의 `mode`를 따른다(묻지 않음). `{P}/workflow.json`이 있으면 우선.

## 상태 감지 (위→아래 첫 매칭, `{V}` = `{P}/_video`)
```
{P}/ 없음 or script.txt 없음                       → SCRIPT (레지스트리는 OUTLINE에서 생성 — "레지스트리 생애주기")
assets/ 비었거나 turnaround/sheet 파일 누락          → ASSET_GEN ★검수 게이트 (진입 시 레지스트리 시각 필드 완성)
storyboard.json 없음                                → STORYBOARD  (존재 = asset 검수 통과로 간주)
scenes/ 비었거나 storyboard.built.json에 FAIL 존재   → SCENE_IMG
{V}/audio.mp3 또는 {V}/subtitle.srt 없음            → TTS
  └ vrew 모드 세부: {P}/vrew/에 오디오+SRT 있음 → ingest 실행
                    vrew_script.txt만 있음 → 사용자 대기(게이트), 없음 → --export-script
{V}/storyboard.json 없음                            → SCENE_TIMING
{V}/veo_hook.json 없음                              → VEO_HOOK (자동, ⚠️유료 ~20크레딧 — 훅 8초 립싱크 클립)
{P}/output/capcut_draft.json 없음                   → RENDER (CapCut export — 성공 시 마커 자동 기록)
{P}/output/*.mp4 없음                               → 사용자 대기 게이트 (CapCut 마무리 편집 → output/에 mp4 내보내기)
{P}/output/upload_result.json 없음                  → UPLOAD
그 외                                               → DONE
```
asset 검수 게이트 있음 — ASSET_GEN 완료 후 **사용자 컨펌 대기**. contact sheet를 `open`으로 띄우고, OK 받기 전에는 STORYBOARD로 넘어가지 않는다.
**★병렬 트랙 (2026-07-19)**: TTS(vrew 낭독)는 SCENE_IMG와 독립이다 — 위 감지 순서는 "남은 것" 확인용일 뿐. vrew export는 **script.txt 확정 직후** 실행하고(TTS 절), 낭독 파일이 도착하면 SCENE_IMG 진행 중에도 ingest→split→SCENE_TIMING까지 먼저 처리한다. scenes 완료를 기다리는 건 RENDER뿐(VEO_HOOK도 씬1만 있으면 가능).

## 단계별 절차

### SCRIPT  (서브 상태머신, `{S}` = `{P}/_script`)
주력 = **장편 2.4~2.9만자 단일 대하 서사** (100~120분 — 시장 실측 정점, guide §4). 공식(playbook) = `prompts/script-guide.md` — **매 편 벤치마킹하지 않는다**, 공식 현재 버전을 그대로 적용. 단계별로 필요한 프롬프트만 로드(lazy-load):

| 단계 | 로드 |
|---|---|
| SCAN·CONCEPT·OUTLINE | script-guide.md |
| DRAFT | script-guide.md + script-constraints.md |
| REVIEW | script-constraints.md |
| (딥 벤치마킹 시에만) | benchmark-guide.md (+playbook-history.md) |

서브 상태 감지 (위→아래 첫 매칭):
```
watchlist.json 없거나 handle 미기입          → WATCHLIST ★대화: 추적 채널 @핸들 확정 (채널당 1회)
{P}/ 없음 (새 영상 요청)                     → SCAN: 최신 research/scan_*.md가 없거나 7일 경과면
                                              python3 scripts/research/scan_channels.py --channel {채널}
                                              ★URL 진입: 요청에 레퍼런스 영상 URL이 있으면 SCAN·소재 제안(①)
                                              생략 — 그 영상을 원전으로 바로 ②부터 (아래 CONCEPT 참조)
{S}/concept.md 없음                          → CONCEPT ★대화 3박자:
                                              ① 소재 제안 — 스캔 리포트에서 **최적 소재 1개**를 근거(조회수/일,
                                                클러스터 규모, guide §7 소재 배율 참고)와 함께 제안. topic_log.json 대조(최근 3편과 감정축·
                                                모티프·훅·악역·폭로 트리거·여운 장치 중복 회피, ✓참고됨 영상 재탕 금지)
                                                + **세이프티 스크리닝**(아래 "세이프티 가드레일" — 미성년 수난이
                                                중심 비트인 소재는 성인 각색안 동반, 불가하면 제외)
                                                → 사용자 승인(다른 소재 원하면 교체 제안)
                                              ② 원전 분석 — 프로젝트 생성(YYMMDD_HHMM) → **그 소재 대표 1편만 수집**
                                                (레퍼런스는 하나 — 이를 토대로 새 이야기를 각색하는 것이 목적).
                                                ★URL 진입 시: 사용자가 준 URL이 곧 원전 — 수집 후 topic_log
                                                중복 대조(①에서 못 했으므로 여기서)와 조회수/일 확인을 수행하고,
                                                답습 범위는 **소재·비트·훅 컨셉까지** — 구조 골격은 playbook,
                                                표면 디테일은 "원전 격리" 그대로(표절 방지 불변):
                                                python3 scripts/research/collect_refs.py --channel {채널} --project {프로젝트} URL
                                                → {P}/_refs/001/의 transcript·댓글 정독(에이전트 위임)으로 줄거리·
                                                정체(반전) 설계·감정 고점·인물·시청자 반응·모티프 파악 →
                                                **분석 보고서를 {P}/_refs/001/analysis.md로 저장**(대화에만 두면
                                                세션 종료 시 유실) → 원전과 뭘 다르게 갈지(차별화 각도)를 사용자와 논의.
                                                ※ 소재(무엇을) 분석만 — 구조·기법(어떻게)은 playbook 고정, 개정 루프 전용
                                              ③ 확정 — **확정 브리프를 제시**해 사용자가 근거를 보고 결정하게 한다
                                                (템플릿은 아래 "확정 브리프" 절) → OK 받으면 concept.md(브리프 수록)
                                                + topic_log.json에 항목 기록(감정축·모티프에 더해 **hook·villain·
                                                twist_trigger·ending_device** 필드 + 참고 영상 id)
                                                + **프로젝트 rename**: `{YYMMDD_HHMM}` → `{YYMMDD_HHMM}_{짧은제목}`
{S}/outline.md 없음                          → OUTLINE ★대화: 콜드 오픈 문안 + 장(章) 설계(8~11장 브리프,
                                              클리프행어 유형, 중반 재점화 위치) + 복선 장부 표
                                              + **characters.json/locations.json 초안 생성** (서사 필드만 —
                                              아래 "레지스트리 생애주기") + **원전 diff 체크** (아래 "원전 격리")
{S}/chapters/ 미완 (outline 장 수 대비)      → DRAFT: 2~3장 배치 순차 집필(병렬 금지, 집필 에이전트 위임) +
                                              {S}/bible.md 갱신(+**레지스트리 동기화** — 새 인물·variants·설정 변경
                                              즉시 반영) + validate_script.py --chapter-target 2500,3500
                                              + **배치마다 줄거리·감정선 요약을 사용자에게 보고 → 피드백 반영 후 다음 배치**
{P}/script.txt 없음                          → REVIEW: 장 병합 → validate_script.py --target 24000,29000 위반 0 →
                                              체크리스트(연속성·복선 회수·미끼 회수·**등장인물↔레지스트리 전수 대조**)
                                              → script.txt + meta.txt → **즉시 vrew export**(★병렬화 — TTS 절)
```
- **확정 브리프** (CONCEPT ③ — concept.md를 쓰기 전에 사용자에게 제시하는 결정 패키지. "사용자가 무엇을 보고 확정하나"의 답):
  1. **제목·썸네일 후보 2~3안** — 시청자 입구 검증이 최우선. 제목이 안 뽑히는 컨셉은 여기서 접는다.
  2. **시장 근거** — 원전 조회수/일 + 클러스터 규모(같은 소재 상위권 편수).
  3. **로그라인 한 문단** — 이야기가 한 호흡에 성립하는지.
  4. **★구조 비교표 (원전 vs 우리)** — playbook(script-guide §1) 골격 비트별 3칸 표 `비트 | 원전 | 우리`:
     콜드 오픈(충격 장면 후보 문안) / 결핍 / 사건·결단 / 조력자+떡밥 / 갈등 계단 / 최저점 / 재기·복선 회수 /
     대반전(트리거·정체 폭로 타이밍, 황금률 준수 확인) / 다중 해소+주제문 후보.
     **어디를 검증된 공식대로 가고, 어디서 원전과 갈라져 우리 이야기가 되는지가 한눈에 보여야 한다.**
     비트당 1~2줄 스케치까지만 — 장 설계 상세는 OUTLINE 몫. 시각 소품 복선(→anchorProp 후보) 1개 이상 포함.
  5. **감정 설계 + 중복 회피** — 감정축(guide §0에서 1개) + topic_log 최근 3편 대조 결과 명시.
  6. **리스크와 대응** — 개연성 구멍, 시청층 거부감 가능성, 기존 편과의 유사 지점,
     **이미지 세이프티 리스크**(미성년 수난 장면 유무 + 각색·연출 우회 방안 — 아래 "세이프티 가드레일").
  합의된 구조 비교표의 "우리" 칸이 OUTLINE 장 설계의 씨앗이 된다.
- **원전 격리 (표절 방지)** — 원전 자료(`_refs/`의 transcript·analysis.md)는 **CONCEPT·OUTLINE까지만** 참조한다. DRAFT 집필 에이전트 입력에 절대 포함 금지 — 구조(비트)는 outline을 통해 물려받되, 표면 디테일은 전부 새로 짓는다. OUTLINE 완료 전 **원전 diff 체크**를 수행해 outline.md에 기록: ① 인물명·지명 ② 핵심 소품(증표·유품) ③ 직접 인용 대사 ④ 장면 연출 디테일이 원전과 겹침 0인지 대조. 모티프 수준(예: "유품 속 증거")의 공유는 허용, 구현물(노리개→노리개)은 금지.
- **★세이프티 가드레일 (이미지 차단 예방 — 스토리 방향을 잡는 시점에 반영)** — Google 이미지 세이프티가 **미성년자 얼굴 클로즈업 + 고통/눈물** 조합을 차단한다(2026-07-19 flow 실측). 대본이 굳은 뒤엔 방향을 못 바꾸므로 상류에서 미리 설계한다:
  - **CONCEPT(주 방어선)**: 미성년자의 학대·수난이 서사의 **중심 비트**인 소재(민며느리 학대, 아이 팔려감 등)는 **수난 당사자의 나이를 성인으로 각색**(15살 며느리 → 갓 스물 며느리)할 수 있을 때만 채택. 각색하면 이야기가 성립하지 않는 소재는 교체 제안. 확정 브리프 6번(리스크)에 판정 결과를 명시.
  - **OUTLINE(레지스트리 초안)**: 고통·학대·죽음을 **당하는** 인물의 age는 성인으로 설정. 아이 캐릭터 자체는 허용 — 단 역할을 정서적 배경(웃는 마을 아이들, 품에 안긴 아기)으로 한정하고 수난의 당사자로 두지 않는다.
  - **STORYBOARD(안전망)**: 그래도 아이가 힘든 장면에 걸리면 visual_desc에서 **아이 얼굴 클로즈업 금지** — 원경·뒷모습·어른의 반응 샷(지켜보는 어미의 일그러진 얼굴)으로 감정을 전달. 직접 묘사보다 반응 샷이 연출로도 여운이 깊다.
- **레지스트리 생애주기 (characters.json/locations.json — 별도 추출 단계 없음)**: ① **OUTLINE에서 태어난다** — 서사 필드만 채운 초안(id, name, type, 역할, physical.age·build 개요, 결핍 메모, anchorProp 후보(시각 소품 복선과 연결); locations는 재등장 장소 desc). outline.md에 인물 표를 중복 작성하지 않고 "레지스트리 참조" 한 줄만. ② **DRAFT 내내 살아있다** — 집필 중 새 인물·나이/상태 변화(variants)·설정 변경은 bible 갱신 때 레지스트리에 즉시 반영. ③ **REVIEW에서 전수 대조** — 최종 대본 등장인물↔레지스트리 일치 확인. ④ **시각 필드(영문 lock·negatives·physical 세분화)는 ASSET_GEN 진입 시 완성** — 인물이 굳기 전에 쓰면 재작성 낭비.
- 단편(1만자 이하)을 요청받으면: SCAN·CONCEPT는 동일, OUTLINE·DRAFT는 chapters 없이 바로 집필 (guide §4 스케일 조절).
- **딥 벤치마킹은 편당 단계가 아니다** — 신규 채널 발견/성과 부진/5~10편마다, 사용자 요청 시 benchmark-guide.md 로드. 산출물은 공식 개정 제안(proposal)이며 사용자 승인 시에만 script-guide.md 개정.

### 레지스트리 시각 필드 완성 (ASSET_GEN 진입 시 수행 — 구 ASSET_EXTRACT)
- OUTLINE이 만들고 DRAFT가 갱신한 레지스트리("레지스트리 생애주기")에 **시각 필드를 채워 완성**한다. script.txt로 등장인물·재등장 장소를 교차 확인. (레지스트리 자체가 없는 구프로젝트만 대본에서 직접 추출.)
- `{P}/characters.json` 완성 — id별 `{name, type, physical{age,build,hair,eyes,uniqueFeatures}, negatives, lock, turnaround, anchorProp}`.
  - **build(키/체형/연령) 필드 필수** (없으면 전부 성인으로 드리프트).
  - **식별 앵커 필수** — 인물마다 한눈에 알아볼 특징 **하나**를 `anchorProp`에 쓰고 **lock 문장에도 넣는다** (turnaround.py가 턴어라운드에, build.py가 씬에 전파). 고르는 법:
    - 4개 축에서 고른다: ① **실루엣**(체형·자세 — 굽은 허리, 장신, 아이) ② **착용 소품**(입거나 매는 것 — 들고 다니는 물건은 씬에서 빠지기 쉬움) ③ **시그니처 색**(저고리/치마 인물당 고유색 1개) ④ **크고 단순한 머리·얼굴 특징**(백발, 민머리, 큰 흉터, 안대 — 미세한 얼굴 특징은 드리프트해서 못 씀).
    - **캐스트 안에서 축·색이 겹치지 않게** 배분한다 (두 명이 다 "붉은 계열" 금지, 다 "모자" 금지). 후면·원거리 씬에서도 보이는 것 우선 — 4뷰 전부에서 보여야 진짜 앵커다.
    - 색은 hex 말고 말로 (예: "faded indigo-dyed jeogori", "a red silk cord tied on the ankle").
  - 같은 인물의 나이/상태 변화 = `variants:{<v>:{physical,lock,turnaround}}` + `default_variant`.
  - 변신/환생 = 별도 id + `reincarnatesTo`/`reincarnationOf` + 공유 `anchorProp`(distinctive prop이 얼굴보다 강한 앵커).
  - `lock` = build.py가 씬 {id}에 치환할 자연어 trait-lock 문장.
- `{P}/locations.json` 작성 — **재등장 장소만** `{desc, sheet}`. 1회성 배경은 넣지 않음(씬 텍스트로 충분).

### ASSET_GEN  (★사용자 검수 게이트 — OK 받기 전 진행 금지)
```
python3 scripts/assets/turnaround.py {P}     # 인물 턴어라운드(흰배경 4뷰)
python3 scripts/assets/background.py {P}      # 재등장 장소 시트
# contact sheet 생성 + 화면에 띄우기 (macOS Preview)
python3 scripts/render/contact_sheet.py --dir {P}/assets/characters   # → {P}/assets/characters/_contact_sheet.png
python3 scripts/render/contact_sheet.py --dir {P}/assets/locations    # 배경 있으면
open {P}/assets/characters/_contact_sheet.png {P}/assets/locations/_contact_sheet.png
```
- **생성 직후 반드시 contact sheet를 만들고 `open`으로 창을 띄운다** — 사용자가 파일 경로를 찾을 필요 없이 바로 눈으로 검수하게. (open은 macOS 전용; 실패 시 경로를 안내)
- 그런 다음 **여기서 멈추고 사용자에게 "캐릭터 일관성 확인하고 OK 주세요"라고 요청한 뒤 대기**한다. 캐릭터 일관성(연령·체형·문화 앵커·식별 앵커)을 확인하는 자리 — 여기서 틀어지면 이후 씬 이미지 수백 장이 전부 어긋난다.
- **사용자가 명시적으로 OK/컨펌 한 뒤에만 STORYBOARD로 진행**. 그 전에는 storyboard.json을 만들지 않는다.
- 드리프트(연령/체형/문화)를 지적하면 characters.json의 `build`/`negatives`/`anchorProp` 또는 style.json 앵커를 고쳐 `--force` 재생성 → contact sheet 다시 띄워 재확인 → 다시 OK 대기.

### STORYBOARD
- 대본을 씬 분할 → `{P}/storyboard.json` 작성.
- **씬 분할 = 서사 비트 기준, 지속시간 기준 아님**. 씬 경계는 화면이 바뀌어야 할 순간에만 둔다: 인물 등장/퇴장, 장소·시간 전환, 사건·정서 전환. 씬 길이 불균등은 정상(5초~40초 자유) — 이미지 지속시간을 비슷하게 맞추려고 비트 중간을 자르지 말 것.
- **★훅·절정은 이미지 밀도를 높인다** (autoworker-youtube 벤치마킹). 훅(첫 막)·재점화·절정 구간은 **문장 1~2개당 한 씬**으로 촘촘히 쪼갠다 — 초반 이탈 방지의 핵심. **씬1은 썸네일급**(가장 강한 시각, 익스트림 구도: 클로즈업·부감·더치앵글). **씬1 = Veo 대사 클립 전제 구도** — 대본 첫 문장의 화자 1인이 화면 중심에 얼굴·입이 보이게(미디엄~클로즈업, 옆모습 금지). 이 이미지를 시작 프레임으로 한 립싱크 클립 생성·주입은 **VEO_HOOK 단계가 자동 수행**(유료 20크레딧/8초 — 훅 전용). 반대로 배경 설명·잔잔한 전개는 3~5문장을 한 씬으로 묶어도 된다. (교훈: 소금장수 씬1이 문장 6개·30초로 훅인데도 가장 길었다 — 정반대. 훅일수록 짧고 강하게.)
- **문장 귀속 원칙** — 각 문장을 "이 문장이 들릴 때 화면에 뭐가 보여야 하나"로 씬에 귀속한다:
  - 새 인물 소개 문장("그 장터를 쥐고 흔드는 이가 있었으니, 박행수였다")은 **그 인물이 보이는 씬의 첫 문장** — 앞 씬의 꼬리로 붙이지 않는다.
  - 전환·시간경과 문장("그러던 어느 봄날이었습니다")은 **다음 씬의 머리**.
  - 같은 행동의 연속 묘사(지게 지고 → 고개 넘고 → 짚신 닳고 → 산을 오르고)는 한 씬으로 묶는다 — 이미지 하나가 다 커버.
  - **문장 단위 충돌 시 대사 앵커 우선** — sentences.json의 문장 단위는 대사와 다음 서술을 한 덩어리로 묶기도 한다(`"고맙습니다, 행수 어른." 그러던 어느 봄날이었습니다.`). 덩어리가 두 씬에 걸치면 **대사가 일어나는 씬**에 통째로 귀속 — 전환 서술이 앞 씬 이미지 위에 얹히는 건 자연스럽지만, 대사가 엉뚱한 화면 위에서 들리면 확 튄다.
- 씬: `{id, act, narration, cast[], location, visual_desc, sentences[]}`.
  - `sentences`: `[첫,끝]` 0-based 문장 index — 이 씬이 덮는 나레이션 문장 범위. **STORYBOARD에서 narration을 나눌 때 함께 확정** (서사 순서대로 전체 문장 빠짐없이, 겹침 없이 커버). SCENE_TIMING이 이걸 자막 큐로 변환한다.
  - `cast`: `"id"` 또는 `"id:variant"` (그 씬 등장 인물만 — 전부 넣지 말 것).
  - `location`: locations.json 키 또는 null.
  - `visual_desc`: 영문 장면 묘사, 인물 자리에 `{id}` placeholder (build.py가 lock으로 치환).
  - **stock_query/stock_eligible/emphasis 필드는 쓰지 않는다** (생성형 100% 전제).
- **세이프티**: 아동 인물의 고통·눈물·얼굴 클로즈업 visual_desc 금지 (SCRIPT 절 "세이프티 가드레일" 안전망 — 원경·뒷모습·어른 반응 샷으로 대체).
- **★청킹 필수 (분량 무관) — 스토리보드는 항상 장 단위로 위임·병합한다.** 한 에이전트에 전체를 맡기면 대용량 단일 Write에서 스톨한다(2026-07-15 9천자 테스트에서도 2회 재현). 대본이 `{S}/chapters/`로 나뉘어 있으니 그 경계를 그대로 쓰고, **장별 에이전트는 병렬 가능**(집필과 달리 연속성 제약 없음 — 씬 id는 청크 로컬 1부터, PD가 병합 시 전역 재부여).
- **narration 필드는 에이전트 산출에서 제외한다** — 씬의 `sentences` 범위만 받고, PD가 `{V}/script_sentences.json`(init_sentences.py 산출, 전 단계에서 미리 생성)에서 프로그램으로 주입. 문장 원문 복사가 없어져 출력이 ~1/4로 줄고 문장-씬 정합이 기계적으로 보장된다.
  - **위임(장 하나 = 청크 하나)**: PD가 각 장을 서브에이전트에 맡긴다. 청크당 넘기는 계약 — ① 그 장의 script 텍스트 ② characters.json 전체(등장 가능한 id·variant·lock 레지스트리 — 새 인물 발명 금지) ③ locations.json 키 목록 ④ **그 장의 전역 문장 시작 index**(sentences를 전역 번호로 authored) ⑤ **시작 씬 id**.
  - **큰 입력은 프롬프트에 붙여넣지 말고 파일 경로로 준다** (autoworker-youtube split 교훈) — 장 텍스트는 `{S}/chapters/NN.md`, 레지스트리는 `{P}/characters.json` 경로만 주고 서브에이전트가 Read 하게. 청크 산출도 `{P}/_chunks/storyboard_NN.json`로 **파일에 쓰게** 하고 PD는 경로만 회수(컨텍스트 절약).
  - **반환**: 그 장의 `scenes[]`(파일) — 씬 id 연속, `sentences`는 전역 문장 index, cast는 레지스트리 id만.
  - **PD 병합·검증** (`merge_storyboard.py`, 없으면 수동): 전체 concat 후 ① 씬 id 1..N 연속 ② `sentences` 0..끝 빠짐없이·겹침없이 커버 ③ cast id 전부 characters.json 존재 ④ location 키 유효. 위반한 장만 재위임.
  - 문장 번호 기준은 `script.txt`의 문장 분할 순서 = 나중 `sentences.json` 순서(같은 대본·같은 순서). TTS 후 문장 수가 어긋나면 SCENE_TIMING **경계 검수 리포트**로 잡아 해당 구간만 sentences 보정.

### SCENE_IMG
```
python3 scripts/storyboard/build.py {P}                 # 전체
python3 scripts/storyboard/build.py {P} --only 3,7,12   # 일부 재생성
python3 scripts/storyboard/build.py {P} --dry-run       # 프롬프트/ref 점검(무료)
```
- refs = cast turnaround(순서대로) + location.sheet(존재 시), style.max_refs로 캡(cast 우선).
- **★씬1 우선 생성·검수**: 배치 첫 실행은 `build.py {P} --only 1` — 씬1은 VEO_HOOK 시작 프레임이라 품질 의존이 크다(유료 클립이 이 한 장에 달림). 화자 정면·입 보임(미디엄~클로즈업, 옆모습 금지)인지 확인하고, 어긋나면 visual_desc를 고쳐 재생성한 뒤 나머지 배치를 시작한다. 씬1은 결과 보고에 **단독 첨부**.
- 결과 `storyboard.built.json` 확인, FAIL 씬만 `--only`로 재시도. contact sheet로 검수.
- **★장편 이미지 배치는 여러 날에 걸친다** (씬마다 고유 이미지 전제). 무료 flow = **계정당 하루 ~15장**, 3계정 병렬이면 ~45장/일 → 300+씬은 8일+. `build.py`는 `storyboard.built.json`의 status로 **완료분을 건너뛰고 이어서** 생성(체크포인트) — 매일 돌리면 됨. 스루풋을 올리려면 flow 레인(계정) 추가(`settings.json image.flow.ports`). 하루 안에 끝내야 하면 그 프로젝트만 `image.engine="gemini"`로 명시(유료, 일일 한도 없음).

### TTS  (`{V}` = `{P}/_video`)
**엔진 선택**: `settings.json tts.engine` — `"vrew"`(반수동, 무료) 또는 `"elevenlabs"`(자동, 유료).

**A) vrew 모드 (반수동, 표준)** — 사용자가 Vrew에서 만든 음성(mp3)+자막(srt)을 `{P}/vrew/`에 넣어 주면 이후는 전부 자동.
- **★병렬화 — export는 REVIEW 직후 즉시 (SCENE_IMG를 기다리지 않는다)**: script.txt가 확정되면 ASSET_GEN으로 넘어가기 **전에** `--export-script`를 실행하고 사용자에게 낭독을 요청한다. 사람 낭독과 자동 제작(asset→storyboard→씬 이미지 며칠)이 겹쳐 리드타임이 ~이틀 준다. 이후 SCENE_IMG 일일 배치를 돌릴 때마다 `{P}/vrew/` 도착 여부를 확인하고, 도착했으면 그 세션에서 ingest→split_long_cues→SCENE_TIMING(씬1이 이미 있으면 VEO_HOOK까지)을 바로 진행한다. **단일 나레이션 정책: 대사 포함 전체를 나레이터 한 명이 낭독** (캐릭터별 보이스 분리 없음). 대본 원천은 `script.txt`.
```
python3 scripts/tts/ingest_vrew.py {P} --export-script --config {CFG}  # → {P}/vrew/vrew_script.txt (+1만자 초과 시 vrew_script_partNN.txt 자동 분할)
# ★사용자 게이트: Vrew에 붙여넣기→나레이터 보이스 선택→음성(mp3/wav)+자막(srt)을 {P}/vrew/에 저장할 때까지 대기
python3 scripts/tts/ingest_vrew.py {P} --config {CFG}      # → {V}/audio.mp3, subtitle.srt, sentences.json (멀티 파트 자동 병합)
python3 scripts/tts/split_long_cues.py {P} --config {CFG} --apply   # ★기본 실행: 문장 경계 스냅 + 20자 초과 큐 분할
```
- **★장편은 Vrew 붙여넣기 한도(1만자)를 넘는다** — `--export-script`가 한도(`tts.vrew_paste_limit`, 기본 9,800자·공백 포함) 초과 시 **문단 경계에서 `vrew_script_partNN.txt`로 자동 분할**. 사용자는 파트마다 별도 Vrew 프로젝트로 낭독(**반드시 같은 보이스·같은 속도**)하고, 내보내기 파일명에 파트 번호를 붙여 `{P}/vrew/`에 저장(`narration_01.mp3`+`narration_01.srt`, `narration_02.…` — 이름순 정렬이 곧 파트 순서). ingest가 짝지어 **오디오를 WAV 샘플 정확도로 병합**하고 SRT는 파트별 프레임 스냅 후 오프셋 이어붙임(실측 오차 ≤1프레임). 2.4~2.9만자 = 파트 3개 안팎.
- 상태 감지: `{P}/vrew/`에 오디오+SRT 있으면 ingest 실행(오디오·SRT 쌍 수가 다르면 에러 — 파트 누락 안내), 없으면 대본 내보내고 사용자에게 요청 (클립보드 복사: 단일 `pbcopy < {P}/vrew/vrew_script.txt`, 파트별 `pbcopy < {P}/vrew/vrew_script_part01.txt` 순서대로).
- 주의: Vrew에서 클립 분할·병합·표기 수정은 자유(split_long_cues가 흡수), **문장 삭제/신규 작성은 금지**(storyboard sentences 범위가 밀림 — 삭제 문장은 경고 후 이웃 보정되지만 씬 싱크 품질이 떨어진다). 완료 후 SCENE_TIMING으로.
- **자막 정형화(split_long_cues)는 vrew 모드 필수 단계** — 두 패스: ① **문장 경계 스냅**: 큐 하나가 대본 문장 경계를 걸치면(Vrew가 짧은 문장들을 한 클립에 합친 경우 등) 그 경계에서 큐를 분할 — 씬 경계가 항상 큐 경계와 일치하게 만드는 안전망. Vrew는 자막에서 마침표를 지우므로 경계는 대본↔자막 비공백 글자 정렬로 찾는다(표기 축약도 difflib로 흡수). ② **길이 분할**: max_chars(20자) 초과 큐를 어절·구두점(쉼표 우선) 경계에서 분할. 타이밍은 두 패스 모두 whisper medium 단어 실측(오디오당 1회, `{V}/whisper/`에 캐시, 수 분 소요) — Vrew 나레이션은 쉼표 호흡이 길어 비례 분배 대비 중앙값 300ms를 고쳐준다. whisper가 없거나 큐 인식 불량이면 음절 비례 자동 폴백이라 저사양 머신(프리랜서)도 그대로 동작(`--no-whisper`로 강제 가능). **`--apply`가 sentences.json에 문장별 실측 `cue_range`/`start`/`end`를 기록** → SCENE_TIMING이 비례 추정 대신 이 실측 매핑을 쓴다(정밀 모드). **반드시 SCENE_TIMING 전에 실행**. 검수만 하려면 `--apply` 빼고 실행 → `{V}/subtitle.split.srt`+`split_report.json`(sentence_snap/long_split 구분), A/B 비교는 `capcut_export.py --compare-srt`.

**B) elevenlabs 모드 (자동)** — 단일 보이스(`tts.voice_id`) 전용. 순수 한글 산문이면 tts_map 변환 생략 가능(script를 tts_script로 그대로). 아라비아 숫자/영어가 있으면 extract_tts_targets→tts-converter→apply_tts_map.
```
.venv/bin/python scripts/tts/init_sentences.py {P}/script.txt -o {V}/script_sentences.json
cp {P}/script.txt {V}/tts_script.txt            # (숫자/영어 없을 때)
.venv/bin/python scripts/tts/generate_tts.py {V}/tts_script.txt {V} --config {CFG}     # → audio_raw.mp3, alignment.json
echo '{"conversions":[]}' > {V}/tts_map.json
.venv/bin/python scripts/tts/analyze_sentences.py {V}/alignment.json --script-sentences {V}/script_sentences.json --tts-map {V}/tts_map.json -o {V}/sentences.json --config {CFG}
.venv/bin/python scripts/tts/split_sentences.py {V}/sentences.json -o {V}/split.json
.venv/bin/python scripts/tts/create_srt.py {V}/sentences.json -o {V}/subtitle_raw.srt --split-data {V}/split.json
.venv/bin/python scripts/tts/remove_silence.py {V}/audio_raw.mp3 {V}/subtitle_raw.srt {V}/audio.mp3 {V}/subtitle_trimmed.srt --config {CFG}
.venv/bin/python scripts/tts/align_to_frames.py {V}/subtitle_trimmed.srt {V}/subtitle.srt --config {CFG}
```

### SCENE_TIMING  ★내러티브 전용
스토리보드를 오디오보다 먼저 만들기 때문에, TTS 후 각 씬을 자막 타임라인에 매핑해야 한다.
- `sentences`는 STORYBOARD에서 이미 authored (없는 씬이 있으면 여기서 채운다 — 문장 귀속 원칙 동일).
- 문장→큐 매핑 2단계: **정밀 모드**(vrew 모드 표준 — split_long_cues --apply가 기록한 실측 cue_range, `[문장→큐 매핑] 정밀 모드` 출력 확인) / **비례 모드**(폴백 — 실측 없거나 cue_count 불일치 시 글자 수 비례 추정). vrew 모드에서 비례 폴백 경고가 뜨면 split_long_cues --apply부터 다시.
- 참고용 문장→큐 맵: `scripts/render/scene_timing.py {P} --emit-sentence-map` → `{V}/sentence_cue_map.json`.
- 렌더용 storyboard 생성: `scripts/render/scene_timing.py {P}` → `{V}/storyboard.json` (씬별 subtitle_range).
- **★경계 검수 필수**: 스크립트가 출력하는 씬별 `첫 큐 … 끝 큐` 텍스트 리포트를 읽고 — 씬의 첫 큐가 그 씬 narration의 첫 문장과 같은 내용인지 확인. 어긋난 씬은 `sentences`를 고쳐 재실행. **균등분배 폴백 경고가 뜨면 진행 금지** (sentences부터 채울 것) — 폴백은 씬 경계를 서사와 무관하게 자르므로 이미지가 문장 중간에 바뀐다.

### VEO_HOOK  ★훅 인트로 립싱크 클립 (자동, ⚠️유료)
씬1 이미지를 시작 프레임으로 Veo i2v 8초 립싱크 클립(네이티브 오디오 — 대사 포함)을 만들어 렌더 storyboard 씬1에 `video_path`로 주입한다. **완전 자동 — confirm 없이 실행**(사용자 지시 2026-07-19).
엔진(`settings.json image.veo.engine`): **`gemini`(기본, 2026-07-19 실측 검증)** = Gemini API `veo-3.1-fast-generate-preview` 1080p/8초, `.env` GEMINI_API_KEY만 있으면 됨(데몬·Chrome 불필요) / `flow` = labs.google 웹세션(~20크레딧, `image.veo.flow.ports` 레인 데몬+Chrome 필요).
```
python3 scripts/render/veo_hook.py {P}                 # 프롬프트 생성→Veo 생성→video_path 주입
python3 scripts/render/veo_hook.py {P} --prompt-only   # 무료: 프롬프트·매니페스트 파일만
```
- 훅 대사는 script.txt 첫 따옴표 대사에서 자동 추출(playbook "대사 선행" 전제), 프롬프트는 씬1 visual_desc 기반 템플릿으로 `{V}/veo_hook_prompt.txt` 생성. **이미 있으면 그대로 쓴다** — PD가 파일을 다듬은 뒤 재실행하는 워크플로우 지원.
- **실패해도 진행을 막지 않는다** — `{V}/veo_hook.json` 매니페스트(시작 프레임·프롬프트·수동 실행 커맨드)가 항상 남으므로, 크레딧 소진/데몬 부재 시 결과 보고에 매니페스트 경로와 수동 커맨드를 첨부하고 RENDER로 진행(씬1은 스틸 폴백). 사람이 나중에 클립을 만들어 `{V}/`에 두고 재실행하면 주입만 수행.
- 재실행 안전: mp4가 이미 있으면 생성 건너뛰고 주입만(크레딧 재소모 없음). 새로 뽑으려면 `--force`.

### RENDER  ★CapCut export 전용 (자동 렌더 없음)
**CapCut 드래프트로 넘겨 마무리 편집을 사람이 한다.** 파이프라인은 mp4를 직접 만들지 않는다.
```
python3 scripts/render/capcut_export.py {V} --name {프로젝트} --config {CFG}
```
- `{V}`의 audio.mp3+subtitle.srt+storyboard.json(scene_timing 산출) → `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/{프로젝트}/` 에 draft 생성(root_meta 갱신) → **CapCut 열면 바로 뜸**(실행 중이면 재시작). 성공 시 `{P}/output/capcut_draft.json` 마커 자동 기록.
- **이후는 사용자 대기 게이트**: 사람이 CapCut에서 마무리 편집 → `{P}/output/`에 mp4 내보내기(파일명 자유, upload.py가 output/의 mp4를 집는다) → UPLOAD 진행 가능.
- 파이썬 규칙: **elevenlabs TTS 체인(generate_tts·analyze·remove_silence 등)과 업로드는 `.venv/bin/python`**(dotenv·numpy·requests·google-api 필요). asset/vrew/scene_timing/render는 표준 `python3`로 충분(ffmpeg만 외부 의존).

**UPLOAD** (자체 스크립트 `scripts/upload/`, 비공개 업로드):
```
# 최초 1회 (채널당): client_secret.json을 channels/{채널}/config/youtube-api/에 두고
.venv/bin/python scripts/upload/auth.py --channel {채널}          # 브라우저 OAuth → token.json
# 매 업로드: PD가 meta.txt 확인(제목/설명/태그 자동 추출됨. 다듬을 게 있으면 output/youtube.md 작성이 우선)
.venv/bin/python scripts/upload/upload.py --project {프로젝트} --channel {채널}   # → output/upload_result.json
```
- 메타 우선순위: CLI 인자 > `output/youtube.md`(`## 제목/## 설명글/## 태그/## 고정 댓글`) > `{P}/meta.txt`(규약은 script-guide.md).
- 썸네일: `output/thumbnails/`에 png/jpg 있으면 자동 첨부(2MB 초과 시 자동 압축).

## 검증된 교훈 (반드시 지킬 것)
- 캐릭터 일관성 3종: **턴어라운드 ref + trait-lock(build 포함) + 씬별 cast**.
- **문화·시대 앵커는 style.json preset에 박는다** — ref 없는 씬(군중·빈 배경)의 유일한 방어선. `"Ghibli/anime"` 금지 → `"Korean webtoon/manhwa"`.
- 동물·신령 등 비인간 인물은 **착용 소품 앵커**로 (발목에 맨 색 끈, 목에 건 방울 등 — 얼굴 잠금이 약해서 소품이 더 강하다). ref는 한 씬 최대 ~5장.
- **미성년자 얼굴 클로즈업+고통/눈물은 세이프티 차단** (2026-07-19 실측) — 수난 당사자는 CONCEPT에서 성인으로 각색, 아이 장면은 STORYBOARD에서 반응 샷 우회. 상세는 SCRIPT 절 "세이프티 가드레일".
