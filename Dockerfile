# Cloud Run build only. Build context is the REPO ROOT (not backend/), unlike
# backend/Dockerfile which docker-compose.yml uses for LOCAL — that one relies
# on docker-compose.yml's volume mount (`./classifier:/classifier:ro`) to get
# the ONNX model in, which Cloud Run has no equivalent of. This file bakes the
# model into the image instead, which is the only option for a Cloud Run
# --source build. See docs/BUILD_LOG.md "Cloud deploy" for why two Dockerfiles
# exist rather than one.
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY classifier/best-model/ ./classifier/best-model/

# Overrides config.py's local-dev defaults (which are "../classifier/...",
# correct when cwd=backend/ and classifier/ is a sibling directory -- not
# correct here, where the model is copied to a subdirectory of /app instead).
ENV CNN_MODEL_PATH=./classifier/best-model/huluhilir_l1.onnx
ENV CNN_LABELS_PATH=./classifier/best-model/labels.txt
ENV CNN_PREPROCESS_PATH=./classifier/best-model/preprocess.json

EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
