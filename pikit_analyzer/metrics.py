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
        tx.groupby(["user_id", "tx_type"])["abs_amount"].sum().unstack(fill_value=0)
    )
    for col in ("DEMO_CREDIT_CHARGE", "BLOCK_REWARD", "ITEM_PURCHASE"):
        if col not in grouped.columns:
            grouped[col] = 0

    counts = (
        tx.groupby(["user_id", "tx_type"])["tx_id"].count().unstack(fill_value=0)
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
        tx.groupby(["user_id", "game_id", "tx_type"])["abs_amount"]
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
) -> pd.DataFrame:
    """Resample transactions into a per-(period, user) time series.

    Parameters
    ----------
    user_ids : list[int] | None
        Only include these users. None → all users in the (already-filtered) tx log.
    freq : str
        Pandas offset alias. "D" = day, "H" = hour, "15min" = 15 min, etc.

    Returns
    -------
    DataFrame with columns:
        period          — period start (UTC tz-aware Timestamp)
        user_id         — int
        username        — str
        block_reward    — credits earned this period
        item_spend      — credits spent on items this period (positive)
        credit_charged  — demo credits issued this period
        pnl             — block_reward - item_spend
        tx_count        — number of transactions
        cum_pnl         — cumulative PNL within this user's series
        cum_block_reward, cum_item_spend — cumulative versions
    """
    tx = ds.filter_real_users(ds.transactions)  # quest 픽스처는 항상 제외
    if exclude_system_users:
        tx = ds.filter_system_users(tx)
    if user_ids is not None:
        tx = tx[tx["user_id"].isin(user_ids)]

    if tx.empty:
        return pd.DataFrame(
            columns=[
                "period",
                "user_id",
                "username",
                "block_reward",
                "item_spend",
                "credit_charged",
                "pnl",
                "tx_count",
                "cum_pnl",
                "cum_block_reward",
                "cum_item_spend",
            ]
        )

    tx = tx.copy()
    tx["abs_amount"] = tx["amount"].abs()
    tx["period"] = tx["created_at"].dt.floor(freq)

    pivot = (
        tx.groupby(["period", "user_id", "tx_type"])["abs_amount"]
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

    # Fill the index so every (user, period) gap shows up as zero — keeps line
    # charts continuous instead of skipping idle hours/days.
    if not out.empty:
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
