"""PIKIT Vault 대시보드 설정 — 지갑 주소, RPC URL, 임계값.

환경변수 우선:
  - TENDERLY_RPC_URL    Tenderly 의 Soneium RPC (없으면 official RPC 만 사용)
  - SMTP_HOST/PORT/USER/PASSWORD/FROM  메일 발송 설정 (안 설정 시 stdout 로그만)
  - ALERT_EMAIL_TO      알림 받을 이메일 (default: alex@depsell.io)
"""
from __future__ import annotations

import os


# ─────────────────────────────────────────────────────────────────
# 추적할 지갑
# ─────────────────────────────────────────────────────────────────
WALLETS = {
    "revenue": {
        "name": "운영 수익 지갑",
        "address": "0x79fc40D88496b6b92EB789d28974dd6C162e8D6E",
        "description": "PIKIT 운영 수익이 모이는 지갑",
        "alert_threshold_usd": None,  # 알림 없음
        "color": "#4caf50",  # 초록
        "icon": "💰",
    },
    "reward_vault": {
        "name": "유저 리워드 Vault",
        "address": "0xee5c5c0f3817563d924c563294b8d4c56d3bd722",
        "description": "유저에게 지급되는 리워드 컨트랙트",
        "alert_threshold_usd": 300,  # $300 이하 시 알림
        "color": "#f5b800",  # 황금
        "icon": "🎁",
    },
}

WALLET_LIST = list(WALLETS.keys())

# ─────────────────────────────────────────────────────────────────
# Soneium 체인 정보
# ─────────────────────────────────────────────────────────────────
SONEIUM_CHAIN_ID = 1868
SONEIUM_NATIVE_SYMBOL = "ETH"

# RPC 엔드포인트들 — 첫 번째 가능한 거부터 시도 (failover).
OFFICIAL_RPC_URLS = [
    "https://rpc.soneium.org",
    "https://soneium.drpc.org",
]


def get_rpc_urls() -> list[str]:
    """RPC URL 우선순위 리스트 — Tenderly 가 있으면 우선.

    wss:// 형태가 들어와도 같은 호스트의 https:// 엔드포인트로 자동 변환
    (Tenderly 게이트웨이는 두 프로토콜이 같은 path 를 공유).
    """
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


# Blockscout REST API (Soneium 공식 explorer)
BLOCKSCOUT_BASE = "https://soneium.blockscout.com/api/v2"

# CoinGecko (ETH/USD) — 무료 tier, 30 calls/min
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
    """캐시 디렉토리 — alert state, tx cache 등."""
    env = os.environ.get("PIKIT_CACHE_DIR", "").strip()
    if env:
        return env
    container = "/app/cache"
    if os.path.exists(container) and os.access(container, os.W_OK):
        return container
    return "."
