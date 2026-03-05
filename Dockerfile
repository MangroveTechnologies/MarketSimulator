# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY experiment_ui/package.json experiment_ui/package-lock.json ./
RUN npm ci
COPY experiment_ui/ ./
RUN npm run build

# Stage 2: Runtime (extends MangroveAI base image)
FROM mangroveai-mangrove-app

# Copy built frontend assets from stage 1
COPY --from=frontend-build /experiment_ui_dist /app/MarketSimulator/experiment_ui_dist

# Copy experiment server code and scripts
COPY experiment_server/ /app/MarketSimulator/experiment_server/
COPY scripts/ /app/MarketSimulator/scripts/
COPY config/ /app/MarketSimulator/config/
COPY data/ohlcv/ /app/MarketSimulator/data/ohlcv/

WORKDIR /app/MarketSimulator
