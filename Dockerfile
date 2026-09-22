FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 HARBORLIGHT_DATA_DIR=/app/var
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home harborlight && mkdir -p /app/var && chown -R harborlight:harborlight /app
COPY --chown=harborlight:harborlight . .
USER harborlight
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:'+__import__('os').environ.get('PORT','8000')+'/api/health',timeout=3)"
CMD ["python", "bootstrap.py"]
