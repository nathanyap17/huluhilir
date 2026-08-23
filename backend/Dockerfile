FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Cloud Run injects $PORT (default 8080) and requires the container to listen
# on it; docker-compose.yml runs this same image locally without PORT set, so
# it falls back to 8000 to match the compose port mapping. Shell form (not
# exec form) so ${PORT} actually expands.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
