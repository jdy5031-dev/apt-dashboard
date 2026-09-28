# 아파트 시세 대시보드

관심 단지들의 **네이버 부동산 매매 호가**와 **국토부 실거래가**를 하루 1~2회 모아
SQLite(`data/apt.db`)에 쌓고, 휴대폰으로 보는 정적 대시보드(`docs/index.html`)를 만듭니다.

## 파일

| 파일 | 역할 |
|---|---|
| `run.py` | 전체 실행(호가 → 실거래 → 대시보드 → 게시). 스케줄러에는 이것만 등록 |
| `collect_listings.py` | 네이버 매물 수집 (`--dry-run --debug`로 응답 확인) |
| `collect_trades.py` | 국토부 실거래 수집 (`--find 시군구코드 키워드`로 단지명 찾기) |
| `build_dashboard.py` | `docs/index.html` 생성 |
| `config.json` | 단지 목록, 평형(전용 ㎡) 조건, 수집 설정 |
| `secrets.json` | 실거래 API 인증키 (직접 만듦, git에 올라가지 않음) |

## 1. 설치 (macOS)

```bash
xcode-select --install          # python3, git 설치 (창이 뜨면 '설치')
cd "~/Documents/APT Project"
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
.venv/bin/python run.py --no-publish                     # 전체 실행
open docs/index.html
```

처음 실행하면 실거래를 36개월치(`trade_backfill_months`) 받아 옵니다. 이후엔 최근 3개월만 다시 받습니다.

## 5. 휴대폰에서 보기 (GitHub Pages)

1. GitHub에 **public** 저장소를 만들고 이 폴더를 push (`secrets.json`, `data/`, `logs/`는 `.gitignore`로 빠짐)
2. 저장소 Settings → Pages → Branch `main`, 폴더 `/docs`
3. `config.json`의 `"publish_git": true` → 매 실행 후 대시보드가 자동으로 push 됩니다

링크를 아는 사람은 누구나 볼 수 있습니다(검색엔진 색인은 막아 둠).

## 6. 자동 실행 (macOS launchd: 로그인할 때 + 매일 8시·20시)

`~/Library/LaunchAgents/com.apt.dashboard.plist` 로 저장:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.apt.dashboard</string>
  <key>ProgramArguments</key><array>
    <string>/Users/skb2930/Documents/APT Project/.venv/bin/python</string>
    <string>/Users/skb2930/Documents/APT Project/run.py</string>
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
