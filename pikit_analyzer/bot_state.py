"""
봇 세트 상태 관리 — bot_state.json 의 read/write + env 필터 + 세트 CRUD.

상태 모델 (bot_state.json):
{
  "remote": {...},                  # SSH 정보 (UI 표시 용)
  "sets": [                         # 봇 세트 목록
    {
      "id": "beta1",
      "name": "beta1",
      "bots": [                     # 12개 (또는 그 이하)
        {
          "id": "beta1:bot-01",
          "slot": 1,
          "label": "bot-01",
          "address": "0x...",       # 주소만 — privateKey 는 commit 안 함
          "strategy": "pickaxe-1"
        },
        ...
      ]
    }
  ],
  "deployments": {                  # 트랙 (env) 별 어떤 set 가 활성인지
    "beta": { "track": "beta", "siteUrl": "...", "setIds": ["beta1"], "excludedBotIds": [] },
    "dev":  { "track": "dev",  "siteUrl": "...", "setIds": [],         "excludedBotIds": [] }
  }
}

저장 위치:
- 컨테이너 내부: /app/cache/bot_state.json (named volume, persistent across rebuilds)
- 로컬 dev: PIKIT_CACHE_DIR/bot_state.json (env 변수)
- 초기값: repo 의 bot_state.json (read-only template) — 첫 실행 시 cache 로 복사
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


# 상태 파일 경로 결정
def _state_writable_path() -> Path:
    """런타임 상태 파일 — 쓰기 가능. /app/cache 또는 PIKIT_CACHE_DIR/."""
    env_cache = os.environ.get("PIKIT_CACHE_DIR", "").strip()
    if env_cache:
        p = Path(env_cache).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return p / "bot_state.json"
    container_cache = Path("/app/cache")
    if container_cache.exists() and os.access(container_cache, os.W_OK):
        return container_cache / "bot_state.json"
    # 마지막 fallback: 현재 디렉터리
    return Path("bot_state.json")


def _state_template_path() -> Path:
    """초기 템플릿 — repo 의 bot_state.json (read-only)."""
    # pikit_analyzer/ 의 부모 디렉터리 (repo 루트) 의 bot_state.json
    return Path(__file__).resolve().parent.parent / "bot_state.json"


WRITABLE_PATH = _state_writable_path()
TEMPLATE_PATH = _state_template_path()


# 트랙 (env) 기본 설정 — 지정되지 않은 env 의 deployments 자동 생성용
DEFAULT_TRACK_CONFIGS = {
    "beta": {"siteUrl": "https://beta.pikit.fun/"},
    "dev": {"siteUrl": "https://dev.pikit.fun/"},
}

# 사용 가능한 전략 — PIKITbot 과 동일
AVAILABLE_STRATEGIES = [
    "pickaxe-1", "pickaxe-2", "pickaxe-3", "pickaxe-4", "pickaxe-5",
    "random-1-3", "random-3-5", "random-1-5",
]


def _empty_state() -> dict[str, Any]:
    return {
        "remote": {"sshTarget": "", "projectPath": ""},
        "sets": [],
        "deployments": {
            "beta": {"track": "beta", "siteUrl": "https://beta.pikit.fun/", "setIds": [], "excludedBotIds": []},
            "dev": {"track": "dev", "siteUrl": "https://dev.pikit.fun/", "setIds": [], "excludedBotIds": []},
        },
    }


def _ensure_state_initialized():
    """첫 호출 시 cache 에 상태 파일이 없으면 template 에서 복사."""
    if WRITABLE_PATH.exists():
        return
    try:
        WRITABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    if TEMPLATE_PATH.exists():
        try:
            shutil.copy2(TEMPLATE_PATH, WRITABLE_PATH)
            return
        except OSError:
            pass
    # 템플릿도 없으면 빈 상태로 생성
    try:
        with WRITABLE_PATH.open("w") as f:
            json.dump(_empty_state(), f, indent=2)
    except OSError:
        pass


def load_state() -> dict[str, Any]:
    """현재 상태 로드. 없으면 template 에서 자동 복사."""
    _ensure_state_initialized()
    try:
        with WRITABLE_PATH.open("r") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    # 안전 보강 — 누락 키 기본값 주입.
    state.setdefault("remote", {})
    state.setdefault("sets", [])
    state.setdefault("deployments", _empty_state()["deployments"])
    for track, default in _empty_state()["deployments"].items():
        state["deployments"].setdefault(track, default)
    return state


def save_state(state: dict[str, Any]) -> bool:
    """상태 atomic 저장 — tmp 쓰고 rename."""
    try:
        WRITABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = WRITABLE_PATH.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(state, f, indent=2)
        tmp.replace(WRITABLE_PATH)
        return True
    except OSError:
        return False


def save_state_with_diag(state: dict[str, Any]) -> tuple[bool, str]:
    """save_state + 진단 메시지. 실패 시 정확한 이유."""
    try:
        WRITABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        return False, f"PermissionError on mkdir({WRITABLE_PATH.parent}): {e}"
    except OSError as e:
        return False, f"OSError on mkdir({WRITABLE_PATH.parent}): {e}"

    # 쓰기 권한 빠르게 사전 진단
    test_target = WRITABLE_PATH.parent / ".write_test"
    try:
        test_target.write_text("ok", encoding="utf-8")
        test_target.unlink()
    except PermissionError as e:
        import os
        try:
            stat = os.stat(WRITABLE_PATH.parent)
            owner = f"uid={stat.st_uid} gid={stat.st_gid} mode={oct(stat.st_mode)[-3:]}"
        except OSError:
            owner = "?"
        try:
            cur_uid = os.geteuid()
        except AttributeError:
            cur_uid = "?"
        return False, (
            f"쓰기 권한 없음: {WRITABLE_PATH.parent} ({owner}), 현재 프로세스 uid={cur_uid}. "
            f"named volume 의 owner 가 root 라 컨테이너의 pikit (uid 1026) 가 못 씀. "
            f"NAS 에서 sudo chown -R 1026:1026 /volume1/@docker/volumes/dataanal_pikit_cache/_data"
        )
    except OSError as e:
        return False, f"OSError on write test: {e}"

    try:
        tmp = WRITABLE_PATH.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(state, f, indent=2)
        tmp.replace(WRITABLE_PATH)
        return True, "OK"
    except OSError as e:
        return False, f"OSError on save: {e}"


# ---------------------------------------------------------------------------
# 세트 / 트랙 조회
# ---------------------------------------------------------------------------

def list_sets_for_track(state: dict[str, Any], track: str) -> list[dict]:
    """현재 트랙의 deployments.setIds 에 포함된 세트만 반환."""
    deployment = state.get("deployments", {}).get(track, {})
    set_ids = set(deployment.get("setIds", []))
    return [s for s in state.get("sets", []) if s.get("id") in set_ids]


def list_all_sets(state: dict[str, Any]) -> list[dict]:
    """모든 세트 — 어느 트랙에도 안 속한 미배포 세트도 포함."""
    return list(state.get("sets", []))


def get_set(state: dict[str, Any], set_id: str) -> dict | None:
    for s in state.get("sets", []):
        if s.get("id") == set_id:
            return s
    return None


def get_track_setIds(state: dict[str, Any], track: str) -> list[str]:
    return list(state.get("deployments", {}).get(track, {}).get("setIds", []))


# ---------------------------------------------------------------------------
# 세트 생성 / 수정 / 삭제
# ---------------------------------------------------------------------------

def generate_wallets(count: int = 12) -> list[dict]:
    """eth-account 로 새 지갑 N 개 생성. 반환: [{address, privateKey}, ...]."""
    from eth_account import Account
    Account.enable_unaudited_hdwallet_features()
    wallets = []
    for _ in range(count):
        acct = Account.create()
        wallets.append({"address": acct.address, "privateKey": acct.key.hex()})
    return wallets


def create_new_set(
    state: dict[str, Any],
    name: str,
    track: str | None = None,
    strategies: list[str] | None = None,
    n_bots: int = 12,
) -> tuple[dict, list[dict]]:
    """새 세트 생성 + 새 wallet 12개.

    반환: (state 에 추가된 set dict, [{address, privateKey} × 12]) — privateKey 는
    호출자가 한 번만 사용자에게 보여주고 절대 저장하지 말 것.
    """
    # set id 충돌 방지
    existing_ids = {s["id"] for s in state.get("sets", [])}
    base_id = name.strip().lower().replace(" ", "_")
    new_id = base_id
    suffix = 2
    while new_id in existing_ids:
        new_id = f"{base_id}_{suffix}"
        suffix += 1

    if strategies is None:
        # 기본 전략 분포 — pickaxe-1~5 각 2개, random 2개 (12개 합)
        strategies = (
            ["pickaxe-1", "pickaxe-1"] +
            ["pickaxe-2", "pickaxe-2"] +
            ["pickaxe-3", "pickaxe-3"] +
            ["pickaxe-4", "pickaxe-4"] +
            ["pickaxe-5", "pickaxe-5"] +
            ["random-1-5", "random-1-5"]
        )
    if len(strategies) < n_bots:
        # 부족하면 마지막 전략으로 채움
        strategies = strategies + [strategies[-1]] * (n_bots - len(strategies))
    strategies = strategies[:n_bots]

    wallets = generate_wallets(n_bots)
    new_set = {
        "id": new_id,
        "name": name.strip() or new_id,
        "bots": [
            {
                "id": f"{new_id}:bot-{i+1:02d}",
                "slot": i + 1,
                "label": f"bot-{i+1:02d}",
                "address": w["address"],
                "strategy": strategies[i],
            }
            for i, w in enumerate(wallets)
        ],
    }
    state.setdefault("sets", []).append(new_set)

    # 트랙 지정되면 deployments.setIds 에도 추가
    if track:
        state.setdefault("deployments", {})
        track_cfg = state["deployments"].setdefault(
            track,
            {
                "track": track,
                "siteUrl": DEFAULT_TRACK_CONFIGS.get(track, {}).get("siteUrl", ""),
                "setIds": [],
                "excludedBotIds": [],
            },
        )
        if new_id not in track_cfg["setIds"]:
            track_cfg["setIds"].append(new_id)

    return new_set, wallets


def delete_set(state: dict[str, Any], set_id: str) -> bool:
    """세트 삭제 + 모든 트랙의 deployments.setIds 에서도 제거."""
    sets = state.get("sets", [])
    found = next((i for i, s in enumerate(sets) if s.get("id") == set_id), None)
    if found is None:
        return False
    del sets[found]
    for dep in state.get("deployments", {}).values():
        if set_id in dep.get("setIds", []):
            dep["setIds"].remove(set_id)
    return True


def update_set_track_assignment(
    state: dict[str, Any],
    set_id: str,
    track: str,
    enabled: bool,
):
    """세트를 특정 트랙에 활성화/비활성화."""
    state.setdefault("deployments", {})
    track_cfg = state["deployments"].setdefault(
        track,
        {
            "track": track,
            "siteUrl": DEFAULT_TRACK_CONFIGS.get(track, {}).get("siteUrl", ""),
            "setIds": [],
            "excludedBotIds": [],
        },
    )
    if enabled:
        if set_id not in track_cfg["setIds"]:
            track_cfg["setIds"].append(set_id)
    else:
        if set_id in track_cfg["setIds"]:
            track_cfg["setIds"].remove(set_id)


def update_bot_strategy(state: dict[str, Any], set_id: str, bot_id: str, strategy: str) -> bool:
    s = get_set(state, set_id)
    if s is None:
        return False
    for b in s.get("bots", []):
        if b.get("id") == bot_id:
            b["strategy"] = strategy
            return True
    return False


def rename_set(state: dict[str, Any], set_id: str, new_name: str) -> bool:
    s = get_set(state, set_id)
    if s is None:
        return False
    s["name"] = new_name.strip() or s["name"]
    return True


# ---------------------------------------------------------------------------
# PNL 통합용 — set_name → wallet_addresses dict (resolve_bot_set 호환)
# ---------------------------------------------------------------------------

def get_wallet_addresses(set_dict: dict) -> list[str]:
    """세트의 모든 봇 주소를 lowercase 로."""
    return [b.get("address", "").lower() for b in set_dict.get("bots", []) if b.get("address")]


def get_pnl_compatible_sets(state: dict[str, Any], track: str) -> dict[str, dict]:
    """PNL 탭의 BOT_SETS 형식으로 변환.

    반환:
      { "세트이름": { "wallets": ["0x...", ...] }, ... }

    track 의 deployments.setIds 안에 있는 세트만 포함.
    """
    out: dict[str, dict] = {}
    for s in list_sets_for_track(state, track):
        out[s["name"]] = {"wallets": get_wallet_addresses(s)}
    return out
