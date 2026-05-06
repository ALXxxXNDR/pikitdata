# PIKIT 밸런스 대시보드

PIKIT 베타 데이터(곡괭이 가격·공격력·지속시간, 블록 보상·드롭률, 유저별 PNL)를
한 화면에서 보고, **단일 날짜 / 날짜 범위**로 슬라이스하고, 원하는 목표 ROI에 맞춘
**추천값을 게임이 바로 쓸 수 있는 CSV / JSON 으로 다운로드**할 수 있는 인터랙티브 툴입니다.

> 🌐 **공개 배포는 [DEPLOY.md](DEPLOY.md)** 참고 — `pikitdata.streamlit.app` 까지 5분 안에 가능.

## 1. 빠른 시작

```bash
cd /Users/moomi/Downloads/z03.Vibe_Coding/dataanal
./run.sh
```

`http://127.0.0.1:8501` 로 접속.

데이터 폴더는 사이드바의 **데이터 폴더** 입력칸에서 변경 가능
(기본값 `/Users/moomi/Downloads/PIKIT BETA DATA`).

## 2. 기간 모드 — 사이드바

세 가지 조회 모드를 지원합니다.

| 모드 | 설명 | 사용 시점 |
| --- | --- | --- |
| **단일 스냅샷** | 특정 일자 백업의 *누적* 전체 데이터 | 베타 시작부터 그 날까지의 누적 흐름이 궁금할 때 |
| **단일 날짜** | 가장 최근 스냅샷에서 *그 하루*의 트랜잭션만 | 특정 일자의 변화량(daily delta)이 궁금할 때 |
| **날짜 범위** | 가장 최근 스냅샷에서 *시작일~종료일* 사이 트랜잭션 | 주간/이벤트 단위 분석, 패치 전후 비교 |

가장 최근 스냅샷에는 누적 트랜잭션 로그가 모두 들어 있어,
한 파일에서 임의의 기간을 잘라 볼 수 있습니다.

## 3. 탭 구성

| 탭 | 내용 |
| --- | --- |
| 👤 유저 | 유저별 PNL 분포 / 세션 PNL / 정렬 가능한 표 (CSV 다운로드 가능) |
| ⛏️ 곡괭이 / TNT | 가격 vs 실측 ROI 산점도, 목표 ROI 슬라이더, 추천 가격 표 |
| 🪨 블록 | 설정 vs 실측 드롭률, HP-보상 산점도, 추천 보상 표 |
| 🧪 밸런스 시뮬레이터 | 가격/공격력/지속시간/HP/보상/드롭률 자유 편집 → 즉시 ROI 재계산 + 게임 포맷 CSV 다운로드 |
| 📤 밸런스 적용 (다운로드) | **추천값을 게임 포맷 그대로 받기**: `item.csv`, `block.csv`, JSON 변경 명세 |
| 📦 원본 데이터 | 12개 원본 테이블 그대로 열람·다운로드 |

## 4. 밸런스 적용 워크플로

`📤 밸런스 적용` 탭에서 한 번에 받을 수 있는 산출물:

1. **추천 적용 `item.csv` (게임 포맷)** — 헤더 없이 12 컬럼, 가격만 추천값으로 갈아치움.
   `/Users/moomi/Downloads/PIKIT BETA DATA/날짜/item.csv` 자리에 그대로 덮어씌울 수 있는 형식.
2. **추천 적용 `block.csv` (게임 포맷)** — 보상 컬럼만 추천값으로 갈아치움.
3. **변경 명세 JSON** — `현재값 → 추천값 + 사유 + 메트릭`이 정리된 JSON.
   설정 시스템(예: GitOps 기반 config) 에 그대로 PR 로 올릴 수 있는 형태.

또한 `🧪 밸런스 시뮬레이터` 에서는 운영자가 직접 편집한 값(추천 X)을
**시뮬 적용 CSV** 로 받을 수 있어, "이 가격으로 가자" 라고 결정한 뒤 바로 export 가능.

목표 ROI / 드롭률 허용 편차 슬라이더로 추천 강도를 조정합니다.

## 5. 핵심 지표 정의

| 지표 | 정의 |
| --- | --- |
| `block_reward` | 블록을 깨서 받은 총 크레딧 (`tx_type=BLOCK_REWARD`) |
| `item_spend` | 곡괭이/TNT 구매에 쓴 총 크레딧 (`tx_type=ITEM_PURCHASE`, 절댓값) |
| `pnl` | `block_reward − item_spend` |
| `roi` | `pnl ÷ item_spend` |
| `theoretical_roi` | 곡괭이를 100% 활용한다고 가정한 ROI: `(duration_s × attack ÷ E[HP]) × E[reward] − price) ÷ price` |
| `realized_roi` | 같은 게임 세션의 블록 보상을 그 게임의 아이템 구매 횟수에 비례 분배해 추정한 실측 ROI |
| `sink_ratio` | `total_item_spend ÷ total_block_reward`. 1보다 크면 시스템이 크레딧을 흡수 |

### 추천 로직

* **아이템**: `realized_roi`(데이터 충분, 구매 ≥ 5회)를 우선 사용, 없으면 `theoretical_roi`.
  `recommended_price = effective_reward_per_buy ÷ (1 + 목표ROI)`.
* **블록**: 같은 모드 평균 `reward_per_hp` 기준으로 ±15% 이상 벗어나면 보상 조정 제안.
  설정 드롭률 vs 실측 드롭률 편차가 ±1.5%p 를 넘으면 플래그.

## 6. 새 스냅샷 추가

`/Users/moomi/Downloads/PIKIT BETA DATA/2026.MM.DD/` 형식 폴더에 12개 CSV
(`block.csv` 등)를 그대로 넣으면 사이드바에 자동 추가됩니다. 스키마가 바뀌면
`pikit_analyzer/data_loader.py` 상단의 `*_COLS` 만 수정하면 됩니다.

## 7. 외부 시스템에서 끌어쓰기

`📤 밸런스 적용` 탭의 모든 다운로드는 동일한 데이터에서 산출됩니다.
다른 시스템에서 이 사이트의 분석 결과를 끌어다 쓰려면:

1. 사람이 검토할 때는 **이 대시보드 UI**.
2. 자동화에 넣을 때는 **JSON 변경 명세** 또는 **게임 포맷 CSV** 다운로드 → 운영 파이프라인.
3. 분석 가공이 필요하면 `user_pnl.csv` / `item_economy.csv` / `block_economy.csv` 다운로드 가능.

분석 모듈은 별도 임포트도 가능합니다.

```python
from pikit_analyzer import (
    load_snapshot, recommend_item_changes,
    items_csv_with_recommendations, balance_config_json,
)
ds = load_snapshot("2026.05.06")
ds_range = ds.filter_by_date_range("2026-05-05", "2026-05-06")
print(items_csv_with_recommendations(ds_range, target_roi=0.2))
```

## 8. 디렉터리

```
dataanal/
├── app.py                  # Streamlit 대시보드
├── pikit_analyzer/
│   ├── data_loader.py      # CSV → DataFrame, 날짜 범위 슬라이스
│   ├── metrics.py          # PNL · 블록/아이템 경제 · 세션 지표
│   ├── balance.py          # 추천 + What-if 시뮬레이터
│   └── exports.py          # 게임 포맷 CSV / JSON 명세 변환
├── requirements.txt
├── run.sh
└── README.md
```
