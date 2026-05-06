# Synology DS720+ 배포 가이드

PIKIT 밸런스 대시보드를 **DS720+** Container Manager 로 띄웁니다.
30분 안에 끝나며, Streamlit Cloud 의 메모리/OAuth/캐시 문제가 모두 사라집니다.

## DS720+ 사양 체크
- CPU: Celeron J4125 (4코어 2.0GHz)
- 기본 RAM: 2GB (6GB 까지 확장 가능 — 분석 도구라면 4GB 권장)
- DSM: 7.0 이상 필요 (Container Manager)
- 현재 메모리는 DSM → 정보 센터 → 시스템 에서 확인

> RAM 2GB여도 PIKIT 만 단독으로 돌리면 충분합니다. Plex 같은 다른 서비스와
> 같이 쓰면 4GB+로 업그레이드 권장. (하이닉스 4GB 모듈 약 3만원)

---

## 1단계 — 사전 준비 (5분)

### 1.1 Container Manager 설치
DSM → 패키지 센터 → "Container Manager" 검색 → 설치.

### 1.2 SSH 활성화 (선택, 더 빠른 길)
DSM → 제어판 → 터미널 및 SNMP → "SSH 서비스 활성화" 체크 → 적용.
- 포트 22 사용
- admin 계정으로 SSH 접속 가능

### 1.3 프로젝트 폴더 생성
DSM File Station 으로 다음 구조 생성:
```
/volume1/docker/pikit/
├── data/                  ← 일별 스냅샷 폴더 둘 곳
└── (코드 파일들 들어갈 자리)
```

---

## 2단계 — 코드 + 데이터 NAS 로 복사 (10분)

### 옵션 A: SMB 공유 + Mac Finder (제일 쉬움)

Finder → **이동 → 서버에 연결** → `smb://시놀로지IP/docker` → admin 로그인.

`/Volumes/docker/pikit/` 가 마운트됨. Mac 에서 Finder 로 직접 복사:

```bash
# 코드 (data 폴더 제외하고 복사)
rsync -av --exclude='.venv/' --exclude='__pycache__/' --exclude='.git/' \
  --exclude='data/' --exclude='*.zip' \
  /Users/moomi/Downloads/z03.Vibe_Coding/dataanal/ \
  /Volumes/docker/pikit/

# 데이터 (별도 복사)
mkdir -p /Volumes/docker/pikit/data
rsync -av "/Users/moomi/Downloads/PIKIT BETA DATA/2026.05.06" \
  /Volumes/docker/pikit/data/
```

### 옵션 B: SSH + git clone

NAS SSH 접속 후:
```bash
sudo -i
mkdir -p /volume1/docker/pikit && cd /volume1/docker/pikit
git clone https://github.com/ALXxxXNDR/pikitdata.git .
# 데이터는 따로 SCP 로:
# (Mac 에서) scp -r "PIKIT BETA DATA/2026.05.06" admin@nas:/volume1/docker/pikit/data/
```

---

## 3단계 — Container Manager 로 빌드 + 실행 (10분)

### 옵션 A: GUI 클릭만으로

1. DSM → **Container Manager** 실행
2. 좌측 메뉴 → **프로젝트** → **만들기**
3. 프로젝트 정보 입력:
   - 프로젝트 이름: `pikit-balance`
   - 경로: `/volume1/docker/pikit`
   - 소스: **기존 docker-compose.yml** 선택
4. 자동 감지된 `docker-compose.yml` 확인 → **다음**
5. **빌드 시작** 클릭 → 첫 빌드 5~10분 소요 (Python + pandas 다운로드)
6. 완료되면 컨테이너 자동 실행

### 옵션 B: SSH 한 줄

```bash
cd /volume1/docker/pikit
sudo docker compose up -d --build
# 빌드 진행 상황 보려면:
sudo docker compose logs -f pikit
```

---

## 4단계 — 접속

### 집 네트워크 안에서
브라우저: `http://시놀로지IP:8501`

예: `http://192.168.1.100:8501` 또는 `http://시놀로지이름.local:8501`

### 외부에서 접속 (선택사항)

#### QuickConnect (가장 쉬움 — 무료)
1. DSM → 제어판 → QuickConnect → 활성화
2. QuickConnect ID 설정: `pikitdata` 같은 이름
3. URL: `https://quickconnect.to/pikitdata` 의 8501 포트로 접근
   - 다만 QuickConnect 는 포트 매핑이 살짝 까다로움

#### DDNS + 포트 포워딩 (직접 도메인)
1. DSM → 제어판 → 외부 액세스 → DDNS → 추가
   - 서비스 공급자: Synology
   - 호스트 이름: `pikit-yourname` → `pikit-yourname.synology.me` 자동 발급
2. 라우터에서 8501 포트 외부 → NAS 로 포워딩
3. URL: `http://pikit-yourname.synology.me:8501`

#### HTTPS + 진짜 도메인 (가장 깔끔)
1. 도메인 구입 (Cloudflare $10/년 추천)
2. DSM → 제어판 → 로그인 포털 → 역방향 프록시 → 새로 만들기
   - 출발지: `https://pikitdata.yourdomain.com`
   - 대상: `http://localhost:8501`
3. DSM → 제어판 → 보안 → 인증서 → Let's Encrypt 추가 (무료)

---

## 5단계 — 운영 워크플로

### 새 데이터 추가
SMB 가 마운트되어 있으면 Mac 에서 직접:
```bash
rsync -av "/Users/moomi/Downloads/PIKIT BETA DATA/2026.05.07" \
  /Volumes/docker/pikit/data/
```

→ Streamlit 자동 감지. 컨테이너 재시작 불필요.

### 코드 업데이트
Mac 에서 코드 수정 후:
```bash
rsync -av --exclude='.venv/' --exclude='data/' --exclude='__pycache__/' \
  /Users/moomi/Downloads/z03.Vibe_Coding/dataanal/ \
  /Volumes/docker/pikit/
```

Container Manager → 프로젝트 → `pikit-balance` → **재빌드**, 또는 SSH로:
```bash
cd /volume1/docker/pikit && sudo docker compose up -d --build
```

### 로그 확인
- GUI: Container Manager → 컨테이너 → `pikit-balance` → 로그
- SSH: `sudo docker logs -f pikit-balance`

### 컨테이너 재시작 / 중지
- GUI: Container Manager → 프로젝트 → 작업 메뉴
- SSH: `sudo docker compose restart` / `sudo docker compose down`

---

## 6단계 — 자주 마주치는 문제

| 증상 | 원인 / 해결 |
|---|---|
| 빌드 실패 `permission denied` | `chown -R 1026:1026 /volume1/docker/pikit/data` 로 권한 부여 |
| 포트 8501 충돌 | docker-compose.yml 에서 `"8580:8501"` 로 변경 |
| `data 에서 스냅샷을 찾지 못했습니다` | `/volume1/docker/pikit/data/2026.05.06/` 형태인지 확인 |
| 빌드 너무 느림 (>15분) | DS720+ Celeron 이라 첫 빌드는 시간 걸림. 두 번째부터는 캐시 사용해 빠름 |
| 외부 접속 안 됨 | 라우터 포트포워딩 확인 + Synology 방화벽에 8501 허용 |
| 메모리 부족 경고 | DS720+ 기본 2GB. RAM 4GB 로 확장 권장 |

---

## 비교 — Streamlit Cloud vs DS720+

| | Streamlit Cloud 무료 | DS720+ NAS |
|---|---|---|
| RAM | 1GB (꽉 참, 자주 OOM) | 2~6GB (여유) |
| CPU | shared (느림) | J4125 dedicated |
| 데이터 보안 | private repo 필요 | 집 NAS 안에 (외부 공개 X) |
| 배포 트리거 | git push (OAuth 만료시 깨짐) | 파일 복사 즉시 반영 |
| 비용 | 무료 (한도 있음) | 0원 (NAS 이미 있음) |
| 외부 URL | `*.streamlit.app` 무료 | DDNS 무료 또는 도메인 $10/년 |
| 깨짐 빈도 | 잦음 (지난 1주 경험) | 거의 없음 |

---

## 다음 단계

1. **지금**: 옵션 A (SMB + Container Manager 클릭) 으로 30분 셋업
2. **확인 후**: 외부 접속 필요하면 QuickConnect 활성화
3. **만족하면**: Streamlit Cloud 앱 정리 (또는 백업용으로 둠)

막히는 단계 있으면 그 단계 번호 + 화면 캡쳐 알려주세요. 정확히 짚어드리겠습니다.
