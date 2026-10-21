FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY requirements-embeddings.txt .
ARG INSTALL_EMBEDDINGS=false
RUN if [ "$INSTALL_EMBEDDINGS" = "true" ]; then pip install --no-cache-dir -r requirements-embeddings.txt; else pip install --no-cache-dir -r requirements.txt; fi

COPY . .

ENV AUDITMIND_MODEL_CACHE=/models HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --uid 10001 --create-home auditmind && mkdir -p /models /app/uploads && chown -R auditmind:auditmind /app /models
USER auditmind

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
