# 빌드 컨텍스트는 저장소 루트여야 한다 (rules.yaml이 server/ 밖, 저장소 루트에 있고,
# app/config.py가 컨테이너 안에서도 로컬과 동일한 상대 위치로 rules.yaml을 찾기 때문).
#   docker build -f server/Dockerfile -t codecourt-server .
FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# 저장소 루트의 법전 원본. app/config.py의 BASE_DIR 계산(app/config.py -> app -> server -> 여기)과
# 반드시 같은 상대 위치를 유지해야 한다.
COPY rules.yaml rules.yaml
COPY server/ server/

WORKDIR /app/server
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# 로컬 docker run 기본값. 실제 배포(Render 등)에서는 render.yaml의 dockerCommand가
# 이 CMD를 덮어써서 web/worker 역할과 마이그레이션 실행을 각각 지정한다.
# exec를 꼭 붙일 것: 안 붙이면 sh(PID 1)가 SIGTERM을 자식 프로세스로 넘기지 않아
# docker stop이 그레이스풀 종료 없이 타임아웃 후 강제 SIGKILL(exit 137)로 끝난다 —
# RUN_WORKER_IN_APP=true일 때 워커 태스크를 깔끔히 취소하는 lifespan 로직이 아예 실행되지 않음.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
