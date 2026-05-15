FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config + entrypoint from the build stage rather than the build
# context so Railway's layer cache can't serve stale versions of these files
# (the historical reason these were inlined as heredocs — see commit b3c74db6).
# The build stage already has the full frontend/ tree, so this is free.
COPY --from=build /app/nginx.conf /etc/nginx/conf.d/default.conf.template
COPY --from=build /app/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000
EXPOSE 80
CMD ["/docker-entrypoint.sh"]
