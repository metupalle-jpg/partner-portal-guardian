FROM python:3.12-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent package
COPY . /app/partner_portal_guardian/
COPY main.py /app/main.py

# Env vars
ENV GOOGLE_CLOUD_PROJECT=dave-487819
ENV GOOGLE_CLOUD_LOCATION=me-central1
ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE
ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "1"]
