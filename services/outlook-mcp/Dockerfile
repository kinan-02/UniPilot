FROM python:3.12.8-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini ./

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

CMD ["python", "-m", "app.main"]
