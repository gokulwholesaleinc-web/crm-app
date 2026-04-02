# Development stage (used by docker-compose for local dev)
FROM node:20-alpine AS development

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage (default - used by Railway)
FROM nginx:alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf docker-entrypoint.sh /tmp/docker-config/
RUN cp /tmp/docker-config/nginx.conf /etc/nginx/conf.d/default.conf.template \
    && cp /tmp/docker-config/docker-entrypoint.sh /docker-entrypoint-custom.sh \
    && chmod +x /docker-entrypoint-custom.sh \
    && rm -rf /tmp/docker-config

ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000

EXPOSE 80

CMD ["/docker-entrypoint-custom.sh"]
