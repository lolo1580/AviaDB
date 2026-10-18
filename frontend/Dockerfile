# Étape 1 — build du SPA
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

# Étape 2 — service statique via Nginx, avec proxy vers l'API
FROM nginx:1.27-alpine

# Le template est rendu au démarrage avec les variables d'environnement
# (entrée officielle nginx : /etc/nginx/templates/*.template -> conf.d/*.conf).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Valeur par défaut (réseau bridge Compose).
ENV BACKEND_URL=http://backend:8000

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
