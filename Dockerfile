FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --uid 10001 --create-home app && mkdir -p /data/uploads /app/instance && chown -R app:app /data /app/instance
USER app
EXPOSE 5000
CMD ["sh", "-c", "python -m flask --app backend:create_app db upgrade && exec gunicorn --config gunicorn.conf.py 'backend:create_app()'"]
