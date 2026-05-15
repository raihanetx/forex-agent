FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

# HF_TOKEN is auto-injected by HuggingFace Spaces at runtime
# Do NOT set ENV HF_TOKEN here — it would override the injected value
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "--timeout", "120", "app:app"]
