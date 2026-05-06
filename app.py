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

# Streamlit Cloud는 secrets.toml 을 `st.secrets` 로 노출하지만, 우리 코드
# (특히 pikit_analyzer.data_loader 의 import 시점)는 `os.environ` 으로 읽기
# 때문에, pikit_analyzer import *전에* 한 번 브리지해 둡니다.
try:
    for _k in list(getattr(st, "secrets", {})):
        _v = st.secrets[_k]
        if isinstance(_v, (str, int, float, bool)) and _k not in os.environ:
            os.environ[_k] = str(_v)
except Exception:
    # 로컬 실행 등 secrets 가 없을 때 조용히 무시.
    pass

# 공개 배포 모드 — `PIKIT_PUBLIC=1` 이면 원본 데이터 탭과 raw CSV
# 다운로드 버튼을 숨겨 익명 방문자가 트랜잭션 로그를 직접 받지 못하게.
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
    compute_user_pnl_path,
    compute_user_timeseries,
    compute_winning_moments,
    compute_per_summon_returns,
    summarize_per_summon,
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


# 헬퍼: 사이드바에서 어떤 모드 필터가 선택되든, 모든 분석 화면이
# 같은 ds 를 쓰도록 마지막에 한 번 적용합니다. 적용 순서는
# (날짜 슬라이스) → (모드 슬라이스) 입니다.
def _apply_mode_filter(dataset, mode):
    if mode is None or mode == "전체":
        return dataset
    return dataset.filter_by_game_mode(mode)
snapshots = list_snapshot_dates(Path(data_root))
if not snapshots:
    # Cloud 환경에서 경로가 안 잡힐 때 진단을 도와줄 정보들을 함께 표시.
    st.sidebar.error(f"`{data_root}` 에서 스냅샷을 찾지 못했습니다.")
    with st.sidebar.expander("진단 정보"):
        resolved = Path(data_root).expanduser()
        if not resolved.is_absolute():
            resolved = (Path(__file__).resolve().parent / resolved).resolve()
        st.write("CWD:", os.getcwd())
        st.write("data_root (입력):", data_root)
        st.write("data_root (해석):", str(resolved))
        st.write("data_root 존재:", resolved.exists())
        st.write("PIKIT_DATA_ROOT env:", os.environ.get("PIKIT_DATA_ROOT", "(미설정)"))
        st.write("PIKIT_PUBLIC env:", os.environ.get("PIKIT_PUBLIC", "(미설정)"))
        if resolved.exists():
            try:
                st.write("data_root 내용:", [p.name for p in resolved.iterdir()][:20])
            except Exception as e:
                st.write("listdir 실패:", str(e))
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

st.sidebar.markdown("### 게임 모드")
available_modes = latest_ds.available_game_modes
mode_options = ["전체"] + [m for m in available_modes if m in ("NORMAL", "HARDCORE")]
_default_mode_idx = mode_options.index("NORMAL") if "NORMAL" in mode_options else 0
selected_game_mode = st.sidebar.radio(
    "모드 분리",
    options=mode_options,
    horizontal=True,
    index=_default_mode_idx,
    help=(
        "**전체** = NORMAL + HARDCORE 합산.\n"
        "**NORMAL** = `DEMO_NORMAL_MODE` 게임 트랜잭션만 (장기/캐주얼 풀).\n"
        "**HARDCORE** = `DEMO_HARDCORE_MODE` 게임 트랜잭션만 (고리스크 풀).\n"
        "모드별 경제는 양상이 완전히 다르므로 분리 분석을 권장합니다. 기본은 NORMAL."
    ),
)
mode_filter_for_ds = None if selected_game_mode == "전체" else selected_game_mode

# 사이드바 선택을 ds에 실제로 적용 (날짜 슬라이스가 끝난 뒤).
ds = _apply_mode_filter(ds, mode_filter_for_ds)
if mode_filter_for_ds:
    filter_caption += f"  ·  모드 **{mode_filter_for_ds}** 만"

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
    "🎯 승리 경험",
    "🎰 곡괭이 소환 ROI",
    "⏱️ 시간대별 PNL",
    "🔍 유저 상세 / 그룹 분석",
    "⛏️ 곡괭이 / TNT",
    "🪨 블록",
]
if not PUBLIC_MODE:
    tab_labels.append("📦 원본 데이터")
tab_labels.extend(["│ 🧪 [부가] 시뮬레이터", "│ 📤 [부가] 밸런스 적용"])

_tabs = st.tabs(tab_labels)
tab_users = _tabs[0]
tab_winning = _tabs[1]
tab_summon = _tabs[2]
tab_hourly = _tabs[3]
tab_user_detail = _tabs[4]
tab_items = _tabs[5]
tab_blocks = _tabs[6]
if PUBLIC_MODE:
    tab_data = None
    tab_sim = _tabs[7]
    tab_export = _tabs[8]
else:
    tab_data = _tabs[7]
    tab_sim = _tabs[8]
    tab_export = _tabs[9]


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


# -------- 🎯 승리 경험 탭 --------
with tab_winning:
    st.subheader("승리 경험 — 유저가 잠깐이라도 이긴 순간이 있었는가")
    st.write(
        "장기적으로는 시스템이 이기더라도, 유저는 **세션 중 한 번이라도 자기 PNL이 흑자로 솟는 경험**이 있어야 "
        "재미를 느끼고 다시 플레이합니다. 이 탭은 각 유저의 누적 PNL 곡선의 **peak**, **흑자 체류 시간**, **최대 drawdown** 을 측정해 "
        "'우리 게임이 충분한 승리 경험을 주고 있는가'를 진단합니다."
    )

    wm = compute_winning_moments(ds, exclude_system_users=exclude_system)
    if wm.empty:
        st.info("이 조건에 트랜잭션이 없습니다.")
    else:
        n_total = len(wm)
        n_winning = int(wm["had_winning_moment"].sum())
        n_never_won = n_total - n_winning
        avg_time_above = wm["time_above_zero_pct"].mean() * 100
        avg_excitement = wm["excitement_score"].mean()

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("승리 경험 있음", f"{n_winning} / {n_total}",
                      help="누적 PNL 이 한 번이라도 0 초과를 찍었던 유저 수")
        with m2:
            st.metric("한 번도 못 이김", n_never_won,
                      help="플레이 시작부터 끝까지 누적 PNL 이 0 이하였던 유저 수")
        with m3:
            st.metric("평균 흑자 체류 시간", f"{avg_time_above:.1f}%",
                      help="누적 PNL > 0 였던 시간이 전체 세션 시간의 몇 % 인가의 평균")
        with m4:
            st.metric("평균 흥미도 점수", f"{avg_excitement:.2f}",
                      help="0~1 범위. 변동성 + 승리 경험 + 흑자 체류시간의 가중 평균")

        # 분포 히스토그램 — peak_pnl, time_above_zero_pct, max_drawdown
        st.markdown("### 분포")
        cc1, cc2 = st.columns(2)
        with cc1:
            fig_peak = px.histogram(
                wm, x="peak_pnl", nbins=30,
                title="유저별 peak PNL — 가장 흑자였을 때 얼마였나",
                labels={"peak_pnl": "peak PNL (credit)"},
            )
            fig_peak.add_vline(x=0, line_dash="dot", line_color="orange")
            st.plotly_chart(fig_peak)
        with cc2:
            fig_above = px.histogram(
                wm, x="time_above_zero_pct", nbins=20,
                title="흑자 체류 시간 비율 — PNL > 0 시간 / 전체 세션",
                labels={"time_above_zero_pct": "시간 비율 (0~1)"},
            )
            st.plotly_chart(fig_above)

        cc3, cc4 = st.columns(2)
        with cc3:
            fig_dd = px.scatter(
                wm,
                x="peak_pnl",
                y="max_drawdown",
                color="had_winning_moment",
                hover_name="username",
                title="peak PNL vs max drawdown — 얼마나 올랐다가 얼마나 떨어졌나",
                labels={"peak_pnl": "peak PNL", "max_drawdown": "max drawdown",
                        "had_winning_moment": "흑자 경험"},
            )
            st.plotly_chart(fig_dd)
        with cc4:
            fig_streak = px.histogram(
                wm, x="longest_winning_streak", nbins=20,
                title="가장 긴 연속 보상 — 곡괭이 한 사이클의 보상 횟수",
                labels={"longest_winning_streak": "연속 BLOCK_REWARD 트랜잭션 수"},
            )
            st.plotly_chart(fig_streak)

        # 누적 PNL 곡선 — 상위 흥미도 유저 N명
        st.markdown("### 누적 PNL 곡선 — 흥미도 상위 / 한 번도 못 이긴 유저")
        top_n = st.slider("상위 흥미도 몇 명을 그릴까", 3, 15, 6, 1)
        top_ids = wm.head(top_n)["user_id"].tolist()
        never_won_ids = wm[~wm["had_winning_moment"]].head(3)["user_id"].tolist()
        sample_ids = top_ids + never_won_ids
        path = compute_user_pnl_path(ds, user_ids=sample_ids, exclude_system_users=exclude_system)
        if not path.empty:
            path["label"] = path.apply(
                lambda r: f"#{int(r['user_id'])} {r['username'] or ''}".strip(), axis=1
            )
            fig_path = px.line(
                path,
                x="created_at",
                y="cum_pnl",
                color="label",
                title=f"누적 PNL 곡선 — 흥미도 상위 {top_n} + 한 번도 흑자 없었던 3명",
                labels={"created_at": "시각", "cum_pnl": "누적 PNL", "label": "유저"},
            )
            fig_path.add_hline(y=0, line_dash="dot", line_color="white")
            st.plotly_chart(fig_path)

        # 표
        st.markdown("### 유저별 승리 경험 표")
        sort_by = st.selectbox(
            "정렬 기준",
            ["excitement_score", "peak_pnl", "time_above_zero_pct", "max_drawdown",
             "longest_winning_streak", "final_pnl"],
            index=0,
            key="winning_sort",
        )
        view_w = wm.sort_values(sort_by, ascending=False).reset_index(drop=True)
        st.dataframe(
            view_w,
            width="stretch",
            column_config={
                "user_id": "유저 ID",
                "username": "닉네임",
                "n_tx": st.column_config.NumberColumn("트랜잭션 수", format="%d"),
                "final_pnl": st.column_config.NumberColumn("최종 PNL", format="%d"),
                "peak_pnl": st.column_config.NumberColumn("peak PNL", format="%d"),
                "peak_at": "peak 시각",
                "time_to_peak_min": st.column_config.NumberColumn("peak 까지 분", format="%.1f"),
                "time_above_zero_pct": st.column_config.NumberColumn("흑자 체류", format="%.1%"),
                "max_drawdown": st.column_config.NumberColumn("max drawdown", format="%d"),
                "max_drawdown_pct": st.column_config.NumberColumn("drawdown 비율", format="%.1%"),
                "longest_winning_streak": st.column_config.NumberColumn("최장 보상 연속", format="%d"),
                "had_winning_moment": "흑자 경험",
                "excitement_score": st.column_config.NumberColumn("흥미도", format="%.2f"),
            },
        )
        st.download_button(
            "승리 경험 CSV 다운로드",
            data=view_w.to_csv(index=False).encode("utf-8-sig"),
            file_name=_ts_filename("winning_moments", "csv"),
            mime="text/csv",
        )

        st.markdown("### 밸런스 진단")
        win_rate_overall = n_winning / n_total
        if win_rate_overall < 0.5:
            st.warning(
                f"⚠️ {n_total}명 중 **{n_never_won}명({100 - win_rate_overall*100:.0f}%) 이 한 번도 흑자가 못 됐습니다.** "
                "이 유저들은 '잠깐이라도 이기는' 경험을 못해서 재방문 가능성이 매우 낮습니다. "
                "곡괭이 가격을 낮추거나 초반 보상을 강화해서 *peak PNL > 0* 경험을 더 많은 유저에게 만들어줘야 합니다."
            )
        elif avg_time_above < 0.1:
            st.warning(
                f"⚠️ 평균 흑자 체류 시간이 **{avg_time_above:.1f}%** 로 매우 짧습니다. "
                "유저가 흑자였던 순간이 있어도 너무 빨리 사라집니다 — drawdown 이 가파르다는 신호."
            )
        else:
            st.success(f"✓ {n_winning}/{n_total} 유저가 승리 경험을 했고, 평균 흑자 체류 {avg_time_above:.0f}%.")


# -------- 🎰 곡괭이 소환 ROI 탭 --------
with tab_summon:
    st.subheader("곡괭이 1회 소환 = 1 row")
    st.write(
        "각 곡괭이 구매(소환)마다 그 곡괭이가 활성인 동안 (최대 duration_ms 까지, 다음 구매 전까지) "
        "유저가 받은 **블록 보상 합계**를 계산합니다. 이게 곡괭이 한 번 사면 평균적으로 얼마 벌지를 보여주는 진짜 ROI 분포입니다."
    )

    psr = compute_per_summon_returns(ds, exclude_system_users=exclude_system)
    if psr.empty:
        st.info("이 조건에 곡괭이 구매 트랜잭션이 없습니다.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("총 소환 수", f"{len(psr):,}")
        with m2:
            st.metric("평균 net PNL", _fmt_int(psr["net_pnl"].mean()))
        with m3:
            st.metric("중위 net PNL", _fmt_int(psr["net_pnl"].median()))
        with m4:
            st.metric("승률 (net > 0)", f"{(psr['net_pnl'] > 0).mean() * 100:.1f}%")

        # 곡괭이별 분포 — box plot
        st.markdown("### 곡괭이별 net PNL 분포 (box plot)")
        cat_filter = st.radio("카테고리", ["PICKAXE", "TNT", "전체"], horizontal=True, index=0,
                              key="summon_cat")
        view_psr = psr if cat_filter == "전체" else psr[psr["category"] == cat_filter]
        # 모드는 사이드바에서 이미 필터링되므로 그대로 보여줌.
        if not view_psr.empty:
            fig_box = px.box(
                view_psr,
                x="item_name",
                y="net_pnl",
                points="outliers",
                color="mode",
                title="곡괭이별 1회 소환 net PNL 분포",
                labels={"item_name": "곡괭이", "net_pnl": "net PNL", "mode": "모드"},
            )
            fig_box.add_hline(y=0, line_dash="dot", line_color="orange")
            st.plotly_chart(fig_box)

            # 가격 vs 평균 보상 산점도
            fig_scatter = px.scatter(
                summarize_per_summon(view_psr),
                x="price",
                y="net_pnl_mean",
                size="summons",
                color="win_rate",
                hover_name="item_name",
                title="가격 vs 평균 net PNL (점 크기 = 소환 수, 색 = 승률)",
                labels={"price": "가격", "net_pnl_mean": "평균 net PNL", "win_rate": "승률"},
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0.5,
            )
            fig_scatter.add_hline(y=0, line_dash="dot", line_color="white")
            st.plotly_chart(fig_scatter)

        # 곡괭이별 분포 요약 표
        st.markdown("### 곡괭이별 분포 요약 — 분석에 핵심")
        summ = summarize_per_summon(view_psr)
        st.dataframe(
            summ,
            width="stretch",
            column_config={
                "item_id": "ID",
                "item_name": "이름",
                "mode": "모드",
                "category": "카테고리",
                "price": st.column_config.NumberColumn("가격", format="%d"),
                "attack": st.column_config.NumberColumn("공격력", format="%.2f"),
                "duration_ms": st.column_config.NumberColumn("지속(ms)", format="%d"),
                "summons": st.column_config.NumberColumn("소환 수", format="%d"),
                "unique_buyers": st.column_config.NumberColumn("구매자 수", format="%d"),
                "gross_mean": st.column_config.NumberColumn("평균 gross 보상", format="%.0f"),
                "gross_median": st.column_config.NumberColumn("중위 gross 보상", format="%.0f"),
                "net_pnl_mean": st.column_config.NumberColumn("평균 net PNL", format="%.0f"),
                "net_pnl_median": st.column_config.NumberColumn("중위 net PNL", format="%.0f"),
                "net_pnl_p25": st.column_config.NumberColumn("p25", format="%.0f"),
                "net_pnl_p75": st.column_config.NumberColumn("p75", format="%.0f"),
                "net_pnl_p95": st.column_config.NumberColumn("p95", format="%.0f"),
                "roi_mean": st.column_config.NumberColumn("평균 ROI", format="%.2f"),
                "roi_median": st.column_config.NumberColumn("중위 ROI", format="%.2f"),
                "win_rate": st.column_config.NumberColumn("승률", format="%.1%"),
            },
        )
        st.download_button(
            "곡괭이별 소환 분포 요약 CSV",
            data=summ.to_csv(index=False).encode("utf-8-sig"),
            file_name=_ts_filename("per_summon_summary", "csv"),
            mime="text/csv",
        )

        with st.expander("소환 단위 원본 데이터 (한 행 = 한 번의 구매)"):
            st.dataframe(view_psr, width="stretch")
            st.download_button(
                "전체 소환 원본 CSV",
                data=view_psr.to_csv(index=False).encode("utf-8-sig"),
                file_name=_ts_filename("per_summon_raw", "csv"),
                mime="text/csv",
            )

        st.markdown("### 밸런스 진단")
        if not summ.empty:
            worst = summ.sort_values("win_rate").head(1).iloc[0]
            best = summ.sort_values("win_rate", ascending=False).head(1).iloc[0]
            st.write(
                f"- **승률 최저**: `{worst['item_name']} ({worst['mode']})` — "
                f"승률 **{worst['win_rate']*100:.1f}%**, 평균 net PNL **{worst['net_pnl_mean']:,.0f}**, "
                f"중위 net PNL **{worst['net_pnl_median']:,.0f}**. "
                f"100명이 사면 {int(worst['win_rate']*100)}명만 이기고 나머지는 잃습니다."
            )
            st.write(
                f"- **승률 최고**: `{best['item_name']} ({best['mode']})` — "
                f"승률 **{best['win_rate']*100:.1f}%**, 평균 net PNL **{best['net_pnl_mean']:,.0f}**."
            )
            overall_win = (view_psr["net_pnl"] > 0).mean()
            st.write(
                f"- **전반 승률**: 모든 소환의 **{overall_win*100:.1f}%** 가 net 흑자입니다. "
                "유저가 곡괭이 한 번 사면 4~5번 중 1번 정도만 이긴다는 의미. "
                "이 비율이 너무 낮으면 유저가 '내가 운이 나쁘구나'를 넘어 '이 게임은 못 이기겠다'로 떠납니다."
            )


# -------- 시간대별 PNL 탭 --------
with tab_hourly:
    st.subheader("시간대별 PNL")
    st.write(
        "`user_transaction_log.csv` 의 `created_at` 타임스탬프를 임의 시간 단위로 "
        "집계해, **선택된 모드 / 날짜 범위 안에서 누가·언제 얼마나 벌고 잃었는지** 보여줍니다."
    )

    cc = st.columns([1, 1, 1, 2])
    with cc[0]:
        h_freq_label = st.radio(
            "시간 단위",
            options=["1시간", "30분", "10분", "1일"],
            index=0,
            horizontal=False,
            help="1시간 단위가 기본. 데이터가 짧으면 10분/30분, 길면 1일.",
        )
    with cc[1]:
        h_metric = st.radio(
            "지표",
            options=["PNL", "블록 보상", "아이템 지출", "트랜잭션 수"],
            index=0,
        )
    with cc[2]:
        h_view = st.radio(
            "보는 방식",
            options=["전체 합산", "유저별"],
            index=0,
            help=(
                "전체 합산: 모든 유저를 더한 한 줄.\n"
                "유저별: 상위 N명을 별도 라인 + 히트맵."
            ),
        )
    with cc[3]:
        top_n = st.slider(
            "유저별 모드일 때 상위 몇 명",
            min_value=3,
            max_value=30,
            value=10,
            step=1,
            disabled=(h_view == "전체 합산"),
        )

    h_freq_map = {"1시간": "h", "30분": "30min", "10분": "10min", "1일": "D"}
    h_freq = h_freq_map[h_freq_label]

    h_metric_map = {
        "PNL": "pnl",
        "블록 보상": "block_reward",
        "아이템 지출": "item_spend",
        "트랜잭션 수": "tx_count",
    }
    h_metric_col = h_metric_map[h_metric]

    # 전체 PNL 추이를 보려면 유저 미선택(None) 으로 호출. quest는 항상 제외, system 토글 따름.
    ts_all = compute_user_timeseries(
        ds, user_ids=None, freq=h_freq, exclude_system_users=exclude_system
    )

    if ts_all.empty:
        st.info("해당 조건에 트랜잭션이 없습니다.")
    else:
        # ----- 1) 전체 합산 시계열 -----
        agg = (
            ts_all.groupby("period")
            .agg(
                pnl=("pnl", "sum"),
                block_reward=("block_reward", "sum"),
                item_spend=("item_spend", "sum"),
                tx_count=("tx_count", "sum"),
                active_users=("user_id", lambda s: int((ts_all.loc[s.index, "tx_count"] > 0).sum())),
            )
            .reset_index()
        )
        agg["cum_pnl"] = agg["pnl"].cumsum()

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("기간", f"{agg['period'].min().strftime('%m/%d %H:%M')} ~ {agg['period'].max().strftime('%m/%d %H:%M')}")
        with m2:
            st.metric("총 블록 보상", _fmt_int(agg["block_reward"].sum()))
        with m3:
            st.metric("총 아이템 지출", _fmt_int(agg["item_spend"].sum()))
        with m4:
            st.metric("순 PNL", _fmt_int(agg["pnl"].sum()))

        # 누적 PNL 추이는 한 모드 안에서 시간이 흐를수록 어떤 방향으로 가는지 한눈에.
        st.markdown("### 누적 PNL 추이 (전체 유저 합산)")
        fig_cum = px.line(
            agg,
            x="period",
            y="cum_pnl",
            markers=True,
            title=f"누적 PNL — {h_freq_label} 단위",
            labels={"period": "기간", "cum_pnl": "누적 PNL"},
        )
        fig_cum.add_hline(y=0, line_dash="dot", line_color="white")
        st.plotly_chart(fig_cum)

        # 전체 합산 모드일 때는 단일 막대 그래프, 유저별 모드면 stacked + heatmap.
        if h_view == "전체 합산":
            st.markdown(f"### {h_freq_label}별 {h_metric}")
            fig_bar = px.bar(
                agg,
                x="period",
                y=h_metric_col,
                title=f"{h_freq_label}별 {h_metric}",
                labels={"period": "기간", h_metric_col: h_metric},
            )
            if h_metric == "PNL":
                fig_bar.add_hline(y=0, line_color="white")
            st.plotly_chart(fig_bar)

            # 활성 유저 수 추이.
            active = (
                ts_all[ts_all["tx_count"] > 0]
                .groupby("period")["user_id"]
                .nunique()
                .reset_index(name="active_users")
            )
            fig_active = px.line(
                active,
                x="period",
                y="active_users",
                markers=True,
                title=f"{h_freq_label}별 활성 유저 수",
                labels={"period": "기간", "active_users": "활성 유저 수"},
            )
            st.plotly_chart(fig_active)

        else:
            # ----- 2) 상위 N 유저별 라인 차트 + 히트맵 -----
            user_totals = (
                ts_all.groupby("user_id")[h_metric_col].sum().sort_values(ascending=False)
            )
            top_users = user_totals.head(top_n).index.tolist()
            sub = ts_all[ts_all["user_id"].isin(top_users)].copy()
            sub["label"] = sub.apply(
                lambda r: f"#{int(r['user_id'])} {r['username'] or ''}".strip(), axis=1
            )

            st.markdown(f"### 상위 {top_n}명 {h_freq_label}별 {h_metric}")
            fig_topn = px.bar(
                sub,
                x="period",
                y=h_metric_col,
                color="label",
                title=f"상위 {top_n}명 {h_freq_label}별 {h_metric} (적층)",
                labels={"period": "기간", h_metric_col: h_metric, "label": "유저"},
            )
            if h_metric == "PNL":
                fig_topn.add_hline(y=0, line_color="white")
            st.plotly_chart(fig_topn)

            # 유저 × 시간 히트맵 — 누가 언제 활동했는지 한눈에.
            st.markdown(f"### 유저 × 시간 히트맵 — {h_metric}")
            pivot = sub.pivot_table(
                index="label", columns="period", values=h_metric_col, aggfunc="sum"
            ).fillna(0)
            # 합계 큰 순으로 정렬 (상위 → 하위)
            pivot = pivot.loc[
                pivot.sum(axis=1).sort_values(ascending=False).index
            ]
            color_scale = "RdBu" if h_metric == "PNL" else "Viridis"
            color_args = (
                {"color_continuous_midpoint": 0} if h_metric == "PNL" else {}
            )
            fig_heat = px.imshow(
                pivot,
                aspect="auto",
                title=f"히트맵 — {h_metric}, {h_freq_label} 단위",
                labels={"x": "기간", "y": "유저", "color": h_metric},
                color_continuous_scale=color_scale,
                **color_args,
            )
            st.plotly_chart(fig_heat)

        st.markdown("### 시계열 원본")
        st.dataframe(agg, width="stretch")
        st.download_button(
            "시간대별 합산 CSV 다운로드",
            data=agg.to_csv(index=False).encode("utf-8-sig"),
            file_name=_ts_filename(f"hourly_{h_freq}_{selected_game_mode}", "csv"),
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
