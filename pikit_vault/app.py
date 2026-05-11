"""PIKIT Vault 대시보드 — Soneium 운영 지갑 모니터링.

화면:
  1) 메인 — 2 지갑 카드 (잔고, USD, 24h 변동)
  2) 상세 — 카운터파티 분포, 시간대 입출금, PNL

실행:
  streamlit run pikit_vault/app.py --server.port 8502

Streamlit 이 스크립트의 부모 폴더만 sys.path 에 넣으므로 (pikit_vault/),
패키지 자체를 못 찾는 문제 회피용으로 /app 을 직접 추가.
"""
from __future__ import annotations

import os
import sys

# pikit_vault 패키지를 절대 import 가능하게 — 스크립트 부모의 부모 (= /app) 를 추가.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from pikit_vault.config import ALERT_EMAIL_TO, WALLETS, is_smtp_configured
from pikit_vault.soneium_client import (
    get_combined_history,
    get_total_usd,
)


st.set_page_config(
    page_title="PIKIT Vault — Soneium",
    page_icon="🏦",
    layout="wide",
)


# ─────────────────────────────────────────────────────────────────
# 캐시 — 60초 단위로 자동 갱신
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def cached_total_usd(address: str) -> dict:
    return get_total_usd(address)


@st.cache_data(ttl=60, show_spinner=False)
def cached_history(address: str, limit: int = 100) -> list[dict]:
    return get_combined_history(address, limit=limit)


# ─────────────────────────────────────────────────────────────────
# 메인 / 상세 라우팅 (query param)
# ─────────────────────────────────────────────────────────────────

qs = st.query_params
selected = qs.get("wallet")
if isinstance(selected, list):
    selected = selected[0] if selected else None

if selected and selected in WALLETS:
    # 상세 페이지
    wallet = WALLETS[selected]
    page = "detail"
else:
    wallet = None
    page = "home"


# ─────────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏦 PIKIT Vault")
    st.caption("Soneium 체인 운영 지갑 모니터")
    st.markdown("---")
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"캐시 TTL: 60초")
    st.markdown("---")
    st.caption("**알림 설정**")
    st.caption(f"수신: `{ALERT_EMAIL_TO}`")
    smtp_ok = is_smtp_configured()
    st.caption(f"SMTP: {'✅ 설정됨' if smtp_ok else '❌ 미설정 (stdout 로그만)'}")
    if page == "detail":
        st.markdown("---")
        if st.button("← 메인으로", use_container_width=True):
            st.query_params.clear()
            st.rerun()


# ─────────────────────────────────────────────────────────────────
# 메인 페이지 — 2 지갑 카드
# ─────────────────────────────────────────────────────────────────
def render_home():
    st.title("PIKIT Vault")
    st.caption(f"Soneium L2 · 갱신 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cols = st.columns(len(WALLETS))
    for col, (key, w) in zip(cols, WALLETS.items()):
        with col:
            try:
                info = cached_total_usd(w["address"])
                total = info["total_usd"]
                tokens = info["tokens"]
            except Exception as e:
                st.error(f"❌ RPC 실패: {e}")
                continue

            # 임계 미달이면 경고 배지
            threshold = w.get("alert_threshold_usd")
            warn = threshold is not None and total < threshold

            border_color = "#d32f2f" if warn else w.get("color", "#888")
            badge = "⚠️ 임계 미달" if warn else ""

            st.markdown(
                f"""
                <div style="border:2px solid {border_color}; border-radius:12px; padding:18px 22px; background:rgba(255,255,255,0.02);">
                  <div style="font-size:20px; font-weight:600;">
                    {w.get('icon', '')} {w['name']}
                  </div>
                  <div style="font-size:12px; color:#888; margin:6px 0 12px 0; font-family:monospace;">
                    {w['address'][:10]}…{w['address'][-8:]}
                  </div>
                  <div style="font-size:36px; font-weight:700; color:{border_color};">
                    ${total:,.2f}
                  </div>
                  <div style="font-size:13px; color:#aaa; margin-top:6px;">
                    {w.get('description', '')}
                  </div>
                  {f'<div style="margin-top:10px; color:#d32f2f; font-weight:600;">{badge} (임계: ${threshold})</div>' if warn else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 토큰 보유 미니 리스트
            if tokens:
                st.caption("**보유 토큰**")
                for t in tokens[:5]:
                    st.write(
                        f"`{t['symbol']:6s}`  {t['value']:>10,.4f}  "
                        f"(${t['usd']:,.2f})"
                    )
            else:
                st.caption("토큰 없음 (native ETH 만)")

            st.markdown("")
            if st.button("📊 상세 보기", key=f"detail_{key}", use_container_width=True, type="primary"):
                st.query_params["wallet"] = key
                st.rerun()


# ─────────────────────────────────────────────────────────────────
# 상세 페이지 — 카운터파티, 시계열, PNL
# ─────────────────────────────────────────────────────────────────
def render_detail(key: str, w: dict):
    st.title(f"{w.get('icon', '')} {w['name']}")
    st.caption(f"주소: `{w['address']}`")

    # 잔고 박스
    try:
        info = cached_total_usd(w["address"])
    except Exception as e:
        st.error(f"RPC 실패: {e}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("총 USD", f"${info['total_usd']:,.2f}")
    c2.metric("ETH", f"{info['eth']:.6f}", help=f"${info['eth_usd']:,.2f}")
    c3.metric("토큰 USD", f"${info['tokens_usd']:,.2f}")

    if info["tokens"]:
        with st.expander("보유 토큰 전체", expanded=False):
            tdf = pd.DataFrame(info["tokens"])
            tdf = tdf[["symbol", "name", "value", "exchange_rate", "usd", "contract"]]
            tdf.columns = ["심볼", "이름", "잔량", "단가($)", "USD", "컨트랙트"]
            st.dataframe(tdf, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 거래 내역
    st.subheader("📜 거래 내역")
    try:
        hist = cached_history(w["address"], limit=100)
    except Exception as e:
        st.error(f"내역 조회 실패: {e}")
        return

    if not hist:
        st.info("거래 내역 없음")
        return

    df = pd.DataFrame(hist)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp", ascending=False)

    # 기간 필터
    col_a, col_b = st.columns([1, 3])
    period = col_a.selectbox(
        "기간",
        ["전체", "최근 24시간", "최근 7일", "최근 30일"],
        index=0,
    )
    now = datetime.now(timezone.utc)
    cutoff: datetime | None = None
    if period == "최근 24시간":
        cutoff = now - timedelta(hours=24)
    elif period == "최근 7일":
        cutoff = now - timedelta(days=7)
    elif period == "최근 30일":
        cutoff = now - timedelta(days=30)
    if cutoff is not None:
        df = df[df["timestamp"] >= cutoff]

    if df.empty:
        st.info("기간 내 거래 없음")
        return

    # PNL 모드 — 지갑 목적에 따라 계산식이 다름.
    # income: 수익 계정. PNL = in - out (양수=수익)
    # treasury: 비용 계정. PNL = -out (음수=내 돈 지출됨)
    pnl_mode = wallet.get("pnl_mode", "income")

    total_in_usd = df.loc[df["direction"] == "in", "usd"].fillna(0).sum()
    total_out_usd = df.loc[df["direction"] == "out", "usd"].fillna(0).sum()

    if pnl_mode == "treasury":
        # 비용 계정: 충전(in)은 owner 가 자기 돈 넣은 것 = PNL 영향 0,
        # 지급(out)만 owner 입장에서 손실로 잡힘.
        pnl_usd = -total_out_usd
        in_label = "총 충전 (입금)"
        out_label = "총 지급 (리워드)"
        pnl_label = "손익 (Owner PNL)"
        # 시계열 PNL 누적: 지급액만 음수로 누적.
        df["usd_signed"] = df.apply(
            lambda r: -(r["usd"] or 0) if r["direction"] == "out" else 0,
            axis=1,
        )
    else:
        # 수익 계정: in - out = 수익
        pnl_usd = total_in_usd - total_out_usd
        in_label = "입금 USD"
        out_label = "출금 USD"
        pnl_label = "순 PNL"
        df["usd_signed"] = df.apply(
            lambda r: (r["usd"] or 0) * (1 if r["direction"] == "in" else -1 if r["direction"] == "out" else 0),
            axis=1,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(in_label, f"${total_in_usd:,.2f}", f"{(df['direction']=='in').sum()}건")
    m2.metric(out_label, f"${total_out_usd:,.2f}", f"{(df['direction']=='out').sum()}건")
    m3.metric(pnl_label, f"${pnl_usd:,.2f}")
    m4.metric("거래 수", f"{len(df):,}건")

    # 카운터파티 집계
    st.markdown("---")
    st.subheader("👥 카운터파티")

    # 입금/출금 별
    cp_in = (
        df[df["direction"] == "in"]
        .groupby("counterparty")
        .agg(건수=("hash", "count"), 합계=("value", "sum"), USD합계=("usd", "sum"))
        .sort_values("USD합계", ascending=False)
        .head(20)
    )
    cp_out = (
        df[df["direction"] == "out"]
        .groupby("counterparty")
        .agg(건수=("hash", "count"), 합계=("value", "sum"), USD합계=("usd", "sum"))
        .sort_values("USD합계", ascending=False)
        .head(20)
    )

    tab_in, tab_out = st.tabs([f"📥 입금처 ({len(cp_in)}개)", f"📤 출금처 ({len(cp_out)}개)"])
    with tab_in:
        if cp_in.empty:
            st.info("입금 없음")
        else:
            df_show = cp_in.reset_index()
            df_show["USD합계"] = df_show["USD합계"].round(2)
            df_show["합계"] = df_show["합계"].round(4)
            st.dataframe(df_show, use_container_width=True, hide_index=True)
    with tab_out:
        if cp_out.empty:
            st.info("출금 없음")
        else:
            df_show = cp_out.reset_index()
            df_show["USD합계"] = df_show["USD합계"].round(2)
            df_show["합계"] = df_show["합계"].round(4)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # 시계열 — 일자별 또는 시간대별
    st.markdown("---")
    st.subheader("📈 시계열 PNL")

    df_ts = df.copy()
    # 기간에 따라 bin 자동
    if period == "최근 24시간":
        df_ts["bucket"] = df_ts["timestamp"].dt.floor("h")
        bin_label = "시간"
    else:
        df_ts["bucket"] = df_ts["timestamp"].dt.floor("D")
        bin_label = "일자"

    # 입금/출금 은 모드 무관하게 raw 합계 — PNL 만 mode 별로 다름 (usd_signed)
    df_ts["usd_in"] = df_ts.apply(
        lambda r: (r["usd"] or 0) if r["direction"] == "in" else 0, axis=1,
    )
    df_ts["usd_out"] = df_ts.apply(
        lambda r: (r["usd"] or 0) if r["direction"] == "out" else 0, axis=1,
    )
    agg = (
        df_ts.groupby("bucket")
        .agg(입금=("usd_in", "sum"),
             출금=("usd_out", "sum"),
             PNL=("usd_signed", "sum"))
        .reset_index()
        .sort_values("bucket")
    )
    agg["누적PNL"] = agg["PNL"].cumsum()

    if agg.empty:
        st.info("시계열 데이터 없음")
    else:
        st.line_chart(agg.set_index("bucket")[["누적PNL"]])
        with st.expander(f"{bin_label}별 상세", expanded=False):
            display = agg.copy()
            display.columns = [bin_label, "입금($)", "출금($)", "PNL($)", "누적PNL($)"]
            for c in display.columns[1:]:
                display[c] = display[c].round(2)
            st.dataframe(display, use_container_width=True, hide_index=True)

    # 거래 내역 테이블
    st.markdown("---")
    st.subheader("📋 거래 원장")
    show = df.copy()
    show["timestamp"] = show["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    show = show[["timestamp", "direction", "symbol", "value", "usd", "counterparty", "hash"]]
    show.columns = ["시각", "방향", "토큰", "수량", "USD", "카운터파티", "tx"]
    show["USD"] = show["USD"].fillna(0).round(2)
    show["수량"] = show["수량"].round(4)
    st.dataframe(show, use_container_width=True, hide_index=True, height=400)


# ─────────────────────────────────────────────────────────────────
# 라우팅
# ─────────────────────────────────────────────────────────────────
if page == "home":
    render_home()
else:
    render_detail(selected, wallet)
