"""Vault 대시보드 — 멀티 프로젝트 (PIKIT / Press A / Pnyx) 운영 지갑 모니터링.

URL 라우팅:
  /vault/                          → 기본 (첫 프로젝트)
  /vault/?project=pikit            → PIKIT 프로젝트 보기
  /vault/?project=pikit&wallet=X   → PIKIT 의 wallet X 상세

실행:
  streamlit run pikit_vault/app.py --server.port 8502 --server.baseUrlPath /vault

shadcn 3-색 디자인:
  background: #0a0a0a (zinc-950)
  foreground: #fafafa (zinc-50)
  accent:     #10b981 (emerald-500)
"""
from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from pikit_vault.config import (
    ALERT_EMAIL_TO,
    PROJECTS,
    is_smtp_configured,
)
from pikit_vault.soneium_client import (
    get_combined_history,
    get_total_usd,
)


st.set_page_config(
    page_title="Vault — Soneium",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─────────────────────────────────────────────────────────────────
# shadcn 3-색 CSS — 모든 기본 컴포넌트 위에 inline 으로 덮어쓰기
# 색: bg #0a0a0a, fg #fafafa, accent #10b981
# fg 의 opacity 변형은 별색이 아닌 같은 색의 투명도 → 3색 규칙 유지
# ─────────────────────────────────────────────────────────────────
SHADCN_CSS = """
<style>
    :root {
        --bg: #0a0a0a;
        --fg: #fafafa;
        --accent: #10b981;
        --border: rgba(250, 250, 250, 0.08);
        --muted: rgba(250, 250, 250, 0.55);
    }
    .stApp { background: var(--bg); color: var(--fg); }
    .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1280px; }
    h1, h2, h3, h4 { color: var(--fg); font-weight: 600; letter-spacing: -0.02em; }
    h1 { font-size: 2rem; }
    h2 { font-size: 1.4rem; margin-top: 1.5rem; }
    h3 { font-size: 1.1rem; }
    a, a:visited { color: var(--accent); text-decoration: none; }
    hr { border-color: var(--border); margin: 1.5rem 0; }
    [data-testid="stMetricLabel"] { color: var(--muted); font-size: 0.85rem; font-weight: 500; }
    [data-testid="stMetricValue"] { color: var(--fg); font-size: 1.8rem; font-weight: 600; }
    [data-testid="stMetricDelta"] { color: var(--muted); }
    .stButton > button {
        background: transparent; color: var(--fg);
        border: 1px solid var(--border); border-radius: 8px;
        padding: 0.5rem 1rem; font-weight: 500;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        border-color: var(--accent); color: var(--accent);
    }
    .stButton > button[kind="primary"] {
        background: var(--accent); color: var(--bg); border-color: var(--accent);
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--fg); color: var(--bg); border-color: var(--fg);
    }
    .vault-card {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.5rem 1.75rem;
        transition: border-color 0.15s ease;
    }
    .vault-card:hover { border-color: rgba(250, 250, 250, 0.2); }
    .vault-card.warn { border-color: var(--accent); }
    .vault-card.disabled { opacity: 0.5; }
    .vault-card .label { color: var(--muted); font-size: 0.8rem; font-weight: 500;
                         text-transform: uppercase; letter-spacing: 0.05em; }
    .vault-card .addr  { color: var(--muted); font-family: ui-monospace, "JetBrains Mono", monospace;
                         font-size: 0.78rem; margin: 0.5rem 0 1rem 0; }
    .vault-card .name  { font-size: 1.2rem; font-weight: 600; color: var(--fg); margin: 0.25rem 0; }
    .vault-card .value { font-size: 2.4rem; font-weight: 700; color: var(--fg);
                         letter-spacing: -0.02em; margin: 0.5rem 0; }
    .vault-card .value.accent { color: var(--accent); }
    .vault-card .desc  { color: var(--muted); font-size: 0.85rem; }
    .vault-card .badge { display: inline-block; background: var(--accent); color: var(--bg);
                         padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem;
                         font-weight: 600; margin-top: 0.5rem; }
    .vault-card .meta  { color: var(--muted); font-size: 0.8rem; margin-top: 0.75rem;
                         font-family: ui-monospace, "JetBrains Mono", monospace; }
    .proj-pill {
        display: inline-block; padding: 0.4rem 1rem; border: 1px solid var(--border);
        border-radius: 9999px; color: var(--muted); font-size: 0.9rem; font-weight: 500;
        margin-right: 0.5rem; transition: all 0.15s ease; cursor: pointer;
    }
    .proj-pill.active { background: var(--fg); color: var(--bg); border-color: var(--fg); }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: var(--accent) !important; border-bottom-color: var(--accent) !important;
    }
    [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; }
</style>
"""
st.markdown(SHADCN_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# 캐시 — 60초 단위로 자동 갱신
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def cached_total_usd(address: str) -> dict:
    return get_total_usd(address)


@st.cache_data(ttl=60, show_spinner=False)
def cached_history(address: str, limit: int = 2000) -> list[dict]:
    return get_combined_history(address, limit=limit)


# ─────────────────────────────────────────────────────────────────
# 쿼리 라우팅
# ─────────────────────────────────────────────────────────────────

def _qp_get(key: str) -> str | None:
    val = st.query_params.get(key)
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _set_qp(**kwargs) -> None:
    """업데이트할 쿼리 키들만 setting (None 이면 제거)."""
    current = dict(st.query_params)
    for k, v in kwargs.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v
    st.query_params.clear()
    for k, v in current.items():
        st.query_params[k] = v


project_keys = list(PROJECTS.keys())
selected_project = _qp_get("project")
if selected_project not in PROJECTS:
    selected_project = project_keys[0]

selected_wallet = _qp_get("wallet")
proj = PROJECTS[selected_project]
proj_wallets = (proj.get("wallets") or {}) if not proj.get("coming_soon") else {}

if selected_wallet and selected_wallet not in proj_wallets:
    selected_wallet = None


# ─────────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Vault")
    st.caption("Soneium 운영 지갑 모니터")
    st.divider()
    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"캐시 TTL · 60s")
    st.divider()
    st.caption(f"알림 수신 · `{ALERT_EMAIL_TO}`")
    st.caption(f"SMTP · {'활성' if is_smtp_configured() else '미설정 (로그만)'}")


# ─────────────────────────────────────────────────────────────────
# 헤더 + 프로젝트 셀렉터 (pill 스타일)
# ─────────────────────────────────────────────────────────────────

def _short_addr(addr: str) -> str:
    addr = (addr or "").strip()
    if len(addr) < 12:
        return addr
    return f"{addr[:8]}…{addr[-6:]}"


def render_header() -> None:
    st.markdown("# Vault")
    st.caption(f"Soneium L2 · 갱신 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 프로젝트 pill — 버튼 가로 정렬
    cols = st.columns(len(project_keys) + 1)
    for col, pkey in zip(cols, project_keys):
        p = PROJECTS[pkey]
        label = p["name"]
        if p.get("coming_soon"):
            label += " · soon"
        with col:
            is_active = pkey == selected_project
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"proj_{pkey}", use_container_width=True, type=btn_type):
                _set_qp(project=pkey, wallet=None)
                st.rerun()


# ─────────────────────────────────────────────────────────────────
# 코밍순 화면
# ─────────────────────────────────────────────────────────────────

def render_coming_soon(proj: dict) -> None:
    st.markdown(
        f"""
        <div class="vault-card disabled" style="text-align:center; padding:3rem 2rem;">
            <div class="label">Coming soon</div>
            <div class="name" style="font-size:1.5rem; margin-top:0.5rem;">{proj['name']}</div>
            <div class="desc" style="margin-top:0.75rem;">{proj.get('description', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────
# 프로젝트 홈 — wallet 카드 그리드
# ─────────────────────────────────────────────────────────────────

def render_wallet_card(project_key: str, wallet_key: str, wallet: dict) -> None:
    address = (wallet.get("address") or "").strip()
    name = wallet.get("name", wallet_key)
    desc = wallet.get("description", "")
    threshold = wallet.get("alert_threshold_usd")

    if not address:
        # 주소 미등록 — placeholder
        st.markdown(
            f"""
            <div class="vault-card disabled">
                <div class="label">미등록</div>
                <div class="name">{name}</div>
                <div class="desc">{desc}</div>
                <div class="meta">주소가 아직 설정되지 않았습니다 (config.py)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    try:
        info = cached_total_usd(address)
        total = info["total_usd"]
        tokens = info.get("tokens") or []
    except Exception as e:
        st.markdown(
            f"""
            <div class="vault-card">
                <div class="label">{wallet.get('kind', '').upper()}</div>
                <div class="name">{name}</div>
                <div class="addr">{_short_addr(address)}</div>
                <div class="desc" style="color:var(--accent)">조회 실패: {e}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    warn = threshold is not None and total < threshold
    value_class = "accent" if warn else ""
    card_class = "vault-card warn" if warn else "vault-card"

    tokens_html = ""
    if tokens:
        items = "".join(
            f'<div class="meta">{t["symbol"]} · {t["value"]:,.2f} '
            f'<span style="opacity:0.6">(${t["usd"]:,.2f})</span></div>'
            for t in tokens[:3]
        )
        tokens_html = f'<div style="margin-top:0.75rem;">{items}</div>'

    badge_html = (
        f'<div class="badge">임계 미달 · 기준 ${threshold:,.0f}</div>' if warn else ""
    )

    st.markdown(
        f"""
        <div class="{card_class}">
            <div class="label">{wallet.get('kind', '').upper() or 'WALLET'}</div>
            <div class="name">{name}</div>
            <div class="addr">{_short_addr(address)}</div>
            <div class="value {value_class}">${total:,.2f}</div>
            <div class="desc">{desc}</div>
            {tokens_html}
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("상세 보기", key=f"detail_{project_key}_{wallet_key}",
                 use_container_width=True):
        _set_qp(project=project_key, wallet=wallet_key)
        st.rerun()


def render_project_home(project_key: str, proj: dict) -> None:
    wallets = proj.get("wallets") or {}
    if not wallets:
        st.info("이 프로젝트엔 등록된 지갑이 없습니다.")
        return

    cols = st.columns(len(wallets))
    for col, (wkey, wallet) in zip(cols, wallets.items()):
        with col:
            render_wallet_card(project_key, wkey, wallet)


# ─────────────────────────────────────────────────────────────────
# Wallet 상세
# ─────────────────────────────────────────────────────────────────

def render_wallet_detail(project_key: str, proj: dict,
                         wallet_key: str, wallet: dict) -> None:
    # 상단 — 뒤로가기 + 헤더
    bcol1, bcol2 = st.columns([1, 6])
    with bcol1:
        if st.button("← 프로젝트", use_container_width=True):
            _set_qp(project=project_key, wallet=None)
            st.rerun()

    address = wallet["address"]
    st.markdown(f"## {proj['name']} · {wallet['name']}")
    st.markdown(
        f'<div class="addr" style="font-size:0.85rem;">{address}</div>',
        unsafe_allow_html=True,
    )

    try:
        info = cached_total_usd(address)
    except Exception as e:
        st.error(f"RPC 실패: {e}")
        return

    # 잔고 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric("총 USD", f"${info['total_usd']:,.2f}")
    c2.metric("ETH", f"{info['eth']:.6f}", help=f"${info['eth_usd']:,.2f}")
    c3.metric("토큰 USD", f"${info['tokens_usd']:,.2f}")

    if info.get("tokens"):
        with st.expander("보유 토큰 전체"):
            tdf = pd.DataFrame(info["tokens"])
            tdf = tdf[["symbol", "name", "value", "exchange_rate", "usd", "contract"]]
            tdf.columns = ["심볼", "이름", "잔량", "단가($)", "USD", "컨트랙트"]
            st.dataframe(tdf, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("거래 내역")

    try:
        with st.spinner("전체 페이지 조회 중..."):
            hist = cached_history(address, limit=2000)
    except Exception as e:
        st.error(f"내역 조회 실패: {e}")
        return

    if not hist:
        st.info("거래 내역 없음")
        return

    df = pd.DataFrame(hist)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp", ascending=False)

    period = st.selectbox("기간", ["전체", "최근 24시간", "최근 7일", "최근 30일"], index=0)
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

    pnl_mode = wallet.get("pnl_mode", "income")
    total_in_usd = df.loc[df["direction"] == "in", "usd"].fillna(0).sum()
    total_out_usd = df.loc[df["direction"] == "out", "usd"].fillna(0).sum()

    if pnl_mode == "treasury":
        pnl_usd = -total_out_usd
        in_label = "총 충전 (입금)"
        out_label = "총 지급 (리워드)"
        pnl_label = "손익 (Owner PNL)"
        df["usd_signed"] = df.apply(
            lambda r: -(r["usd"] or 0) if r["direction"] == "out" else 0, axis=1,
        )
    else:
        pnl_usd = total_in_usd - total_out_usd
        in_label = "입금 USD"
        out_label = "출금 USD"
        pnl_label = "순 PNL"
        df["usd_signed"] = df.apply(
            lambda r: (r["usd"] or 0) * (
                1 if r["direction"] == "in" else -1 if r["direction"] == "out" else 0
            ), axis=1,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(in_label, f"${total_in_usd:,.2f}", f"{(df['direction']=='in').sum()}건")
    m2.metric(out_label, f"${total_out_usd:,.2f}", f"{(df['direction']=='out').sum()}건")
    m3.metric(pnl_label, f"${pnl_usd:,.2f}")
    m4.metric("거래 수", f"{len(df):,}건")

    # 카운터파티
    st.divider()
    st.subheader("카운터파티")
    cp_in = (
        df[df["direction"] == "in"].groupby("counterparty")
        .agg(건수=("hash", "count"), 합계=("value", "sum"), USD합계=("usd", "sum"))
        .sort_values("USD합계", ascending=False).head(20)
    )
    cp_out = (
        df[df["direction"] == "out"].groupby("counterparty")
        .agg(건수=("hash", "count"), 합계=("value", "sum"), USD합계=("usd", "sum"))
        .sort_values("USD합계", ascending=False).head(20)
    )

    def _render_cp(d: pd.DataFrame, empty: str) -> None:
        if d.empty:
            st.info(empty)
        else:
            df_show = d.reset_index()
            df_show["USD합계"] = df_show["USD합계"].round(2)
            df_show["합계"] = df_show["합계"].round(4)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    in_label_tab = f"입금처 ({len(cp_in)})"
    out_label_tab = f"출금처 ({len(cp_out)})"
    if pnl_mode == "treasury":
        tab_out, tab_in = st.tabs([out_label_tab, in_label_tab])
    else:
        tab_in, tab_out = st.tabs([in_label_tab, out_label_tab])
    with tab_out:
        _render_cp(cp_out, "출금 없음")
    with tab_in:
        _render_cp(cp_in, "입금 없음")

    # 시계열 PNL
    st.divider()
    st.subheader("시계열 PNL")
    df_ts = df.copy()
    if period == "최근 24시간":
        df_ts["bucket"] = df_ts["timestamp"].dt.floor("h")
        bin_label = "시간"
    else:
        df_ts["bucket"] = df_ts["timestamp"].dt.floor("D")
        bin_label = "일자"

    df_ts["usd_in"] = df_ts.apply(
        lambda r: (r["usd"] or 0) if r["direction"] == "in" else 0, axis=1,
    )
    df_ts["usd_out"] = df_ts.apply(
        lambda r: (r["usd"] or 0) if r["direction"] == "out" else 0, axis=1,
    )
    agg = (
        df_ts.groupby("bucket")
        .agg(입금=("usd_in", "sum"), 출금=("usd_out", "sum"),
             PNL=("usd_signed", "sum"))
        .reset_index().sort_values("bucket")
    )
    agg["누적PNL"] = agg["PNL"].cumsum()

    if agg.empty:
        st.info("시계열 데이터 없음")
    else:
        st.line_chart(agg.set_index("bucket")[["누적PNL"]])
        with st.expander(f"{bin_label}별 상세"):
            display = agg.copy()
            display.columns = [bin_label, "입금($)", "출금($)", "PNL($)", "누적PNL($)"]
            for c in display.columns[1:]:
                display[c] = display[c].round(2)
            st.dataframe(display, use_container_width=True, hide_index=True)

    # 거래 원장
    st.divider()
    st.subheader("거래 원장")
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
render_header()
st.divider()

if proj.get("coming_soon"):
    render_coming_soon(proj)
elif selected_wallet and selected_wallet in proj_wallets:
    render_wallet_detail(selected_project, proj,
                         selected_wallet, proj_wallets[selected_wallet])
else:
    render_project_home(selected_project, proj)
