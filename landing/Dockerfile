FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
CMD sed -i "s/80/$PORT/g" /etc/nginx/conf.d/default.conf && nginx -g "daemon off;"
