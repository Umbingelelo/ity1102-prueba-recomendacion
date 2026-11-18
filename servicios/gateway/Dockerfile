# La configuración va DENTRO de la imagen (EP2, regla 3: sin bind mounts).
#   docker build -t gateway servicios/gateway
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
# nginx -t al construir: una configuración rota hace fallar el build en el pipeline, no la defensa
RUN nginx -t
EXPOSE 8080
