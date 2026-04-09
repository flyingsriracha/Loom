FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY graph ./graph
COPY migration ./migration
COPY retrieval ./retrieval
COPY artifacts ./artifacts
COPY ingestion ./ingestion
COPY services ./services

CMD ["uvicorn", "services.app:app", "--host", "0.0.0.0", "--port", "8090"]
