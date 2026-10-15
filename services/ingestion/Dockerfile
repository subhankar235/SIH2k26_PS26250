FROM node:24.19.0-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY src ./src
COPY scripts ./scripts
COPY docs ./docs
COPY dashboard ./dashboard
RUN npm run setup && mkdir -p var && chown node:node var
USER node
ENV HOST=0.0.0.0
EXPOSE 3100
CMD ["node", "src/server.js"]
