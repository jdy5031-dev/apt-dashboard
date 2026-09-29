#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한 번에 실행: 호가 수집 → 실거래 수집 → 대시보드 생성 → (설정 시) GitHub 에 게시.
작업 스케줄러/launchd 에는 이 파일만 등록하면 된다.
"""

import argparse
import os
import socket
import subprocess
import sys
import time

import requests

import build_dashboard
import collect_listings
import collect_trades
from common import BASE_DIR, load_config, setup_logging

log = setup_logging("run")


def publish():
    """docs/index.html 이 바뀌었으면 커밋해서 push 한다(GitHub Pages 용)."""
    def git(*args):
        # launchd 에는 터미널이 없으므로 인증 프롬프트를 띄우지 말고 바로 실패하게 한다
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, env=env, timeout=120)

    git("add", "docs/index.html")
    if git("diff", "--cached", "--quiet").returncode == 0:
        log.info("게시: 변경 없음")
        return
    r = git("commit", "-m", "대시보드 갱신")
    if r.returncode == 0:
        r = git("push")
    if r.returncode != 0:
        log.error("게시 실패: %s", (r.stderr or r.stdout).strip())
    else:
        log.info("게시 완료")


def wait_for_network(timeout_sec: int = 180) -> bool:
    """맥을 켠 직후에는 인터넷 연결 전에 실행되기도 하므로, 연결될 때까지 잠깐 기다린다."""
    deadline = time.time() + timeout_sec
    while True:
        try:
            socket.getaddrinfo("fin.land.naver.com", 443)
            return True
        except OSError:
            if time.time() >= deadline:
                return False
            time.sleep(10)


def main():
    p = argparse.ArgumentParser(description="수집 + 대시보드 생성")
    p.add_argument("--skip-listings", action="store_true", help="네이버 호가 수집 생략")
    p.add_argument("--skip-trades", action="store_true", help="실거래 수집 생략")
    p.add_argument("--no-publish", action="store_true", help="GitHub 게시 생략")
    args = p.parse_args()
    ok = True
    if not wait_for_network():
        log.error("인터넷에 연결되지 않아 이번 회차를 건너뜀")
        sys.exit(1)

    if not args.skip_listings:
        try:
            collect_listings.run()
        except Exception:
            log.exception("호가 수집 중 오류")
            ok = False

    if not args.skip_trades:
        try:
            collect_trades.run()
        except (collect_trades.ApiError, requests.RequestException) as e:
            log.error("실거래 수집 실패: %s", e)
            ok = False
        except Exception:
            log.exception("실거래 수집 중 오류")
            ok = False

    build_dashboard.build()

    if load_config().get("publish_git") and not args.no_publish:
        publish()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
