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
- **주기 실행**: Windows 작업 스케줄러를 쓴다(새 PC가 Windows일 경우).

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
- launchd 에이전트(`~/Library/LaunchAgents/com.apt.dashboard.plist`, RunAtLoad + 8시·20시)를 만들었으나
  **~/Documents 접근이 macOS 권한(TCC)에 막혀 실패** → bootout 해 둠. 프로젝트를 Documents 밖으로 옮길지 사용자 결정 대기.
- 로컬 git 저장소 생성, 첫 커밋 완료(아직 GitHub 원격 없음, push 안 함).

## 다음 단계
1. 프로젝트 폴더를 Documents 밖(예: ~/apt-dashboard)으로 옮길지 결정 → plist 경로 수정 후 launchd 등록
2. 공공데이터포털 인증키 발급 → secrets.json → `collect_trades.py --find 11230 이문` 등으로 실거래 단지명 매칭 확인
   (네이버 이름과 다를 가능성 높음: 이문e-편한세상, 길음래미안1차 등 → molit_name 채우기)
3. GitHub에 public 저장소 생성 → remote 추가·push → Pages(/docs) 켜기 → config `publish_git: true`

## 파일
- `run.py`: 전체 실행 진입점 / `common.py`: 설정·DB 스키마
- `collect_listings.py`: 네이버 호가(fin.land API) → listing_snapshot, listing_article
- `collect_trades.py`: 국토부 실거래 → trade (시군구×월 단위, trade_fetch_log로 과거 달 재호출 방지)
- `build_dashboard.py`: docs/index.html 생성 (Chart.js CDN, 데이터 인라인, 타입·기간 선택)
- `config.json`, `secrets.json.example`, `.gitignore`, `README.md`
