"""
Aggregate metrics derived from a PikitDataset snapshot.

Everything here is recomputed from `transactions` so we never depend on the
already-aggregated stats tables being correct — those are reported alongside
for cross-checking.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data_loader import PikitDataset


# ---------------------------------------------------------------------------
# Per-user PNL
# ---------------------------------------------------------------------------

def compute_user_pnl(ds: PikitDataset, exclude_system_users: bool = True) -> pd.DataFrame:
    """One row per user with credit charged, block reward, item spend, PNL.

    PNL semantics (demo / beta context):
        - DEMO_CREDIT_CHARGE  → free credit issued to the user
        - BLOCK_REWARD        → credit earned in-game by mining
        - ITEM_PURCHASE       → credit spent buying pickaxes / TNT
        - PNL = block_reward - item_spend
            (positive  → mining is more profitable than gear cost)
            (negative  → user is bleeding credits — bad for retention)
    """
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)

    if tx.empty:
        return pd.DataFrame(
            columns=[
                "user_id",
                "username",
                "credit_charged",
                "block_reward",
                "item_spend",
                "pnl",
                "roi",
                "tx_count",
                "first_tx",
                "last_tx",
                "active_minutes",
                "blocks_mined",
                "items_purchased",
            ]
        )

    # ITEM_PURCHASE amounts are recorded as negative debits — convert to
    # positive magnitudes so "spend" is a positive number throughout.
    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()

    grouped = (
        tx.groupby(["user_id", "tx_type"], observed=True)["abs_amount"].sum().unstack(fill_value=0)
    )
    for col in ("DEMO_CREDIT_CHARGE", "BLOCK_REWARD", "ITEM_PURCHASE"):
        if col not in grouped.columns:
            grouped[col] = 0

    counts = (
        tx.groupby(["user_id", "tx_type"], observed=True)["tx_id"].count().unstack(fill_value=0)
    )
    blocks_mined = counts.get("BLOCK_REWARD", pd.Series(0, index=grouped.index))
    items_purchased = counts.get("ITEM_PURCHASE", pd.Series(0, index=grouped.index))

    span = tx.groupby("user_id")["created_at"].agg(["min", "max", "count"])
    span.columns = ["first_tx", "last_tx", "tx_count"]
    span["active_minutes"] = (
        (span["last_tx"] - span["first_tx"]).dt.total_seconds().fillna(0) / 60
    )

    out = grouped.join(span)
    out = out.rename(
        columns={
            "DEMO_CREDIT_CHARGE": "credit_charged",
            "BLOCK_REWARD": "block_reward",
            "ITEM_PURCHASE": "item_spend",
        }
    )
    out["pnl"] = out["block_reward"] - out["item_spend"]
    out["roi"] = np.where(
        out["item_spend"] > 0,
        out["pnl"] / out["item_spend"],
        np.nan,
    )
    out["blocks_mined"] = blocks_mined
    out["items_purchased"] = items_purchased
    out = out.reset_index()

    users = ds.users[["user_id", "username", "wallet_address"]].copy()
    out = out.merge(users, on="user_id", how="left")

    return out[
        [
            "user_id",
            "username",
            "wallet_address",
            "credit_charged",
            "block_reward",
            "item_spend",
            "pnl",
            "roi",
            "tx_count",
            "blocks_mined",
            "items_purchased",
            "first_tx",
            "last_tx",
            "active_minutes",
        ]
    ].sort_values("pnl", ascending=False, ignore_index=True)


# ---------------------------------------------------------------------------
# Block economy
# ---------------------------------------------------------------------------

def compute_block_economy(ds: PikitDataset, exclude_system_users: bool = True) -> pd.DataFrame:
    """How often each block actually drops and the credits it pays out."""
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    block_tx = tx[tx["tx_type"] == "BLOCK_REWARD"].copy()
    block_tx["abs_amount"] = block_tx["amount"].abs()

    agg = (
        block_tx.groupby("source_id")
        .agg(
            actual_drops=("tx_id", "count"),
            actual_total_reward=("abs_amount", "sum"),
            actual_unique_miners=("user_id", "nunique"),
        )
        .reset_index()
        .rename(columns={"source_id": "block_id"})
    )

    blocks = ds.blocks[["block_id", "name", "mode", "drop_rate", "hp", "reward"]].copy()
    out = blocks.merge(agg, on="block_id", how="left").fillna(
        {"actual_drops": 0, "actual_total_reward": 0, "actual_unique_miners": 0}
    )

    total_drops_per_mode = (
        out.groupby("mode")["actual_drops"].transform("sum").replace(0, np.nan)
    )
    out["actual_drop_rate"] = out["actual_drops"] / total_drops_per_mode
    out["drop_rate_delta"] = out["actual_drop_rate"] - out["drop_rate"]

    out["reward_per_hp"] = np.where(out["hp"] > 0, out["reward"] / out["hp"], np.nan)
    out["expected_reward_per_drop"] = out["reward"]
    return out.sort_values(["mode", "block_id"], ignore_index=True)


# ---------------------------------------------------------------------------
# Item (pickaxe / TNT) economy
# ---------------------------------------------------------------------------

def compute_item_economy(ds: PikitDataset, exclude_system_users: bool = True) -> pd.DataFrame:
    """Per-item purchase volume + theoretical & realized output.

    - `theoretical_reward_per_use` = average block reward for the mode, weighted
      by drop rate, multiplied by (duration_ms in seconds).
    - `attack_per_credit` = attack ÷ price (fairness across price tiers).
    - `realized_revenue_per_buy` = avg block reward credited to a user
      *during the same game* as that user's recent item purchase.
    """
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    item_tx = tx[tx["tx_type"] == "ITEM_PURCHASE"].copy()
    item_tx["abs_amount"] = item_tx["amount"].abs()

    agg = (
        item_tx.groupby("source_id")
        .agg(
            purchases=("tx_id", "count"),
            total_revenue=("abs_amount", "sum"),
            unique_buyers=("user_id", "nunique"),
        )
        .reset_index()
        .rename(columns={"source_id": "item_id"})
    )

    items = ds.items.copy()
    out = items.merge(agg, on="item_id", how="left").fillna(
        {"purchases": 0, "total_revenue": 0, "unique_buyers": 0}
    )

    # Mode-level expected reward per block drop.
    blocks = ds.blocks
    expected_reward = (
        blocks.assign(weighted=blocks["drop_rate"] * blocks["reward"])
        .groupby("mode")["weighted"]
        .sum()
    )
    expected_hp = (
        blocks.assign(weighted_hp=blocks["drop_rate"] * blocks["hp"])
        .groupby("mode")["weighted_hp"]
        .sum()
    )
    out["mode_expected_reward_per_drop"] = out["mode"].map(expected_reward)
    out["mode_expected_hp_per_drop"] = out["mode"].map(expected_hp)

    # Theoretical reward = (duration_seconds * attack / expected_hp_per_drop) * expected_reward_per_drop
    out["duration_s"] = out["duration_ms"] / 1000
    out["theoretical_breaks_per_use"] = np.where(
        out["mode_expected_hp_per_drop"] > 0,
        out["duration_s"] * out["attack"] / out["mode_expected_hp_per_drop"],
        np.nan,
    )
    out["theoretical_reward_per_use"] = (
        out["theoretical_breaks_per_use"] * out["mode_expected_reward_per_drop"]
    )
    out["theoretical_roi"] = np.where(
        out["price"] > 0,
        (out["theoretical_reward_per_use"] - out["price"]) / out["price"],
        np.nan,
    )
    out["attack_per_credit"] = np.where(
        out["price"] > 0, out["attack"] / out["price"], np.nan
    )

    # Realized ROI per item, computed by attributing each user's per-game
    # block reward to the items that user purchased in the same game,
    # weighted by item purchase count.
    realized = _compute_realized_item_roi(ds, exclude_system_users=exclude_system_users)
    out = out.merge(realized, on="item_id", how="left")

    return out.sort_values(["mode", "item_id"], ignore_index=True)


def _compute_realized_item_roi(ds: PikitDataset, exclude_system_users: bool = True) -> pd.DataFrame:
    """Approximate realized reward per credit spent on each item.

    Method: for each (user_id, game_id), distribute the user's BLOCK_REWARD
    total proportionally across the items they purchased in that game,
    weighted by item count. Then sum per item to get realized_revenue, and
    divide by realized_spend to get realized ROI.
    """
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)

    if tx.empty:
        return pd.DataFrame(
            columns=[
                "item_id",
                "realized_spend",
                "realized_reward_attributed",
                "realized_roi",
            ]
        )

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()

    rewards = (
        tx[tx["tx_type"] == "BLOCK_REWARD"]
        .groupby(["user_id", "game_id"])["abs_amount"]
        .sum()
        .rename("user_game_reward")
    )

    items = tx[tx["tx_type"] == "ITEM_PURCHASE"].copy()
    items["source_id"] = items["source_id"].astype("Int64")
    item_counts = items.groupby(["user_id", "game_id", "source_id"]).agg(
        spend=("abs_amount", "sum"), count=("tx_id", "count")
    )

    user_game_total_count = item_counts.groupby(level=[0, 1])["count"].sum().rename(
        "total_item_count"
    )

    merged = item_counts.join(rewards, on=["user_id", "game_id"]).join(
        user_game_total_count, on=["user_id", "game_id"]
    )
    merged = merged.fillna({"user_game_reward": 0, "total_item_count": 0})
    merged["attributed_reward"] = np.where(
        merged["total_item_count"] > 0,
        merged["user_game_reward"] * merged["count"] / merged["total_item_count"],
        0,
    )

    by_item = merged.groupby(level=2).agg(
        realized_spend=("spend", "sum"),
        realized_reward_attributed=("attributed_reward", "sum"),
    )
    by_item["realized_roi"] = np.where(
        by_item["realized_spend"] > 0,
        (by_item["realized_reward_attributed"] - by_item["realized_spend"])
        / by_item["realized_spend"],
        np.nan,
    )
    by_item.index.name = "item_id"
    return by_item.reset_index()


# ---------------------------------------------------------------------------
# Per-game session metrics
# ---------------------------------------------------------------------------

def compute_session_metrics(ds: PikitDataset, exclude_system_users: bool = True) -> pd.DataFrame:
    """One row per (user, game) session — useful for distribution charts."""
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)

    if tx.empty:
        return pd.DataFrame()

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    pivot = (
        tx.groupby(["user_id", "game_id", "tx_type"], observed=True)["abs_amount"]
        .sum()
        .unstack(fill_value=0)
    )
    for col in ("DEMO_CREDIT_CHARGE", "BLOCK_REWARD", "ITEM_PURCHASE"):
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot.rename(
        columns={
            "DEMO_CREDIT_CHARGE": "credit_charged",
            "BLOCK_REWARD": "block_reward",
            "ITEM_PURCHASE": "item_spend",
        }
    )
    pivot["pnl"] = pivot["block_reward"] - pivot["item_spend"]
    pivot["roi"] = np.where(
        pivot["item_spend"] > 0,
        pivot["pnl"] / pivot["item_spend"],
        np.nan,
    )

    times = tx.groupby(["user_id", "game_id"])["created_at"].agg(["min", "max", "count"])
    times.columns = ["session_start", "session_end", "tx_count"]
    times["duration_s"] = (
        (times["session_end"] - times["session_start"]).dt.total_seconds().fillna(0)
    )

    out = pivot.join(times).reset_index()

    games = ds.games[["game_id", "mode_name"]].rename(columns={"mode_name": "game_mode"})
    out = out.merge(games, on="game_id", how="left")

    users = ds.users[["user_id", "username"]]
    out = out.merge(users, on="user_id", how="left")

    return out.sort_values("pnl", ignore_index=True)


# ---------------------------------------------------------------------------
# Per-user time series
# ---------------------------------------------------------------------------

def compute_user_timeseries(
    ds: PikitDataset,
    user_ids: list[int] | None = None,
    freq: str = "D",
    exclude_system_users: bool = True,
    fill_gaps: bool = False,
) -> pd.DataFrame:
    """Resample transactions into a per-(period, user) time series.

    `fill_gaps=False` (기본) — 활동 없는 (period,user) 셀은 행을 만들지 않음.
    `fill_gaps=True` — 빈 셀을 0으로 채워 라인 차트가 끊기지 않게 (느림).

    필터 순서를 (1) user_ids → (2) quest → (3) system 으로 바꿔서 큰 카피가
    먼저 줄어들도록 했습니다. 이게 1분 단위 60만 건 트랜잭션에서 가장 큰 win.
    """
    tx = ds.transactions

    # 가장 강한 필터부터 — 데이터 양을 즉시 줄여서 이후 작업이 가벼워짐.
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]
    if ds.quest_user_ids:
        tx = tx[~tx["user_id"].isin(ds.quest_user_ids)]
    if exclude_system_users and ds.system_user_ids:
        tx = tx[~tx["user_id"].isin(ds.system_user_ids)]

    if tx.empty:
        return pd.DataFrame(
            columns=[
                "period", "user_id", "username", "block_reward", "item_spend",
                "credit_charged", "pnl", "tx_count", "cum_pnl",
                "cum_block_reward", "cum_item_spend",
            ]
        )

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    tx["period"] = tx["created_at"].dt.floor(freq)

    pivot = (
        tx.groupby(["period", "user_id", "tx_type"], observed=True)["abs_amount"]
        .sum()
        .unstack("tx_type", fill_value=0)
    )
    for col in ("DEMO_CREDIT_CHARGE", "BLOCK_REWARD", "ITEM_PURCHASE"):
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot.rename(
        columns={
            "DEMO_CREDIT_CHARGE": "credit_charged",
            "BLOCK_REWARD": "block_reward",
            "ITEM_PURCHASE": "item_spend",
        }
    )

    counts = (
        tx.groupby(["period", "user_id"])["tx_id"].count().rename("tx_count")
    )
    out = pivot.join(counts).fillna(0).reset_index()
    out["pnl"] = out["block_reward"] - out["item_spend"]

    # 빈 (user, period) 셀 0 으로 채우기 — 옵션화. 1분 단위로 4320 period * N 유저
    # 를 곱하면 매트릭스가 폭증해서 느려집니다.
    if fill_gaps and not out.empty:
        period_min = out["period"].min()
        period_max = out["period"].max()
        all_periods = pd.date_range(period_min, period_max, freq=freq)
        users_present = out["user_id"].unique()
        full_index = pd.MultiIndex.from_product(
            [all_periods, users_present], names=["period", "user_id"]
        )
        out = (
            out.set_index(["period", "user_id"])
            .reindex(full_index, fill_value=0)
            .reset_index()
        )

    out = out.sort_values(["user_id", "period"]).reset_index(drop=True)

    grouped = out.groupby("user_id", group_keys=False)
    out["cum_block_reward"] = grouped["block_reward"].cumsum()
    out["cum_item_spend"] = grouped["item_spend"].cumsum()
    out["cum_pnl"] = grouped["pnl"].cumsum()

    users = ds.users[["user_id", "username", "wallet_address"]]
    out = out.merge(users, on="user_id", how="left")
    return out


def compute_user_block_breakdown(
    ds: PikitDataset,
    user_ids: list[int] | None = None,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """Per-user, per-block totals (count and credits earned)."""
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]

    block_tx = tx[tx["tx_type"] == "BLOCK_REWARD"].copy()
    if block_tx.empty:
        return pd.DataFrame(
            columns=["user_id", "username", "block_id", "block_name", "mode", "count", "reward_total"]
        )
    block_tx["abs_amount"] = block_tx["amount"].abs()

    agg = (
        block_tx.groupby(["user_id", "source_id"])
        .agg(count=("tx_id", "count"), reward_total=("abs_amount", "sum"))
        .reset_index()
        .rename(columns={"source_id": "block_id"})
    )
    blocks = ds.blocks[["block_id", "name", "mode"]].rename(columns={"name": "block_name"})
    out = agg.merge(blocks, on="block_id", how="left")
    users = ds.users[["user_id", "username"]]
    out = out.merge(users, on="user_id", how="left")
    return out.sort_values(["user_id", "reward_total"], ascending=[True, False]).reset_index(drop=True)


def compute_user_item_breakdown(
    ds: PikitDataset,
    user_ids: list[int] | None = None,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """Per-user, per-item purchase totals."""
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]

    item_tx = tx[tx["tx_type"] == "ITEM_PURCHASE"].copy()
    if item_tx.empty:
        return pd.DataFrame(
            columns=["user_id", "username", "item_id", "item_name", "mode", "category", "count", "spend_total"]
        )
    item_tx["abs_amount"] = item_tx["amount"].abs()

    agg = (
        item_tx.groupby(["user_id", "source_id"])
        .agg(count=("tx_id", "count"), spend_total=("abs_amount", "sum"))
        .reset_index()
        .rename(columns={"source_id": "item_id"})
    )
    items = ds.items[["item_id", "name", "mode", "category"]].rename(
        columns={"name": "item_name"}
    )
    out = agg.merge(items, on="item_id", how="left")
    users = ds.users[["user_id", "username"]]
    out = out.merge(users, on="user_id", how="left")
    return out.sort_values(["user_id", "spend_total"], ascending=[True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Winning Moments — "유저가 잠깐이라도 이긴 순간이 있었는가"
# ---------------------------------------------------------------------------

def compute_winning_moments(
    ds: PikitDataset,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """유저별 누적 PNL 곡선의 형태 분석.

    게임은 장기적으로 시스템(곡괭이 가격) 이 유저보다 유리하게 설계되더라도,
    유저 입장에서는 *잠깐이라도* 자기 PNL 이 양수로 솟아오른 순간이 있어야
    재미·재방문이 일어납니다. 이 함수는 그 "승리 경험"을 정량화합니다.

    반환 컬럼
    ----------
    user_id, username
    n_tx              : 트랜잭션 수
    final_pnl         : 마지막 누적 PNL
    peak_pnl          : 누적 PNL 최댓값 (가장 흑자였을 때)
    peak_at           : peak_pnl 시각
    time_to_peak_min  : 첫 트랜잭션 → peak 까지 걸린 분
    time_above_zero_pct : 누적 PNL > 0 였던 시간 비율
    max_drawdown      : peak − final
    max_drawdown_pct  : peak 대비 떨어진 비율
    longest_winning_streak : BLOCK_REWARD 연속 트랜잭션 최장
    had_winning_moment : 한 번이라도 흑자였는가
    excitement_score  : 변동성 + 승리경험 + 흑자체류시간의 가중 합 (0~1)
    """
    tx = ds.filter_real_users(ds.transactions)
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if tx.empty:
        return pd.DataFrame()

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    tx["signed"] = np.where(
        tx["tx_type"] == "BLOCK_REWARD", tx["abs_amount"],
        np.where(tx["tx_type"] == "ITEM_PURCHASE", -tx["abs_amount"], 0),
    )
    tx = tx.sort_values(["user_id", "created_at"]).reset_index(drop=True)

    rows = []
    for uid, sub in tx.groupby("user_id", sort=False):
        s = sub.sort_values("created_at")
        cum = s["signed"].cumsum()
        ts = s["created_at"]

        peak_pnl = float(cum.max()) if not cum.empty else 0.0
        peak_idx = cum.idxmax() if not cum.empty else None
        peak_at = ts.loc[peak_idx] if peak_idx is not None else pd.NaT
        first_t = ts.iloc[0]
        last_t = ts.iloc[-1]

        time_to_peak_min = (
            (peak_at - first_t).total_seconds() / 60 if pd.notna(peak_at) else 0
        )
        total_seconds = max((last_t - first_t).total_seconds(), 1)

        deltas = s["created_at"].diff().shift(-1).dt.total_seconds().fillna(0)
        positive_weighted = float(deltas[cum.values > 0].sum()) if not cum.empty else 0.0
        time_above_zero_pct = positive_weighted / total_seconds if total_seconds else 0.0

        max_dd = max(peak_pnl - float(cum.iloc[-1]), 0) if not cum.empty else 0
        max_dd_pct = (max_dd / peak_pnl) if peak_pnl > 0 else None

        is_reward = (s["tx_type"] == "BLOCK_REWARD").astype(int).values
        longest_streak = 0
        cur = 0
        for v in is_reward:
            if v:
                cur += 1
                longest_streak = max(longest_streak, cur)
            else:
                cur = 0

        had_winning_moment = peak_pnl > 0
        std_pnl = float(cum.std()) if len(cum) > 1 else 0.0
        norm_std = min(std_pnl / 1_000_000, 1.0)
        score = 0.4 * norm_std + 0.4 * float(had_winning_moment) + 0.2 * float(time_above_zero_pct)

        rows.append({
            "user_id": int(uid),
            "n_tx": int(len(s)),
            "final_pnl": float(cum.iloc[-1]) if not cum.empty else 0.0,
            "peak_pnl": peak_pnl,
            "peak_at": peak_at,
            "time_to_peak_min": float(time_to_peak_min),
            "time_above_zero_pct": float(time_above_zero_pct),
            "max_drawdown": float(max_dd),
            "max_drawdown_pct": max_dd_pct,
            "longest_winning_streak": int(longest_streak),
            "had_winning_moment": bool(had_winning_moment),
            "excitement_score": float(score),
            "first_tx": first_t,
            "last_tx": last_t,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        users = ds.users[["user_id", "username"]]
        out = out.merge(users, on="user_id", how="left")
    return out.sort_values("excitement_score", ascending=False, ignore_index=True)


def compute_user_pnl_path(
    ds: PikitDataset,
    user_ids: list[int] | None = None,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """유저별 누적 PNL 곡선 시계열 (그래프용)."""
    tx = ds.filter_real_users(ds.transactions)
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]
    if tx.empty:
        return pd.DataFrame(columns=["user_id", "username", "created_at", "signed_amount", "cum_pnl"])

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    tx["signed_amount"] = np.where(
        tx["tx_type"] == "BLOCK_REWARD", tx["abs_amount"],
        np.where(tx["tx_type"] == "ITEM_PURCHASE", -tx["abs_amount"], 0),
    )
    tx = tx.sort_values(["user_id", "created_at"])
    tx["cum_pnl"] = tx.groupby("user_id")["signed_amount"].cumsum()
    users = ds.users[["user_id", "username"]]
    return tx[["user_id", "created_at", "signed_amount", "cum_pnl"]].merge(
        users, on="user_id", how="left"
    )


# ---------------------------------------------------------------------------
# Per-summon credit return — 곡괭이 한 번 구매당 가져온 보상
# ---------------------------------------------------------------------------

def compute_per_summon_returns(
    ds: PikitDataset,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """곡괭이 1회 소환(구매) 당 net 수익 분포.

    윈도우 = [구매 시각, min(다음 구매 시각, 구매 시각 + duration_ms)).
    그 윈도우 안에서 동일 유저의 BLOCK_REWARD 합산.

    한 행 = 한 번의 구매. 컬럼: user_id, item_id, item_name, mode, category,
    price, attack, duration_ms, purchased_at, ended_at, gross_reward,
    net_pnl, roi.
    """
    tx = ds.filter_real_users(ds.transactions)
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if tx.empty:
        return pd.DataFrame()

    items = ds.items[
        ["item_id", "name", "mode", "category", "price", "attack", "duration_ms"]
    ].rename(columns={"name": "item_name"})

    purchases = tx[tx["tx_type"] == "ITEM_PURCHASE"]
    if purchases.empty:
        return pd.DataFrame()

    # ---- 구매 행 가공 (벡터화) ----
    purchases = purchases[["user_id", "created_at", "source_id", "amount"]].copy()
    purchases["item_id"] = pd.to_numeric(
        purchases["source_id"], errors="coerce"
    ).astype("Int64")
    purchases = purchases.dropna(subset=["item_id"])
    purchases["item_id"] = purchases["item_id"].astype(int)
    # item 정보 조인 (없는 item_id 는 자연스럽게 inner join 으로 제거됨)
    purchases = purchases.merge(items, on="item_id", how="inner")
    if purchases.empty:
        return pd.DataFrame()

    purchases = purchases.sort_values(["user_id", "created_at"]).reset_index(drop=True)

    # 윈도우 끝 시각 = min(다음 구매, 구매+duration). next 가 NaT 이면 duration 만.
    purchases["t_buy"] = purchases["created_at"]
    purchases["next_purchase_at"] = purchases.groupby("user_id")["created_at"].shift(-1)
    duration_td = pd.to_timedelta(purchases["duration_ms"].fillna(0), unit="ms")
    purchases["t_dur_end"] = purchases["t_buy"] + duration_td
    nxt = purchases["next_purchase_at"]
    dur = purchases["t_dur_end"]
    # next < dur 면 next, 아니면 dur (next NaT 이면 비교가 False → dur).
    purchases["t_end"] = nxt.where(nxt < dur, dur)

    # ---- 보상 행 가공 + 유저별 prefix-sum ----
    rewards = tx[tx["tx_type"] == "BLOCK_REWARD"][
        ["user_id", "created_at", "amount"]
    ].copy()
    rewards["abs_amount"] = rewards["amount"].abs().astype(np.float64)
    rewards = rewards.sort_values(["user_id", "created_at"]).reset_index(drop=True)

    gross = np.zeros(len(purchases), dtype=np.float64)
    if not rewards.empty:
        # 유저별 cumulative sum + searchsorted 로 [t_buy, t_end) 구간 합을 O(log N) 로.
        # 외부 루프는 유저(보통 수십~수백명) 하나당 한 번 — 행 단위 iterrows 의 O(M) 보다
        # 압도적으로 빠름 (M = 구매 수, 수만~수십만).
        purchases_uid = purchases["user_id"].to_numpy()
        p_buy = purchases["t_buy"].to_numpy()
        p_end = purchases["t_end"].to_numpy()
        for uid, r_grp in rewards.groupby("user_id", sort=False):
            mask = purchases_uid == uid
            if not mask.any():
                continue
            r_times = r_grp["created_at"].to_numpy()
            r_cum = np.empty(len(r_grp) + 1, dtype=np.float64)
            r_cum[0] = 0.0
            np.cumsum(r_grp["abs_amount"].to_numpy(), out=r_cum[1:])
            idx_buy = np.searchsorted(r_times, p_buy[mask], side="left")
            idx_end = np.searchsorted(r_times, p_end[mask], side="left")
            gross[mask] = r_cum[idx_end] - r_cum[idx_buy]

    purchases["gross_reward"] = gross
    price_safe = purchases["price"].astype(np.float64).fillna(0.0)
    purchases["price"] = price_safe
    purchases["net_pnl"] = gross - price_safe.to_numpy()
    # ROI: price 가 양수일 때만, 아니면 NaN.
    purchases["roi"] = np.where(
        price_safe > 0,
        purchases["net_pnl"].to_numpy() / price_safe.to_numpy(),
        np.nan,
    )

    return purchases[
        [
            "user_id", "item_id", "item_name", "mode", "category",
            "price", "attack", "duration_ms",
            "t_buy", "t_end",
            "gross_reward", "net_pnl", "roi",
        ]
    ].rename(columns={"t_buy": "purchased_at", "t_end": "ended_at"}).reset_index(drop=True)


def summarize_per_summon(per_summon: pd.DataFrame) -> pd.DataFrame:
    """곡괭이별 소환 결과 분포 요약 — mean/median/percentile/win_rate."""
    if per_summon.empty:
        return pd.DataFrame()
    grouped = per_summon.groupby(
        ["item_id", "item_name", "mode", "category", "price", "attack", "duration_ms"],
        dropna=False,
    )
    summary = grouped.agg(
        summons=("net_pnl", "size"),
        unique_buyers=("user_id", "nunique"),
        gross_mean=("gross_reward", "mean"),
        gross_median=("gross_reward", "median"),
        net_pnl_mean=("net_pnl", "mean"),
        net_pnl_median=("net_pnl", "median"),
        net_pnl_p25=("net_pnl", lambda s: float(np.percentile(s, 25))),
        net_pnl_p75=("net_pnl", lambda s: float(np.percentile(s, 75))),
        net_pnl_p95=("net_pnl", lambda s: float(np.percentile(s, 95))),
        roi_mean=("roi", "mean"),
        roi_median=("roi", "median"),
        win_rate=("net_pnl", lambda s: float((s > 0).mean())),
    ).reset_index()
    return summary.sort_values(["mode", "category", "price"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Casino-style engagement metrics
# ---------------------------------------------------------------------------

OUTCOME_TIERS = ["BUST", "LOSS", "BREAK_EVEN", "WIN", "JACKPOT"]
"""곡괭이 1회 소환 결과 등급 — 가격 대비 net_pnl 비율 (=ROI) 기준.

  BUST       : ROI < -0.75   가격의 25% 미만 회수 (사실상 꽝)
  LOSS       : -0.75 <= ROI < 0
  BREAK_EVEN : 0 <= ROI < 0.50  본전 ~ 살짝 흑자
  WIN        : 0.50 <= ROI < 2.00   1.5x ~ 3x — 만족스러운 흑자
  JACKPOT    : ROI >= 2.00   3x 이상 — 도파민 트리거
"""


def classify_outcome(roi: float | None) -> str:
    """ROI(net_pnl/price) 를 5단계 결과 등급으로."""
    if roi is None or pd.isna(roi):
        return "UNKNOWN"
    if roi < -0.75:
        return "BUST"
    if roi < 0:
        return "LOSS"
    if roi < 0.5:
        return "BREAK_EVEN"
    if roi < 2.0:
        return "WIN"
    return "JACKPOT"


def compute_summon_outcomes(
    ds: PikitDataset,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """소환별 결과에 outcome_tier + hit (gross>0) 컬럼 추가.

    `compute_per_summon_returns` 결과에 카지노식 등급을 붙입니다.
    """
    psr = compute_per_summon_returns(ds, exclude_system_users=exclude_system_users)
    if psr.empty:
        return psr
    psr = psr.copy()
    psr["outcome_tier"] = psr["roi"].apply(classify_outcome)
    psr["hit"] = psr["gross_reward"] > 0
    psr = psr.sort_values(["user_id", "purchased_at"]).reset_index(drop=True)
    return psr


def summarize_outcome_tiers(psr: pd.DataFrame) -> pd.DataFrame:
    """곡괭이별 등급 분포 + hit_rate + 종합 통계.

    각 곡괭이에 대해 BUST/LOSS/BREAK_EVEN/WIN/JACKPOT 비율 + hit_rate.
    """
    if psr.empty or "outcome_tier" not in psr.columns:
        return pd.DataFrame()

    keys = ["item_id", "item_name", "mode", "category", "price", "attack", "duration_ms"]
    grouped = psr.groupby(keys, dropna=False)

    rows = []
    for k, sub in grouped:
        n = len(sub)
        row = dict(zip(keys, k))
        row["summons"] = n
        row["hit_rate"] = float(sub["hit"].mean()) if n else 0.0
        for tier in OUTCOME_TIERS:
            row[f"pct_{tier.lower()}"] = float((sub["outcome_tier"] == tier).sum() / n) if n else 0.0
        row["pct_win_or_better"] = float((sub["outcome_tier"].isin(["WIN", "JACKPOT"])).sum() / n) if n else 0.0
        row["pct_jackpot"] = float((sub["outcome_tier"] == "JACKPOT").sum() / n) if n else 0.0
        row["expected_roi"] = float(sub["roi"].mean()) if n else None  # = casino RTP - 1
        rows.append(row)
    out = pd.DataFrame(rows).sort_values(["mode", "category", "price"]).reset_index(drop=True)
    return out


def compute_engagement_pulse(
    ds: PikitDataset,
    drought_threshold: int = 5,
    comeback_window: int = 3,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """유저별 카지노식 흥미도 지표.

    - inter_win_gap_summons : WIN+ 결과 사이의 평균 소환 수
    - inter_win_gap_minutes : WIN+ 결과 사이의 평균 시간 (분)
    - longest_drought_summons : 연속 non-WIN(BUST/LOSS/BREAK_EVEN) 최장
    - longest_drought_minutes : 그 drought 기간 (분)
    - drought_total_minutes : 전체 drought 시간 합
    - comeback_rate : drought_threshold 이상 못 이겼을 때, 그 다음 comeback_window 안에 WIN+ 나온 비율
    - jackpot_count, win_count, total_summons
    """
    psr = compute_summon_outcomes(ds, exclude_system_users=exclude_system_users)
    if psr.empty:
        return pd.DataFrame()

    rows = []
    for uid, sub in psr.groupby("user_id"):
        s = sub.sort_values("purchased_at").reset_index(drop=True)
        is_win = s["outcome_tier"].isin(["WIN", "JACKPOT"]).values

        # WIN+ 의 인덱스
        win_idxs = np.where(is_win)[0]
        if len(win_idxs) >= 2:
            gaps_count = np.diff(win_idxs)
            gap_count_mean = float(gaps_count.mean())
            gap_count_median = float(np.median(gaps_count))
            # 시간 차이
            win_times = s.loc[win_idxs, "purchased_at"].reset_index(drop=True)
            gaps_min = (win_times.diff().dt.total_seconds() / 60).dropna().tolist()
            gap_min_mean = float(np.mean(gaps_min)) if gaps_min else None
            gap_min_median = float(np.median(gaps_min)) if gaps_min else None
        else:
            gap_count_mean = gap_count_median = None
            gap_min_mean = gap_min_median = None

        # Drought = 연속 non-WIN
        droughts = []
        cur_run = 0
        cur_start = None
        max_drought = 0
        max_drought_start = None
        max_drought_end = None
        for i, w in enumerate(is_win):
            if not w:
                if cur_run == 0:
                    cur_start = i
                cur_run += 1
                if cur_run > max_drought:
                    max_drought = cur_run
                    max_drought_start = cur_start
                    max_drought_end = i
            else:
                if cur_run > 0:
                    droughts.append(cur_run)
                cur_run = 0
        if cur_run > 0:
            droughts.append(cur_run)

        if max_drought_start is not None and max_drought_end is not None and max_drought_end > max_drought_start:
            longest_drought_min = (
                s.loc[max_drought_end, "purchased_at"]
                - s.loc[max_drought_start, "purchased_at"]
            ).total_seconds() / 60
        else:
            longest_drought_min = 0

        drought_total_min = 0
        cur_run = 0
        run_start = None
        for i, w in enumerate(is_win):
            if not w:
                if cur_run == 0:
                    run_start = i
                cur_run += 1
            else:
                if cur_run > 0 and run_start is not None:
                    drought_total_min += (
                        s.loc[i, "purchased_at"] - s.loc[run_start, "purchased_at"]
                    ).total_seconds() / 60
                cur_run = 0
                run_start = None
        if cur_run > 0 and run_start is not None:
            drought_total_min += (
                s.loc[len(s) - 1, "purchased_at"] - s.loc[run_start, "purchased_at"]
            ).total_seconds() / 60

        # Comeback rate
        comeback_total = 0
        comeback_success = 0
        cur_run = 0
        for i, w in enumerate(is_win):
            if not w:
                cur_run += 1
            else:
                if cur_run >= drought_threshold:
                    comeback_total += 1
                    # 이미 win 이라 1로 친다 — 즉 drought 끝나고 첫 결과가 WIN+ 인지.
                    comeback_success += 1
                cur_run = 0
        # 또 다른 정의: drought_threshold 도달 시점부터 comeback_window 내에 WIN+ 가 있었는지.
        cb2_total = 0
        cb2_success = 0
        cur_run = 0
        for i, w in enumerate(is_win):
            if not w:
                cur_run += 1
                if cur_run == drought_threshold:
                    cb2_total += 1
                    # 이후 comeback_window 안에 WIN+
                    upper = min(i + comeback_window + 1, len(is_win))
                    if any(is_win[i + 1:upper]):
                        cb2_success += 1
            else:
                cur_run = 0
        comeback_rate = (cb2_success / cb2_total) if cb2_total else None

        rows.append({
            "user_id": int(uid),
            "total_summons": int(len(s)),
            "win_count": int(is_win.sum()),
            "jackpot_count": int((s["outcome_tier"] == "JACKPOT").sum()),
            "win_or_better_rate": float(is_win.mean()) if len(is_win) else 0.0,
            "hit_rate": float(s["hit"].mean()),
            "inter_win_gap_summons_mean": gap_count_mean,
            "inter_win_gap_summons_median": gap_count_median,
            "inter_win_gap_minutes_mean": gap_min_mean,
            "inter_win_gap_minutes_median": gap_min_median,
            "longest_drought_summons": int(max_drought),
            "longest_drought_minutes": float(longest_drought_min),
            "drought_total_minutes": float(drought_total_min),
            "drought_count": len(droughts),
            "comeback_rate": comeback_rate,
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        users = ds.users[["user_id", "username"]]
        out = out.merge(users, on="user_id", how="left")
    return out.sort_values("win_or_better_rate", ascending=False, ignore_index=True)


def compute_per_minute_grid(
    ds: PikitDataset,
    user_ids: list[int] | None = None,
    freq: str = "1min",
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """유저 × 시간 버킷 그리드 — 카지노 히트맵 데이터.

    각 (user, period) 셀에 다음을 계산:
    - delta_pnl    : block_reward - item_spend 합 (양수=흑자, 음수=적자)
    - n_summons    : ITEM_PURCHASE 수
    - n_rewards    : BLOCK_REWARD 수
    - max_reward   : 그 버킷에서 받은 최대 단일 보상 (큰 값 = 그 순간 흥분)
    - any_jackpot  : 그 버킷에 JACKPOT(>= 3x ROI) 결과가 있었는지
    """
    tx = ds.filter_real_users(ds.transactions)
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]
    if tx.empty:
        return pd.DataFrame(columns=[
            "user_id", "username", "period", "delta_pnl", "n_summons",
            "n_rewards", "max_reward", "any_jackpot",
        ])

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    tx["signed"] = np.where(
        tx["tx_type"] == "BLOCK_REWARD", tx["abs_amount"],
        np.where(tx["tx_type"] == "ITEM_PURCHASE", -tx["abs_amount"], 0),
    )
    tx["period"] = tx["created_at"].dt.floor(freq)

    # delta_pnl
    pnl_grid = (
        tx.groupby(["user_id", "period"])
        .agg(
            delta_pnl=("signed", "sum"),
            n_summons=("tx_type", lambda s: int((s == "ITEM_PURCHASE").sum())),
            n_rewards=("tx_type", lambda s: int((s == "BLOCK_REWARD").sum())),
            max_reward=("abs_amount", lambda s: float(s[tx.loc[s.index, "tx_type"] == "BLOCK_REWARD"].max()) if any(tx.loc[s.index, "tx_type"] == "BLOCK_REWARD") else 0.0),
        )
        .reset_index()
    )

    # any_jackpot — 그 (user, period) 안에 JACKPOT 결과 소환이 포함됐는지.
    psr = compute_summon_outcomes(ds, exclude_system_users=exclude_system_users)
    if not psr.empty:
        if user_ids is not None:
            psr = psr[psr["user_id"].isin(user_ids)]
        psr = psr.copy()
        psr["period"] = psr["purchased_at"].dt.floor(freq)
        jpx = (
            psr.groupby(["user_id", "period"])["outcome_tier"]
            .apply(lambda s: bool((s == "JACKPOT").any()))
            .reset_index(name="any_jackpot")
        )
        pnl_grid = pnl_grid.merge(jpx, on=["user_id", "period"], how="left")
        pnl_grid["any_jackpot"] = pnl_grid["any_jackpot"].fillna(False)
    else:
        pnl_grid["any_jackpot"] = False

    users = ds.users[["user_id", "username"]]
    pnl_grid = pnl_grid.merge(users, on="user_id", how="left")
    return pnl_grid.sort_values(["user_id", "period"], ignore_index=True)


# ---------------------------------------------------------------------------
# Top-level KPI summary
# ---------------------------------------------------------------------------

def compute_kpi_summary(ds: PikitDataset, exclude_system_users: bool = True) -> dict:
    """High-level numbers for the dashboard header."""
    pnl = compute_user_pnl(ds, exclude_system_users=exclude_system_users)
    sessions = compute_session_metrics(ds, exclude_system_users=exclude_system_users)
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)

    n_users = pnl["user_id"].nunique() if not pnl.empty else 0
    n_paying = int((pnl["item_spend"] > 0).sum()) if not pnl.empty else 0
    n_winning = int((pnl["pnl"] > 0).sum()) if not pnl.empty else 0
    n_losing = int((pnl["pnl"] < 0).sum()) if not pnl.empty else 0

    total_block_reward = float(pnl["block_reward"].sum()) if not pnl.empty else 0
    total_item_spend = float(pnl["item_spend"].sum()) if not pnl.empty else 0
    total_charged = float(pnl["credit_charged"].sum()) if not pnl.empty else 0

    median_pnl = float(pnl["pnl"].median()) if not pnl.empty else 0
    avg_session_pnl = float(sessions["pnl"].mean()) if not sessions.empty else 0
    avg_session_minutes = (
        float(sessions["duration_s"].mean() / 60) if not sessions.empty else 0
    )

    sink_ratio = (total_item_spend / total_block_reward) if total_block_reward else None

    return {
        "snapshot_date": ds.snapshot_date,
        "n_users": int(n_users),
        "n_paying_users": n_paying,
        "n_winning_users": n_winning,
        "n_losing_users": n_losing,
        "total_credit_charged": total_charged,
        "total_block_reward": total_block_reward,
        "total_item_spend": total_item_spend,
        "global_pnl": total_block_reward - total_item_spend,
        "median_user_pnl": median_pnl,
        "avg_session_pnl": avg_session_pnl,
        "avg_session_minutes": avg_session_minutes,
        "sink_ratio": sink_ratio,
        "transaction_count": int(len(tx)),
    }
