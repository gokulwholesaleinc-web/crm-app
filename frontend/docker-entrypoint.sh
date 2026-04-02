#!/bin/sh
# Determine the system DNS resolver for nginx
RESOLVER=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)
RESOLVER=${RESOLVER:-8.8.8.8}
export RESOLVER

# Substitute BACKEND_HOST, BACKEND_PORT, and RESOLVER in nginx config
envsubst '${BACKEND_HOST} ${BACKEND_PORT} ${RESOLVER}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/conf.d/default.conf.template
exec nginx -g 'daemon off;'
