FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REGINTEL_HOST=0.0.0.0 \
    REGINTEL_DATA_DIR=/app/data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py index.html ./
COPY regintel ./regintel
COPY assets ./assets
COPY prototypes ./prototypes
COPY scripts ./scripts

EXPOSE 8082
CMD ["python", "server.py"]
