# Dockerfile for oratoria-backend server
# Optimized multi-stage build for Docker deployment

# Build stage
FROM oven/bun:1 AS builder

WORKDIR /app

# Copy package files
COPY package.json bun.lock* ./
COPY apps/server/package.json ./apps/server/
COPY packages/db/package.json ./packages/db/

# Install dependencies
RUN bun install --frozen-lockfile

# Copy source code
COPY . .

# Build the application
RUN bun run build --filter=@oratoria-backend/server

# Production stage
FROM oven/bun:1-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Copy built application
COPY --from=builder /app/apps/server/dist ./dist
COPY --from=builder /app/apps/server/package.json ./

# Install production dependencies only
RUN bun install --production --frozen-lockfile

EXPOSE 3000

CMD ["bun", "run", "dist/index.js"]
