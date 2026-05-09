# Frontend (Gradio) as a Docker Space.
# We use Docker (not the Gradio SDK) so we control Python version and pip
# resolution explicitly — HF was defaulting Gradio SDK Spaces to Python 3.13,
# which breaks gradio 4.44.0 (audioop removed; HfFolder removed in newer
# huggingface_hub).
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
