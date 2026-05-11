# PIKIT Vault — Soneium 운영 지갑 모니터

`despell.synology.me/pikit` 에서 PIKIT 의 두 운영 지갑 (운영 수익 + 유저 리워드)
을 실시간 추적하고, 리워드 Vault 잔고가 임계 미만으로 떨어지면 메일로 알림.

## 추적 대상

| 지갑 | 주소 | 임계 |
|------|------|------|
| 💰 운영 수익 | `0x79fc40D8…162e8D6E` | 없음 |
| 🎁 유저 리워드 Vault | `0xee5c5c0f…6d3bd722` | $300 미만 시 알림 |

## 화면

- **메인** — 2 지갑 카드 (현재 USD 총합, 보유 토큰, 임계 미달 시 빨간 배지)
- **상세** — 카드 클릭 → 카운터파티 분포 (입금처/출금처 Top 20), 기간별 시계열 PNL, 거래 원장

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run pikit_vault/app.py --server.port 8502
```

브라우저: http://localhost:8502/

## NAS 배포 (Synology DS720+)

이미 메인 PIKIT 사이트가 배포된 상태에서 vault 만 추가:

```bash
ssh admin@<nas>
cd /volume1/docker/pikit
git pull
sudo docker compose up -d --build pikit-vault
```

확인: `http://<nas-ip>:8502/pikit/`

## 리버스 프록시 (DSM Control Panel)

`Control Panel → Login Portal → Advanced → Reverse Proxy → Create`

| 항목 | 값 |
|------|-----|
| Source Protocol | HTTPS |
| Source Hostname | despell.synology.me |
| Source Port | 443 |
| Destination Protocol | HTTP |
| Destination Hostname | localhost |
| Destination Port | 8502 |

`Custom Header` 탭에서 WebSocket:
- `Upgrade: $http_upgrade`
- `Connection: $connection_upgrade`

URL 매핑: `despell.synology.me/pikit/` → `http://localhost:8502/pikit/`
컨테이너의 `STREAMLIT_SERVER_BASEURLPATH=/pikit` 가 subpath 처리.

## 알림 메일 설정

`.env` 파일을 `/volume1/docker/pikit/.env` 에 만들기:

```env
ALERT_EMAIL_TO=alex@depsell.io
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-bot@gmail.com
SMTP_PASSWORD=app-specific-password
SMTP_USE_TLS=true

# 옵션
TENDERLY_RPC_URL=https://soneium.gateway.tenderly.co/<your-key>
```

`docker compose up -d` 다시 실행하면 환경변수가 컨테이너로 주입됨.

## 알림 데몬 (1분마다 자동 체크)

`pikit-vault-alert` 컨테이너가 1분 간격으로 잔고를 체크하고 임계 미만이면 메일 발송.

- 체크 주기: `ALERT_INTERVAL_SECONDS` (기본 60s)
- 재발송 쿨다운: `ALERT_COOLDOWN_HOURS` (기본 6h) — 1분 체크여도 메일은 6시간에 한 번
- 잔고 회복 시 상태 자동 리셋
- SMTP 미설정 시 stdout 로그만 → `docker logs pikit-vault-alert` 에서 확인

```bash
# 로그 확인
sudo docker logs -f pikit-vault-alert

# 데몬 재시작 (env 변경 후)
sudo docker compose restart pikit-vault-alert
```

## 수동 테스트

```bash
# 1회 체크 (쿨다운 적용)
sudo docker exec pikit-vault python -m pikit_vault.alert

# 쿨다운 무시 강제 발송
sudo docker exec pikit-vault python -m pikit_vault.alert --force

# 임시로 빠른 체크 데몬 (5초 간격)
sudo docker exec pikit-vault-alert python -m pikit_vault.alert --daemon --interval 5
```

## 파일 구조

```
pikit_vault/
├── __init__.py
├── config.py         # 지갑 주소, RPC URL, SMTP 설정
├── soneium_client.py # JSON-RPC + Blockscout + 가격
├── app.py            # Streamlit 대시보드 (메인 + 상세)
├── alert.py          # 임계 알림 CLI (cron 용)
└── README.md         # 이 파일
```

## RPC failover

`config.get_rpc_urls()` 우선순위:
1. `TENDERLY_RPC_URL` (env) — 있으면 최우선
2. `https://rpc.soneium.org` (공식)
3. `https://soneium.drpc.org` (백업)

순차 시도, 첫 성공 응답 반환. 모두 실패 시 마지막 에러 raise.
