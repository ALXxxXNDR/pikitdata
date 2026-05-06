# PIKIT 밸런스 대시보드 — Synology DS720+ / 일반 Docker 호스트용
#
# 이미지 크기: 최종 ~400MB (slim 기반)
# 빌드: docker build -t pikit-balance:latest .
# 실행: docker run -p 8501:8501 -v $(pwd)/data:/app/data:ro pikit-balance:latest

FROM python:3.11-slim

# 시스템 패키지 — pandas/pyarrow 가 필요로 하는 최소 라이브러리.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 비루트 사용자 (Synology 권장 — UID 1026 은 admin 그룹).
RUN groupadd -g 1026 pikit && useradd -u 1026 -g 1026 -m -s /bin/bash pikit

WORKDIR /app

# 의존성을 먼저 설치 — 코드 변경 시 캐시 재사용.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사 (data 폴더는 의도적으로 제외 — 볼륨으로 마운트).
COPY pikit_analyzer /app/pikit_analyzer
COPY app.py /app/app.py
COPY .streamlit /app/.streamlit

# Streamlit 기본값 — Container Manager에서 환경변수로 덮어쓸 수 있음.
ENV PYTHONUNBUFFERED=1 \
    PIKIT_DATA_ROOT=/app/data \
    PIKIT_PUBLIC=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHERUSAGESTATS=false

USER pikit

EXPOSE 8501

# 헬스체크 — Synology Container Manager가 컨테이너 상태를 감시할 때 사용.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
