# Flow 무료 이미지 생성 (labs.google 웹세션)

Gemini 유료 API 대신 **labs.google Flow** 웹세션(구글 로그인)으로 이미지를 **무료** 생성한다.
**Nano Banana(NARWHAL) + 다중 참조 이미지(캐릭터 일관성) + 2K 업스케일**이 기본이다.

> 모델 기본값이 banana인 이유(A/B 실측 2026-07, 빈밥상 씬 6·22 동일 프롬프트·시드):
> ① 캐릭터 일관성이 banana-pro(GEM_PIX_2)와 동급(식별 앵커·트레잇 락 모두 유지),
> ② banana-pro는 일일 쿼터가 ~15장 수준으로 빡빡한 반면 banana는 훨씬 느슨(~100장대),
> ③ banana-pro도 원본은 1376×768로 나옴 — 2K는 어차피 `upsampleImage` 업스케일로 확보(모델 무관).

> 원리: Flow 웹앱은 내부적으로 `aisandbox-pa.googleapis.com`를 OAuth 세션 토큰으로 호출한다.
> 그 토큰과 요청마다 필요한 reCAPTCHA 토큰을 **Chrome 확장 + 상주 데몬**이 브리지한다.
> API 키 불필요. 구현은 `liorium/flow-proxy`(MIT)의 wire 계약을 Python으로 재구현.

## ⚠️ 먼저 — 버너(별도) 구글 계정을 쓸 것

문서화되지 않은 내부 API 사용은 구글 ToS 회색지대이고, 위반 시 계정 정지 권한이 명시돼 있다.
**메인 계정 말고 전용 버너 계정**으로 로그인해서 쓴다. 정지돼도 본계정·Gmail·유튜브는 안전.

## 구성요소

| 파일 | 역할 |
|---|---|
| `scripts/image/flow_token_server.py` | 상주 데몬(:3847). 토큰 저장/리프레시 + reCAPTCHA 중개 |
| `scripts/image/flow_extension/` | Chrome 확장(MV3). 로그인 토큰 캡처 + reCAPTCHA 실행 |
| `scripts/image/flow_client.py` | 업로드→생성→저장 클라이언트 |
| `scripts/image/generate_image.py` | 엔진 디스패처(`settings.json image.engine`로 flow/gemini 분기) |

토큰은 `~/.flow-proxy/token.json`, 업로드 캐시는 `~/.flow-proxy/uploads.json`.

## 최초 설정 (1회)

1. **Chrome 확장 로드**
   - `chrome://extensions` → 우상단 **개발자 모드** 켜기 → **압축해제된 확장 프로그램을 로드** →
     `scripts/image/flow_extension/` 폴더 선택.

2. **버너 계정으로 Flow 로그인**
   - `https://labs.google/fx/tools/flow` 열고 버너 구글 계정으로 로그인.
   - 아무 프로젝트나 하나 열어 URL의 UUID를 기억: `.../flow/project/<이-UUID가-projectId>`

3. **데몬 실행 (배치 도는 동안 켜둠)**
   ```bash
   python3 scripts/image/flow_token_server.py
   ```

4. **확장에서 Connect**
   - Flow 탭이 열린 상태에서 확장 아이콘 클릭 → **Connect**.
   - 데몬 로그에 연결됨 표시. 세션쿠키로 **~30일 자동 리프레시**.

5. **projectId 저장 (최초 1회)**
   - 확장 Connect 시 함께 저장되지만, 안 되면 수동으로:
   ```bash
   curl -X POST localhost:3847/set-project -d '{"projectId":"<위에서-복사한-UUID>"}'
   ```

## 사용 (평소 워크플로우)

`settings.json`에 `image.engine: "flow"`가 이미 기본값이라, **평소처럼 파이프라인만 돌리면** 무료로 나간다:

```bash
python3 scripts/assets/turnaround.py <project_dir>      # 턴어라운드
python3 scripts/assets/background.py <project_dir>      # 배경 시트
python3 scripts/storyboard/build.py <project_dir>       # 씬 이미지
```

조건: **① 데몬 상주 + ② Chrome에 Flow 탭 로그인 상태로 열려 있음**. (Vrew 반수동과 같은 결)

### 상태 확인
```bash
curl -s localhost:3847/status      # {"connected": true, ...} 면 준비됨
```

### 엔진 전환
- 무료(기본): `settings.json` → `image.engine: "flow"`
- 유료 폴백: `image.engine: "gemini"` (또는 일회성으로 `IMAGE_ENGINE=gemini …` / `--engine gemini`)

### 모델·업스케일 설정 (`settings.json image.flow`)
- `model`: `banana`(기본, NARWHAL) | `banana-pro`(GEM_PIX_2, 쿼터 빡빡) | `imagen4`
- `upscale`: `"2K"`(기본) | `"4K"` | `""`(끄기) — 생성 직후 `upsampleImage`로 업스케일, **실패 시 원본(1376×768) 저장으로 폴백** (배치가 죽지 않음). 업스케일 1회당 reCAPTCHA 토큰 1개를 추가 소모.

## 단독 호출 (디버그)
```bash
echo "a red apple on white" > /tmp/p.txt
python3 scripts/image/flow_client.py /tmp/p.txt /tmp/out.png ref1.png ref2.png --model banana --ratio 16:9 --upscale 2K
```

## 트러블슈팅

| 증상 | 원인/조치 |
|---|---|
| `토큰 데몬(:3847)에 연결 실패` | 데몬 미실행 → `flow_token_server.py` 먼저 실행 |
| `reCAPTCHA timeout` | Chrome에 Flow 탭이 닫혔거나 미로그인/확장 미로드 → 탭 열고 Connect |
| `session cookie expired` | 확장에서 **Reconnect** |
| `projectId 미설정` | 위 5번 `/set-project` |
| `HTTP 403/408/429/5xx` | 레이트리밋/일시 오류 — 클라이언트가 상태코드별 대기 후 재시도(403→30s, 429→120s). 지속되면 일일 쿼터 소진 의심 |
| `HTTP 401` | 세션 만료 — 재시도 안 함. 확장에서 **Reconnect** |
| `업스케일 실패, 원본 저장` | upsampleImage 일시 오류 — 원본(1376×768)으로 폴백됨. 해당 씬만 나중에 재생성 |
| 캐릭터 일관성 저하 | `model`이 `banana`/`banana-pro`인지 확인(Imagen은 약함) |

## 한계

- **완전 무인(cron) 불가**: reCAPTCHA 때문에 Chrome 탭이 살아있어야 함. 반수동.
- **비공식/ToS 회색지대**: 내부 API 스키마가 바뀌면 깨질 수 있음. 그때는 `gemini`로 즉시 폴백.
- 다중 참조(imageInputs 배열)는 flow-proxy 원본(단일 ref)보다 확장한 것 — Flow의 "ingredients" 다중 참조에 기댄다.
