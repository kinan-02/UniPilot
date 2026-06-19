FROM python:3.12.8-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/curated ./data/curated

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

CMD ["sleep", "infinity"]
