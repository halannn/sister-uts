FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# install deps as root
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# create non-root and switch
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# app src
COPY src/ ./src/

EXPOSE 8080
CMD ["python", "-m", "src.main"]
