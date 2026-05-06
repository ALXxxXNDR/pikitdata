"""
Balance recommendations & a what-if simulator.

Two complementary outputs:
    * `recommend_item_changes` / `recommend_block_changes` — diff between the
      *current* config and a target equilibrium, with a per-row reasoning note.
    * `simulate_balance` — apply user-supplied tweaks to item / block tables
      and recompute theoretical PNL & ROI without touching real game data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .data_loader import PikitDataset
from .metrics import compute_block_economy, compute_item_economy


# ---------------------------------------------------------------------------
# Target heuristics — the "what would be fun" anchors.
# ---------------------------------------------------------------------------

TARGET_THEORETICAL_ROI = 0.20            # +20% expected return per pickaxe use
TARGET_DROP_RATE_TOLERANCE = 0.015       # actual vs configured drop rate band
TARGET_REWARD_PER_HP = None              # populated dynamically per mode


# ---------------------------------------------------------------------------
# Item recommendations
# ---------------------------------------------------------------------------

def recommend_item_changes(
    ds: PikitDataset,
    target_roi: float = TARGET_THEORETICAL_ROI,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """For each item, suggest a new price / attack / duration to hit `target_roi`.

    Strategy: keep the item's *theoretical reward per use* fixed and solve
    backwards for the price that yields the target ROI:

        target_roi = (reward - price') / price'   →   price' = reward / (1 + target_roi)

    If `theoretical_reward_per_use` is essentially zero (e.g. mode has no drops),
    fall back to keeping the existing price and flagging the row.
    """
    economy = compute_item_economy(ds, exclude_system_users=exclude_system_users)

    cols = [
        "item_id",
        "name",
        "category",
        "mode",
        "price",
        "attack",
        "duration_ms",
        "duration_s",
        "purchases",
        "unique_buyers",
        "mode_expected_reward_per_drop",
        "mode_expected_hp_per_drop",
        "theoretical_reward_per_use",
        "theoretical_roi",
        "attack_per_credit",
        "realized_spend",
        "realized_reward_attributed",
        "realized_roi",
    ]
    rec = economy[[c for c in cols if c in economy.columns]].copy()

    rec["target_roi"] = target_roi

    # Recommended price uses *realized* reward per use when we have data,
    # falling back to theoretical otherwise.
    realized_reward_per_buy = np.where(
        (rec.get("realized_spend", 0) > 0) & (rec.get("purchases", 0) > 0),
        rec["realized_reward_attributed"] / rec["purchases"],
        np.nan,
    )
    theoretical_reward = rec["theoretical_reward_per_use"]
    rec["effective_reward_per_buy"] = np.where(
        np.isfinite(realized_reward_per_buy), realized_reward_per_buy, theoretical_reward
    )
    rec["recommended_price"] = np.where(
        rec["effective_reward_per_buy"] > 0,
        rec["effective_reward_per_buy"] / (1 + target_roi),
        rec["price"],
    )
    rec["price_delta"] = rec["recommended_price"] - rec["price"]
    rec["price_delta_pct"] = np.where(
        rec["price"] > 0, rec["price_delta"] / rec["price"], np.nan
    )

    rec["recommendation"] = rec.apply(_describe_item_change, axis=1)
    return rec.sort_values(["mode", "category", "item_id"], ignore_index=True)


def _describe_item_change(row: pd.Series) -> str:
    realized = row.get("realized_roi", np.nan)
    theoretical = row.get("theoretical_roi", np.nan)

    # Pick the ROI that reflects actual play if there's real-world data.
    if pd.notna(realized) and row.get("purchases", 0) >= 5:
        roi = realized
        roi_label = f"realized ROI {roi:+.0%}"
    elif pd.notna(theoretical):
        roi = theoretical
        roi_label = f"theoretical ROI {roi:+.0%}"
    else:
        return "Insufficient data — leave as-is."

    target = row["target_roi"]
    if abs(roi - target) < 0.05:
        return f"On target ({roi_label})."

    new_price = row.get("recommended_price")
    if roi < target:
        if pd.notna(new_price) and new_price < row["price"]:
            return (
                f"Underperforming ({roi_label}). Lower price to "
                f"{new_price:.0f} or buff attack/duration."
            )
        return f"Underperforming ({roi_label}). Buff attack or duration."

    if pd.notna(new_price) and new_price > row["price"]:
        return (
            f"Overpowered ({roi_label}). Raise price to "
            f"{new_price:.0f} or shorten duration."
        )
    return f"Overpowered ({roi_label}). Reduce attack or duration."


# ---------------------------------------------------------------------------
# Block recommendations
# ---------------------------------------------------------------------------

def recommend_block_changes(
    ds: PikitDataset,
    drop_tolerance: float = TARGET_DROP_RATE_TOLERANCE,
    exclude_system_users: bool = True,
) -> pd.DataFrame:
    """Compares configured drop_rate / reward_per_hp against observed."""
    economy = compute_block_economy(ds, exclude_system_users=exclude_system_users)

    rec = economy.copy()
    rec["drop_rate_in_band"] = rec["drop_rate_delta"].abs() <= drop_tolerance

    # Reward-per-HP fairness: a user mining one HP should gain roughly the same
    # weighted credit. Compute a target reward by stretching reward to the mean
    # reward_per_hp inside the same mode.
    mean_rp = (
        rec.groupby("mode")["reward_per_hp"].transform("mean").replace(0, np.nan)
    )
    rec["mode_mean_reward_per_hp"] = mean_rp
    rec["recommended_reward"] = (rec["hp"] * mean_rp).round()
    rec["reward_delta"] = rec["recommended_reward"] - rec["reward"]
    rec["reward_delta_pct"] = np.where(
        rec["reward"] > 0, rec["reward_delta"] / rec["reward"], np.nan
    )

    rec["recommendation"] = rec.apply(
        lambda r: _describe_block_change(r, drop_tolerance), axis=1
    )
    return rec.sort_values(["mode", "block_id"], ignore_index=True)


def _describe_block_change(row: pd.Series, tol: float) -> str:
    msgs = []
    delta = row.get("drop_rate_delta")
    if pd.notna(delta):
        if delta > tol:
            msgs.append(
                f"Drops {delta * 100:+.1f}pp more than configured — possibly too generous."
            )
        elif delta < -tol:
            msgs.append(
                f"Drops {delta * 100:+.1f}pp less than configured — players rarely see this."
            )

    rd = row.get("reward_delta_pct")
    if pd.notna(rd) and abs(rd) > 0.15:
        direction = "raise" if rd > 0 else "lower"
        msgs.append(
            f"{direction.title()} reward to ~{row['recommended_reward']:.0f} "
            f"({rd * 100:+.0f}%) to align with mode-average reward/HP."
        )

    if not msgs:
        return "Within tolerance."
    return " ".join(msgs)


# ---------------------------------------------------------------------------
# What-if simulator
# ---------------------------------------------------------------------------

@dataclass
class BalanceTweak:
    """A proposed change to a single item or block."""
    item_overrides: dict[int, dict[str, float]] | None = None  # {item_id: {price/attack/duration_ms: value}}
    block_overrides: dict[int, dict[str, float]] | None = None  # {block_id: {hp/reward/drop_rate: value}}


def simulate_balance(ds: PikitDataset, tweak: BalanceTweak) -> pd.DataFrame:
    """Apply tweaks and return the theoretical ROI for every item, before & after."""
    items = ds.items.copy()
    blocks = ds.blocks.copy()

    if tweak.item_overrides:
        for item_id, fields in tweak.item_overrides.items():
            mask = items["item_id"] == item_id
            for k, v in fields.items():
                if k in items.columns and v is not None:
                    items.loc[mask, k] = v

    if tweak.block_overrides:
        for block_id, fields in tweak.block_overrides.items():
            mask = blocks["block_id"] == block_id
            for k, v in fields.items():
                if k in blocks.columns and v is not None:
                    blocks.loc[mask, k] = v

    expected_reward_per_drop = (
        blocks.assign(weighted=blocks["drop_rate"] * blocks["reward"])
        .groupby("mode")["weighted"]
        .sum()
    )
    expected_hp_per_drop = (
        blocks.assign(weighted_hp=blocks["drop_rate"] * blocks["hp"])
        .groupby("mode")["weighted_hp"]
        .sum()
    )

    sim = items.copy()
    sim["duration_s"] = sim["duration_ms"] / 1000
    sim["mode_expected_reward_per_drop"] = sim["mode"].map(expected_reward_per_drop)
    sim["mode_expected_hp_per_drop"] = sim["mode"].map(expected_hp_per_drop)
    sim["theoretical_breaks_per_use"] = np.where(
        sim["mode_expected_hp_per_drop"] > 0,
        sim["duration_s"] * sim["attack"] / sim["mode_expected_hp_per_drop"],
        np.nan,
    )
    sim["theoretical_reward_per_use"] = (
        sim["theoretical_breaks_per_use"] * sim["mode_expected_reward_per_drop"]
    )
    sim["theoretical_roi"] = np.where(
        sim["price"] > 0,
        (sim["theoretical_reward_per_use"] - sim["price"]) / sim["price"],
        np.nan,
    )

    # Compare against current (untweaked) baseline.
    baseline = compute_item_economy(ds)
    merged = sim.merge(
        baseline[["item_id", "theoretical_roi", "theoretical_reward_per_use", "price"]]
        .rename(
            columns={
                "theoretical_roi": "baseline_roi",
                "theoretical_reward_per_use": "baseline_reward_per_use",
                "price": "baseline_price",
            }
        ),
        on="item_id",
        how="left",
    )

    merged["roi_delta"] = merged["theoretical_roi"] - merged["baseline_roi"]
    return merged[
        [
            "item_id",
            "name",
            "category",
            "mode",
            "baseline_price",
            "price",
            "attack",
            "duration_ms",
            "baseline_reward_per_use",
            "theoretical_reward_per_use",
            "baseline_roi",
            "theoretical_roi",
            "roi_delta",
        ]
    ].sort_values(["mode", "item_id"], ignore_index=True)
