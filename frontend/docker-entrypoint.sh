#!/bin/sh
# Substitute only BACKEND_HOST and BACKEND_PORT in nginx config
envsubst '${BACKEND_HOST} ${BACKEND_PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/conf.d/default.conf.template
exec nginx -g 'daemon off;'
