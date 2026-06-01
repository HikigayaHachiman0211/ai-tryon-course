FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

ARG VITE_API_BASE_URL=/
ARG VITE_TRYON_BASE_URL
ARG VITE_ADMIN_BASE_URL

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TRYON_BASE_URL=$VITE_TRYON_BASE_URL
ENV VITE_ADMIN_BASE_URL=$VITE_ADMIN_BASE_URL

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PORT=8080

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend
COPY database.json /app/database.json
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
