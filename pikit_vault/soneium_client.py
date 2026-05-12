"""Soneium 체인 RPC + Blockscout API + 가격 클라이언트.

기능:
- 잔고 조회 (eth_getBalance via RPC, ETH 단위 + USD 환산)
- 트랜잭션 내역 (Blockscout REST API)
- 토큰 전송 내역 (ERC20)
- ETH/USD 가격 (CoinGecko)

RPC failover: Tenderly URL 우선, 실패 시 official RPC 들 순차 시도.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from .config import (
    BLOCKSCOUT_BASE,
    COINGECKO_PRICE_URL,
    get_rpc_urls,
)


_TIMEOUT = 10  # 초


# ─────────────────────────────────────────────────────────────────
# Stablecoin USD 환산 — 시세가 $0.998 같은 노이즈가 있어도 액면가 그대로 사용.
# 회계상 "1 USDC = $1" 로 다루는 게 직관적 (owner 입장 PNL).
# ─────────────────────────────────────────────────────────────────

_STABLE_SYMBOLS = {"USDC", "USDT", "USDSC", "DAI", "BUSD", "TUSD", "USDD", "FRAX", "GUSD"}


def _is_stablecoin(symbol: str | None, rate: float | None) -> bool:
    if symbol:
        s = symbol.upper().strip()
        if s in _STABLE_SYMBOLS:
            return True
        # USDC.e, sUSD 등 변형도 포착
        if "USD" in s and len(s) <= 8:
            return True
    if rate is not None and 0.97 <= rate <= 1.03:
        return True
    return False


def _token_to_usd(value: float, rate: float | None, symbol: str | None) -> float:
    """토큰 → USD 환산. stablecoin 이면 액면가 그대로."""
    if _is_stablecoin(symbol, rate):
        return value
    if rate is None:
        return 0.0
    return value * rate


# ─────────────────────────────────────────────────────────────────
# RPC — JSON-RPC over HTTPS with failover
# ─────────────────────────────────────────────────────────────────

def _rpc_call(method: str, params: list) -> Any:
    """첫 RPC 부터 순차 시도, 첫 성공 응답 반환. 모두 실패하면 마지막 에러 raise."""
    last_err: Exception | None = None
    for url in get_rpc_urls():
        try:
            r = requests.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                last_err = RuntimeError(f"RPC error from {url}: {data['error']}")
                continue
            return data.get("result")
        except requests.RequestException as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    raise RuntimeError("모든 RPC URL 응답 없음")


def get_balance_wei(address: str) -> int:
    """eth_getBalance — wei 단위 (정수)."""
    result = _rpc_call("eth_getBalance", [address, "latest"])
    return int(result, 16) if isinstance(result, str) else int(result)


def get_balance_eth(address: str) -> float:
    """잔고 → ETH 단위 (소수점)."""
    return get_balance_wei(address) / 1e18


def get_block_number() -> int:
    result = _rpc_call("eth_blockNumber", [])
    return int(result, 16) if isinstance(result, str) else int(result)


# ─────────────────────────────────────────────────────────────────
# Blockscout REST API — 트랜잭션 내역
# ─────────────────────────────────────────────────────────────────

def _bs_get(path: str, params: dict | None = None) -> dict:
    url = f"{BLOCKSCOUT_BASE}{path}"
    r = requests.get(url, params=params or {}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _bs_get_paginated(path: str, max_items: int = 2000, max_pages: int = 50) -> list[dict]:
    """Blockscout next_page_params 자동 따라가기.

    Blockscout 는 한 페이지에 최대 50건씩 줌. max_items 또는 max_pages 도달 시 중단.
    """
    items: list[dict] = []
    params: dict | None = None
    for _ in range(max_pages):
        data = _bs_get(path, params or {})
        page_items = data.get("items") or []
        items.extend(page_items)
        if len(items) >= max_items:
            return items[:max_items]
        next_params = data.get("next_page_params")
        if not next_params:
            return items
        params = next_params
    return items


def get_transactions(address: str, limit: int = 2000) -> list[dict]:
    """주소의 일반 트랜잭션 내역 (native ETH 전송) — 페이지네이션 자동.

    각 row 형식:
      hash, timestamp, from, to, value (wei str), fee, status, ...
    """
    return _bs_get_paginated(f"/addresses/{address}/transactions", max_items=limit)


def get_token_transfers(address: str, limit: int = 2000) -> list[dict]:
    """ERC20 토큰 전송 내역 — 페이지네이션 자동.

    각 row 형식:
      hash, timestamp, from, to, token (symbol/decimals/name), total (value_wei + decimals)
    """
    return _bs_get_paginated(f"/addresses/{address}/token-transfers", max_items=limit)


def get_address_info(address: str) -> dict:
    """주소 메타 — coin_balance, exchange_rate 등."""
    return _bs_get(f"/addresses/{address}")


def get_token_balances(address: str) -> list[dict]:
    """주소가 보유한 ERC20 토큰 목록.

    반환 형식 (per token):
      symbol, name, decimals(int), value_raw(str), value(float), exchange_rate(float|None),
      usd(float), contract(str)
    """
    data = _bs_get(f"/addresses/{address}/tokens", {"type": "ERC-20"})
    items = data.get("items", [])
    out: list[dict] = []
    for it in items:
        tok = it.get("token", {}) or {}
        try:
            decimals = int(tok.get("decimals") or 18)
        except (TypeError, ValueError):
            decimals = 18
        try:
            raw = int(it.get("value") or 0)
        except (TypeError, ValueError):
            raw = 0
        value = raw / (10 ** decimals) if decimals >= 0 else 0.0
        rate_str = tok.get("exchange_rate")
        try:
            rate = float(rate_str) if rate_str not in (None, "", "null") else None
        except (TypeError, ValueError):
            rate = None
        symbol = tok.get("symbol") or "?"
        usd = _token_to_usd(value, rate, symbol)
        out.append({
            "symbol": symbol,
            "name": tok.get("name") or "",
            "decimals": decimals,
            "value_raw": str(raw),
            "value": value,
            "exchange_rate": rate,
            "usd": usd,
            "contract": tok.get("address_hash") or "",
        })
    return out


def get_total_usd(address: str) -> dict:
    """주소의 native ETH + ERC20 USD 합계.

    반환:
      eth(float), eth_usd(float), tokens(list[dict]), tokens_usd(float),
      total_usd(float), eth_usd_rate(float)
    """
    eth = get_balance_eth(address)
    rate = get_eth_usd()
    eth_usd = eth * rate
    tokens = get_token_balances(address)
    tokens_usd = sum(t["usd"] for t in tokens)
    return {
        "eth": eth,
        "eth_usd": eth_usd,
        "eth_usd_rate": rate,
        "tokens": tokens,
        "tokens_usd": tokens_usd,
        "total_usd": eth_usd + tokens_usd,
    }


def get_combined_history(address: str, limit: int = 2000) -> list[dict]:
    """native tx + token transfer 통합 시계열.

    각 row:
      hash, timestamp(str ISO), direction("in"|"out"|"self"),
      counterparty(str), symbol(str), value(float), usd(float|None), kind("native"|"token")
    timestamp 내림차순 정렬.
    """
    addr_lo = (address or "").lower()
    out: list[dict] = []

    # native ETH txs
    try:
        for tx in get_transactions(address, limit=limit):
            ts = tx.get("timestamp") or ""
            fr = ((tx.get("from") or {}).get("hash") or "").lower()
            to = ((tx.get("to") or {}).get("hash") or "").lower()
            try:
                val_wei = int(tx.get("value") or 0)
            except (TypeError, ValueError):
                val_wei = 0
            val_eth = val_wei / 1e18
            if val_eth == 0:
                # gas-only or contract call; skip from PNL view
                continue
            direction = "self" if fr == to else ("in" if to == addr_lo else "out")
            counterparty = fr if direction == "in" else to
            out.append({
                "hash": tx.get("hash") or "",
                "timestamp": ts,
                "direction": direction,
                "counterparty": counterparty,
                "symbol": "ETH",
                "value": val_eth,
                "usd": None,  # 가격 채우기는 호출자가 (현재가 사용 시 간단)
                "kind": "native",
            })
    except Exception:
        pass

    # ERC20 token transfers
    try:
        for tt in get_token_transfers(address, limit=limit):
            ts = tt.get("timestamp") or ""
            fr = ((tt.get("from") or {}).get("hash") or "").lower()
            to = ((tt.get("to") or {}).get("hash") or "").lower()
            tok = tt.get("token") or {}
            try:
                decimals = int(tok.get("decimals") or 18)
            except (TypeError, ValueError):
                decimals = 18
            total = tt.get("total") or {}
            try:
                raw = int(total.get("value") or 0)
            except (TypeError, ValueError):
                raw = 0
            val = raw / (10 ** decimals) if decimals >= 0 else 0.0
            rate_str = tok.get("exchange_rate")
            try:
                rate = float(rate_str) if rate_str not in (None, "", "null") else None
            except (TypeError, ValueError):
                rate = None
            symbol = tok.get("symbol") or "?"
            # stablecoin 이면 액면가, 아니면 시세 환산
            usd = _token_to_usd(val, rate, symbol) if (rate is not None or _is_stablecoin(symbol, rate)) else None
            direction = "self" if fr == to else ("in" if to == addr_lo else "out")
            counterparty = fr if direction == "in" else to
            out.append({
                "hash": tt.get("transaction_hash") or tt.get("tx_hash") or "",
                "timestamp": ts,
                "direction": direction,
                "counterparty": counterparty,
                "symbol": symbol,
                "value": val,
                "usd": usd,
                "kind": "token",
            })
    except Exception:
        pass

    out.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return out


# ─────────────────────────────────────────────────────────────────
# 가격 — ETH/USD via CoinGecko (캐시 60초)
# ─────────────────────────────────────────────────────────────────

_PRICE_CACHE: dict[str, tuple[float, float]] = {}  # key → (timestamp, price)
_PRICE_TTL = 60.0


def get_eth_usd() -> float:
    """ETH/USD 환율. 1분 캐시."""
    cached = _PRICE_CACHE.get("eth_usd")
    if cached and (time.time() - cached[0]) < _PRICE_TTL:
        return cached[1]
    try:
        r = requests.get(COINGECKO_PRICE_URL, timeout=_TIMEOUT)
        r.raise_for_status()
        price = float(r.json()["ethereum"]["usd"])
    except (requests.RequestException, KeyError, ValueError):
        # Fallback: 캐시된 값 있으면 stale 이라도 반환
        if cached:
            return cached[1]
        return 0.0
    _PRICE_CACHE["eth_usd"] = (time.time(), price)
    return price


# ─────────────────────────────────────────────────────────────────
# 편의: 잔고 + USD 한 번에
# ─────────────────────────────────────────────────────────────────

def get_balance_with_usd(address: str) -> dict:
    """잔고 wei/eth + ETH/USD + USD 환산 반환 (native ETH 만)."""
    wei = get_balance_wei(address)
    eth = wei / 1e18
    rate = get_eth_usd()
    usd = eth * rate
    return {
        "wei": wei,
        "eth": eth,
        "usd": usd,
        "eth_usd_rate": rate,
    }


# ─────────────────────────────────────────────────────────────────
# 가격 — 토큰 USD via Blockscout token meta (1분 캐시)
# ─────────────────────────────────────────────────────────────────

_TOKEN_PRICE_CACHE: dict[str, tuple[float, float]] = {}  # symbol → (ts, price)
_TOKEN_PRICE_TTL = 60.0


def get_token_price(symbol: str, contract: str | None = None) -> float | None:
    """Blockscout token meta 에서 exchange_rate 가져오기. 캐시 60초."""
    key = (contract or symbol or "").lower()
    if not key:
        return None
    cached = _TOKEN_PRICE_CACHE.get(key)
    if cached and (time.time() - cached[0]) < _TOKEN_PRICE_TTL:
        return cached[1]
    if not contract:
        return None
    try:
        data = _bs_get(f"/tokens/{contract}")
        rate_str = data.get("exchange_rate")
        if rate_str in (None, "", "null"):
            return None
        rate = float(rate_str)
    except (requests.RequestException, KeyError, ValueError):
        if cached:
            return cached[1]
        return None
    _TOKEN_PRICE_CACHE[key] = (time.time(), rate)
    return rate
