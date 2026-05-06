# 배포 가이드 — `pikitdata.streamlit.app`

이 가이드는 **Streamlit Community Cloud** 에 무료로 올려서
`https://pikitdata.streamlit.app` 같은 공개 URL을 받는 절차입니다.

> **왜 Vercel이 아닌가?**
> Vercel은 서버리스(요청-응답 모델)라 Streamlit이 쓰는 상시 WebSocket과
> 잘 안 맞고, 실제 운영 시 connecting 에러가 자주 납니다. Streamlit Cloud는
> 같은 회사가 운영하는 native 호스팅이라 한 번에 깔끔히 됩니다.

---

## 사전 체크 (1분)

| 항목 | 확인 |
|---|---|
| GitHub 계정 | `gh auth status` 또는 https://github.com 로그인 |
| Streamlit Cloud 계정 | https://share.streamlit.io 에 GitHub 로그인으로 가입 |
| 데이터 폴더 위치 | 이 저장소 안 `data/` 또는 외부 경로 |

---

## 1) 비공개 GitHub 저장소 만들기

```bash
cd <repo>

git init
git branch -M main

# 데이터 폴더가 외부에 있으면 그대로 두고, 저장소 안에 두려면
# data/ 디렉터리에 복사 (이 폴더는 .gitignore 로 차단됩니다)
mkdir -p data
cp -R "~/Downloads/PIKIT BETA DATA/2026.05.06" data/
# (필요시 다른 날짜도 복사)

git add .
git status                                  # data/ 가 안 잡혔는지 확인 ★
git commit -m "init: PIKIT balance dashboard"

# GitHub에서 새 private 저장소 'pikitdata' 만들고:
git remote add origin git@github.com:<YOUR_GH_ID>/pikitdata.git
git push -u origin main
```

> **데이터 어떻게 같이 올릴 건가요?**
> `.gitignore` 가 `data/` 와 `PIKIT BETA DATA/` 를 막아두기 때문에
> public 저장소에 raw CSV가 노출될 위험은 없습니다.
> Streamlit Cloud에 데이터를 함께 보내려면 두 옵션:
>
> 1) **private 저장소 안에 강제 포함** — `.gitignore` 의 `data/` 줄을 지우고
>    `git add data/ -f` 로 추가. 저장소가 private 인 한 외부에 안 보입니다.
>    파일당 100MB 미만이어야 하고, 합쳐서 1GB 이내가 적당합니다.
> 2) **별도 클라우드 스토리지 (S3/Supabase/Drive)** — 앱이 시작할 때
>    스토리지에서 다운로드. 큰 데이터에 적합. 필요하면 알려주세요, 코드 추가해드립니다.

---

## 2) Streamlit Cloud 에 배포

1. https://share.streamlit.io 접속 → **Create app**
2. 저장소 선택: `<YOUR_GH_ID>/pikitdata` (Branch: `main`)
3. Main file: `app.py`
4. **App URL**: 입력칸에 `pikitdata` 라고 적으면 → `pikitdata.streamlit.app`
5. **Advanced settings → Secrets** (선택, 필요 시)
   ```toml
   # 데이터를 외부 클라우드에서 가져오는 경우만 사용. private repo 안에 데이터가 있으면 비워둠.
   ```
6. **Advanced settings → Environment variables**
   ```
   PIKIT_PUBLIC=1
   PIKIT_DATA_ROOT=./data
   ```
   - `PIKIT_PUBLIC=1` → 원본 데이터 탭과 raw CSV 다운로드 버튼이 숨겨져
     익명 방문자가 트랜잭션 로그를 받아갈 수 없게 됩니다.
   - `PIKIT_DATA_ROOT=./data` → 저장소 안 `data/` 폴더를 데이터 루트로 사용.
7. **Deploy** — 1-2분이면 빌드/실행 완료, 위 URL이 활성화됩니다.

---

## 3) 데이터 추가 (운영)

새 일별 스냅샷이 생기면:

```bash
# 로컬에서 새 폴더 복사
cp -R "~/Downloads/PIKIT BETA DATA/2026.05.07" data/

# 1) data/ 가 .gitignore 로 막혀 있으면 해제하거나:
git add -f data/2026.05.07
# 2) 처음에 data/ 줄을 지웠다면 그냥:
git add data/2026.05.07

git commit -m "data: 2026.05.07 snapshot"
git push
```

push 하면 Streamlit Cloud가 약 30~60초 안에 자동 재배포 → 사이트에 새 날짜가 올라갑니다.

---

## 4) 자주 마주치는 문제

| 증상 | 원인 / 해결 |
|---|---|
| 빌드 실패 `ModuleNotFoundError` | `requirements.txt` 가 git에 들어갔는지 확인 |
| 화면이 비어 있음 | Logs 에서 `No snapshots found` → `PIKIT_DATA_ROOT` 또는 `data/` 폴더 위치 점검 |
| connecting 으로 멈춤 | 인터넷 연결 또는 캐시 문제. 시크릿 창에서 새로 열기 |
| 데이터가 너무 큼 | 파일당 100MB 넘으면 git-lfs 또는 외부 스토리지로. 알려주세요 |
| 비공개로 운영하고 싶음 | Streamlit Cloud 앱 설정에서 **Viewer** 를 GitHub email 로 제한 가능 (무료 계정도 일부 지원) |

---

## 5) 로컬 운영 vs 공개 배포 모드 차이

| | 로컬 (개발) | `PIKIT_PUBLIC=1` (공개) |
|---|---|---|
| 데이터 폴더 입력칸 | 보임 (변경 가능) | 숨김 (고정) |
| 📦 원본 데이터 탭 | 보임 | 숨김 |
| 추천 적용 탭의 raw CSV 다운로드 | 보임 | 숨김 (게임 포맷 다운로드만 보임) |
| 시뮬레이터 / 추천 / 차트 | 모두 동일 | 모두 동일 |

즉 **밸런스 분석 결과는 공개**되지만 **트랜잭션 로그 같은 raw 데이터는 외부에서 받아갈 수 없게** 분리되어 있습니다.

---

## 6) 도메인을 `pikitdata.com` 으로 바꾸고 싶다면

Streamlit Cloud는 무료 플랜에선 커스텀 도메인을 지원하지 않습니다.
- 무료: `pikitdata.streamlit.app` 까지만 가능
- 유료 (Streamlit Teams/Enterprise) 또는 자체 도메인 + Cloudflare 리다이렉트
- 또는 Render/Fly.io/Railway 같은 컨테이너 호스팅에 직접 배포 → `pikitdata.com` 가능 (월 $5 정도)

원하시면 그쪽 설정도 도와드릴 수 있습니다.
