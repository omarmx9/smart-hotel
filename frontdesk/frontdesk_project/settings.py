"""
Django settings for Smart Hotel Front Desk Application
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

DEBUG = os.environ.get('DEBUG', '0').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Trusted origins for CSRF
CSRF_TRUSTED_ORIGINS = [
    'https://saddevsatator.qzz.io',
    'https://*.saddevastator.qzz.io',
]

# Trust proxy headers from Nginx/Cloudflare
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',
    'employees',
    'reservations',
    'documents',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'frontdesk_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'frontdesk_project.wsgi.application'

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
# Front Desk has its own PostgreSQL database for employee credentials
# Separate from the main dashboard database for security isolation

# Use environment variable for Docker PostgreSQL path
import os as _os
_db_path = Path('/app/data/db.sqlite3') if _os.path.isdir('/app/data') else BASE_DIR / 'db.sqlite3'

# Primary database for front desk (employee auth, reservations)
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('FRONTDESK_DB', 'frontdesk'),
            'USER': os.environ.get('FRONTDESK_DB_USER', 'frontdesk'),
            'PASSWORD': os.environ.get('FRONTDESK_DB_PASSWORD', ''),
            'HOST': os.environ.get('FRONTDESK_DB_HOST', 'postgres-frontdesk'),
            'PORT': os.environ.get('FRONTDESK_DB_PORT', '5432'),
        }
    }
else:
    # SQLite for local development
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _db_path,
        }
    }

# Custom user model for employees
AUTH_USER_MODEL = 'employees.Employee'

# Password hashing using Argon2 (most secure)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# SESSION CONFIGURATION
# =============================================================================
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'frontdesk_session'
SESSION_COOKIE_AGE = 28800  # 8 hours (work shift)
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = True

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('TIMEZONE', 'UTC')
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC FILES
# =============================================================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# =============================================================================
# MEDIA FILES
# =============================================================================
MEDIA_URL = '/media/'
_media_path = '/app/media' if _os.path.isdir('/app/media') else str(BASE_DIR / 'media')
MEDIA_ROOT = _media_path

# =============================================================================
# CRISPY FORMS
# =============================================================================
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# =============================================================================
# CORS SETTINGS
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# =============================================================================
# SECURITY SETTINGS (disable external resource headers for local-only assets)
# =============================================================================
# Remove COOP header issues by not setting it (handled by proxy if needed)
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# Content Security Policy - only allow local resources
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")
CSP_FONT_SRC = ("'self'",)
CSP_IMG_SRC = ("'self'", "data:")

# =============================================================================
# LOGIN/LOGOUT
# =============================================================================
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# KIOSK INTEGRATION
# =============================================================================
# URL to access kiosk media files (passports, documents)
KIOSK_MEDIA_URL = os.environ.get('KIOSK_MEDIA_URL', 'http://kiosk:8000/media/')
KIOSK_API_URL = os.environ.get('KIOSK_API_URL', 'http://kiosk:8000/api/')

# Dashboard API for room management
DASHBOARD_API_URL = os.environ.get('DASHBOARD_API_URL', 'http://dashboard:8000/api/')
DASHBOARD_API_TOKEN = os.environ.get('DASHBOARD_API_TOKEN', '')

# =============================================================================
# MQTT CONFIGURATION (for RFID card programming)
# =============================================================================
MQTT_HOST = os.environ.get('MQTT_HOST', 'mosquitto')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
MQTT_USER = os.environ.get('MQTT_USER', '')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', '')
