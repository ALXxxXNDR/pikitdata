"""PIKIT Vault — 잔고 임계 알림.

각 지갑에 `alert_threshold_usd` 가 설정되어 있고 현재 잔고가 그 이하면 메일 발송.

중복 알림 방지:
  - cache_dir()/vault_alert_state.json 에 마지막 알림 시각 저장
  - 같은 지갑에 대해 ALERT_COOLDOWN_HOURS (기본 6h) 내 재발송 안 함
  - 잔고가 임계 위로 회복되면 상태 리셋

실행:
  python -m pikit_vault.alert                       # 1회 체크 후 종료
  python -m pikit_vault.alert --force               # 쿨다운 무시 (테스트용)
  python -m pikit_vault.alert --daemon              # 무한 루프, ALERT_INTERVAL_SECONDS (기본 60s) 마다 체크
  python -m pikit_vault.alert --daemon --interval 60
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .config import (
    ALERT_EMAIL_TO,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
    WALLETS,
    cache_dir,
    is_smtp_configured,
)
from .soneium_client import get_total_usd


ALERT_COOLDOWN_HOURS = float(os.environ.get("ALERT_COOLDOWN_HOURS", "6"))
_STATE_FILE = "vault_alert_state.json"


def _state_path() -> Path:
    return Path(cache_dir()) / _STATE_FILE


def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def _send_email(subject: str, body: str) -> bool:
    if not is_smtp_configured():
        print(f"[ALERT][stdout] {subject}", flush=True)
        print(body, flush=True)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = ALERT_EMAIL_TO
    msg.set_content(body)

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        print(f"[ALERT][error] SMTP 전송 실패: {e}", file=sys.stderr, flush=True)
        return False


def check_and_alert(force: bool = False) -> int:
    """모든 지갑 잔고 확인 + 임계 미달 시 알림. 발송한 알림 수 반환."""
    state = _load_state()
    now = time.time()
    cooldown = ALERT_COOLDOWN_HOURS * 3600
    sent = 0

    for key, w in WALLETS.items():
        threshold = w.get("alert_threshold_usd")
        if threshold is None:
            continue

        try:
            info = get_total_usd(w["address"])
        except Exception as e:
            print(f"[ALERT][error] {key} RPC 실패: {e}", file=sys.stderr, flush=True)
            continue

        total = info["total_usd"]
        last = state.get(key, {})
        last_ts = float(last.get("last_alert_ts") or 0)

        if total >= threshold:
            # 회복 — 상태 리셋
            if last_ts:
                print(f"[ALERT] {key}: 잔고 회복 (${total:.2f} >= ${threshold}) — 상태 리셋")
                state.pop(key, None)
            continue

        # 임계 미달
        if not force and last_ts and (now - last_ts) < cooldown:
            wait_h = (cooldown - (now - last_ts)) / 3600
            print(f"[ALERT] {key}: 쿨다운 중 ({wait_h:.1f}h 남음) — 스킵")
            continue

        subject = f"🚨 PIKIT {w['name']} 잔고 ${total:,.2f} (< ${threshold})"
        token_lines = "\n".join(
            f"  - {t['symbol']}: {t['value']:,.4f} (${t['usd']:,.2f})"
            for t in info["tokens"]
        ) or "  (보유 토큰 없음)"

        body = f"""PIKIT Vault 잔고 알림

지갑: {w['name']}
주소: {w['address']}
설명: {w.get('description', '')}

현재 총 USD: ${total:,.2f}
임계값: ${threshold}
부족분: ${threshold - total:,.2f}

보유 내역:
  - ETH: {info['eth']:.6f} (${info['eth_usd']:,.2f})
{token_lines}

탐색기: https://soneium.blockscout.com/address/{w['address']}
대시보드: https://despell.synology.me/pikit/?wallet={key}

발송 시각: {datetime.now(timezone.utc).isoformat()}
"""

        ok = _send_email(subject, body)
        state[key] = {
            "last_alert_ts": now,
            "last_total": total,
            "last_threshold": threshold,
            "sent_ok": ok,
        }
        if ok:
            sent += 1
            print(f"[ALERT] {key}: 메일 전송 완료 → {ALERT_EMAIL_TO}")
        else:
            print(f"[ALERT] {key}: stdout 로그만 (SMTP 미설정 or 실패)")

    _save_state(state)
    return sent


def _run_daemon(interval: float) -> int:
    """무한 루프 — interval 초 마다 체크. SIGTERM/SIGINT 에서 깨끗이 종료."""
    import signal

    stop = {"flag": False}

    def _handler(signum, frame):
        print(f"[ALERT][daemon] signal {signum} 받음 — 종료 준비", flush=True)
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)

    print(f"[ALERT][daemon] 시작 — {interval:.0f}s 간격, 쿨다운 {ALERT_COOLDOWN_HOURS}h", flush=True)
    while not stop["flag"]:
        try:
            sent = check_and_alert(force=False)
            if sent:
                print(f"[ALERT][daemon] {datetime.now(timezone.utc).isoformat()} 발송 {sent}건", flush=True)
        except Exception as e:
            # 한 번의 오류가 데몬을 죽이지 않게.
            print(f"[ALERT][daemon][error] {type(e).__name__}: {e}", file=sys.stderr, flush=True)

        # 깨어있는 sleep — 신호 받으면 즉시 빠져나옴.
        slept = 0.0
        while slept < interval and not stop["flag"]:
            time.sleep(min(1.0, interval - slept))
            slept += 1.0

    print("[ALERT][daemon] 종료", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PIKIT Vault 잔고 임계 알림")
    parser.add_argument("--force", action="store_true", help="쿨다운 무시하고 즉시 발송 (테스트용)")
    parser.add_argument("--daemon", action="store_true", help="무한 루프 모드 — interval 초 마다 체크")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("ALERT_INTERVAL_SECONDS", "60")),
        help="daemon 모드 체크 주기 (초). env ALERT_INTERVAL_SECONDS 로도 설정.",
    )
    args = parser.parse_args(argv)

    if args.daemon:
        return _run_daemon(args.interval)

    sent = check_and_alert(force=args.force)
    print(f"[ALERT] 발송: {sent} 건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
