FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

RUN cat > /etc/nginx/conf.d/default.conf.template << 'NGINX_EOF'
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
server {
    listen 80;
    listen [::]:80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied expired no-cache no-store private auth;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml application/javascript application/json;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' http://localhost:* https://*;" always;
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    resolver ${RESOLVER} valid=10s;
    set $backend_upstream http://${BACKEND_HOST}:${BACKEND_PORT};
    location /api {
        limit_req zone=api burst=20 nodelay;
        proxy_pass $backend_upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 90s;
        proxy_connect_timeout 10s;
    }
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache, must-revalidate" always;
    }
    location ~ /\. { deny all; access_log off; log_not_found off; }
    error_page 500 502 503 504 /50x.html;
    location = /50x.html { root /usr/share/nginx/html; }
}
NGINX_EOF

RUN cat > /docker-entrypoint.sh << 'ENTRY_EOF'
#!/bin/sh
RAW_RESOLVER=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)
if echo "$RAW_RESOLVER" | grep -q ':'; then
  RESOLVER="[$RAW_RESOLVER]"
else
  RESOLVER="${RAW_RESOLVER:-8.8.8.8}"
fi
export RESOLVER
envsubst '${BACKEND_HOST} ${BACKEND_PORT} ${RESOLVER}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/conf.d/default.conf.template
exec nginx -g 'daemon off;'
ENTRY_EOF
RUN chmod +x /docker-entrypoint.sh

ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000
EXPOSE 80
CMD ["/docker-entrypoint.sh"]
