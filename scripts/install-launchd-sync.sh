#!/usr/bin/env bash
#
# Mac launchd 에 sync-bot-state.sh 를 1분 주기로 등록.
# Mac 이 로그인 상태라면 자동으로 PIKITbot state.json 변경을 NAS 로 push.
#
# 사용:
#   ./scripts/install-launchd-sync.sh         # 1분 주기 등록
#   ./scripts/install-launchd-sync.sh --uninstall   # 제거
#
# 동작 후:
#   - 1분마다 sync-bot-state.sh 자동 실행
#   - 변경 없으면 1초만에 종료 (이미 diff 체크 있음)
#   - 변경 있으면 git commit + push → NAS 자동 배포 (~1-5분)
#   - 로그: /tmp/pikit-bot-sync.log

set -e

PLIST_NAME="com.pikit.bot-sync"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sync-bot-state.sh"

if [ "$1" = "--uninstall" ]; then
    if [ -f "$PLIST_PATH" ]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm "$PLIST_PATH"
        echo "✓ 제거 완료: $PLIST_PATH"
    else
        echo "이미 미설치 상태."
    fi
    exit 0
fi

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "❌ sync 스크립트 없음: $SCRIPT_PATH"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${SCRIPT_PATH}</string>
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>/tmp/pikit-bot-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/pikit-bot-sync.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

# 이미 로드돼 있으면 unload 먼저 (덮어쓰기 안전하게)
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "✅ 설치 완료"
echo ""
echo "  설정: $PLIST_PATH"
echo "  주기: 60초"
echo "  로그: /tmp/pikit-bot-sync.log"
echo ""
echo "확인:"
echo "  launchctl list | grep pikit"
echo "  tail -f /tmp/pikit-bot-sync.log"
echo ""
echo "제거:"
echo "  $0 --uninstall"
