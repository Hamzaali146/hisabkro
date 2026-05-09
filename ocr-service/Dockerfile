# OCR Service — Hugging Face Spaces uses port 7860 by convention.
FROM python:3.11-slim

# tesseract = the actual OCR engine; libgl1 = needed by Pillow on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# HF Spaces sets $PORT=7860; we honor it but also default for local docker-run.
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
