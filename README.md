# 아파트 시세 대시보드

관심 단지들의 **네이버 부동산 매매 호가**와 **국토부 실거래가**를 모아
휴대폰으로 보는 정적 대시보드(`docs/index.html`, GitHub Pages)를 만듭니다.

## 구조 (맥 + GitHub Actions)

네이버가 GitHub 서버 IP를 막아서 일을 나눴습니다. 두 쪽이 서로 다른 파일만 쓰므로 git 충돌이 없습니다.

| 어디서 | 하는 일 | 쓰는 파일 |
|---|---|---|
| 맥 (`run.py`, launchd) | 네이버 호가 수집 → `data/apt.db` → 요약을 push | `state/asking.json` |
| GitHub Actions (`.github/workflows/update.yml`, 매일 07시 + asking.json push 때) | 국토부 실거래 수집, 대시보드 생성 | `state/trades.json`, `docs/index.html` |

맥이 꺼져 있어도 실거래는 매일 갱신되고, 호가는 맥이 켜졌을 때 갱신됩니다.
GitHub Actions 는 저장소 Settings → Secrets and variables → Actions 의 `MOLIT_SERVICE_KEY` 를 인증키로 씁니다.
config.json 에 단지를 추가하면 다음 실거래 수집 때 그 시군구의 과거 36개월을 자동으로 다시 받습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `run.py` | 맥에서 실행(호가 수집 → `state/asking.json` push). launchd 에는 이것만 등록 |
| `collect_listings.py` | 네이버 매물 수집 (`--dry-run --debug`로 응답 확인) |
| `collect_trades.py` | 국토부 실거래 수집 (`--find 시군구코드 키워드`로 단지명 찾기) |
| `build_dashboard.py` | `state/*.json` → `docs/index.html` 생성 (`--export-asking`: DB → asking.json) |
| `config.json` | 단지 목록, 평형(전용 ㎡) 조건, 수집 설정 |
| `secrets.json` | 실거래 API 인증키 — 맥에서 직접 실거래를 받을 때만 (git에 올라가지 않음) |

## 1. 설치 (macOS)

```bash
xcode-select --install          # python3, git 설치 (창이 뜨면 '설치')
cd "/Users/Shared/APT Project"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. 단지 설정 (`config.json`)

- `excl_area_min` / `excl_area_max`: 전용면적(㎡) 범위(지금 58~86 = 59~84타입). 단지별로 따로 넣으면 그 값이 우선합니다.
  대시보드에서는 59·73·79·84 같은 타입별로 나눠서 보여 줍니다.
  호가·실거래 모두 이 기준으로 거릅니다(실거래 자료엔 전용면적만 있어서 공급 평형 대신 전용을 씁니다).
- 단지마다
  - `name`: 대시보드에 보일 이름. **DB의 키로도 쓰이니 수집을 시작한 뒤엔 바꾸지 마세요.**
  - `complex_no`: 네이버 단지 번호. `fin.land.naver.com`에서 단지를 열었을 때 주소의 `complexes/12345`의 숫자.
  - `lawd_cd`: 시군구 코드 5자리 (예: 동대문구 11230, 성북구 11290). 단지 주소 기준이라 이름과 다를 수 있음
    (래미안아트리치는 석관동, 길음래미안은 길음동이라 성북구).
  - `molit_name`: 실거래 자료상의 단지명(네이버 이름과 다를 때만). `umd_nm`: 법정동(이름이 겹칠 때만).
    `python collect_trades.py --find 11230 이문` 으로 후보를 볼 수 있습니다.

## 3. 실거래 API 인증키

1. 공공데이터포털(data.go.kr)에서 "국토교통부_아파트 매매 실거래가 상세 자료" 활용신청
2. `secrets.json.example`을 `secrets.json`으로 복사하고 **일반 인증키(Decoding)**를 넣기

## 4. 첫 실행

```bash
.venv/bin/python collect_listings.py --dry-run --debug   # 네이버 응답 확인 (logs/debug_*.json)
# 직전 수집 후 6시간(min_interval_hours)이 안 지났으면 건너뜀. 강제로 하려면 --force
.venv/bin/python run.py --no-publish                     # 호가 수집 + 로컬에서 대시보드 생성(--trades: 실거래도)
open docs/index.html
```

처음 실행하면 실거래를 36개월치(`trade_backfill_months`) 받아 옵니다. 이후엔 최근 3개월만 다시 받습니다.

## 5. 휴대폰에서 보기 (GitHub Pages)

1. GitHub에 **public** 저장소를 만들고 이 폴더를 push (`secrets.json`, `data/`, `logs/`는 `.gitignore`로 빠짐)
2. 저장소 Settings → Pages → Branch `main`, 폴더 `/docs`
3. `config.json`의 `"publish_git": true` → 맥은 호가 요약을 push 하고, GitHub Actions 가 대시보드를 만들어 커밋합니다

링크를 아는 사람은 누구나 볼 수 있습니다(검색엔진 색인은 막아 둠).

## 6. 자동 실행 (macOS launchd: 로그인할 때 + 매일 8시·20시)

`~/Library/LaunchAgents/com.apt.dashboard.plist` 로 저장:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.apt.dashboard</string>
  <key>ProgramArguments</key><array>
    <string>/Users/Shared/APT Project/.venv/bin/python</string>
    <string>-W</string><string>ignore</string>
    <string>/Users/Shared/APT Project/run.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.apt.dashboard.plist
```

맥이 잠자기 중이면 깨어난 뒤 한 번 실행됩니다. 로그는 `logs/run.log`.
**주의:** macOS는 백그라운드 프로그램의 `~/Documents` 접근을 막습니다. 프로젝트가 `~/Documents` 안에 있으면
`Operation not permitted`로 실패하므로 홈 폴더 바로 아래 등 다른 곳에 두세요.

## 주의

네이버 부동산은 공식 API가 없습니다. `fin.land.naver.com` 웹 화면이 쓰는 내부 API를 호출하므로
구조가 바뀌거나 막히면 호가 수집이 실패하고(로그에 오류가 남음) 대시보드는 마지막으로 모은 데이터까지 보여 줍니다.
빠르게 여러 번 호출하면 429(요청 과다)가 오니 `request_delay_sec`를 줄이지 마세요.
같은 호를 여러 중개사가 올린 매물은 네이버가 묶어 주므로 1건으로 셉니다.
