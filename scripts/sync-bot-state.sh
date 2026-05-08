#!/usr/bin/env bash
#
# PIKITbot 의 state.json 을 dataanal 의 bot_state.json (sanitized) 로 sync.
#
# 동작:
#   1. PIKITbot/dashboard/data/state.json 읽기
#   2. privateKey 제거 (public repo 보안)
#   3. dataanal/bot_state.json 에 쓰기
#   4. 변경 있으면 git commit + push → NAS 자동 배포로 Streamlit 에 반영
#
# 사용:
#   ./scripts/sync-bot-state.sh           # 기본: 변경 있으면 commit + push
#   ./scripts/sync-bot-state.sh --dry-run # 변경 미리보기만, commit 안 함
#   ./scripts/sync-bot-state.sh --no-push # commit 만, push 안 함
#
# 자동화 (선택):
#   ./scripts/sync-bot-state.sh 를 launchd 또는 cron 으로 5분마다 실행

set -e

DATAANAL_DIR="/Users/moomi/Downloads/z03.Vibe_Coding/dataanal"
PIKITBOT_STATE="/Users/moomi/Downloads/z03.Vibe_Coding/PIKITbot/dashboard/data/state.json"
TARGET_FILE="$DATAANAL_DIR/bot_state.json"

DRY_RUN=0
NO_PUSH=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-push) NO_PUSH=1 ;;
        -h|--help)
            head -25 "$0" | tail -22
            exit 0
            ;;
    esac
done

# 1) 소스 파일 존재 확인
if [ ! -f "$PIKITBOT_STATE" ]; then
    echo "❌ 소스 파일이 없습니다: $PIKITBOT_STATE"
    echo "   PIKITbot 이 다른 경로면 이 스크립트의 PIKITBOT_STATE 변수 수정."
    exit 1
fi

# 2) sanitize (privateKey 제거) — Python 으로
TMP=$(mktemp -t bot-sync-XXXXXX.json)
trap 'rm -f "$TMP"' EXIT

python3 - <<EOF
import json
with open("$PIKITBOT_STATE") as f:
    src = json.load(f)
sanitized = {
    "remote": src.get("remote", {}),
    "sets": [
        {
            "id": s["id"],
            "name": s["name"],
            "bots": [
                {k: v for k, v in b.items() if k != "privateKey"}
                for b in s["bots"]
            ],
        }
        for s in src.get("sets", [])
    ],
    "deployments": src.get("deployments", {}),
}
with open("$TMP", "w") as f:
    json.dump(sanitized, f, indent=2)
n_sets = len(sanitized["sets"])
n_bots = sum(len(s["bots"]) for s in sanitized["sets"])
print(f"  Sanitized OK — {n_sets} sets, {n_bots} bots, privateKey 제거됨")
EOF

# 3) 차이 확인
if [ -f "$TARGET_FILE" ] && diff -q "$TMP" "$TARGET_FILE" > /dev/null 2>&1; then
    echo "✓ 변경 없음 — sync 불필요."
    exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
    echo ""
    echo "=== DRY RUN: 변경 미리보기 ==="
    diff -u "$TARGET_FILE" "$TMP" 2>/dev/null | head -40 || true
    echo ""
    echo "→ 실제 적용하려면 --dry-run 빼고 다시 실행"
    exit 0
fi

# 4) 실제 적용
mv "$TMP" "$TARGET_FILE"
trap - EXIT
echo "✓ $TARGET_FILE 업데이트됨"

# 5) git commit + push
cd "$DATAANAL_DIR"
if ! git diff --quiet bot_state.json 2>/dev/null; then
    SETS_INFO=$(python3 -c "
import json
with open('bot_state.json') as f:
    s = json.load(f)
sets = s.get('sets', [])
deps = s.get('deployments', {})
parts = []
for set_obj in sets:
    name = set_obj['name']
    n = len(set_obj['bots'])
    tracks = [t for t, d in deps.items() if set_obj['id'] in d.get('setIds', [])]
    parts.append(f'{name}({n}봇,{','.join(tracks) or '미배포'})')
print(', '.join(parts))
" 2>/dev/null || echo "")

    git add bot_state.json
    git commit -m "sync: PIKITbot 상태 → bot_state.json

세트 현황: $SETS_INFO

(자동 sync 스크립트 — privateKey 제거된 sanitized 버전)" 2>&1 | tail -3

    if [ "$NO_PUSH" = "0" ]; then
        echo ""
        echo "git push origin main..."
        git push origin main 2>&1 | tail -3
        echo ""
        echo "✅ Sync 완료. NAS 의 다음 자동 배포 (~5~15분) 후 Streamlit 에 반영됨."
    else
        echo "✓ Commit 만 — push 는 수동으로 진행"
    fi
else
    echo "✓ git 차이 없음"
fi
