FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Par défaut, base SQLite et images vivent sous /app/data (volume monté).
ENV DATABASE_URL=sqlite:////app/data/aviadb.db \
    UPLOAD_DIR=/app/data/uploads

RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
