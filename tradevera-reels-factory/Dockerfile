FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p assets/broll assets/music assets/sfx inputs outputs assets/brand/fonts

EXPOSE 10000

CMD ["sh", "-c", "gunicorn --workers 1 --threads 2 --timeout 1800 --bind 0.0.0.0:${PORT} web_app:app"]
