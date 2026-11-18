# El front son archivos estáticos servidos por nginx. No publica puertos: se llega por el gateway.
#   docker build -t front servicios/front
FROM nginx:1.27-alpine
COPY index.html dashboard.html app.js estilo.css /usr/share/nginx/html/
