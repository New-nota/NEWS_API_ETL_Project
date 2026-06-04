FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash etluser \
    && mkdir -p /app/data/raw /app/data/clean \
    && chown -R etluser:etluser /app

USER etluser

CMD ["python", "main.py", "--worker", "--bootstrap"]
