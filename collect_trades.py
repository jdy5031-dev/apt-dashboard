#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토교통부 아파트 매매 실거래가(상세) 수집기.

공공데이터포털 "국토교통부_아파트 매매 실거래가 상세 자료" API를 시군구(LAWD_CD) × 계약월 단위로 호출해서
config.json 의 단지와 이름이 맞는 거래만 data/apt.db 의 trade 테이블에 저장한다.

- 처음 실행하면 trade_backfill_months 개월치를 받아 온다.
- 이후에는 최근 trade_refresh_months 개월만 다시 받는다(신고 기한 30일, 해제 신고 반영).
- 인증키는 secrets.json 의 molit_service_key 에 넣는다(secrets.json.example 참고).

단지 이름 확인용:
    python collect_trades.py --find 11230 이문
    → 동대문구(11230) 최근 거래에서 '이문'이 들어간 단지명·법정동·단지코드를 보여 준다.
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from urllib.parse import unquote

import requests

from common import connect, load_config, load_secrets, setup_logging

log = setup_logging("trades")

API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
ROWS_PER_PAGE = 1000


class ApiError(Exception):
    pass


def service_key() -> str:
    key = load_secrets().get("molit_service_key", "").strip()
    if not key or "여기에" in key:
        raise ApiError("secrets.json 에 molit_service_key 가 없습니다. secrets.json.example 을 참고하세요.")
    # 포털의 '인코딩' 키를 넣어도 requests 가 한 번 더 인코딩하지 않도록 디코딩 키로 맞춘다.
    return unquote(key) if "%" in key else key


def month_list(n: int) -> list:
    """이번 달부터 거꾸로 n개월의 'YYYYMM' 목록."""
    y, m = date.today().year, date.today().month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def text(item, tag) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def fetch_month(key: str, lawd_cd: str, deal_ymd: str) -> list:
    """한 시군구·한 달의 거래 전체. 각 거래는 {태그: 값} dict."""
    items, page = [], 1
    while True:
        params = {"serviceKey": key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd,
                  "pageNo": page, "numOfRows": ROWS_PER_PAGE}
        resp = requests.get(API_URL, params=params, timeout=20)
        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code} ({lawd_cd}/{deal_ymd}): {resp.text[:200]}")
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            raise ApiError(f"XML 파싱 실패 ({lawd_cd}/{deal_ymd}): {resp.text[:200]}")

        code = text(root, ".//resultCode") or text(root, ".//returnReasonCode")
        if code not in ("00", "000"):
            msg = text(root, ".//resultMsg") or text(root, ".//returnAuthMsg") or text(root, ".//errMsg")
            raise ApiError(f"API 오류 code={code} msg={msg} ({lawd_cd}/{deal_ymd})")

        page_items = [{child.tag: (child.text or "").strip() for child in it} for it in root.iter("item")]
        items.extend(page_items)
        total = int(text(root, ".//totalCount") or 0)
        if not page_items or len(items) >= total:
            return items
        page += 1
        time.sleep(0.3)


def to_record(it: dict) -> dict:
    y, m, d = int(it["dealYear"]), int(it["dealMonth"]), int(it["dealDay"])
    cancel_day = it.get("cdealDay", "")  # 예: '24.10.05'
    if cancel_day:
        yy, mm, dd = cancel_day.split(".")
        cancel_day = f"20{yy}-{mm}-{dd}" if len(yy) == 2 else f"{yy}-{mm}-{dd}"
    return {
        "deal_date": f"{y:04d}-{m:02d}-{d:02d}",
        "price": int(it["dealAmount"].replace(",", "")),
        "excl_area": float(it["excluUseAr"]),
        "floor": int(it.get("floor") or 0),
        "apt_dong": it.get("aptDong", ""),
        "cancelled": 1 if it.get("cdealType", "") == "O" else 0,
        "cancel_date": cancel_day or None,
        "dealing_type": it.get("dealingGbn") or None,
    }


def matches(it: dict, c: dict) -> bool:
    """거래가 config 단지에 해당하는지. molit_apt_seq 가 있으면 그걸로, 없으면 단지명(+법정동)으로 비교."""
    if c.get("molit_apt_seq"):
        return it.get("aptSeq") == c["molit_apt_seq"]
    name = c.get("molit_name") or c.get("name")
    if it.get("aptNm", "").replace(" ", "") != name.replace(" ", ""):
        return False
    return not c.get("umd_nm") or it.get("umdNm") == c["umd_nm"]


def run(force: bool = False) -> int:
    """저장(갱신)한 거래 건수를 돌려준다."""
    config = load_config()
    key = service_key()
    backfill = config.get("trade_backfill_months", 36)
    refresh = config.get("trade_refresh_months", 3)
    complexes = [c for c in config.get("complexes", []) if c.get("lawd_cd")]
    for c in config.get("complexes", []):
        if not c.get("lawd_cd"):
            log.warning("건너뜀 (lawd_cd 미설정): %s", c.get("name"))

    conn = connect()
    now_dt = datetime.now()
    now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    last = conn.execute("SELECT MAX(fetched_at) FROM trade_fetch_log").fetchone()[0]
    min_hours = config.get("min_interval_hours", 6)
    if last and not force and (now_dt - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < min_hours * 3600:
        log.info("실거래 수집 건너뜀: 마지막 수집 %s (%d시간 이내)", last, min_hours)
        conn.close()
        return 0
    fetched_before = {(r["lawd_cd"], r["deal_ymd"]) for r in conn.execute("SELECT lawd_cd, deal_ymd FROM trade_fetch_log")}
    recent = set(month_list(refresh))
    saved = 0

    for lawd_cd in sorted({c["lawd_cd"] for c in complexes}):
        targets = [c for c in complexes if c["lawd_cd"] == lawd_cd]
        for ymd in month_list(backfill):
            if ymd not in recent and (lawd_cd, ymd) in fetched_before:
                continue
            items = fetch_month(key, lawd_cd, ymd)
            rows = []
            for it in items:
                for c in targets:
                    if matches(it, c):
                        rows.append(dict(to_record(it), complex=c["name"], updated_at=now))
            conn.executemany(
                """INSERT INTO trade (complex, deal_date, price, excl_area, floor, apt_dong,
                                      cancelled, cancel_date, dealing_type, updated_at)
                   VALUES (:complex, :deal_date, :price, :excl_area, :floor, :apt_dong,
                           :cancelled, :cancel_date, :dealing_type, :updated_at)
                   ON CONFLICT (complex, deal_date, excl_area, floor, apt_dong, price) DO UPDATE SET cancelled = excluded.cancelled,
                       cancel_date = excluded.cancel_date, updated_at = excluded.updated_at""",
                rows,
            )
            conn.execute("INSERT OR REPLACE INTO trade_fetch_log VALUES (?, ?, ?)", (lawd_cd, ymd, now))
            conn.commit()
            saved += len(rows)
            log.info("실거래 %s/%s: 전체 %d건 중 대상 단지 %d건", lawd_cd, ymd, len(items), len(rows))
            time.sleep(0.3)

    conn.close()
    return saved


def find(lawd_cd: str, keyword: str):
    """시군구 최근 3개월 거래에서 단지명 후보를 보여 준다(config 작성용)."""
    key = service_key()
    counter = Counter()
    for ymd in month_list(3):
        for it in fetch_month(key, lawd_cd, ymd):
            if keyword in it.get("aptNm", "") or keyword in it.get("umdNm", ""):
                counter[(it.get("aptNm"), it.get("umdNm"), it.get("aptSeq", ""))] += 1
    if not counter:
        print("검색 결과 없음 (최근 3개월 거래 기준)")
    for (apt, umd, seq), n in counter.most_common():
        print(f"{apt:<24} 법정동={umd:<8} aptSeq={seq:<14} 거래 {n}건")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="국토부 아파트 실거래가 수집")
    p.add_argument("--find", nargs=2, metavar=("LAWD_CD", "KEYWORD"), help="단지명 후보 검색")
    p.add_argument("--force", action="store_true", help="최근에 수집했어도 다시 수집")
    args = p.parse_args()
    try:
        if args.find:
            find(*args.find)
        else:
            run(args.force)
    except (ApiError, requests.RequestException) as e:
        log.error("%s", e)
        sys.exit(1)
