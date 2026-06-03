FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY services/ingestion/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --default-timeout=100 --prefer-binary --no-cache-dir -r /tmp/requirements.txt

COPY services/events /app/events
COPY services/ingestion/main.py /app/main.py

CMD ["python", "main.py"]
