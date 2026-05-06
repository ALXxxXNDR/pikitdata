"""
Export recommended balance changes in formats the game can ingest directly.

Two output shapes:
    * `*_csv()` — game-native CSV (same column order as the input snapshot,
      no header), so an ops engineer can drop it back into the data pipeline.
    * `balance_config_json()` — a single JSON document with the *diff* between
      current and recommended values, suitable for a config-as-code workflow.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .balance import recommend_block_changes, recommend_item_changes
from .data_loader import BLOCK_COLS, ITEM_COLS, PikitDataset


def _isoformat(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat() if pd.notna(value) else ""
    return value


def items_csv_with_recommendations(
    ds: PikitDataset,
    target_roi: float = 0.20,
    fields: tuple[str, ...] = ("price",),
    exclude_system_users: bool = True,
) -> str:
    """Game-native item.csv with `fields` overwritten by recommended values.

    `fields` controls which columns get replaced. Default is just `price`.
    Pass `("price", "attack", "duration_ms")` to overwrite all three.
    """
    rec = recommend_item_changes(
        ds, target_roi=target_roi, exclude_system_users=exclude_system_users
    )
    rec = rec.set_index("item_id")

    items = ds.items.copy()
    if "price" in fields:
        items["price"] = items["item_id"].map(rec["recommended_price"]).round().astype("Int64")
    # Attack and duration recommendations are out of scope for the recommender,
    # but exposing the column lets us swap in custom values from a simulator run.
    return _df_to_native_csv(items, BLOCK_COLS_OR_ITEMS=ITEM_COLS)


def blocks_csv_with_recommendations(
    ds: PikitDataset,
    drop_tolerance: float = 0.015,
    fields: tuple[str, ...] = ("reward",),
    exclude_system_users: bool = True,
) -> str:
    rec = recommend_block_changes(
        ds, drop_tolerance=drop_tolerance, exclude_system_users=exclude_system_users
    )
    rec = rec.set_index("block_id")

    blocks = ds.blocks.copy()
    if "reward" in fields:
        blocks["reward"] = (
            blocks["block_id"].map(rec["recommended_reward"]).round().astype("Int64")
        )
    return _df_to_native_csv(blocks, BLOCK_COLS_OR_ITEMS=BLOCK_COLS)


def _df_to_native_csv(df: pd.DataFrame, BLOCK_COLS_OR_ITEMS: list[str]) -> str:
    """Reproduce the headerless CSV shape the game pipeline expects."""
    # Re-pad to the original column count (some derived columns may have been added).
    keep = [c for c in BLOCK_COLS_OR_ITEMS if c in df.columns]
    cleaned = df[keep].copy()
    for c in cleaned.columns:
        cleaned[c] = cleaned[c].apply(_isoformat)
    buf = io.StringIO()
    cleaned.to_csv(buf, index=False, header=False)
    return buf.getvalue()


def balance_config_json(
    ds: PikitDataset,
    target_roi: float = 0.20,
    drop_tolerance: float = 0.015,
    exclude_system_users: bool = True,
    notes: str | None = None,
) -> str:
    """A single JSON doc with current → recommended diffs for items and blocks."""
    items = recommend_item_changes(
        ds, target_roi=target_roi, exclude_system_users=exclude_system_users
    )
    blocks = recommend_block_changes(
        ds, drop_tolerance=drop_tolerance, exclude_system_users=exclude_system_users
    )

    item_payload = []
    for _, r in items.iterrows():
        if pd.isna(r.get("recommended_price")):
            continue
        if abs(float(r["recommended_price"]) - float(r["price"])) < 1:
            continue
        item_payload.append(
            {
                "item_id": int(r["item_id"]),
                "name": r["name"],
                "mode": r["mode"],
                "category": r["category"],
                "current": {"price": _to_native(r["price"])},
                "recommended": {"price": int(round(r["recommended_price"]))},
                "metrics": {
                    "theoretical_roi": _to_native(r.get("theoretical_roi")),
                    "realized_roi": _to_native(r.get("realized_roi")),
                    "purchases": _to_native(r.get("purchases")),
                    "unique_buyers": _to_native(r.get("unique_buyers")),
                },
                "reason": r.get("recommendation"),
            }
        )

    block_payload = []
    for _, r in blocks.iterrows():
        if pd.isna(r.get("recommended_reward")):
            continue
        if abs(float(r["recommended_reward"]) - float(r["reward"])) < 1:
            continue
        block_payload.append(
            {
                "block_id": int(r["block_id"]),
                "name": r["name"],
                "mode": r["mode"],
                "current": {
                    "reward": _to_native(r["reward"]),
                    "drop_rate": _to_native(r["drop_rate"]),
                    "hp": _to_native(r["hp"]),
                },
                "recommended": {
                    "reward": int(round(r["recommended_reward"])),
                },
                "metrics": {
                    "actual_drop_rate": _to_native(r.get("actual_drop_rate")),
                    "drop_rate_delta": _to_native(r.get("drop_rate_delta")),
                    "actual_drops": _to_native(r.get("actual_drops")),
                },
                "reason": r.get("recommendation"),
            }
        )

    payload = {
        "snapshot_date": ds.snapshot_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_roi": target_roi,
        "drop_tolerance": drop_tolerance,
        "notes": notes,
        "items": item_payload,
        "blocks": block_payload,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def simulator_overrides_csv(simulated: pd.DataFrame, kind: str) -> str:
    """Convert a simulator output DataFrame to game-native CSV.

    `kind` must be 'items' or 'blocks'. Use this when the user has tweaked
    values in the simulator and wants those exact values, not the recommender's.
    """
    if kind == "items":
        cols = ITEM_COLS
    elif kind == "blocks":
        cols = BLOCK_COLS
    else:
        raise ValueError("kind must be 'items' or 'blocks'")
    return _df_to_native_csv(simulated, BLOCK_COLS_OR_ITEMS=cols)


def _to_native(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or not np.isfinite(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v
