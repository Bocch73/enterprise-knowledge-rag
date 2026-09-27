# syntax=docker/dockerfile:1.7

FROM node:26.10.0-alpine3.23 AS frontend-builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.28.3-alpine AS runtime

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-builder --chown=101:101 /build/dist /usr/share/nginx/html

USER 101:101
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
