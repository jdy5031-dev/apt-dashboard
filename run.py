#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
맥(launchd)에서 실행: 네이버 호가 수집 → state/asking.json 내보내기 → GitHub 에 push.

네이버가 GitHub 서버 IP를 막아서 호가만 맥에서 모은다. 실거래 수집과 대시보드 생성은
GitHub Actions(.github/workflows/update.yml)가 맡고, asking.json 이 push 되면 대시보드를 다시 만든다.
--no-publish 면 push 하지 않고 docs/index.html 을 로컬에서 만든다(미리보기).
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
from common import ASKING_STATE, BASE_DIR, load_config, setup_logging

log = setup_logging("run")


def git(*args):
    # launchd 에는 터미널이 없으므로 인증 프롬프트를 띄우지 말고 바로 실패하게 한다
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, env=env, timeout=120)


def pull() -> bool:
    """GitHub Actions 가 올린 실거래·대시보드를 받아 온다. 작업 중인 수정은 autostash 로 보존."""
    r = git("pull", "--rebase", "--autostash")
    if r.returncode != 0:
        log.error("git pull 실패: %s", (r.stderr or r.stdout).strip())
        git("rebase", "--abort")
    return r.returncode == 0


def publish():
    """state/asking.json 만 커밋해서 push 한다. 다른 파일은 GitHub Actions 만 쓰므로 rebase 충돌이 없다."""
    git("add", str(ASKING_STATE))
    if git("diff", "--cached", "--quiet", "--", str(ASKING_STATE)).returncode != 0:
        r = git("commit", "-m", "호가 갱신", "--", str(ASKING_STATE))
        if r.returncode != 0:
            log.error("커밋 실패: %s", (r.stderr or r.stdout).strip())
            return
    # 이번에 커밋할 게 없어도, 지난번에 push 못 한 커밋이 남아 있을 수 있다
    for attempt in range(3):
        r = git("push")
        if r.returncode == 0:
            log.info("게시 완료")
            return
        log.warning("push 실패, 받아 와서 다시 시도: %s", (r.stderr or r.stdout).strip())
        if not pull():
            break
    log.error("게시 실패 (다음 실행 때 다시 시도)")


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
    p = argparse.ArgumentParser(description="호가 수집 + GitHub 게시 (맥)")
    p.add_argument("--skip-listings", action="store_true", help="네이버 호가 수집 생략")
    p.add_argument("--trades", action="store_true", help="실거래도 여기서 수집(보통은 GitHub Actions 가 함)")
    p.add_argument("--no-publish", action="store_true", help="GitHub 게시 대신 docs/index.html 을 로컬에서 생성")
    args = p.parse_args()
    publish_on = load_config().get("publish_git") and not args.no_publish
    ok = True
    if not wait_for_network():
        log.error("인터넷에 연결되지 않아 이번 회차를 건너뜀")
        sys.exit(1)

    if publish_on:
        pull()

    if not args.skip_listings:
        try:
            collect_listings.run()
        except Exception:
            log.exception("호가 수집 중 오류")
            ok = False

    if args.trades:
        try:
            collect_trades.run()
        except (collect_trades.ApiError, requests.RequestException) as e:
            log.error("실거래 수집 실패: %s", e)
            ok = False
        except Exception:
            log.exception("실거래 수집 중 오류")
            ok = False

    build_dashboard.export_asking()
    if publish_on:
        publish()
    else:
        build_dashboard.build()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
