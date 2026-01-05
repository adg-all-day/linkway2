FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies for PostgreSQL client and building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/production.txt /app/requirements/production.txt
COPY requirements/base.txt /app/requirements/base.txt
RUN pip install --no-cache-dir -r requirements/production.txt

# Copy project code
COPY . /app

ENV DJANGO_SETTINGS_MODULE=config.settings.production

# Collect static files at build time (will go to STATIC_ROOT)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

