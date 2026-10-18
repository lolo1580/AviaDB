FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Utilisateur applicatif non privilégié (UID/GID 1000, comme l'utilisateur
# courant sur l'hôte) : les images et sauvegardes ne sont plus créées en root.
RUN mkdir -p /app/data/uploads \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin app

# Par défaut, base SQLite et images vivent sous /app/data (volume monté).
ENV DATABASE_URL=sqlite:////app/data/aviadb.db \
    UPLOAD_DIR=/app/data/uploads

EXPOSE 8000

# Le point d'entrée rend la propriété du volume à l'utilisateur applicatif puis
# abandonne les privilèges avant de lancer la commande.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
