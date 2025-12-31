FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Use German Debian mirror (faster for Egypt/Middle East)
RUN sed -i 's|deb.debian.org|ftp.de.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libv4l-dev \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy MRZ application code
COPY layer1_capture ./layer1_capture
COPY layer2_readjustment ./layer2_readjustment
COPY layer3_mrz ./layer3_mrz
COPY layer4_document_filling ./layer4_document_filling
COPY models ./models
COPY templates ./templates
COPY web ./web
COPY app.py ./
COPY error_handlers.py ./

# Create directories for outputs (new structure with Logs/)
RUN mkdir -p /app/Logs/captured_passports/captured_images \
    /app/Logs/captured_passports/captured_json \
    /app/Logs/filled_documents

EXPOSE 5000

# Run with gunicorn for production, use app.py for development
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--workers", "1", "--threads", "4", "--timeout", "120"]
