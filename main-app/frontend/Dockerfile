FROM node:22-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL
ARG VITE_TRYON_BASE_URL
ARG VITE_ADMIN_BASE_URL

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TRYON_BASE_URL=$VITE_TRYON_BASE_URL
ENV VITE_ADMIN_BASE_URL=$VITE_ADMIN_BASE_URL

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . ./
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
