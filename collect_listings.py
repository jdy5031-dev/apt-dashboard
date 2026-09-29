#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 부동산 매물(호가) 수집기.

config.json 의 단지마다 매물 목록 전체를 받아서 SQLite(data/apt.db)에 스냅샷으로 쌓는다.
평형 필터는 저장 시점이 아니라 대시보드 생성 시점에 적용한다(나중에 평형 조건을 바꿔도 과거 이력이 살아 있게).

네이버 부동산(fin.land.naver.com)의 웹 화면이 쓰는 비공식 API를 호출한다.
- 같은 호를 여러 중개사가 올린 매물은 네이버가 한 항목으로 묶어 주므로, 목록 한 항목 = 매물 1건으로 센다.
- 공식 API가 아니라서 구조가 바뀌거나 막힐 수 있다. 너무 빨리 호출하면 429(TOO_MANY_REQUESTS)가 온다.
- --debug 로 첫 페이지 원본 응답을 logs/ 에 저장해 확인할 수 있다.
"""

import argparse
import json
import random
import time
from datetime import datetime

import requests

from common import BASE_DIR, connect, load_config, setup_logging

log = setup_logging("listings")

API = "https://fin.land.naver.com/front-api/v1"
PAGE_SIZE = 30
TRADE_TYPE_NAMES = {"A1": "매매", "B1": "전세", "B2": "월세"}


class NaverError(Exception):
    pass


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Origin": "https://fin.land.naver.com",
        "Referer": "https://fin.land.naver.com/",
    })
    s.get("https://fin.land.naver.com/", timeout=10)
    return s


def post(session, path: str, body: dict) -> dict:
    """429 이면 잠깐 쉬었다가 두 번까지 다시 시도한다."""
    for attempt in range(3):
        resp = session.post(API + path, json=body, timeout=15)
        if resp.status_code == 429 and attempt < 2:
            wait = 30 * (attempt + 1)
            log.warning("429 요청 과다, %d초 후 재시도", wait)
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            raise NaverError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if not data.get("isSuccess"):
            raise NaverError(f"실패 응답: {json.dumps(data, ensure_ascii=False)[:200]}")
        return data["result"]


def update_complex_info(session, conn, complexes: list, refresh_days: int, delay: float, force: bool = False):
    """사용승인일·세대수·용적률·건폐율. 저장된 지 refresh_days 가 안 지났으면 건너뛴다."""
    fetched = {r["complex"]: r["fetched_at"] for r in conn.execute("SELECT complex, fetched_at FROM complex_info")}
    now = datetime.now()
    for c in complexes:
        name, complex_no = c.get("name", "?"), str(c.get("complex_no", ""))
        if not complex_no or complex_no == "REPLACE_ME":
            continue
        last = fetched.get(name)
        if last and not force and (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).days < refresh_days:
            continue
        resp = session.get(API + "/complex", params={"complexNumber": complex_no}, timeout=15)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code != 200 or not data.get("isSuccess"):
            log.error("단지 정보 조회 실패: %s (HTTP %d)", name, resp.status_code)
            continue
        r = data["result"]
        ratio = r.get("buildingRatioInfo") or {}
        conn.execute(
            "INSERT OR REPLACE INTO complex_info VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, r.get("useApprovalDate"), r.get("totalHouseholdNumber"), ratio.get("floorAreaRatio"),
             ratio.get("buildingCoverageRatio"), json.dumps(r, ensure_ascii=False), now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        log.info("단지 정보: %s 사용승인 %s, %s세대, 용적률 %s%%, 건폐율 %s%%", name, r.get("useApprovalDate"),
                 r.get("totalHouseholdNumber"), ratio.get("floorAreaRatio"), ratio.get("buildingCoverageRatio"))
        time.sleep(delay + random.uniform(0, 1))


def fetch_articles(session, complex_no: str, trade_type: str, delay: float, max_pages: int, debug: bool) -> list:
    """단지 매물 목록 전체(묶인 매물은 대표 매물 한 건)."""
    items, last_info, seed = [], [], None
    for page in range(max_pages):
        body = {"size": PAGE_SIZE, "complexNumber": complex_no, "tradeTypes": [trade_type],
                "pyeongTypes": [], "dongNumbers": [], "userChannelType": "PC",
                "articleSortType": "PRICE_ASC", "lastInfo": last_info}
        if seed:
            body["seed"] = seed
        result = post(session, "/complex/article/list", body)
        if debug and page == 0:
            path = BASE_DIR / "logs" / f"debug_{complex_no}_{trade_type}.json"
            path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            log.info("원본 응답 저장 -> %s", path)
        items.extend(result.get("list") or [])
        if not result.get("hasNextPage"):
            break
        last_info, seed = result.get("lastInfo") or [], result.get("seed")
        time.sleep(delay + random.uniform(0, 1))
    return items


def normalize(item: dict):
    a = item.get("representativeArticleInfo") or {}
    if not a.get("articleNumber"):
        return None
    space = a.get("spaceInfo") or {}
    detail = a.get("articleDetail") or {}
    price = (a.get("priceInfo") or {}).get("dealPrice")
    return {
        "article_no": str(a["articleNumber"]),
        "price": price // 10000 if price else None,  # 원 → 만원
        "excl_area": space.get("exclusiveSpace"),
        "supply_area": space.get("supplySpace"),
        "building": a.get("dongName"),
        "floor": detail.get("floorInfo"),
        "direction": detail.get("direction"),
        "confirm_date": (a.get("verificationInfo") or {}).get("articleConfirmDate"),
    }


def save_snapshot(conn, complex_name: str, trade_type: str, articles: list, collected_at: str):
    cur = conn.execute(
        "INSERT INTO listing_snapshot (complex, trade_type, collected_at) VALUES (?, ?, ?)",
        (complex_name, trade_type, collected_at),
    )
    conn.executemany(
        """INSERT OR REPLACE INTO listing_article
           (snapshot_id, article_no, price, excl_area, supply_area, building, floor, direction, confirm_date)
           VALUES (:sid, :article_no, :price, :excl_area, :supply_area, :building, :floor, :direction, :confirm_date)""",
        [dict(a, sid=cur.lastrowid) for a in articles],
    )
    conn.commit()


def run(dry_run: bool = False, debug: bool = False, force: bool = False) -> int:
    """수집에 성공한 단지 수를 돌려준다."""
    config = load_config()
    delay = config.get("request_delay_sec", 3)
    max_pages = config.get("max_pages_per_query", 20)
    trade_types = config.get("trade_types", ["A1"])
    now = datetime.now()
    collected_at = now.strftime("%Y-%m-%d %H:%M:%S")
    conn = None if dry_run else connect()

    # 맥을 켤 때마다 실행되므로, 직전 수집 후 min_interval_hours 가 안 지났으면 건너뛴다.
    min_hours = config.get("min_interval_hours", 6)
    if conn and not force:
        last = conn.execute("SELECT MAX(collected_at) FROM listing_snapshot").fetchone()[0]
        if last and (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < min_hours * 3600:
            log.info("호가 수집 건너뜀: 마지막 수집 %s (%d시간 이내)", last, min_hours)
            conn.close()
            return 0
    session = new_session()
    done = 0
    if conn:
        update_complex_info(session, conn, config.get("complexes", []), config.get("info_refresh_days", 30), delay)

    for c in config.get("complexes", []):
        name, complex_no = c.get("name", "?"), str(c.get("complex_no", ""))
        if not complex_no or complex_no == "REPLACE_ME":
            log.warning("건너뜀 (complex_no 미설정): %s", name)
            continue
        for tt in trade_types:
            try:
                raw = fetch_articles(session, complex_no, tt, delay, max_pages, debug)
            except (NaverError, requests.RequestException, ValueError) as e:
                log.error("조회 실패, 이번 회차 건너뜀: %s (%s): %s", name, TRADE_TYPE_NAMES.get(tt, tt), e)
                continue
            articles = [a for a in map(normalize, raw) if a]
            prices = sorted(a["price"] for a in articles if a["price"])
            log.info("%s (%s): 매물 %d건, 최저 %s만원", name, TRADE_TYPE_NAMES.get(tt, tt),
                     len(articles), f"{prices[0]:,}" if prices else "-")
            if dry_run:
                for a in articles[:3]:
                    log.info("    %s", a)
            else:
                save_snapshot(conn, name, tt, articles, collected_at)
            done += 1
            time.sleep(delay + random.uniform(0, 1))

    if conn:
        conn.close()
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="네이버 부동산 매물 수집")
    p.add_argument("--dry-run", action="store_true", help="DB에 저장하지 않고 콘솔에만 출력")
    p.add_argument("--debug", action="store_true", help="첫 페이지 원본 응답을 logs/debug_*.json 으로 저장")
    p.add_argument("--force", action="store_true", help="최근에 수집했어도 다시 수집")
    p.add_argument("--info", action="store_true", help="단지 정보(사용승인일·세대수·용적률·건폐율)만 지금 다시 받기")
    args = p.parse_args()
    if args.info:
        cfg = load_config()
        db = connect()
        update_complex_info(new_session(), db, cfg.get("complexes", []), 0, cfg.get("request_delay_sec", 3), force=True)
        db.close()
    else:
        run(args.dry_run, args.debug, args.force)
