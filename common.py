# -*- coding: utf-8 -*-
"""설정·로그·SQLite 공통 모듈."""

import json
import logging
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SECRETS_PATH = BASE_DIR / "secrets.json"
DB_PATH = BASE_DIR / "data" / "apt.db"
LOG_PATH = BASE_DIR / "logs" / "run.log"
DOCS_DIR = BASE_DIR / "docs"

SCHEMA = """
-- 네이버 매물 조회 1회분. 평형 필터는 대시보드 생성 시 적용하므로 여기엔 전체 매물을 저장한다.
CREATE TABLE IF NOT EXISTS listing_snapshot (
    id           INTEGER PRIMARY KEY,
    complex      TEXT NOT NULL,          -- config.json 의 단지 name
    trade_type   TEXT NOT NULL,          -- A1 매매 / B1 전세 / B2 월세
    collected_at TEXT NOT NULL           -- 'YYYY-MM-DD HH:MM:SS' (로컬 시간)
);
CREATE INDEX IF NOT EXISTS idx_snapshot ON listing_snapshot (complex, trade_type, collected_at);

CREATE TABLE IF NOT EXISTS listing_article (
    snapshot_id  INTEGER NOT NULL REFERENCES listing_snapshot(id),
    article_no   TEXT NOT NULL,
    price        INTEGER,                -- 만원
    excl_area    REAL,                   -- 전용면적 ㎡
    supply_area  REAL,                   -- 공급면적 ㎡
    building     TEXT,                   -- 동
    floor        TEXT,                   -- 예: '12/25', '중/25'
    direction    TEXT,
    confirm_date TEXT,
    PRIMARY KEY (snapshot_id, article_no)
);

-- 국토부 실거래. 거래 고유번호가 없어서 (단지, 계약일, 면적, 층, 동, 금액)을 키로 쓴다.
CREATE TABLE IF NOT EXISTS trade (
    complex      TEXT NOT NULL,
    deal_date    TEXT NOT NULL,          -- 'YYYY-MM-DD'
    price        INTEGER NOT NULL,       -- 만원
    excl_area    REAL NOT NULL,
    floor        INTEGER NOT NULL DEFAULT 0,
    apt_dong     TEXT NOT NULL DEFAULT '',
    cancelled    INTEGER NOT NULL DEFAULT 0,
    cancel_date  TEXT,
    dealing_type TEXT,                   -- 중개거래 / 직거래
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (complex, deal_date, excl_area, floor, apt_dong, price)
);

-- 실거래 API에서 (시군구, 계약월)을 언제 마지막으로 받아왔는지. 오래된 달은 한 번만 받는다.
CREATE TABLE IF NOT EXISTS trade_fetch_log (
    lawd_cd    TEXT NOT NULL,
    deal_ymd   TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (lawd_cd, deal_ymd)
);
"""


def setup_logging(name: str) -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
        )
    return logging.getLogger(name)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def area_range(config: dict, complex_cfg: dict) -> tuple:
    """단지별 전용면적(㎡) 범위. 단지에 값이 없으면 전역 기본값을 쓴다."""
    lo = complex_cfg.get("excl_area_min", config.get("excl_area_min", 0))
    hi = complex_cfg.get("excl_area_max", config.get("excl_area_max", 999))
    return float(lo), float(hi)


def format_price(v) -> str:
    """만원 단위 정수를 '8억 5,000' 형식으로."""
    if v is None:
        return "-"
    v = int(v)
    eok, man = divmod(v, 10000)
    if eok and man:
        return f"{eok}억 {man:,}"
    if eok:
        return f"{eok}억"
    return f"{man:,}만"
