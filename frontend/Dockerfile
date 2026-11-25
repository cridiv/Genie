FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_GENIE_AI_URL=http://102.209.46.116:8001
ARG NEXT_PUBLIC_ML_INFRA_URL=http://102.209.46.116:8000
ENV NEXT_PUBLIC_GENIE_AI_URL=$NEXT_PUBLIC_GENIE_AI_URL \
    NEXT_PUBLIC_ML_INFRA_URL=$NEXT_PUBLIC_ML_INFRA_URL

RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
