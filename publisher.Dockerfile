FROM python:3.11-slim
WORKDIR /app

# install deps as root
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# create non-root and switch
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# publisher scripts
COPY scripts/ ./scripts/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGG_URL=http://aggregator:8080/publish

CMD ["python", "scripts/publisher.py"]
