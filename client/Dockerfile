# 빌드 컨텍스트는 client/ 디렉터리 (docker build -f client/Dockerfile client/).
# NEXT_PUBLIC_API_URL은 브라우저에 내려가는 클라이언트 번들에 그대로 박히는 값이라
# 런타임 환경변수로는 바꿀 수 없다 — 반드시 빌드 시점 ARG로 받아 builder 단계에서
# `next build`를 실행하기 전에 주입해야 한다.
#   docker build --build-arg NEXT_PUBLIC_API_URL=https://... -t codecourt-client .

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# standalone 출력물은 서버 코드+최소 node_modules만 담는다 — 정적 자산은 별도로 복사해야 한다.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

ENV PORT=3000
EXPOSE 3000

# JSON 배열(exec) 형태라 node가 PID 1이 되어 SIGTERM을 직접 받는다 — 서버 배포에서 겪은
# `sh -c` 래핑 문제(그레이스풀 셧다운 실패, exit 137)가 여기서는 애초에 발생하지 않는다.
CMD ["node", "server.js"]
