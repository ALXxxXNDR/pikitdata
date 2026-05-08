"""
PIKITbot 대시보드 API 클라이언트 — Tailscale 등으로 접근 가능한 호스트의 PIKITbot
서버에 직접 HTTP 호출. 실시간 상태 조회 + CRUD + 봇 시작/중지.

설정: 환경변수 PIKIT_BOT_API_URL 로 base URL 지정.
   예: http://100.123.168.53:4317

미설정 시 모든 함수가 None / False 반환 → 호출자가 file 기반 fallback 사용 가능.
"""
from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


# ---------------------------------------------------------------------------
# 환경설정
# ---------------------------------------------------------------------------

API_URL = os.environ.get("PIKIT_BOT_API_URL", "").strip().rstrip("/")
TIMEOUT_GET = 5  # 읽기 timeout (초)
TIMEOUT_POST = 15  # 쓰기 timeout (지갑 생성 등 시간 걸리는 것 대비)


def is_configured() -> bool:
    """API URL 환경변수가 설정돼 있나."""
    return bool(API_URL)


def health_check() -> tuple[bool, str]:
    """API 연결 가능한지 ping. 반환: (ok, 메시지)."""
    if not is_configured():
        return False, "PIKIT_BOT_API_URL 환경변수 미설정"
    try:
        r = requests.get(f"{API_URL}/api/state", timeout=3)
        if r.status_code == 200:
            return True, f"연결 OK ({API_URL})"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectTimeout:
        return False, "Connection timeout — Tailscale 또는 PIKITbot 서버 미실행"
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection 실패 — {type(e).__name__}"
    except requests.RequestException as e:
        return False, f"오류: {e}"


# ---------------------------------------------------------------------------
# 읽기 — Streamlit cache 적용 (TTL 짧게)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=20, show_spinner=False)
def get_state() -> dict[str, Any] | None:
    """state.json 전체 (sanitized — privateKey 제외된 응답)."""
    if not is_configured():
        return None
    try:
        r = requests.get(f"{API_URL}/api/state", timeout=TIMEOUT_GET)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


@st.cache_data(ttl=15, show_spinner=False)
def get_track_health(track: str | None = None) -> dict[str, Any] | None:
    """트랙 health (트랙 미지정 시 전체)."""
    if not is_configured():
        return None
    try:
        url = f"{API_URL}/api/track-health"
        if track:
            url += f"?track={track}"
        r = requests.get(url, timeout=TIMEOUT_GET)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def get_export_addresses(track: str) -> str | None:
    """트랙의 활성 봇 주소들 — 'label\\taddress' 텍스트."""
    if not is_configured():
        return None
    try:
        r = requests.get(
            f"{API_URL}/api/export-addresses",
            params={"track": track},
            timeout=TIMEOUT_GET,
        )
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# 쓰기 — 캐시 무효화 + 결과 반환
# ---------------------------------------------------------------------------

def _invalidate_cache():
    """모든 GET 캐시 클리어 (쓰기 직후 호출)."""
    try:
        get_state.clear()
        get_track_health.clear()
    except Exception:
        pass


def create_set_auto(name: str) -> tuple[bool, dict | str]:
    """12개 지갑 자동 생성 + 새 set 만들기.

    반환: (성공, 응답 dict 또는 에러 메시지)
    """
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/sets/auto-create",
            json={"name": name},
            timeout=TIMEOUT_POST,
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, r.json()
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


def update_strategies(set_id: str, strategies: list[str]) -> tuple[bool, str]:
    """세트의 12 봇 전략 일괄 업데이트."""
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/sets/strategies",
            json={"setId": set_id, "strategies": strategies},
            timeout=TIMEOUT_POST,
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, "OK"
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


def update_deployment(
    track: str,
    set_ids: list[str],
    excluded_bot_ids: list[str] | None = None,
) -> tuple[bool, str]:
    """트랙 배포 설정 변경 — 어떤 set 가 활성인지 + 어떤 봇만 제외할지."""
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/deployments",
            json={
                "track": track,
                "setIds": set_ids,
                "excludedBotIds": excluded_bot_ids or [],
            },
            timeout=TIMEOUT_POST,
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, "OK"
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


def start_track(track: str) -> tuple[bool, str]:
    """트랙의 봇 일괄 시작 (SSH 통한 원격 실행)."""
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/start",
            json={"track": track},
            timeout=30,  # SSH 핸드쉐이크 시간 여유
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, "OK"
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


def stop_track(track: str) -> tuple[bool, str]:
    """트랙의 봇 일괄 중지."""
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/stop",
            json={"track": track},
            timeout=30,
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, "OK"
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


def toggle_bot(track: str, bot_id: str, enabled: bool) -> tuple[bool, str]:
    """개별 봇 ON/OFF (트랙 재시작 없이 다음 cycle 부터 반영)."""
    if not is_configured():
        return False, "API 미설정"
    try:
        r = requests.post(
            f"{API_URL}/api/toggle-bot",
            json={"track": track, "botId": bot_id, "enabled": enabled},
            timeout=TIMEOUT_POST,
        )
        r.raise_for_status()
        _invalidate_cache()
        return True, "OK"
    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except requests.RequestException as e:
        return False, f"요청 실패: {e}"


# ---------------------------------------------------------------------------
# PNL 통합 — file 기반과 동일 인터페이스
# ---------------------------------------------------------------------------

def get_pnl_compatible_sets(state: dict, track: str) -> dict[str, dict]:
    """API 응답의 state 를 PNL 호환 형식으로 변환.

    bot_state.get_pnl_compatible_sets 와 동일 인터페이스. 트랙의 deployments.setIds
    안에 있는 세트만 포함.

    반환:
      { "세트이름": { "wallets": ["0x...", ...] }, ... }
    """
    if not state:
        return {}
    deployments = state.get("deployments", {}) or {}
    track_cfg = deployments.get(track, {}) or {}
    set_ids = set(track_cfg.get("setIds", []) or [])
    sets = state.get("sets", []) or []
    out: dict[str, dict] = {}
    for s in sets:
        if s.get("id") in set_ids:
            wallets = [
                b.get("address", "").lower()
                for b in s.get("bots", [])
                if b.get("address")
            ]
            out[s.get("name", s.get("id"))] = {"wallets": wallets}
    return out
