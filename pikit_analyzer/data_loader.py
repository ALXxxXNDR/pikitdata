"""
Loads PIKIT beta CSV snapshots into typed pandas DataFrames.

The raw CSVs have no header rows. Column schemas were inferred from observed
data and the in-game economy (e.g. block drop rates summing to 1, pickaxe
attack/duration scaling). All schemas are documented at the top of each
loader function below.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

def _resolve_default_data_root() -> Path:
    """Pick the default data folder.

    Resolution order:
        1. `PIKIT_DATA_ROOT` env var (set in production / Streamlit Cloud)
        2. `./data` next to the repo root (in-repo private folder)
        3. Local laptop fallback
    """
    env = os.environ.get("PIKIT_DATA_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    repo_data = Path(__file__).resolve().parent.parent / "data"
    if repo_data.exists():
        return repo_data
    return Path("/Users/moomi/Downloads/PIKIT BETA DATA")


DEFAULT_DATA_ROOT = _resolve_default_data_root()
SNAPSHOT_PATTERN = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


# ---------------------------------------------------------------------------
# Schemas — column definitions for each headerless CSV in a daily snapshot.
# ---------------------------------------------------------------------------

BLOCK_COLS = [
    "block_id",
    "name",
    "display_name",
    "mode",
    "drop_rate",
    "hp",
    "reward",
    "created_at",
    "updated_at",
    "extra",
]

ITEM_COLS = [
    "item_id",
    "name",
    "description",
    "mode",
    "price",
    "size_mult",
    "weight_mult",
    "attack",
    "duration_ms",
    "created_at",
    "updated_at",
    "extra",
]

GAME_COLS = [
    "game_id",
    "mode_name",
    "description",
    "status",
    "param_a",
    "param_b",
    "param_c",
    "created_at",
    "updated_at",
    "extra",
]

USER_COLS = [
    "user_id",
    "username",
    "balance",
    "demo_balance",
    "lifetime_credit",
    "wallet_address",
    "created_at",
    "updated_at",
    "extra",
]

# Tx log: tx_id, user_id, game_id, type, direction, amount, balance_before,
# balance_after, source_type, source_id, message, created_at
TX_COLS = [
    "tx_id",
    "user_id",
    "game_id",
    "tx_type",
    "direction",
    "amount",
    "balance_before",
    "balance_after",
    "source_type",
    "source_id",
    "message",
    "created_at",
]

USER_STATS_COLS = [
    "user_id",
    "stat_a",
    "stat_b",
    "stat_c",
    "stat_d",
    "total_block_reward",
    "total_item_spend",
    "stat_e",
    "created_at",
    "updated_at",
]

USER_BLOCK_COLS = [
    "user_id",
    "block_id",
    "count",
    "first_seen",
    "last_seen",
]

USER_ITEM_COLS = [
    "user_id",
    "item_id",
    "count",
    "first_seen",
    "last_seen",
]

GAME_USER_STATS_COLS = ["game_id"] + USER_STATS_COLS
GAME_USER_BLOCK_COLS = ["game_id"] + USER_BLOCK_COLS
GAME_USER_ITEM_COLS = ["game_id"] + USER_ITEM_COLS

USER_ATTENDANCE_COLS = [
    "user_id",
    "streak",
    "total_days",
    "first_attendance",
    "last_attendance",
    "updated_at",
]


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

@dataclass
class PikitDataset:
    """A single daily snapshot of PIKIT beta data."""

    snapshot_date: str
    blocks: pd.DataFrame
    items: pd.DataFrame
    games: pd.DataFrame
    users: pd.DataFrame
    user_stats: pd.DataFrame
    user_block_stats: pd.DataFrame
    user_item_stats: pd.DataFrame
    user_attendance: pd.DataFrame
    game_user_stats: pd.DataFrame
    game_user_block_stats: pd.DataFrame
    game_user_item_stats: pd.DataFrame
    transactions: pd.DataFrame

    # Quest fixture accounts (e.g. user_id 1-10) — these are seeded for in-game
    # quests and never represent organic play. They are *always* removed from
    # any analysis surface and there is no UI option to include them.
    quest_user_ids: list[int] = field(default_factory=list)
    # The operational system account (e.g. user_id 11). Tracks how much the
    # in-house "system pickaxe" has mined, so it's useful to keep around when
    # auditing internal activity. The dashboard exposes this as a toggle.
    system_user_ids: list[int] = field(default_factory=list)

    @property
    def test_user_ids(self) -> list[int]:
        """Backwards-compatible accessor: union of quest + system."""
        return list(self.quest_user_ids) + list(self.system_user_ids)

    def filter_real_users(self, df: pd.DataFrame, user_col: str = "user_id") -> pd.DataFrame:
        """Always drop quest fixture accounts.

        Use this for *every* analytic surface — quest wallets are static seed
        data and including them poisons every aggregate.
        """
        if not self.quest_user_ids:
            return df
        return df[~df[user_col].isin(self.quest_user_ids)].copy()

    def filter_system_users(self, df: pd.DataFrame, user_col: str = "user_id") -> pd.DataFrame:
        """Optionally drop system / admin accounts (user_id 11 etc.)."""
        if not self.system_user_ids:
            return df
        return df[~df[user_col].isin(self.system_user_ids)].copy()

    def filter_by_date_range(self, start, end) -> "PikitDataset":
        """Return a copy with transactions sliced to [start, end] (inclusive on both ends).

        Configs (blocks, items, games, users) remain as-is — we use the latest
        snapshot's config but only count activity within the date range.

        `start` / `end` may be `datetime.date`, `datetime.datetime`, or strings
        like "2026-05-04". `None` means "no bound on that side".
        """
        tx = self.transactions
        if "created_at" in tx.columns and len(tx) > 0:
            mask = pd.Series(True, index=tx.index)
            if start is not None:
                start_ts = pd.Timestamp(start, tz="UTC")
                mask &= tx["created_at"] >= start_ts
            if end is not None:
                end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
                mask &= tx["created_at"] <= end_ts
            tx = tx[mask].copy()

        return PikitDataset(
            snapshot_date=self.snapshot_date,
            blocks=self.blocks,
            items=self.items,
            games=self.games,
            users=self.users,
            user_stats=self.user_stats,
            user_block_stats=self.user_block_stats,
            user_item_stats=self.user_item_stats,
            user_attendance=self.user_attendance,
            game_user_stats=self.game_user_stats,
            game_user_block_stats=self.game_user_block_stats,
            game_user_item_stats=self.game_user_item_stats,
            transactions=tx,
            quest_user_ids=list(self.quest_user_ids),
            system_user_ids=list(self.system_user_ids),
        )

    @property
    def transaction_date_range(self) -> tuple:
        """Min and max transaction date (UTC date objects), or (None, None) if empty."""
        tx = self.transactions
        if "created_at" not in tx.columns or len(tx) == 0:
            return (None, None)
        ts = tx["created_at"].dropna()
        if ts.empty:
            return (None, None)
        return (ts.min().date(), ts.max().date())


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    """Read a headerless CSV with a fixed column list, padding/trimming as needed."""
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(
        path,
        header=None,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    # Pad / truncate to expected number of columns.
    n_expected = len(columns)
    if df.shape[1] < n_expected:
        for i in range(df.shape[1], n_expected):
            df[i] = pd.NA
    elif df.shape[1] > n_expected:
        df = df.iloc[:, :n_expected]
    df.columns = columns
    return df


def _to_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _to_datetime(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df


def list_snapshot_dates(data_root: Path = DEFAULT_DATA_ROOT) -> list[str]:
    """Returns sorted snapshot folder names like ['2026.05.05', '2026.05.06']."""
    if not data_root.exists():
        return []
    dates = [
        p.name
        for p in data_root.iterdir()
        if p.is_dir() and SNAPSHOT_PATTERN.match(p.name)
    ]
    return sorted(dates)


@lru_cache(maxsize=8)
def load_snapshot(snapshot_date: str, data_root: str | None = None) -> PikitDataset:
    """Load a single daily snapshot identified by its folder name."""
    root = Path(data_root) if data_root else DEFAULT_DATA_ROOT
    snap_dir = root / snapshot_date
    if not snap_dir.exists():
        raise FileNotFoundError(f"Snapshot not found: {snap_dir}")

    blocks = _read_csv(snap_dir / "block.csv", BLOCK_COLS)
    blocks = _to_numeric(blocks, ["block_id", "drop_rate", "hp", "reward"])
    blocks = _to_datetime(blocks, ["created_at", "updated_at"])

    items = _read_csv(snap_dir / "item.csv", ITEM_COLS)
    items = _to_numeric(
        items,
        ["item_id", "price", "size_mult", "weight_mult", "attack", "duration_ms"],
    )
    items = _to_datetime(items, ["created_at", "updated_at"])
    items["category"] = items["name"].apply(_classify_item)

    games = _read_csv(snap_dir / "game.csv", GAME_COLS)
    games = _to_numeric(games, ["game_id", "param_a", "param_b", "param_c"])
    games = _to_datetime(games, ["created_at", "updated_at"])

    users = _read_csv(snap_dir / "user.csv", USER_COLS)
    users = _to_numeric(users, ["user_id", "balance", "demo_balance", "lifetime_credit"])
    users = _to_datetime(users, ["created_at", "updated_at"])

    user_stats = _read_csv(snap_dir / "user_stats.csv", USER_STATS_COLS)
    user_stats = _to_numeric(
        user_stats,
        [
            "user_id",
            "stat_a",
            "stat_b",
            "stat_c",
            "stat_d",
            "total_block_reward",
            "total_item_spend",
            "stat_e",
        ],
    )
    user_stats = _to_datetime(user_stats, ["created_at", "updated_at"])

    user_block_stats = _read_csv(snap_dir / "user_block_stats.csv", USER_BLOCK_COLS)
    user_block_stats = _to_numeric(user_block_stats, ["user_id", "block_id", "count"])
    user_block_stats = _to_datetime(user_block_stats, ["first_seen", "last_seen"])

    user_item_stats = _read_csv(snap_dir / "user_item_stats.csv", USER_ITEM_COLS)
    user_item_stats = _to_numeric(user_item_stats, ["user_id", "item_id", "count"])
    user_item_stats = _to_datetime(user_item_stats, ["first_seen", "last_seen"])

    user_attendance = _read_csv(snap_dir / "user_attendance.csv", USER_ATTENDANCE_COLS)
    user_attendance = _to_numeric(user_attendance, ["user_id", "streak", "total_days"])
    user_attendance = _to_datetime(
        user_attendance, ["first_attendance", "last_attendance", "updated_at"]
    )

    game_user_stats = _read_csv(snap_dir / "game_user_stats.csv", GAME_USER_STATS_COLS)
    game_user_stats = _to_numeric(
        game_user_stats,
        [
            "game_id",
            "user_id",
            "stat_a",
            "stat_b",
            "stat_c",
            "stat_d",
            "total_block_reward",
            "total_item_spend",
            "stat_e",
        ],
    )
    game_user_stats = _to_datetime(game_user_stats, ["created_at", "updated_at"])

    game_user_block_stats = _read_csv(
        snap_dir / "game_user_block_stats.csv", GAME_USER_BLOCK_COLS
    )
    game_user_block_stats = _to_numeric(
        game_user_block_stats, ["game_id", "user_id", "block_id", "count"]
    )
    game_user_block_stats = _to_datetime(
        game_user_block_stats, ["first_seen", "last_seen"]
    )

    game_user_item_stats = _read_csv(
        snap_dir / "game_user_item_stats.csv", GAME_USER_ITEM_COLS
    )
    game_user_item_stats = _to_numeric(
        game_user_item_stats, ["game_id", "user_id", "item_id", "count"]
    )
    game_user_item_stats = _to_datetime(
        game_user_item_stats, ["first_seen", "last_seen"]
    )

    transactions = _read_csv(snap_dir / "user_transaction_log.csv", TX_COLS)
    transactions = _to_numeric(
        transactions,
        ["tx_id", "user_id", "game_id", "amount", "balance_before", "balance_after", "source_id"],
    )
    transactions = _to_datetime(transactions, ["created_at"])
    if "created_at" in transactions.columns:
        transactions["snapshot_day"] = transactions["created_at"].dt.date

    quest_user_ids = _detect_quest_users(users)
    system_user_ids = _detect_system_users(users)

    return PikitDataset(
        snapshot_date=snapshot_date,
        blocks=blocks,
        items=items,
        games=games,
        users=users,
        user_stats=user_stats,
        user_block_stats=user_block_stats,
        user_item_stats=user_item_stats,
        user_attendance=user_attendance,
        game_user_stats=game_user_stats,
        game_user_block_stats=game_user_block_stats,
        game_user_item_stats=game_user_item_stats,
        transactions=transactions,
        quest_user_ids=quest_user_ids,
        system_user_ids=system_user_ids,
    )


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_QUEST_FIXTURE_NAMES = {
    "MegaDrill",
    "GoldDigger",
    "PitterPatter",
    "MineCraft2",
    "DeepBlue",
    "StoneCrusher",
    "GemHunter",
    "DrillMaster",
    "CaveExplorer",
    "IronFist",
}

# Wallet prefix shared by every seeded fixture account: 38 zero hex chars
# after `0x`. The last two chars distinguish quest wallets (01..0a) from the
# system account (00).
_FIXTURE_WALLET_PREFIX = "0x" + "0" * 38
_SYSTEM_WALLET = "0x" + "0" * 40


def _detect_quest_users(users: pd.DataFrame) -> list[int]:
    """Quest fixture accounts (id 1-10): pre-seeded wallets used for in-game
    quests, *never* organic play. Always filtered out, no opt-out.
    """
    if users.empty:
        return []
    name_mask = users["username"].isin(_QUEST_FIXTURE_NAMES)
    wallet_str = users["wallet_address"].fillna("").astype(str)
    wallet_mask = wallet_str.str.startswith(_FIXTURE_WALLET_PREFIX) & (
        wallet_str != _SYSTEM_WALLET
    )
    flagged = users[name_mask | wallet_mask]
    return [int(uid) for uid in flagged["user_id"].dropna().tolist()]


def _detect_system_users(users: pd.DataFrame) -> list[int]:
    """The operational / admin account (e.g. user_id 11 with the all-zero wallet).

    Useful to keep when auditing how much the *system pickaxe* has mined, so
    the UI exposes this as a toggle rather than a permanent exclusion.
    """
    if users.empty:
        return []
    wallet_str = users["wallet_address"].fillna("").astype(str)
    return [int(uid) for uid in users[wallet_str == _SYSTEM_WALLET]["user_id"].dropna().tolist()]


def _classify_item(name: str) -> str:
    if not isinstance(name, str):
        return "OTHER"
    if name.upper().startswith("TNT"):
        return "TNT"
    if "PICKAXE" in name.upper():
        return "PICKAXE"
    return "OTHER"
