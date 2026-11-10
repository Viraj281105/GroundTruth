# Web image (Next.js). Build context: repository root.
# NEXT_PUBLIC_* values are inlined at build time, so they are build args.
FROM node:20-alpine AS deps
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_DEMO_MODE=false
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY apps/web ./
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --chown=node:node --from=build /web/package.json /web/package-lock.json ./
COPY --chown=node:node --from=build /web/node_modules ./node_modules
COPY --chown=node:node --from=build /web/.next ./.next
COPY --chown=node:node --from=build /web/public ./public
# next.config.mjs imports security-headers.mjs; both must be in the image or `next start` exits.
COPY --chown=node:node --from=build /web/next.config.mjs /web/security-headers.mjs ./
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
