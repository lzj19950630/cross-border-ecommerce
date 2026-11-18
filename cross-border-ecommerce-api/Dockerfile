FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY . /app
RUN pip install --no-cache-dir -r cross-border-ecommerce-api/requirements.txt

EXPOSE 8000
VOLUME ["/data"]

CMD ["python", "-m", "runtime", "serve", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--checkpointer", "sqlite", \
     "--db", "/data/runtime.db", \
     "--checkpoint-db", "/data/checkpoints.db"]
