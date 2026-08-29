# ===== 构建阶段 =====
FROM node:22-alpine AS builder

WORKDIR /app

# 安装 pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# 复制依赖文件
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY postcss.config.js tailwind.config.js vite.config.ts tsconfig.json tsconfig.app.json ./

# 安装依赖
RUN pnpm install --frozen-lockfile

# 复制源码
COPY src ./src
COPY index.html ./

# 构建（API 通过同域 nginx 代理，baseURL 设为 /api/v1）
ENV VITE_API_BASE_URL=/api/v1
RUN pnpm build

# ===== 运行阶段：仅保留构建产物 =====
FROM alpine:latest
COPY --from=builder /app/dist /dist
CMD ["/bin/true"]