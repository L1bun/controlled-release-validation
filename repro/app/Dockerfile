FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# /data has to exist and belong to the service user in the image, otherwise a
# fresh named volume gets mounted root-owned and the readiness check fails.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data \
    && chown app:app /data

USER 10001
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "app:app"]
