"""Vault 대시보드 설정 — 프로젝트별 지갑, RPC URL, SMTP, 임계값.

환경변수 우선:
  - TENDERLY_RPC_URL    Tenderly 의 Soneium RPC (없으면 official RPC 만 사용)
  - SMTP_HOST/PORT/USER/PASSWORD/FROM  메일 발송 설정 (안 설정 시 stdout 로그만)
  - ALERT_EMAIL_TO      알림 받을 이메일 (default: alex@depsell.io)
"""
from __future__ import annotations

import os


# ─────────────────────────────────────────────────────────────────
# 프로젝트별 지갑 구성
# ─────────────────────────────────────────────────────────────────
# 각 프로젝트는 여러 wallet 을 가질 수 있음.
# wallet 필드:
#   - address              체인 주소
#   - kind                 "revenue" | "reward" — 라벨링용
#   - pnl_mode             "income" (수익) | "treasury" (비용)
#   - alert_threshold_usd  None 또는 임계값 (이하 시 메일 알림)
#   - description          짧은 설명
# 프로젝트 자체:
#   - name                 표시명
#   - description          짧은 설명
#   - coming_soon          True 면 카드는 보이지만 비활성 (지갑 없어도 OK)
# ─────────────────────────────────────────────────────────────────

PROJECTS: dict = {
    "pikit": {
        "name": "PIKIT",
        "description": "PIKIT 메인 프로젝트",
        "wallets": {
            "revenue": {
                "name": "운영 수익 지갑",
                "address": "0x79fc40D88496b6b92EB789d28974dd6C162e8D6E",
                "description": "PIKIT 운영 수익이 모이는 지갑",
                "kind": "revenue",
                "pnl_mode": "income",
                "alert_threshold_usd": None,
            },
            "reward_vault": {
                "name": "유저 리워드 Vault",
                "address": "0xee5c5c0f3817563d924c563294b8d4c56d3bd722",
                "description": "유저에게 지급되는 리워드 컨트랙트",
                "kind": "reward",
                "pnl_mode": "treasury",
                "alert_threshold_usd": 300,
            },
        },
    },
    "press_a": {
        "name": "Press A",
        "description": "Press A 프로젝트",
        "wallets": {
            "revenue": {
                "name": "운영 수익 지갑",
                "address": "",  # TODO: 주소 등록 필요
                "description": "Press A 운영 수익",
                "kind": "revenue",
                "pnl_mode": "income",
                "alert_threshold_usd": None,
            },
            "reward_pool": {
                "name": "리워드 풀",
                "address": "",  # TODO: 주소 등록 필요
                "description": "Press A 리워드 지급 풀",
                "kind": "reward",
                "pnl_mode": "treasury",
                "alert_threshold_usd": 300,
            },
        },
    },
    "pnyx": {
        "name": "Pnyx",
        "description": "Pnyx — 준비 중",
        "coming_soon": True,
    },
}


def iter_active_wallets():
    """모든 프로젝트의 활성 지갑 순회 — (project_key, wallet_key, project, wallet)."""
    for pkey, proj in PROJECTS.items():
        if proj.get("coming_soon"):
            continue
        for wkey, wallet in (proj.get("wallets") or {}).items():
            if not (wallet.get("address") or "").strip():
                continue
            yield pkey, wkey, proj, wallet


# 호환성 — 기존 코드/cron 이 WALLETS 를 쓰면 PIKIT 만 노출 (마이그레이션 brige)
WALLETS = {
    f"{pkey}__{wkey}" if pkey != "pikit" else wkey: wallet
    for pkey, wkey, _proj, wallet in iter_active_wallets()
}


# ─────────────────────────────────────────────────────────────────
# Soneium 체인 정보
# ─────────────────────────────────────────────────────────────────
SONEIUM_CHAIN_ID = 1868
SONEIUM_NATIVE_SYMBOL = "ETH"

OFFICIAL_RPC_URLS = [
    "https://rpc.soneium.org",
    "https://soneium.drpc.org",
]


def get_rpc_urls() -> list[str]:
    """RPC URL 우선순위 — Tenderly 있으면 최상위. wss → https 자동 변환."""
    urls: list[str] = []
    tenderly = os.environ.get("TENDERLY_RPC_URL", "").strip()
    if tenderly:
        if tenderly.startswith("wss://"):
            tenderly = "https://" + tenderly[len("wss://"):]
        elif tenderly.startswith("ws://"):
            tenderly = "http://" + tenderly[len("ws://"):]
        urls.append(tenderly)
    urls.extend(OFFICIAL_RPC_URLS)
    return urls


BLOCKSCOUT_BASE = "https://soneium.blockscout.com/api/v2"

COINGECKO_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=ethereum&vs_currencies=usd"
)

# ─────────────────────────────────────────────────────────────────
# 알림 설정
# ─────────────────────────────────────────────────────────────────
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "alex@depsell.io").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER).strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")


def is_smtp_configured() -> bool:
    return all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])


# ─────────────────────────────────────────────────────────────────
# 캐시 / 상태 파일
# ─────────────────────────────────────────────────────────────────
def cache_dir() -> str:
    env = os.environ.get("PIKIT_CACHE_DIR", "").strip()
    if env:
        return env
    container = "/app/cache"
    if os.path.exists(container) and os.access(container, os.W_OK):
        return container
    return "."
