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

## 진행 상황 (2026-09-28 두 번째 세션)
- 작업 PC: macOS 14.3.1 (JDys-MacBook-Pro, 계정 skb2930). **이 맥이 개인 PC인지 아직 확인 안 됨.**
  python3·git 없음(Command Line Tools 미설치) → 사용자가 `xcode-select --install` 해야 함.
  테스트는 scratchpad에 받은 standalone Python으로만 했다. 네이버·국토부 실제 호출은 아직 안 함.
- 3~5단계 코드 작성 완료, 가짜 데이터로 테스트 통과(DB 저장, 해제거래 처리, API 오류 감지, 375px 화면 렌더링).
- 평형 기준을 **전용면적(㎡)**으로 바꿈(실거래 자료가 전용만 있어서). 기본값 55~62㎡(전용 59 타입) — 사용자 확인 필요.
- 평형 필터는 대시보드 생성 시 적용하고, DB엔 전체 매물을 저장한다(조건을 바꿔도 과거 이력 유지).
- 인증키는 `secrets.json`(gitignore). 주기 실행은 맥이면 launchd(README 6번).
- 기존 `naver_land_monitor.py`, `state/`는 삭제함.

## 다음 단계
1. 이 맥이 개인 PC인지, 24시간 켜 두는지, GitHub 계정 확인
2. `xcode-select --install` → venv + requests 설치
3. 단지 목록·평형 확정 → config.json 의 complex_no / lawd_cd / molit_name 채우기
4. `collect_listings.py --dry-run --debug`로 네이버 실제 응답 필드 확인(prc, spc2, bildNm, flrInfo)
5. 인증키 발급 후 `collect_trades.py --find`로 단지명 매칭 확인 → `run.py --no-publish`
6. GitHub Pages 게시 + launchd 등록

## 파일
- `run.py`: 전체 실행 진입점 / `common.py`: 설정·DB 스키마
- `collect_listings.py`: 네이버 호가 → listing_snapshot, listing_article
- `collect_trades.py`: 국토부 실거래 → trade (시군구×월 단위, trade_fetch_log로 과거 달 재호출 방지)
- `build_dashboard.py`: docs/index.html 생성 (Chart.js CDN, 데이터 인라인)
- `config.json`, `secrets.json.example`, `.gitignore`, `README.md`(새 구조로 다시 씀)
