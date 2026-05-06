# PIKIT 밸런스 대시보드

PIKIT 베타 트랜잭션 데이터를 한 화면에서 보고, **모드별 / 기간별 / 유저별 / 시간대별** 로 슬라이스하고,
**목표 ROI 에 맞춘 곡괭이·블록 추천값을 게임 포맷 그대로** 다운로드할 수 있는 인터랙티브 도구.

> 🌐 **공개 배포** — `pikitdata.streamlit.app` (Streamlit Community Cloud).
> 배포 절차는 [DEPLOY.md](DEPLOY.md) 참고.

---

## 1. 사이드바 — 핵심 4개의 필터

| 필터 | 옵션 |
| --- | --- |
| **데이터 폴더** | 로컬 개발 시에만 표시. 운영 배포에서는 `PIKIT_DATA_ROOT` env 로 고정 |
| **기간 모드** | 단일 스냅샷 / 단일 날짜 / 날짜 범위 |
| **게임 모드** | 전체 / NORMAL / HARDCORE (기본 NORMAL) |
| **계정 필터** | 퀘스트 더미 10개는 항상 제외, 시스템 계정 1개는 토글로 제어 |

> 게임 모드는 `DEMO_NORMAL_MODE` / `DEMO_HARDCORE_MODE` 트랜잭션을 분리하며, 모드별 경제는 양상이 완전히 다르므로 분리 분석을 기본으로 권장합니다.

> 시스템 계정(보통 user_id 11)은 인게임 운영용 — 끄면 일반 유저만, 켜면 "시스템 곡괭이가 얼마나 캤는가"까지 포함됩니다.

---

## 2. 탭 구성

데이터 보기(메인)와 밸런스 도구(부가)가 좌→우 순서로 분리되어 있습니다.

| 탭 | 내용 |
| --- | --- |
| 👤 **유저** | 유저별 PNL 표 / 분포 히스토그램 / 모드별 세션 박스플롯 / CSV 다운로드 |
| ⏱️ **시간대별 PNL** | 1시간 / 30분 / 10분 / 1일 단위 리샘플링. 전체 합산 또는 상위 N명 유저별. 누적 PNL · 기간별 보상/지출/PNL · 활성 유저 수 · 유저×시간 히트맵 |
| 🔍 **유저 상세 / 그룹 분석** | 1~N명 멀티셀렉트. 개별/합산 모드. 시계열 + 블록·아이템 분포 차트 |
| ⛏️ **곡괭이 / TNT** | 가격 vs 실측 ROI 산점도 + 목표 ROI 슬라이더 + 추천 가격 표 |
| 🪨 **블록** | 설정 vs 실측 드롭률, HP-보상 산점도, 추천 보상 표 |
| 📦 **원본 데이터** | 12개 원본 테이블 그대로 열람 (공개 배포에서는 자동 숨김) |
| │ 🧪 **[부가] 시뮬레이터** | 가격/공격력/지속시간/HP/보상/드롭률 자유 편집 → 즉시 ROI 재계산 + 게임 포맷 CSV 다운로드 |
| │ 📤 **[부가] 밸런스 적용** | 추천값을 `item.csv` / `block.csv` / JSON 변경 명세로 다운로드 |

---

## 3. 밸런스 적용 워크플로

`📤 밸런스 적용` 탭에서 한 번에 받을 수 있는 산출물:

1. **`item.csv` (게임 포맷)** — 헤더 없는 12-컬럼, 가격만 추천값으로 갈아치움. `PIKIT BETA DATA/날짜/item.csv` 자리에 그대로 덮어씌울 수 있음.
2. **`block.csv` (게임 포맷)** — 보상 컬럼만 추천값으로 갈아치움.
3. **변경 명세 JSON** — `현재값 → 추천값 + 사유 + 메트릭` 정리. GitOps 기반 config PR 로 그대로 사용 가능.

`🧪 시뮬레이터` 에서는 운영자가 직접 편집한 값(추천 X) 도 동일 포맷 CSV 로 받을 수 있어, "이 가격으로 가자" 결정 후 바로 export 가능.

목표 ROI / 드롭률 허용 편차 슬라이더로 추천 강도를 조정합니다.

---

## 4. 핵심 지표 정의

| 지표 | 정의 |
| --- | --- |
| `block_reward` | 블록을 깨서 받은 총 크레딧 (`tx_type=BLOCK_REWARD`) |
| `item_spend` | 곡괭이/TNT 구매에 쓴 총 크레딧 (`tx_type=ITEM_PURCHASE`, 절댓값) |
| `pnl` | `block_reward − item_spend` |
| `roi` | `pnl ÷ item_spend` |
| `theoretical_roi` | 곡괭이를 100% 활용한다고 가정한 ROI: `(duration_s × attack ÷ E[HP]) × E[reward] − price) ÷ price` |
| `realized_roi` | 같은 게임 세션의 블록 보상을 그 게임의 아이템 구매 횟수에 비례 분배해 추정한 실측 ROI |
| `sink_ratio` | `total_item_spend ÷ total_block_reward`. 1보다 크면 시스템이 크레딧을 흡수 |
| `cum_pnl` | 시계열에서 유저별 누적 PNL |

### 추천 로직

* **아이템**: 데이터가 충분한 아이템(구매 ≥ 5회)은 `realized_roi` 우선, 아니면 `theoretical_roi`. `recommended_price = effective_reward_per_buy ÷ (1 + 목표ROI)`.
* **블록**: 같은 모드 평균 `reward_per_hp` 기준으로 ±15% 이상 벗어나면 보상 조정 제안. 설정 드롭률 vs 실측 드롭률 편차가 ±1.5%p 를 넘으면 플래그.

---

## 5. 새 스냅샷 추가

`{데이터 루트}/2026.MM.DD/` 형식 폴더에 12개 CSV (`block.csv`, `user_transaction_log.csv` 등) 를 그대로 넣으면 사이드바에 자동 추가됩니다.

운영 배포(Streamlit Cloud) 시:

```bash
mkdir -p data/2026.MM.DD
cp -R "~/Downloads/PIKIT BETA DATA/2026.MM.DD/" data/
git add -f data/2026.MM.DD
git commit -m "data: 2026.MM.DD snapshot"
git push
```

push 직후 Streamlit Cloud 가 자동 재배포합니다.

스키마가 바뀌면 `pikit_analyzer/data_loader.py` 상단의 `*_COLS` 만 수정하면 됩니다.

---

## 6. 외부 시스템에서 끌어쓰기

`📤 밸런스 적용` 탭의 모든 다운로드는 같은 데이터에서 산출됩니다.

- 사람이 검토할 때 → **이 대시보드 UI**
- 자동화에 넣을 때 → **JSON 변경 명세** 또는 **게임 포맷 CSV** 다운로드
- 분석 가공이 필요하면 → `user_pnl.csv` / `item_economy.csv` / `block_economy.csv`

분석 모듈은 별도 import 도 가능합니다.

```python
from pikit_analyzer import (
    load_snapshot, recommend_item_changes,
    items_csv_with_recommendations, balance_config_json,
)
ds = load_snapshot("2026.05.06")
ds_range = ds.filter_by_date_range("2026-05-05", "2026-05-06")
ds_normal = ds_range.filter_by_game_mode("NORMAL")
print(items_csv_with_recommendations(ds_normal, target_roi=0.2))
```

---

## 7. 환경변수

| 변수 | 의미 |
| --- | --- |
| `PIKIT_DATA_ROOT` | 데이터 루트 폴더. 상대경로면 repo 루트 기준. 기본 `~/Downloads/PIKIT BETA DATA` |
| `PIKIT_PUBLIC` | `1` 이면 공개 배포 모드 — 원본 데이터 탭과 raw CSV 다운로드 비활성화 |

Streamlit Cloud 에서는 위 변수를 `.streamlit/secrets.toml` (TOML 형식) 으로 등록하면 자동으로 `os.environ` 에 노출됩니다.

```toml
PIKIT_PUBLIC = "1"
PIKIT_DATA_ROOT = "./data"
```
