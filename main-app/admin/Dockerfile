# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend

ARG VITE_ADMIN_API_BASE_URL=/

ENV VITE_ADMIN_API_BASE_URL=$VITE_ADMIN_API_BASE_URL

COPY admin/frontend/package.json admin/frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY admin/frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend ----
FROM python:3.11-slim

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

# Copy database.json for product seed
COPY database.json ./database.json

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
