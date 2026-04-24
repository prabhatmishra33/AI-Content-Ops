# ──── Stage 1: Dependencies ────
FROM node:22-alpine AS deps
WORKDIR /app
COPY ui/package.json ui/package-lock.json ./
RUN npm ci

# ──── Stage 2: Build ────
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY ui/ .
# Bake in the API URL at build time (Next.js requirement for NEXT_PUBLIC_ vars)
ARG NEXT_PUBLIC_API_BASE_URL=http://35.196.100.221/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

# ──── Stage 3: Runtime ────
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production

# Copy only what's needed for `next start`
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json

# Copy public dir if it exists (static assets)
COPY --from=build /app/public ./public

RUN addgroup -S appgroup && adduser -S appuser -G appgroup && chown -R appuser:appuser /app
USER appuser

EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
