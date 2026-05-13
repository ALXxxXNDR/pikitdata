# Vault — 멀티 프로젝트 지갑 대시보드

Next.js 15 + Tailwind v4 로 만든 Soneium 운영 지갑 모니터링 대시보드.

- 프로젝트: **PIKIT**, **Press A** (주소 등록 대기), **Pnyx** (coming soon)
- 데이터: Soneium Blockscout REST + JSON-RPC (Tenderly 우선)
- 알림: Vercel Cron → `/api/alert` → Resend 메일
- 디자인: warm off-white (`#F4F3EE`) + ink (`#0E0E0C`) + indigo accent (`#3B5BFD`)

## 로컬 개발

```bash
cd vault-web
npm install
cp .env.example .env.local   # 키 채우기
npm run dev
```

브라우저: <http://localhost:3000>

## Vercel 배포 (5분)

### 1) GitHub 에 push

이미 push 되어 있음. Vercel 은 GitHub repo 의 `vault-web/` 폴더만 본다.

### 2) Vercel 에서 Import

1. <https://vercel.com/new> → GitHub 의 `pikitdata` repo 선택
2. **Root Directory** → `vault-web` 지정 (중요!)
3. Framework: `Next.js` (자동 감지)
4. **Build Command** / **Output Directory**: 기본값 그대로

### 3) Environment Variables 설정

Vercel Dashboard → Project → Settings → Environment Variables 에서:

| 키 | 값 | 필수 |
|---|---|---|
| `TENDERLY_RPC_URL` | `wss://soneium.gateway.tenderly.co/...` | 권장 |
| `RESEND_API_KEY` | `re_...` (resend.com 가입 후 발급) | 메일 발송 시 |
| `RESEND_FROM` | `Vault Alert <onboarding@resend.dev>` | 메일 발송 시 |
| `ALERT_EMAIL_TO` | `alex@depsell.io` | 메일 발송 시 |
| `ALERT_COOLDOWN_HOURS` | `1` | 선택 |
| `CRON_SECRET` | 랜덤 문자열 | 권장 (cron 보호) |
| `NEXT_PUBLIC_BASE_URL` | `https://<your-vault>.vercel.app` | 메일 본문 링크용 |

### 4) Cron 활성화 확인

`vercel.json` 의 `crons` 항목이 자동 등록됨:

```json
{
  "crons": [{ "path": "/api/alert", "schedule": "0 * * * *" }]
}
```

기본은 **매 시간 정각** (Hobby 플랜 최대 빈도). 더 짧게 (예: 10분마다) 하려면 Vercel Pro 가 필요.

대안: <https://cron-job.org> 같은 외부 cron 서비스로 더 짧은 주기 호출:

```
GET https://<your-vault>.vercel.app/api/alert?secret=<CRON_SECRET>
```

### 5) 도메인 (선택)

Vercel → Settings → Domains 에서 커스텀 도메인 연결.

## 라우팅

| URL | 화면 |
|---|---|
| `/` | 기본 (PIKIT 개요) |
| `/?project=pikit` | PIKIT 프로젝트 개요 |
| `/?project=press_a` | Press A (주소 미설정 안내) |
| `/?project=pnyx` | Coming soon |
| `/?project=pikit&wallet=reward_vault` | 리워드 Vault 상세 |
| `/api/alert` | 잔고 체크 (cron + 수동) |
| `/api/alert?force=1` | 쿨다운 무시 강제 체크 |

## Press A 주소 등록

`lib/projects.ts` 의 `press_a.wallets[]` 에 실주소 채우고 push 하면 자동 배포.

```typescript
{
  key: "revenue",
  address: "0x...",  // ← 여기
  ...
}
```

## 폴더 구조

```
vault-web/
├── app/
│   ├── layout.tsx        — 폰트 + 글로벌 CSS
│   ├── page.tsx          — 메인 (서버 컴포넌트, 데이터 fetch)
│   ├── globals.css       — Tailwind v4 + 테마 토큰
│   └── api/alert/route.ts — 알림 cron 엔드포인트
├── components/
│   ├── topbar.tsx
│   ├── project-switcher.tsx   (client — 드롭다운)
│   ├── hero-total.tsx + sparkline.tsx
│   ├── allocation-card.tsx
│   ├── wallets-table.tsx
│   ├── assets-list.tsx
│   ├── activity-list.tsx
│   ├── wallet-detail.tsx
│   └── coming-soon.tsx
├── lib/
│   ├── types.ts
│   ├── projects.ts            — 프로젝트/지갑 설정
│   ├── soneium.ts             — Blockscout + RPC + 분석 헬퍼
│   └── alert.ts               — 임계 체크 + Resend
├── vercel.json                — cron 설정
├── package.json
├── next.config.mjs
├── tsconfig.json
└── .env.example
```
