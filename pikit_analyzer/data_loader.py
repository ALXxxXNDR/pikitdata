"""
Loads PIKIT beta CSV snapshots into typed pandas DataFrames.

베타 후반에 데이터 스키마가 헤더 포함 + 깔끔한 컬럼명으로 정비됐습니다.
이 로더는 두 포맷을 모두 지원합니다 — 새 헤더가 있으면 그걸 따라 읽고 내부
이름으로 rename, 없으면 옛 위치 기반 컬럼 목록으로 fallback.

내부 컬럼 이름은 *그대로 유지* 합니다 (block_id, mode, hp, drop_rate,
tx_type, direction, source_id 등) — 다른 모든 분석 코드가 이 이름을 쓰기 때문에.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import re
# `dataclasses` is intentionally avoided — Python 3.14 has a regression where
# `@dataclass` on a class with `from __future__ import annotations` triggers
# `AttributeError: 'NoneType' object has no attribute '__dict__'` inside
# `dataclasses._is_type` during initial class processing. We use a plain class
# with explicit `__init__` instead. (cpython issue around 3.14.4 / b/130962.)
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd


def _resolve_cache_dir() -> Path | None:
    """디스크 캐시 폴더 — 컨테이너의 /app/cache 또는 PIKIT_CACHE_DIR 환경변수.

    None 을 반환하면 캐시 비활성 (개발 환경 등).
    """
    env = os.environ.get("PIKIT_CACHE_DIR", "").strip()
    if env:
        p = Path(env).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            return None
    container_cache = Path("/app/cache")
    if container_cache.exists() and os.access(container_cache, os.W_OK):
        return container_cache
    return None


CACHE_DIR = _resolve_cache_dir()
# pickle 파일 호환성 보호 — 코드가 바뀌어 deserialize 가 실패하면 cache 무효화.
# 새 필드 추가하거나 구조 바꿀 때 이 값을 올리면 옛 캐시 자동 무시됨.
CACHE_VERSION = 2

def _resolve_default_data_root() -> Path:
    """Pick the default data folder.

    Resolution order:
        1. `PIKIT_DATA_ROOT` env var (set in production / Streamlit Cloud)
        2. `./data` next to the repo root (in-repo private folder)
        3. Local laptop fallback
    """
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.get("PIKIT_DATA_ROOT", "").strip()
    if env:
        p = Path(env).expanduser()
        # `./data`, `data/`, `data` 같은 상대 경로는 CWD 가 아니라 repo 루트
        # 기준으로 해석 — Streamlit Cloud에선 CWD 가 항상 repo 루트는 아니라서.
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        return p
    repo_data = repo_root / "data"
    if repo_data.exists():
        return repo_data
    # 마지막 대안: 사용자 홈 디렉터리 아래 'Downloads/PIKIT BETA DATA'.
    return Path.home() / "Downloads" / "PIKIT BETA DATA"


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
# 새 외부 헤더 → 내부 컬럼명 매핑.
# 외부에서 추가된 컬럼은 내부 이름으로 옮기고, 사라진 컬럼은 기본값으로 채움.
# ---------------------------------------------------------------------------

BLOCK_RENAME = {
    "id": "block_id",
    "category": "mode",
    "ratio": "drop_rate",
    "health": "hp",
    "deleted_at": "extra",
    # name, reward, created_at, updated_at, description 은 그대로
}
BLOCK_INTERNAL_DEFAULTS = {"display_name": ""}  # 새 스키마엔 별도 display_name 없음

ITEM_RENAME = {
    "id": "item_id",
    "category": "mode",
    "scale": "size_mult",
    "weight": "weight_mult",
    "duration": "duration_ms",
    "deleted_at": "extra",
}

GAME_RENAME = {
    "id": "game_id",
    "name": "mode_name",
    "max_users": "param_a",
    "map_width": "param_b",
    "map_height": "param_c",
    "deleted_at": "extra",
}

USER_RENAME = {
    "id": "user_id",
    "name": "username",
    "credit": "balance",
    "demo_credit": "demo_balance",
    "deleted_at": "extra",
    # bonus 는 새 컬럼 — 그대로 유지하면서 lifetime_credit 도 호환용으로 둡니다.
}

USER_STATS_RENAME = {
    "total_demo_credit_earned": "total_block_reward",   # NORMAL 모드 보상 누적
    "total_demo_credit_spent": "total_item_spend",      # NORMAL 모드 지출 누적
    # 나머지는 그대로 — total_credit_earned/spent, total_bonus_earned/spent, total_pnl
}

GAME_USER_STATS_RENAME = USER_STATS_RENAME

USER_BLOCK_RENAME = {
    "break_count": "count",
    # first_seen / last_seen 은 새 스키마에서 created_at/updated_at 으로 바뀜
    "created_at": "first_seen",
    "updated_at": "last_seen",
}

USER_ITEM_RENAME = {
    "purchase_count": "count",
    "created_at": "first_seen",
    "updated_at": "last_seen",
}

USER_ATTENDANCE_RENAME = {
    "attendance_days": "total_days",
    "attendance_streak": "streak",
    "last_attended_at": "last_attendance",
    "created_at": "first_attendance",
}

TX_RENAME = {
    "id": "tx_id",
    "event_type": "tx_type",
    "currency_type": "direction",
    "ref_type": "source_type",
    "ref_id": "source_id",
    "memo": "message",
}


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

class PikitDataset:
    """A single daily snapshot of PIKIT beta data.

    Plain class instead of `@dataclass` due to a Python 3.14 dataclass
    introspection regression (see comment near the imports above).
    """

    def __init__(
        self,
        snapshot_date,
        blocks,
        items,
        games,
        users,
        user_stats,
        user_block_stats,
        user_item_stats,
        user_attendance,
        game_user_stats,
        game_user_block_stats,
        game_user_item_stats,
        transactions,
        quest_user_ids=None,
        system_user_ids=None,
    ):
        self.snapshot_date = snapshot_date
        self.blocks = blocks
        self.items = items
        self.games = games
        self.users = users
        self.user_stats = user_stats
        self.user_block_stats = user_block_stats
        self.user_item_stats = user_item_stats
        self.user_attendance = user_attendance
        self.game_user_stats = game_user_stats
        self.game_user_block_stats = game_user_block_stats
        self.game_user_item_stats = game_user_item_stats
        self.transactions = transactions
        # Quest fixture accounts (e.g. user_id 1-10) — seeded for in-game
        # quests, never organic play. Always filtered, no UI toggle.
        self.quest_user_ids = list(quest_user_ids) if quest_user_ids else []
        # The operational system account (e.g. user_id 11). Tracks how much the
        # in-house "system pickaxe" has mined. UI exposes this as a toggle.
        self.system_user_ids = list(system_user_ids) if system_user_ids else []

    @property
    def test_user_ids(self):
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
        """Return a copy with transactions sliced to [start, end].

        `start` / `end` may be `datetime.date`, `datetime.datetime`, pandas Timestamp,
        or ISO string. None = no bound on that side.

        - `date` (no time component) → 그 하루 끝(23:59:59.999)까지 inclusive 로 처리
        - `datetime` (시·분 포함) → 그 시각 정확히 사용
        """
        from datetime import date as _date_cls, datetime as _datetime_cls

        def _to_ts(v, end_of_day_if_date: bool):
            """Normalize input to UTC pandas Timestamp."""
            if v is None:
                return None
            # datetime 객체이면서 date 만 있는 경우 (datetime.date 클래스인 게 정확)
            is_pure_date = isinstance(v, _date_cls) and not isinstance(v, _datetime_cls)
            ts = pd.Timestamp(v, tz="UTC")
            if is_pure_date and end_of_day_if_date:
                # 종료일이 date 형이면 그 하루 끝까지 포함하도록 (옛 동작 유지).
                ts = ts + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
            return ts

        tx = self.transactions
        if "created_at" in tx.columns and len(tx) > 0:
            mask = pd.Series(True, index=tx.index)
            start_ts = _to_ts(start, end_of_day_if_date=False)
            end_ts = _to_ts(end, end_of_day_if_date=True)
            if start_ts is not None:
                mask &= tx["created_at"] >= start_ts
            if end_ts is not None:
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

    def filter_by_game_mode(self, mode: str | None) -> "PikitDataset":
        """`mode` ∈ {'NORMAL', 'HARDCORE', None/'전체'}. None 이면 변경 없이 반환.

        DEMO_CREDIT_CHARGE 같은 메타 트랜잭션도 같이 분류되므로, 단순히
        `transactions[transactions.game_mode == mode]` 한 결과를 새 dataset 으로
        감싸 반환합니다.
        """
        if mode is None or mode in ("전체", "ALL"):
            return self
        tx = self.transactions
        if "game_mode" in tx.columns and len(tx) > 0:
            tx = tx[tx["game_mode"] == mode].copy()

        # 같은 모드 블록/아이템만 보이게 config 도 함께 슬라이스 — 다만 모드별
        # 설정 자체는 두 모드가 모두 들어있으므로 mode 컬럼 기준으로 필터.
        blocks = self.blocks
        if "mode" in blocks.columns:
            blocks = blocks[blocks["mode"] == mode].copy()
        items = self.items
        if "mode" in items.columns:
            items = items[items["mode"] == mode].copy()

        return PikitDataset(
            snapshot_date=self.snapshot_date,
            blocks=blocks,
            items=items,
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
    def available_game_modes(self) -> list[str]:
        """Modes that actually appear in this dataset's transactions."""
        tx = self.transactions
        if "game_mode" not in tx.columns or tx.empty:
            return []
        modes = tx["game_mode"].dropna().unique().tolist()
        # NORMAL 먼저, HARDCORE 다음, 그 외는 뒤쪽
        order = {"NORMAL": 0, "HARDCORE": 1, "TEST": 2, "UNKNOWN": 3}
        return sorted(modes, key=lambda m: order.get(m, 99))

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

def _read_csv(
    path: Path,
    fallback_columns: list[str],
    rename_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Read a CSV with header auto-detection + new→internal column rename.

    1. 첫 줄을 헤더로 보고 시도. 첫 줄에 숫자만 있는 게 아니라면 (= 진짜 헤더)
       헤더로 인식하고 rename_map 에 따라 내부 이름으로 변환.
    2. 첫 줄이 데이터처럼 보이면 (옛 포맷) fallback_columns 로 위치 기반 매핑.
    """
    if not path.exists():
        return pd.DataFrame(columns=fallback_columns)

    # 1차 시도: 헤더 있다고 가정.
    df = pd.read_csv(
        path,
        header=0,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    cols = list(df.columns)
    looks_like_header = any(not _is_numeric_string(c) for c in cols)

    if not looks_like_header:
        # 옛 포맷 — 헤더 없이 위치 기반.
        df = pd.read_csv(
            path,
            header=None,
            low_memory=False,
            dtype=str,
            keep_default_na=False,
            na_values=[""],
        )
        n_expected = len(fallback_columns)
        if df.shape[1] < n_expected:
            for i in range(df.shape[1], n_expected):
                df[i] = pd.NA
        elif df.shape[1] > n_expected:
            df = df.iloc[:, :n_expected]
        df.columns = fallback_columns
        return df

    # 새 포맷: rename 적용해 내부 이름으로 통일.
    if rename_map:
        df = df.rename(columns=rename_map)
    # fallback_columns 에 있는 이름 중 빠진 게 있으면 빈 컬럼 추가 (downstream 호환).
    for col in fallback_columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def _is_numeric_string(s: str) -> bool:
    """Crude check — used only to distinguish header rows from data rows."""
    if s is None:
        return False
    s = str(s).strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


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


def _snapshot_cache_key(snap_dir: Path) -> str:
    """캐시 키 = 스냅샷 폴더의 모든 CSV mtime + size 의 해시.

    파일이 하나라도 바뀌면 키가 바뀌어 캐시가 자동 무효화됨.
    """
    parts: list[str] = [f"v{CACHE_VERSION}"]
    for f in sorted(snap_dir.glob("*.csv")):
        try:
            stat = f.stat()
            parts.append(f"{f.name}:{int(stat.st_mtime)}:{stat.st_size}")
        except OSError:
            continue
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]
    return f"snapshot_{snap_dir.name}_{digest}"


@lru_cache(maxsize=2)  # 동일 스냅샷 인스턴스 누적 방지 (Cloud 1GB 한도)
def load_snapshot(snapshot_date: str, data_root: str | None = None) -> PikitDataset:
    """Load a single daily snapshot identified by its folder name.

    캐싱 계층 두 단계:
      1. lru_cache (메모리) — 동일 인자 재호출 시 즉시 반환.
      2. /app/cache 의 pickle (디스크) — 컨테이너 재시작 후에도 보존.
         CSV mtime 이 바뀌면 자동 무효화. (~ 5초 → 0.2초)
    """
    root = Path(data_root) if data_root else DEFAULT_DATA_ROOT
    snap_dir = root / snapshot_date
    if not snap_dir.exists():
        raise FileNotFoundError(f"Snapshot not found: {snap_dir}")

    # ---- 디스크 캐시 hit 시 즉시 반환 ----
    if CACHE_DIR is not None:
        try:
            cache_file = CACHE_DIR / f"{_snapshot_cache_key(snap_dir)}.pkl"
            if cache_file.exists():
                with cache_file.open("rb") as fh:
                    cached = pickle.load(fh)
                # 캐시는 PikitDataset 인스턴스만 저장. 클래스가 바뀌었으면 fresh load.
                if isinstance(cached, PikitDataset):
                    return cached
        except (OSError, pickle.UnpicklingError, AttributeError, EOFError):
            # 손상된 캐시 — 무시하고 fresh load 후 덮어쓰기.
            pass

    ds = _load_snapshot_from_csv(snap_dir, snapshot_date)

    # ---- 디스크 캐시 저장 (best-effort) ----
    if CACHE_DIR is not None:
        try:
            # 옛 캐시 정리 — 같은 snapshot_date 의 옛 mtime 파일 제거.
            for old in CACHE_DIR.glob(f"snapshot_{snapshot_date}_*.pkl"):
                try:
                    old.unlink()
                except OSError:
                    pass
            cache_file = CACHE_DIR / f"{_snapshot_cache_key(snap_dir)}.pkl"
            tmp = cache_file.with_suffix(".pkl.tmp")
            with tmp.open("wb") as fh:
                pickle.dump(ds, fh, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(cache_file)  # 원자적 교체
        except OSError:
            pass

    return ds


def _load_snapshot_from_csv(snap_dir: Path, snapshot_date: str) -> PikitDataset:
    """캐시 무관, 모든 CSV 를 새로 읽어 PikitDataset 을 생성. 내부용."""
    blocks = _read_csv(snap_dir / "block.csv", BLOCK_COLS, BLOCK_RENAME)
    blocks = _to_numeric(blocks, ["block_id", "drop_rate", "hp", "reward"])
    blocks = _to_datetime(blocks, ["created_at", "updated_at"])

    items = _read_csv(snap_dir / "item.csv", ITEM_COLS, ITEM_RENAME)
    items = _to_numeric(
        items,
        ["item_id", "price", "size_mult", "weight_mult", "attack", "duration_ms"],
    )
    items = _to_datetime(items, ["created_at", "updated_at"])
    items["category"] = items["name"].apply(_classify_item)

    games = _read_csv(snap_dir / "game.csv", GAME_COLS, GAME_RENAME)
    games = _to_numeric(games, ["game_id", "param_a", "param_b", "param_c"])
    games = _to_datetime(games, ["created_at", "updated_at"])

    users = _read_csv(snap_dir / "user.csv", USER_COLS, USER_RENAME)
    users = _to_numeric(users, ["user_id", "balance", "demo_balance", "lifetime_credit"])
    if "bonus" in users.columns:
        users["bonus"] = pd.to_numeric(users["bonus"], errors="coerce")
    users = _to_datetime(users, ["created_at", "updated_at"])

    user_stats = _read_csv(snap_dir / "user_stats.csv", USER_STATS_COLS, USER_STATS_RENAME)
    user_stats = _to_numeric(
        user_stats,
        [
            "user_id",
            "total_block_reward",
            "total_item_spend",
            "total_credit_earned",
            "total_credit_spent",
            "total_bonus_earned",
            "total_bonus_spent",
            "total_pnl",
        ],
    )
    user_stats = _to_datetime(user_stats, ["created_at", "updated_at"])

    user_block_stats = _read_csv(
        snap_dir / "user_block_stats.csv", USER_BLOCK_COLS, USER_BLOCK_RENAME
    )
    user_block_stats = _to_numeric(user_block_stats, ["user_id", "block_id", "count"])
    user_block_stats = _to_datetime(user_block_stats, ["first_seen", "last_seen"])

    user_item_stats = _read_csv(
        snap_dir / "user_item_stats.csv", USER_ITEM_COLS, USER_ITEM_RENAME
    )
    user_item_stats = _to_numeric(user_item_stats, ["user_id", "item_id", "count"])
    user_item_stats = _to_datetime(user_item_stats, ["first_seen", "last_seen"])

    user_attendance = _read_csv(
        snap_dir / "user_attendance.csv", USER_ATTENDANCE_COLS, USER_ATTENDANCE_RENAME
    )
    user_attendance = _to_numeric(user_attendance, ["user_id", "streak", "total_days"])
    user_attendance = _to_datetime(
        user_attendance, ["first_attendance", "last_attendance", "updated_at"]
    )

    game_user_stats = _read_csv(
        snap_dir / "game_user_stats.csv", GAME_USER_STATS_COLS, GAME_USER_STATS_RENAME
    )
    game_user_stats = _to_numeric(
        game_user_stats,
        [
            "game_id",
            "user_id",
            "total_block_reward",
            "total_item_spend",
            "total_credit_earned",
            "total_credit_spent",
            "total_bonus_earned",
            "total_bonus_spent",
            "total_pnl",
        ],
    )
    game_user_stats = _to_datetime(game_user_stats, ["created_at", "updated_at"])

    game_user_block_stats = _read_csv(
        snap_dir / "game_user_block_stats.csv", GAME_USER_BLOCK_COLS, USER_BLOCK_RENAME
    )
    game_user_block_stats = _to_numeric(
        game_user_block_stats, ["game_id", "user_id", "block_id", "count"]
    )
    game_user_block_stats = _to_datetime(
        game_user_block_stats, ["first_seen", "last_seen"]
    )

    game_user_item_stats = _read_csv(
        snap_dir / "game_user_item_stats.csv", GAME_USER_ITEM_COLS, USER_ITEM_RENAME
    )
    game_user_item_stats = _to_numeric(
        game_user_item_stats, ["game_id", "user_id", "item_id", "count"]
    )
    game_user_item_stats = _to_datetime(
        game_user_item_stats, ["first_seen", "last_seen"]
    )

    transactions = _read_csv(snap_dir / "user_transaction_log.csv", TX_COLS, TX_RENAME)
    transactions = _to_numeric(
        transactions,
        ["tx_id", "user_id", "game_id", "amount", "source_id"],
    )
    transactions = _to_datetime(transactions, ["created_at"])

    # ---- 메모리 절감 (Streamlit Cloud 1GB 한도 대응) ----
    # 1) 분석에 사용 안 하는 컬럼 즉시 drop. 60만+ 행에서 ~50MB+ 절감.
    for unused_col in ("balance_before", "balance_after", "message"):
        if unused_col in transactions.columns:
            del transactions[unused_col]
    # 2) ID 들은 Int32 (작은 정수).
    for col in ("user_id", "game_id", "source_id"):
        if col in transactions.columns:
            try:
                transactions[col] = transactions[col].astype("Int32")
            except (TypeError, ValueError):
                pass
    # 3) 반복 문자열 → category (tx_type/direction/source_type 은 카디널리티 < 10).
    for col in ("tx_type", "direction", "source_type"):
        if col in transactions.columns:
            try:
                transactions[col] = transactions[col].astype("category")
            except (TypeError, ValueError):
                pass

    if "created_at" in transactions.columns:
        transactions["snapshot_day"] = transactions["created_at"].dt.date

    # game_id → game_mode 분류 (NORMAL / HARDCORE / TEST / UNKNOWN).
    # `mode_name` 가 'HARDCORE' 를 포함하면 HARDCORE, 'NORMAL' 이면 NORMAL,
    # 그 외엔 TEST 로 분류하여 어떤 mode_name 이 추가돼도 동작하도록 합니다.
    if not games.empty:
        mode_map: dict[int, str] = {}
        for _, row in games.iterrows():
            gid = row["game_id"]
            name = (row["mode_name"] or "").upper() if isinstance(row["mode_name"], str) else ""
            if pd.isna(gid):
                continue
            if "HARDCORE" in name:
                mode_map[int(gid)] = "HARDCORE"
            elif "NORMAL" in name:
                mode_map[int(gid)] = "NORMAL"
            elif "TEST" in name:
                mode_map[int(gid)] = "TEST"
            else:
                mode_map[int(gid)] = "UNKNOWN"
        transactions["game_mode"] = (
            transactions["game_id"].map(mode_map).fillna("UNKNOWN").astype("category")
        )
    else:
        transactions["game_mode"] = "UNKNOWN"

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
