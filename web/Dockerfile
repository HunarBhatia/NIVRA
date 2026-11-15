# Nivra website image (section 21.8): Next.js standalone server.
# Build from the REPOSITORY ROOT:  docker build -f web/Dockerfile .
FROM node:22-slim AS build
# Where the website forwards /api/* - baked into the build by Next.js.
ARG NIVRA_API_URL=http://api:8000
ENV NIVRA_API_URL=$NIVRA_API_URL
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# scripts/sync-platforms.mjs (run by prebuild) reads ../../shared from
# /app/scripts, i.e. /shared.
COPY shared/platforms.json /shared/platforms.json
RUN npm run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN useradd --create-home --uid 10001 nivra
COPY --from=build --chown=nivra /app/.next/standalone ./
COPY --from=build --chown=nivra /app/.next/static ./.next/static
COPY --from=build --chown=nivra /app/public ./public
USER nivra
EXPOSE 3000
CMD ["node", "server.js"]
