# 아파트 가격 추이 대시보드 프로젝트

## 목표
특정 아파트 단지들의 **매도 호가(네이버 부동산)**와 **실거래가(국토부)** 추이를
주기적으로 수집해서, 휴대폰에서도 한눈에 볼 수 있는 웹 대시보드로 보여준다.

## 지금까지 결정한 것 (2026-09-28)
- **실행 환경**: 회사 PC(사내망)는 쓰지 않는다. 개인 PC로 옮겨서 작업하고 실행한다.
- **슬랙 알림은 뺀다**: 대시보드만 만든다. 기존 `naver_land_monitor.py`의 슬랙 부분은 제거하거나 대체한다.
- **호가 수집**: 네이버 부동산 비공식 API(`m.land.naver.com/complex/getComplexArticleList`)를 쓴다.
  하루 1~2회 조회해서 단지별 매물 수, 최저 호가, 중간값 호가를 SQLite에 쌓는다.
  (현재 스크립트는 직전 상태를 덮어쓰기만 해서 이력이 남지 않는다.)
- **실거래가**: 공공데이터포털 "국토교통부_아파트 매매 실거래가 상세 자료" API를 쓴다.
  인증키는 사용자가 직접 발급해서 설정 파일에 넣는다. 대화창에 붙여넣게 하지 않는다.
- **대시보드**: 수집할 때마다 정적 HTML을 새로 만든다. 모바일 화면에 맞추고,
  단지별로 호가와 실거래가를 겹친 그래프를 보여준다.
- **휴대폰에서 보기**: GitHub Pages를 추천했다(링크를 아는 사람은 볼 수 있음).
  비밀번호 보호가 필요하면 Cloudflare Pages 등을 검토한다. 사용자의 GitHub 계정 여부는 아직 모른다.
- **주기 실행**: 맥 launchd — 켜질 때(로그인) + 8시·20시. 6시간 이내 재수집은 건너뜀.

## 아직 받지 못한 정보
- 추적할 **단지 목록과 평형 조건**. 기존 config.json의 12개 단지와 공급 23~28평에서 바꾸기로 했다.
  사용자에게 단지명(동 포함), 평형 기준(공급 평형 또는 전용 ㎡), 가능하면 네이버 complex_no를 받는다.
- 새 PC의 OS, 24시간 켜 두는지 여부, GitHub 계정 여부

## 진행 상황 (2026-09-28 세 번째 세션)
- 작업 PC = 이 맥(macOS 14.3.1, 개인 PC 확인). 24시간 켜 두지 않음 → **켜질 때만 업데이트**하면 됨.
  Python 3.9(CLT) + `.venv` 설치 완료. GitHub 계정: `jdy5031-dev`.
- **네이버 m.land API는 막힘**(null 반환, fin.land 로 리다이렉트). `fin.land.naver.com/front-api/v1/complex/article/list`
  (POST, seed/lastInfo 페이지네이션)로 교체. 가격은 원 단위, 같은 호 중복은 네이버가 묶어 줌. 빠르게 호출하면 429.
- 단지 12곳 complex_no·시군구·법정동 확정(config.json). 래미안아트리치(석관동)·길음래미안1차(길음동)는 **성북구 11290**.
- 평형: 사용자 요청 "59~84타입" → 전용 58~86㎡. 대시보드는 타입(59/73/79/84)별 버튼으로 나눠 보여 줌.
- 2026-09-28 16:22 첫 호가 수집 성공(12곳 전부). 실거래는 인증키가 아직 없어 미수집.
- 켤 때마다 실행되므로 호가·실거래 모두 직전 수집 후 6시간(min_interval_hours) 이내면 건너뜀(--force로 무시).
- 프로젝트 위치를 **/Users/Shared/APT Project** 로 옮김(~/Documents 는 macOS 권한 때문에 launchd 실행 불가).
  .venv 재생성. launchd 에이전트(`~/Library/LaunchAgents/com.apt.dashboard.plist`, 로그인 시 + 8시·20시) 등록·동작 확인.
  실행 출력은 /tmp/apt-dashboard.{out,err}, 로그는 logs/run.log.
- 로컬 git 저장소 생성, 첫 커밋 완료(아직 GitHub 원격 없음, push 안 함).

- (네 번째 세션) 인증키 설정 완료. 12곳 모두 국토부 단지 매칭 → config에 `molit_apt_seq`(aptSeq)로 고정.
  이름이 다른 곳: 이문 e편한세상=대림e-편한세상, 길음래미안1단지=길음뉴타운1단지(래미안길음1차), 이문대우=대우, 휘경 SK뷰=휘경SK뷰.
  36개월 백필 완료(2,129건). 래미안라그란데(13건)·휘경자이디센시아(2건)는 신축이라 거래가 적음(분양권 거래는 이 API에 없음).
- GitHub 원격 `jdy5031-dev/apt-dashboard`(public) 연결·push 완료. `publish_git: true` — 수집 후 docs/index.html 바뀌면 자동 커밋·push.
  인증은 맥 키체인(osxkeychain)에 저장된 자격 증명을 씀.

- (2026-11-03~04 다섯 번째 세션) **맥 + GitHub Actions 분담**으로 변경. GitHub Actions 서버(Azure IP)에서는 네이버가
  첫 요청부터 429로 막아서(두 번 다른 IP로 확인) 호가는 맥에서만 수집. 실거래(국토부)는 Actions 에서 접속됨.
  맥: 호가 → data/apt.db → `state/asking.json` 만 커밋·push. Actions(update.yml, 매일 07시 KST + asking.json·config 등 push 시):
  실거래 → `state/trades.json`, 대시보드 → docs/index.html 커밋. 파일마다 쓰는 쪽이 하나라 충돌 없음. Actions 는 `ref: main` 으로 체크아웃.
  **Actions Secret `MOLIT_SERVICE_KEY` 는 사용자가 아직 등록 안 함** → 그 전까지 Actions 실거래 단계는 실패(대시보드 생성은 계속됨).
- 네이버 Connection reset 이 단지 정보 조회에서 나면 호가 수집 전체가 죽던 버그 수정(재시도 + 단지별로 건너뜀).
- 네이버 단지 검색: `GET fin.land.naver.com/front-api/v1/search/autocomplete/complexes?keyword=`.
- 단지 7곳 추가(총 19곳): 이문푸르지오2차, 이문현대(국토부 '현대'), 이문쌍용, 이문아이파크자이(3-1BL, 174562), 중앙하이츠빌, 이문삼익, 래미안이문2차.
  사용자가 말한 '이문푸르지오1차'는 기존 이문대우(3374)와 같은 단지(네이버 검색 별칭). '이문현대아아파크'는 이문동 현대(1125)로 판단.
  trades.json 의 `covered` 에 없는 단지가 config 에 생기면 그 시군구 과거분을 자동 재수집.

## 다음 단계
1. 사용자가 GitHub 저장소 Settings → Secrets and variables → Actions 에 `MOLIT_SERVICE_KEY` 등록 → Actions 실거래 수집 성공 확인

## 파일
- `run.py`: 맥 실행 진입점(호가 + asking.json push) / `common.py`: 설정·DB 스키마·state 경로
- `.github/workflows/update.yml`: 실거래 + 대시보드(GitHub Actions) / `state/asking.json`(맥), `state/trades.json`(Actions)
- `collect_listings.py`: 네이버 호가(fin.land API) → listing_snapshot, listing_article / 단지 정보(`/complex`: 사용승인일·세대수·용적률·건폐율) → complex_info (30일마다, `--info`로 즉시)
- `collect_trades.py`: 국토부 실거래 → trade (시군구×월 단위, trade_fetch_log로 과거 달 재호출 방지). 실행 시 state/trades.json 불러오고 끝나면 내보냄
- `build_dashboard.py`: state/*.json → docs/index.html 생성 (Chart.js CDN, 데이터 인라인, 타입·기간 선택), `export_asking()`: DB → asking.json
- `config.json`, `secrets.json.example`, `.gitignore`, `README.md`
