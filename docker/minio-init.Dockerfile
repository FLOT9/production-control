FROM python:3.11-alpine

RUN pip install --no-cache-dir minio==7.2.20

COPY scripts/init_minio.py /app/init_minio.py

CMD ["python", "/app/init_minio.py"]
