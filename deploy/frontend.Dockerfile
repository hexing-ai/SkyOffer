FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend ./
ARG BACKEND_URL=http://backend:8001
ARG DEPLOYMENT_VERSION=local
ENV BACKEND_URL=${BACKEND_URL} \
    DEPLOYMENT_VERSION=${DEPLOYMENT_VERSION}
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3200
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
USER nextjs
EXPOSE 3200
CMD ["node", "server.js"]
