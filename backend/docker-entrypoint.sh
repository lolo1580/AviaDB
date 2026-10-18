#!/bin/sh
# Point d'entrée du conteneur backend.
#
# Le volume monté sur /app/data peut appartenir à root (créé par une exécution
# précédente du conteneur en root). On lui rend la propriété de l'utilisateur
# applicatif, puis on abandonne les privilèges : les fichiers créés sur l'hôte
# appartiennent ainsi à l'utilisateur courant (UID 1000), plus à root.
set -e

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

if [ "$(id -u)" = "0" ]; then
  chown -R "$APP_UID:$APP_GID" /app/data 2>/dev/null || true
  if [ -d /app/backups ]; then
    chown -R "$APP_UID:$APP_GID" /app/backups 2>/dev/null || true
  fi
  exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups "$@"
fi

exec "$@"
