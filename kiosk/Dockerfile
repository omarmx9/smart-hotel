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
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy only the project files we need to ensure kiosk is complete inside the image
COPY manage.py ./
COPY kiosk_project ./kiosk_project
COPY kiosk ./kiosk
COPY templates ./templates
COPY static ./static

# Create directories for database and media
RUN mkdir -p /app/data /app/media/temp_scans /app/media/filled_documents

ENV DJANGO_SETTINGS_MODULE=kiosk_project.settings

# Collect static (best-effort)
RUN python manage.py collectstatic --noinput || true

# Run migrations at startup via entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "kiosk_project.wsgi:application", "--workers", "3"]
