"""
PIKIT 베타 밸런스 대시보드.

실행: streamlit run app.py
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# 공개 배포 모드 — 환경변수 `PIKIT_PUBLIC=1` 이면 원본 데이터 탭과
# raw CSV 다운로드 버튼을 모두 숨겨, 익명 방문자가 트랜잭션 로그
# 같은 민감 데이터를 직접 받지 못하도록 합니다.
PUBLIC_MODE = os.environ.get("PIKIT_PUBLIC", "").lower() in ("1", "true", "yes", "on")

from pikit_analyzer import (
    BalanceTweak,
    DEFAULT_DATA_ROOT,
    balance_config_json,
    blocks_csv_with_recommendations,
    compute_block_economy,
    compute_item_economy,
    compute_kpi_summary,
    compute_session_metrics,
    compute_user_block_breakdown,
    compute_user_item_breakdown,
    compute_user_pnl,
    compute_user_timeseries,
    items_csv_with_recommendations,
    list_snapshot_dates,
    load_snapshot,
    recommend_block_changes,
    recommend_item_changes,
    simulate_balance,
    simulator_overrides_csv,
)

st.set_page_config(
    page_title="PIKIT 밸런스 대시보드",
    page_icon="⛏️",
    layout="wide",
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _cached_snapshot(date_str: str, data_root: str):
    return load_snapshot(date_str, data_root=data_root)


def _fmt_int(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.0f}"


def _safe_metric(label: str, value, delta=None, help_text: str | None = None):
    if isinstance(value, (int, float)) and not pd.isna(value):
        formatted = f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.2f}"
    else:
        formatted = str(value)
    st.metric(label, formatted, delta=delta, help=help_text)


def _ts_filename(prefix: str, ext: str) -> str:
    """Slugify a label for download filenames."""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


# ---------------------------------------------------------------------------
# 사이드바 — 데이터 소스 / 기간 선택
# ---------------------------------------------------------------------------

st.sidebar.title("⛏️ PIKIT 밸런스")

if PUBLIC_MODE:
    # 공개 모드: 데이터 경로를 사용자가 변경할 수 없게 고정.
    data_root = str(DEFAULT_DATA_ROOT)
else:
    data_root = st.sidebar.text_input(
        "데이터 폴더",
        value=str(DEFAULT_DATA_ROOT),
        help="`2026.05.06` 같은 일별 스냅샷 폴더가 들어 있는 상위 폴더입니다.",
    )
snapshots = list_snapshot_dates(Path(data_root))
if not snapshots:
    st.sidebar.error(f"`{data_root}` 에서 스냅샷을 찾지 못했습니다.")
    st.stop()

# 가장 최근 스냅샷에는 누적 트랜잭션 로그가 모두 들어 있어, 임의 기간 슬라이스가 가능합니다.
latest_choice = snapshots[-1]
latest_ds = _cached_snapshot(latest_choice, data_root)
min_date, max_date = latest_ds.transaction_date_range
if min_date is None:
    min_date = max_date = date.today()

st.sidebar.markdown("### 기간 선택")
mode = st.sidebar.radio(
    "조회 모드",
    options=["단일 스냅샷", "단일 날짜", "날짜 범위"],
    index=2,
    help=(
        "• **단일 스냅샷** — 특정 일자에 백업된 전체 누적 데이터.\n"
        "• **단일 날짜** — 가장 최근 스냅샷에서 선택한 날짜 하루치 트랜잭션만.\n"
        "• **날짜 범위** — 가장 최근 스냅샷에서 시작일~종료일 사이 트랜잭션."
    ),
)

filter_caption = ""
if mode == "단일 스냅샷":
    selected_snapshot = st.sidebar.selectbox(
        "스냅샷 일자", snapshots, index=len(snapshots) - 1
    )
    base_ds = _cached_snapshot(selected_snapshot, data_root)
    ds = base_ds
    filter_caption = f"스냅샷 **{selected_snapshot}** (누적 데이터)"

elif mode == "단일 날짜":
    chosen = st.sidebar.date_input(
        "조회 날짜",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
    )
    base_ds = latest_ds
    ds = base_ds.filter_by_date_range(chosen, chosen)
    filter_caption = f"**{chosen}** 하루치 (스냅샷 {latest_choice} 기준)"

else:  # 날짜 범위
    default_start = max_date - timedelta(days=2) if max_date else min_date
    if default_start < min_date:
        default_start = min_date
    chosen_range = st.sidebar.date_input(
        "조회 기간",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(chosen_range, tuple) and len(chosen_range) == 2:
        start_d, end_d = chosen_range
    else:
        start_d = end_d = chosen_range  # type: ignore[assignment]
    base_ds = latest_ds
    ds = base_ds.filter_by_date_range(start_d, end_d)
    filter_caption = f"**{start_d} ~ {end_d}** (스냅샷 {latest_choice} 기준)"

st.sidebar.markdown("### 계정 필터")

# 퀘스트 픽스처는 항상 제외 — 토글 없음.
if latest_ds.quest_user_ids:
    st.sidebar.caption(
        f"🚫 퀘스트 더미 계정 **{len(latest_ds.quest_user_ids)}개 항상 제외** "
        f"(user_id {sorted(latest_ds.quest_user_ids)})"
    )

exclude_system = st.sidebar.checkbox(
    "시스템 계정 제외 (user_id 11)",
    value=True,
    help=(
        "체크 해제 시 시스템 계정(지갑 `0x000…0000`, 보통 user_id 11)이 분석에 포함됩니다. "
        "시스템(운영용) 곡괭이가 얼마나 채굴했는지 보고 싶을 때 끄세요."
    ),
)
if latest_ds.system_user_ids:
    if exclude_system:
        st.sidebar.caption(
            f"🚫 시스템 계정 {len(latest_ds.system_user_ids)}개 제외 중 "
            f"(user_id {sorted(latest_ds.system_user_ids)})"
        )
    else:
        st.sidebar.caption(
            f"🔧 시스템 계정 {len(latest_ds.system_user_ids)}개 포함 — 시스템 곡괭이 채굴 활동 추적 모드"
        )


# ---------------------------------------------------------------------------
# 헤더 KPI
# ---------------------------------------------------------------------------

kpi = compute_kpi_summary(ds, exclude_system_users=exclude_system)

st.title("PIKIT 베타 밸런스 대시보드")
st.caption(
    f"조회 범위: {filter_caption}  ·  트랜잭션 {kpi['transaction_count']:,} 건"
)

cols = st.columns(5)
with cols[0]:
    _safe_metric("활성 유저", kpi["n_users"], help_text="이 기간에 트랜잭션이 있었던 실유저 수")
with cols[1]:
    _safe_metric(
        "흑자 / 적자",
        f"{kpi['n_winning_users']} / {kpi['n_losing_users']}",
        help_text="PNL > 0 / < 0 인 유저 수",
    )
with cols[2]:
    _safe_metric(
        "유저 PNL 중위값",
        kpi["median_user_pnl"],
        help_text="block_reward − item_spend 의 중위값",
    )
with cols[3]:
    _safe_metric(
        "Sink 비율",
        kpi["sink_ratio"],
        help_text="총 아이템 지출 ÷ 총 블록 보상. 1보다 크면 시스템이 크레딧을 흡수.",
    )
with cols[4]:
    _safe_metric(
        "평균 세션(분)",
        kpi["avg_session_minutes"],
        help_text="(유저, 게임) 단위 세션의 평균 지속 시간",
    )

st.divider()


# ---------------------------------------------------------------------------
# 탭 — 데이터 보기(메인) ◀───▶ 밸런스 도구(보조, 맨 오른쪽)
# ---------------------------------------------------------------------------

st.markdown(
    "<div style='color:#888;font-size:13px;margin-bottom:6px;'>"
    "📊 데이터 보기 (메인) → → → 🛠️ 밸런스 도구 (부가, 오른쪽 끝)"
    "</div>",
    unsafe_allow_html=True,
)

tab_labels = [
    "👤 유저",
    "🔍 유저 상세 / 그룹 분석",
    "⛏️ 곡괭이 / TNT",
    "🪨 블록",
]
if not PUBLIC_MODE:
    tab_labels.append("📦 원본 데이터")
tab_labels.extend(["│ 🧪 [부가] 시뮬레이터", "│ 📤 [부가] 밸런스 적용"])

_tabs = st.tabs(tab_labels)
tab_users = _tabs[0]
tab_user_detail = _tabs[1]
tab_items = _tabs[2]
tab_blocks = _tabs[3]
if PUBLIC_MODE:
    tab_data = None
    tab_sim = _tabs[4]
    tab_export = _tabs[5]
else:
    tab_data = _tabs[4]
    tab_sim = _tabs[5]
    tab_export = _tabs[6]


# -------- 유저 탭 --------
with tab_users:
    st.subheader("유저별 PNL")
    pnl = compute_user_pnl(ds, exclude_system_users=exclude_system)

    # 방어적 필터: quest 는 항상, system 은 토글에 따라 PNL 표에서 추가 보장 제거.
    blocked_ids = list(ds.quest_user_ids)
    if exclude_system:
        blocked_ids += list(ds.system_user_ids)
    if blocked_ids and not pnl.empty:
        before = len(pnl)
        pnl = pnl[~pnl["user_id"].isin(blocked_ids)].reset_index(drop=True)
        if before - len(pnl) > 0:
            st.warning(
                f"필터 보강: {before - len(pnl)}개 계정을 PNL 표에서 추가로 제거했습니다."
            )

    if pnl.empty:
        st.info("이 기간에는 트랜잭션 데이터가 없습니다.")
    else:
        caption_bits = []
        if ds.quest_user_ids:
            caption_bits.append(f"퀘스트 계정 {len(ds.quest_user_ids)}개 (항상 제외)")
        if ds.system_user_ids:
            caption_bits.append(
                f"시스템 계정 {len(ds.system_user_ids)}개 "
                + ("(제외)" if exclude_system else "(포함)")
            )
        if caption_bits:
            st.caption("🚫 " + " · ".join(caption_bits))
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            st.metric("총 블록 보상", _fmt_int(pnl["block_reward"].sum()))
        with c2:
            st.metric("총 아이템 지출", _fmt_int(pnl["item_spend"].sum()))
        with c3:
            st.metric("순 PNL", _fmt_int(pnl["pnl"].sum()))

        fig = px.histogram(
            pnl,
            x="pnl",
            nbins=30,
            title="유저별 PNL 분포",
            labels={"pnl": "PNL (credit)"},
        )
        fig.add_vline(x=0, line_dash="dash", line_color="white")
        st.plotly_chart(fig)

        sort_col = st.selectbox(
            "정렬 기준",
            options=[
                "pnl",
                "roi",
                "block_reward",
                "item_spend",
                "active_minutes",
                "blocks_mined",
            ],
            index=0,
        )
        ascending = st.toggle("오름차순", value=False)
        view = pnl.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
        st.dataframe(
            view,
            width="stretch",
            column_config={
                "user_id": "유저 ID",
                "username": "닉네임",
                "wallet_address": "지갑 주소",
                "credit_charged": st.column_config.NumberColumn("Credit 충전", format="%d"),
                "block_reward": st.column_config.NumberColumn("블록 보상", format="%d"),
                "item_spend": st.column_config.NumberColumn("아이템 지출", format="%d"),
                "pnl": st.column_config.NumberColumn("PNL", format="%d"),
                "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
                "tx_count": st.column_config.NumberColumn("트랜잭션 수", format="%d"),
                "blocks_mined": st.column_config.NumberColumn("채굴 횟수", format="%d"),
                "items_purchased": st.column_config.NumberColumn("아이템 구매 수", format="%d"),
                "first_tx": "첫 트랜잭션",
                "last_tx": "마지막 트랜잭션",
                "active_minutes": st.column_config.NumberColumn("활동 시간(분)", format="%.1f"),
            },
        )

        st.download_button(
            "유저 PNL CSV 다운로드",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name=_ts_filename("user_pnl", "csv"),
            mime="text/csv",
        )

        st.markdown("### 세션별 PNL")
        sessions = compute_session_metrics(ds, exclude_system_users=exclude_system)
        if sessions.empty:
            st.info("세션 데이터가 없습니다.")
        else:
            fig2 = px.box(
                sessions,
                x="game_mode",
                y="pnl",
                points="all",
                color="game_mode",
                title="게임 모드별 세션 PNL 분포",
            )
            st.plotly_chart(fig2)
            with st.expander("세션 원본 보기", expanded=False):
                st.dataframe(sessions, width="stretch")
            st.download_button(
                "세션 PNL CSV 다운로드",
                data=sessions.to_csv(index=False).encode("utf-8-sig"),
                file_name=_ts_filename("session_pnl", "csv"),
                mime="text/csv",
            )


# -------- 유저 상세 / 그룹 분석 탭 --------
with tab_user_detail:
    st.subheader("유저 상세 / 그룹 시계열 분석")
    st.write(
        "유저를 1명 또는 여러 명 선택해 **시간대별 PNL · 블록 보상 · 아이템 지출** 추이를 봅니다. "
        "추후 시간 단위 데이터(스냅샷)가 들어와도 같은 화면에서 그대로 사용할 수 있습니다."
    )

    pnl_for_picker = compute_user_pnl(ds, exclude_system_users=exclude_system)
    # 동일한 안전장치: 멀티셀렉트 후보에 quest 는 항상, system 은 토글에 따라 숨김.
    blocked_picker = list(ds.quest_user_ids)
    if exclude_system:
        blocked_picker += list(ds.system_user_ids)
    if blocked_picker and not pnl_for_picker.empty:
        pnl_for_picker = pnl_for_picker[
            ~pnl_for_picker["user_id"].isin(blocked_picker)
        ].reset_index(drop=True)

    if pnl_for_picker.empty:
        st.info("조회 범위 안에 유저 활동이 없습니다.")
    else:
        # 활동량(트랜잭션 수) 많은 순으로 정렬해서 selectbox 후보로 사용.
        users_sorted = pnl_for_picker.sort_values("tx_count", ascending=False)
        option_to_id: dict[str, int] = {}
        options: list[str] = []
        for _, row in users_sorted.iterrows():
            uid = int(row["user_id"])
            uname = row.get("username") or "(no name)"
            wallet = row.get("wallet_address") or ""
            wallet_short = (wallet[:8] + "…" + wallet[-4:]) if isinstance(wallet, str) and len(wallet) > 12 else wallet
            label = f"#{uid} {uname}  ·  {wallet_short}  ·  PNL {row['pnl']:,.0f}"
            options.append(label)
            option_to_id[label] = uid

        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            picked = st.multiselect(
                "유저 선택 (검색 가능, 닉네임/지갑/유저ID로 검색됨)",
                options=options,
                default=options[:1],
                help="여러 명을 선택하면 개별 또는 합산 모드로 비교할 수 있습니다.",
            )
        with c2:
            freq_label = st.radio(
                "시간 단위",
                options=["일 (D)", "시간 (1h)", "30분", "10분"],
                index=0,
                help="현재 데이터는 일 단위 스냅샷이지만, 트랜잭션 타임스탬프 기준으로 시간/분 단위 리샘플링이 가능합니다.",
            )
        with c3:
            view_mode = st.radio(
                "표시 방식",
                options=["개별 라인", "합산 라인"],
                index=0,
                help="개별 = 유저마다 한 줄. 합산 = 선택한 유저들을 더해서 한 줄.",
            )

        freq_map = {"일 (D)": "D", "시간 (1h)": "h", "30분": "30min", "10분": "10min"}
        freq = freq_map[freq_label]

        if not picked:
            st.warning("최소 1명을 선택하세요.")
        else:
            picked_ids = [option_to_id[label] for label in picked]
            ts = compute_user_timeseries(
                ds, user_ids=picked_ids, freq=freq, exclude_system_users=exclude_system
            )

            if ts.empty:
                st.info("선택한 유저(들)의 트랜잭션이 없습니다.")
            else:
                # 합산 모드: 유저 차원을 없애고 그룹 합산 시리즈 1개를 만든다.
                if view_mode == "합산 라인":
                    grouped = (
                        ts.groupby("period")
                        .agg(
                            block_reward=("block_reward", "sum"),
                            item_spend=("item_spend", "sum"),
                            credit_charged=("credit_charged", "sum"),
                            tx_count=("tx_count", "sum"),
                            pnl=("pnl", "sum"),
                        )
                        .reset_index()
                        .sort_values("period")
                    )
                    grouped["cum_block_reward"] = grouped["block_reward"].cumsum()
                    grouped["cum_item_spend"] = grouped["item_spend"].cumsum()
                    grouped["cum_pnl"] = grouped["pnl"].cumsum()
                    grouped["label"] = f"합산({len(picked_ids)}명)"
                    series = grouped
                    color_col = "label"
                else:
                    series = ts.copy()
                    series["label"] = series.apply(
                        lambda r: f"#{int(r['user_id'])} {r['username'] or ''}".strip(), axis=1
                    )
                    color_col = "label"

                # 요약 카드
                if view_mode == "합산 라인":
                    total_reward = float(grouped["block_reward"].sum())
                    total_spend = float(grouped["item_spend"].sum())
                    total_pnl = total_reward - total_spend
                    total_tx = int(grouped["tx_count"].sum())
                else:
                    total_reward = float(ts["block_reward"].sum())
                    total_spend = float(ts["item_spend"].sum())
                    total_pnl = total_reward - total_spend
                    total_tx = int(ts["tx_count"].sum())
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("선택 유저 수", f"{len(picked_ids)}명")
                with m2:
                    st.metric("총 블록 보상", _fmt_int(total_reward))
                with m3:
                    st.metric("총 아이템 지출", _fmt_int(total_spend))
                with m4:
                    st.metric("순 PNL", _fmt_int(total_pnl))

                # 그래프 — 누적 PNL (가장 중요한 지표)
                st.markdown("### 누적 PNL 추이")
                fig_cum = px.line(
                    series,
                    x="period",
                    y="cum_pnl",
                    color=color_col,
                    markers=True,
                    title=f"누적 PNL — {freq_label}",
                    labels={"period": "기간", "cum_pnl": "누적 PNL", "label": "유저"},
                )
                fig_cum.add_hline(y=0, line_dash="dot", line_color="white")
                st.plotly_chart(fig_cum)

                # 기간별 블록 보상 / 아이템 지출 (양옆 배치)
                st.markdown("### 기간별 보상 vs 지출")
                cc = st.columns(2)
                with cc[0]:
                    fig_r = px.bar(
                        series,
                        x="period",
                        y="block_reward",
                        color=color_col,
                        barmode="group",
                        title=f"블록 보상 — {freq_label}",
                        labels={"period": "기간", "block_reward": "블록 보상", "label": "유저"},
                    )
                    st.plotly_chart(fig_r)
                with cc[1]:
                    fig_s = px.bar(
                        series,
                        x="period",
                        y="item_spend",
                        color=color_col,
                        barmode="group",
                        title=f"아이템 지출 — {freq_label}",
                        labels={"period": "기간", "item_spend": "아이템 지출", "label": "유저"},
                    )
                    st.plotly_chart(fig_s)

                # 기간별 PNL (양수/음수 색 다르게)
                st.markdown("### 기간별 PNL")
                fig_pnl = px.bar(
                    series,
                    x="period",
                    y="pnl",
                    color=color_col,
                    barmode="group",
                    title=f"기간별 PNL — {freq_label}",
                    labels={"period": "기간", "pnl": "PNL", "label": "유저"},
                )
                fig_pnl.add_hline(y=0, line_color="white")
                st.plotly_chart(fig_pnl)

                # 트랜잭션 빈도
                st.markdown("### 활동량 (트랜잭션 수)")
                fig_tx = px.line(
                    series,
                    x="period",
                    y="tx_count",
                    color=color_col,
                    markers=True,
                    title=f"기간별 트랜잭션 수 — {freq_label}",
                    labels={"period": "기간", "tx_count": "트랜잭션 수", "label": "유저"},
                )
                st.plotly_chart(fig_tx)

                st.markdown("### 시계열 원본")
                st.dataframe(ts, width="stretch")
                st.download_button(
                    "시계열 데이터 CSV 다운로드",
                    data=ts.to_csv(index=False).encode("utf-8-sig"),
                    file_name=_ts_filename(f"timeseries_{freq}_{'_'.join(map(str, picked_ids))}", "csv"),
                    mime="text/csv",
                )

                # 블록 / 아이템 분포
                st.divider()
                st.markdown("### 블록 종류별 채굴 분포")
                bb = compute_user_block_breakdown(
                    ds, user_ids=picked_ids, exclude_system_users=exclude_system
                )
                if not bb.empty:
                    bb["label"] = bb.apply(
                        lambda r: f"#{int(r['user_id'])} {r['username'] or ''}".strip(), axis=1
                    )
                    fig_b = px.bar(
                        bb,
                        x="reward_total",
                        y="block_name",
                        color="label" if view_mode == "개별 라인" else None,
                        orientation="h",
                        barmode="stack",
                        facet_col="mode",
                        title="블록별 누적 보상",
                        labels={
                            "reward_total": "획득 보상",
                            "block_name": "블록",
                            "label": "유저",
                            "mode": "모드",
                        },
                    )
                    st.plotly_chart(fig_b)
                    with st.expander("블록 분포 표"):
                        st.dataframe(bb, width="stretch")
                else:
                    st.info("선택한 유저의 블록 보상 트랜잭션이 없습니다.")

                st.markdown("### 곡괭이 / TNT 구매 분포")
                ib = compute_user_item_breakdown(
                    ds, user_ids=picked_ids, exclude_system_users=exclude_system
                )
                if not ib.empty:
                    ib["label"] = ib.apply(
                        lambda r: f"#{int(r['user_id'])} {r['username'] or ''}".strip(), axis=1
                    )
                    fig_i = px.bar(
                        ib,
                        x="spend_total",
                        y="item_name",
                        color="label" if view_mode == "개별 라인" else "category",
                        orientation="h",
                        barmode="stack",
                        facet_col="mode",
                        title="아이템별 누적 지출",
                        labels={
                            "spend_total": "지출",
                            "item_name": "아이템",
                            "category": "카테고리",
                            "label": "유저",
                            "mode": "모드",
                        },
                    )
                    st.plotly_chart(fig_i)
                    with st.expander("아이템 분포 표"):
                        st.dataframe(ib, width="stretch")
                else:
                    st.info("선택한 유저의 아이템 구매 트랜잭션이 없습니다.")


# -------- 곡괭이 / TNT 탭 --------
with tab_items:
    st.subheader("곡괭이 · TNT 경제")

    target = st.slider(
        "목표 ROI",
        min_value=-0.3,
        max_value=1.0,
        value=0.20,
        step=0.05,
        help="이 값을 기준으로 추천 가격을 계산합니다.",
    )
    rec = recommend_item_changes(ds, target_roi=target, exclude_system_users=exclude_system)

    f1, f2 = st.columns(2)
    with f1:
        mode_filter = st.radio(
            "모드", ["NORMAL", "HARDCORE", "전체"], horizontal=True, index=0
        )
    with f2:
        cat_filter = st.radio(
            "카테고리", ["PICKAXE", "TNT", "전체"], horizontal=True, index=0
        )

    view = rec.copy()
    if mode_filter != "전체":
        view = view[view["mode"] == mode_filter]
    if cat_filter != "전체":
        view = view[view["category"] == cat_filter]

    fig = px.scatter(
        view,
        x="price",
        y="realized_roi",
        size=np.maximum(view["purchases"], 1),
        color="category",
        hover_name="name",
        title="가격 vs 실측 ROI (점 크기 = 구매 수)",
        labels={"price": "가격", "realized_roi": "실측 ROI", "category": "카테고리"},
    )
    fig.add_hline(y=target, line_dash="dash", line_color="orange",
                  annotation_text=f"목표 {target:.0%}")
    fig.add_hline(y=0, line_color="white", line_dash="dot")
    st.plotly_chart(fig)

    st.markdown("### 추천 사항")
    show_cols = [
        "name",
        "category",
        "mode",
        "price",
        "attack",
        "duration_s",
        "purchases",
        "unique_buyers",
        "theoretical_roi",
        "realized_roi",
        "recommended_price",
        "price_delta_pct",
        "recommendation",
    ]
    show = view[show_cols].sort_values(["mode", "category", "price"]).reset_index(drop=True)
    st.dataframe(
        show,
        width="stretch",
        column_config={
            "name": "이름",
            "category": "카테고리",
            "mode": "모드",
            "price": st.column_config.NumberColumn("현재 가격", format="%d"),
            "attack": st.column_config.NumberColumn("공격력", format="%.2f"),
            "duration_s": st.column_config.NumberColumn("지속(초)", format="%.1f"),
            "purchases": st.column_config.NumberColumn("구매 수", format="%d"),
            "unique_buyers": st.column_config.NumberColumn("구매자 수", format="%d"),
            "theoretical_roi": st.column_config.NumberColumn("이론 ROI", format="%.2f"),
            "realized_roi": st.column_config.NumberColumn("실측 ROI", format="%.2f"),
            "recommended_price": st.column_config.NumberColumn("추천 가격", format="%d"),
            "price_delta_pct": st.column_config.NumberColumn("가격 변동률", format="%.1%"),
            "recommendation": "코멘트",
        },
    )

    st.download_button(
        "아이템 추천 CSV 다운로드",
        data=show.to_csv(index=False).encode("utf-8-sig"),
        file_name=_ts_filename("item_recommendations", "csv"),
        mime="text/csv",
    )

    with st.expander("아이템 경제 원본"):
        ie = compute_item_economy(ds, exclude_system_users=exclude_system)
        st.dataframe(ie, width="stretch")


# -------- 블록 탭 --------
with tab_blocks:
    st.subheader("블록 경제")

    tol = st.slider("드롭률 허용 편차 (±)", 0.005, 0.05, 0.015, 0.005)
    rec_b = recommend_block_changes(
        ds, drop_tolerance=tol, exclude_system_users=exclude_system
    )

    mode_b = st.radio("모드 ", ["NORMAL", "HARDCORE", "전체"], horizontal=True, index=0,
                      key="block_mode")
    view_b = rec_b if mode_b == "전체" else rec_b[rec_b["mode"] == mode_b]

    fig = px.bar(
        view_b,
        x="name",
        y=["drop_rate", "actual_drop_rate"],
        barmode="group",
        title="설정 드롭률 vs 실측 드롭률",
        labels={"value": "드롭률", "variable": "", "name": "블록"},
    )
    st.plotly_chart(fig)

    fig2 = px.scatter(
        view_b,
        x="hp",
        y="reward",
        size=np.maximum(view_b["actual_drops"], 1),
        color="mode",
        hover_name="name",
        title="HP vs 보상 (점 크기 = 실측 드롭 수)",
        labels={"hp": "HP", "reward": "보상", "mode": "모드"},
    )
    st.plotly_chart(fig2)

    st.markdown("### 추천 사항")
    show_b = view_b[
        [
            "name",
            "mode",
            "drop_rate",
            "actual_drop_rate",
            "drop_rate_delta",
            "hp",
            "reward",
            "reward_per_hp",
            "recommended_reward",
            "reward_delta_pct",
            "actual_drops",
            "actual_unique_miners",
            "recommendation",
        ]
    ].reset_index(drop=True)
    st.dataframe(
        show_b,
        width="stretch",
        column_config={
            "name": "이름",
            "mode": "모드",
            "drop_rate": st.column_config.NumberColumn("설정 드롭률", format="%.4f"),
            "actual_drop_rate": st.column_config.NumberColumn("실측 드롭률", format="%.4f"),
            "drop_rate_delta": st.column_config.NumberColumn("드롭률 차이", format="%+.4f"),
            "hp": st.column_config.NumberColumn("HP", format="%.2f"),
            "reward": st.column_config.NumberColumn("현재 보상", format="%d"),
            "reward_per_hp": st.column_config.NumberColumn("보상/HP", format="%.3f"),
            "recommended_reward": st.column_config.NumberColumn("추천 보상", format="%d"),
            "reward_delta_pct": st.column_config.NumberColumn("보상 변동률", format="%.1%"),
            "actual_drops": st.column_config.NumberColumn("실측 드롭 수", format="%d"),
            "actual_unique_miners": st.column_config.NumberColumn("채굴 유저 수", format="%d"),
            "recommendation": "코멘트",
        },
    )

    st.download_button(
        "블록 추천 CSV 다운로드",
        data=show_b.to_csv(index=False).encode("utf-8-sig"),
        file_name=_ts_filename("block_recommendations", "csv"),
        mime="text/csv",
    )


# -------- 시뮬레이터 탭 --------
with tab_sim:
    st.subheader("What-if 밸런스 시뮬레이터")
    st.write(
        "가격 / 공격력 / 지속시간 / 블록 HP / 보상 / 드롭률을 자유롭게 조정하면, "
        "변경된 값으로 다시 계산한 **이론 ROI** 가 즉시 갱신됩니다. "
        "원본 데이터는 건드리지 않으니 안전하게 실험하세요."
    )

    items = ds.items.copy()
    blocks = ds.blocks.copy()

    with st.expander("곡괭이 / TNT 오버라이드", expanded=True):
        item_overrides: dict[int, dict[str, float]] = {}
        for _, row in items.sort_values(["mode", "item_id"]).iterrows():
            label = f"#{int(row['item_id'])} {row['name']} ({row['mode']})"
            cc = st.columns(4)
            with cc[0]:
                st.write(f"**{label}**")
            with cc[1]:
                new_price = st.number_input(
                    "가격",
                    min_value=0.0,
                    value=float(row["price"]) if pd.notna(row["price"]) else 0.0,
                    step=100.0,
                    key=f"price_{row['item_id']}",
                )
            with cc[2]:
                new_attack = st.number_input(
                    "공격력",
                    min_value=0.0,
                    value=float(row["attack"]) if pd.notna(row["attack"]) else 0.0,
                    step=1.0,
                    key=f"attack_{row['item_id']}",
                )
            with cc[3]:
                new_duration = st.number_input(
                    "지속(ms)",
                    min_value=0.0,
                    value=float(row["duration_ms"]) if pd.notna(row["duration_ms"]) else 0.0,
                    step=500.0,
                    key=f"duration_{row['item_id']}",
                )
            if (
                new_price != row["price"]
                or new_attack != row["attack"]
                or new_duration != row["duration_ms"]
            ):
                item_overrides[int(row["item_id"])] = {
                    "price": new_price,
                    "attack": new_attack,
                    "duration_ms": new_duration,
                }

    with st.expander("블록 오버라이드"):
        block_overrides: dict[int, dict[str, float]] = {}
        for _, row in blocks.sort_values(["mode", "block_id"]).iterrows():
            label = f"#{int(row['block_id'])} {row['name']} ({row['mode']})"
            cc = st.columns(4)
            with cc[0]:
                st.write(f"**{label}**")
            with cc[1]:
                new_hp = st.number_input(
                    "HP",
                    min_value=0.0,
                    value=float(row["hp"]) if pd.notna(row["hp"]) else 0.0,
                    step=10.0,
                    key=f"hp_{row['block_id']}",
                )
            with cc[2]:
                new_reward = st.number_input(
                    "보상",
                    min_value=0.0,
                    value=float(row["reward"]) if pd.notna(row["reward"]) else 0.0,
                    step=10.0,
                    key=f"reward_{row['block_id']}",
                )
            with cc[3]:
                new_drop = st.number_input(
                    "드롭률",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(row["drop_rate"]) if pd.notna(row["drop_rate"]) else 0.0,
                    step=0.005,
                    format="%.4f",
                    key=f"drop_{row['block_id']}",
                )
            if (
                new_hp != row["hp"]
                or new_reward != row["reward"]
                or new_drop != row["drop_rate"]
            ):
                block_overrides[int(row["block_id"])] = {
                    "hp": new_hp,
                    "reward": new_reward,
                    "drop_rate": new_drop,
                }

    tweak = BalanceTweak(item_overrides=item_overrides, block_overrides=block_overrides)
    sim = simulate_balance(ds, tweak)

    st.markdown("### 변경 전 / 후 이론 ROI")
    if not sim.empty:
        x_min = float(sim["baseline_roi"].dropna().min() or 0)
        x_max = float(sim["baseline_roi"].dropna().max() or 0)
        size_basis = np.where(sim["price"] > 0, np.log10(np.maximum(sim["price"], 1)) + 1, 1)
        fig = px.scatter(
            sim,
            x="baseline_roi",
            y="theoretical_roi",
            color="mode",
            symbol="category",
            size=size_basis,
            hover_name="name",
            title="ROI: 변경 전(x) vs 시뮬레이션(y) — 대각선 위 = 강해짐",
            labels={
                "baseline_roi": "변경 전 ROI",
                "theoretical_roi": "시뮬 ROI",
                "mode": "모드",
                "category": "카테고리",
            },
        )
        if x_max > x_min:
            fig.add_shape(
                type="line",
                x0=x_min,
                x1=x_max,
                y0=x_min,
                y1=x_max,
                line=dict(color="white", dash="dot"),
            )
        st.plotly_chart(fig)

    st.dataframe(
        sim,
        width="stretch",
        column_config={
            "item_id": "ID",
            "name": "이름",
            "category": "카테고리",
            "mode": "모드",
            "baseline_price": st.column_config.NumberColumn("변경 전 가격", format="%d"),
            "price": st.column_config.NumberColumn("시뮬 가격", format="%d"),
            "attack": st.column_config.NumberColumn("공격력", format="%.2f"),
            "duration_ms": st.column_config.NumberColumn("지속(ms)", format="%d"),
            "baseline_reward_per_use": st.column_config.NumberColumn("변경 전 회당 보상", format="%.0f"),
            "theoretical_reward_per_use": st.column_config.NumberColumn("시뮬 회당 보상", format="%.0f"),
            "baseline_roi": st.column_config.NumberColumn("변경 전 ROI", format="%.2f"),
            "theoretical_roi": st.column_config.NumberColumn("시뮬 ROI", format="%.2f"),
            "roi_delta": st.column_config.NumberColumn("ROI 차이", format="%+.2f"),
        },
    )

    if item_overrides or block_overrides:
        st.success(
            f"오버라이드 적용 — 아이템 {len(item_overrides)}개, "
            f"블록 {len(block_overrides)}개"
        )
        # 시뮬레이터에서 직접 편집한 결과를 게임 포맷 CSV 로 다운로드.
        sim_items = items.copy()
        for iid, over in item_overrides.items():
            mask = sim_items["item_id"] == iid
            for k, v in over.items():
                sim_items.loc[mask, k] = v
        sim_blocks = blocks.copy()
        for bid, over in block_overrides.items():
            mask = sim_blocks["block_id"] == bid
            for k, v in over.items():
                sim_blocks.loc[mask, k] = v

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "🧪 시뮬 적용 item.csv 다운로드 (게임 포맷)",
                data=simulator_overrides_csv(sim_items, "items"),
                file_name=_ts_filename("simulated_items", "csv"),
                mime="text/csv",
            )
        with d2:
            st.download_button(
                "🧪 시뮬 적용 block.csv 다운로드 (게임 포맷)",
                data=simulator_overrides_csv(sim_blocks, "blocks"),
                file_name=_ts_filename("simulated_blocks", "csv"),
                mime="text/csv",
            )


# -------- 밸런스 적용 (Export) 탭 --------
with tab_export:
    st.subheader("밸런스 적용 — 게임에 그대로 넣을 수 있는 형식으로 다운로드")
    st.write(
        "현재 데이터에서 산출된 추천값을 **게임이 사용하는 CSV 포맷** "
        "(헤더 없이 같은 컬럼 순서) 또는 **JSON 변경 명세**로 내보낼 수 있습니다. "
        "운영 파이프라인에 그대로 투입 가능한 형태입니다."
    )

    e1, e2 = st.columns(2)
    with e1:
        target_roi_export = st.slider(
            "추천 가격 산출용 목표 ROI",
            min_value=-0.3,
            max_value=1.0,
            value=0.20,
            step=0.05,
            key="export_roi",
        )
    with e2:
        drop_tol_export = st.slider(
            "블록 드롭률 허용 편차",
            min_value=0.005,
            max_value=0.05,
            value=0.015,
            step=0.005,
            key="export_tol",
        )

    notes = st.text_area(
        "운영 메모 (JSON에 함께 기록됩니다)",
        value="",
        height=70,
        placeholder="예: 2026-05-06 베타 4일차 데이터 기준, NORMAL 곡괭이 가격 인하 적용",
    )

    items_csv = items_csv_with_recommendations(
        ds, target_roi=target_roi_export, exclude_system_users=exclude_system
    )
    blocks_csv = blocks_csv_with_recommendations(
        ds, drop_tolerance=drop_tol_export, exclude_system_users=exclude_system
    )
    cfg_json = balance_config_json(
        ds,
        target_roi=target_roi_export,
        drop_tolerance=drop_tol_export,
        exclude_system_users=exclude_system,
        notes=notes or None,
    )

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "📥 추천 적용 item.csv (게임 포맷)",
            data=items_csv,
            file_name=_ts_filename("item_balanced", "csv"),
            mime="text/csv",
            help="`item.csv` 와 동일한 헤더 없는 12-컬럼 포맷으로, 가격만 추천값으로 갈아치운 파일.",
        )
    with d2:
        st.download_button(
            "📥 추천 적용 block.csv (게임 포맷)",
            data=blocks_csv,
            file_name=_ts_filename("block_balanced", "csv"),
            mime="text/csv",
            help="`block.csv` 와 동일한 포맷으로, 보상 컬럼만 추천값으로 갈아치운 파일.",
        )
    with d3:
        st.download_button(
            "📥 변경 명세 JSON",
            data=cfg_json,
            file_name=_ts_filename("balance_changes", "json"),
            mime="application/json",
            help="현재값 → 추천값 + 사유 + 메트릭이 정리된 JSON 명세.",
        )

    st.markdown("### 변경 명세 미리보기")
    st.code(cfg_json[:4000] + ("\n…" if len(cfg_json) > 4000 else ""), language="json")

    st.markdown("### 추천 가격으로 갈아치운 item.csv 미리보기")
    st.code("\n".join(items_csv.splitlines()[:25]), language="csv")

    st.markdown("### 추천 보상으로 갈아치운 block.csv 미리보기")
    st.code("\n".join(blocks_csv.splitlines()[:25]), language="csv")

    if not PUBLIC_MODE:
        st.markdown("---")
        st.markdown("### 분석 산출물 다운로드 (raw)")
        st.write("외부 시스템에서 끌어쓰기 좋은 일반 CSV 산출물입니다.")

        full_pnl_csv = compute_user_pnl(ds, exclude_system_users=exclude_system).to_csv(index=False).encode("utf-8-sig")
        full_item_economy_csv = compute_item_economy(ds, exclude_system_users=exclude_system).to_csv(index=False).encode("utf-8-sig")
        full_block_economy_csv = compute_block_economy(ds, exclude_system_users=exclude_system).to_csv(index=False).encode("utf-8-sig")

        e1, e2, e3 = st.columns(3)
        with e1:
            st.download_button(
                "📊 user_pnl.csv",
                data=full_pnl_csv,
                file_name=_ts_filename("user_pnl_full", "csv"),
                mime="text/csv",
            )
        with e2:
            st.download_button(
                "📊 item_economy.csv",
                data=full_item_economy_csv,
                file_name=_ts_filename("item_economy_full", "csv"),
                mime="text/csv",
            )
        with e3:
            st.download_button(
                "📊 block_economy.csv",
                data=full_block_economy_csv,
                file_name=_ts_filename("block_economy_full", "csv"),
                mime="text/csv",
            )
    else:
        st.info(
            "🔒 공개 배포 모드 — raw 산출물 다운로드는 비활성화되어 있습니다. "
            "추천값/시뮬 결과의 게임 포맷 다운로드는 위에서 받을 수 있습니다."
        )


# -------- 원본 데이터 탭 (PUBLIC_MODE 에서는 비활성화) --------
if tab_data is not None:
  with tab_data:
    st.subheader("원본 테이블")
    table = st.selectbox(
        "테이블 선택",
        [
            "users",
            "blocks",
            "items",
            "games",
            "user_stats",
            "user_block_stats",
            "user_item_stats",
            "user_attendance",
            "game_user_stats",
            "game_user_block_stats",
            "game_user_item_stats",
            "transactions (필터 적용된 결과)",
        ],
    )
    df_map = {
        "users": ds.users,
        "blocks": ds.blocks,
        "items": ds.items,
        "games": ds.games,
        "user_stats": ds.user_stats,
        "user_block_stats": ds.user_block_stats,
        "user_item_stats": ds.user_item_stats,
        "user_attendance": ds.user_attendance,
        "game_user_stats": ds.game_user_stats,
        "game_user_block_stats": ds.game_user_block_stats,
        "game_user_item_stats": ds.game_user_item_stats,
        "transactions (필터 적용된 결과)": ds.transactions,
    }
    df = df_map[table]
    if "user_id" in df.columns:
        df = ds.filter_real_users(df)  # quest 항상 제외
        if exclude_system:
            df = ds.filter_system_users(df)
    st.dataframe(df, width="stretch")
    st.caption(f"{len(df):,} 행")
    st.download_button(
        f"{table} 다운로드 (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=_ts_filename(table.split()[0], "csv"),
        mime="text/csv",
    )
