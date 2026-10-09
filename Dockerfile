FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    GAME_MODE=live \
    GROQ_MODEL=openai/gpt-oss-120b

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt \
    && useradd --uid 10001 --create-home game
RUN mkdir -p /app/.data && chown 10001:10001 /app/.data

COPY *.py ./
COPY static/ ./static/

USER 10001:10001
VOLUME ["/app/.data"]
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/health', timeout=3)"
CMD ["python", "app.py"]
