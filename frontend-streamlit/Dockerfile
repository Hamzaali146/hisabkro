# Streamlit frontend as a Docker Space — same pattern as the backends so we
# control Python explicitly and avoid HF's SDK auto-upgrades.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PORT=7860
EXPOSE 7860

# --server.address=0.0.0.0  → bind to all interfaces (HF requires this)
# --server.headless=true    → suppress the "open browser" prompt + telemetry banner
# --server.enableXsrfProtection=false → needed because the embed iframe spans HF's domain
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --server.enableXsrfProtection=false"]
