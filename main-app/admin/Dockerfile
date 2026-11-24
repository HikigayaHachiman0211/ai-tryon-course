# ---- Stage 1: Build frontend ----
# node:22-alpine (reviewed 2026-08-12; linux/amd64 digest)
FROM node:22-alpine@sha256:76789712cd1ae89a1225eac9077010d68987a423588042dac30446f502f1858c AS frontend-build
WORKDIR /app/frontend

ARG VITE_ADMIN_API_BASE_URL=/
ARG VITE_ADMIN_API_URL

ENV VITE_ADMIN_API_BASE_URL=$VITE_ADMIN_API_BASE_URL
ENV VITE_ADMIN_API_URL=$VITE_ADMIN_API_URL

COPY admin/frontend/package.json admin/frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY admin/frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend ----
# python:3.11-slim (reviewed 2026-08-12; linux/amd64 digest)
FROM python:3.11-slim@sha256:78b39ef14d8e2b4d71f8dc304f1328c37df95fe0ef99477c2ae6bd3d03784553

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Install Python dependencies
COPY admin/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY admin/backend/ ./
COPY backend/app/i18n/catalog-translations/ ./catalog-translations/

# Copy database.json for product seed
COPY database.json ./database.json

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
