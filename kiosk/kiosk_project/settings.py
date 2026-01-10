import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

DEBUG = os.environ.get('DEBUG', '0').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = ['*']

# Trusted origins for CSRF (add external domains here)
CSRF_TRUSTED_ORIGINS = [
    'https://saddevsatator.qzz.io',
    'https://*.saddevastator.qzz.io',
]

# Trust proxy headers from Nginx/Cloudflare
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'kiosk',
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

ROOT_URLCONF = 'kiosk_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'kiosk.context_processors.kiosk_language',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'kiosk_project.wsgi.application'

# SQLite database for kiosk sessions and local data
# Use /app/data path if it exists (Docker), otherwise use BASE_DIR
import os as _os
_db_path = Path('/app/data/db.sqlite3') if _os.path.isdir('/app/data') else BASE_DIR / 'db.sqlite3'

# Check if frontdesk database is configured
_use_frontdesk = bool(os.environ.get('FRONTDESK_DB_PASSWORD'))

if _use_frontdesk:
    # Use frontdesk PostgreSQL for reservations, SQLite for sessions
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _db_path,
        },
        'frontdesk': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('FRONTDESK_DB', 'frontdesk'),
            'USER': os.environ.get('FRONTDESK_DB_USER', 'frontdesk'),
            'PASSWORD': os.environ.get('FRONTDESK_DB_PASSWORD', ''),
            'HOST': os.environ.get('FRONTDESK_DB_HOST', 'postgres-frontdesk'),
            'PORT': os.environ.get('FRONTDESK_DB_PORT', '5432'),
            'OPTIONS': {
                'options': '-c search_path=public',
            },
        }
    }
else:
    # SQLite only (development/fallback)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _db_path,
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
# Where `collectstatic` will collect files for production/static serving
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files (uploaded passport scans, filled documents)
MEDIA_URL = '/media/'
_media_path = '/app/media' if _os.path.isdir('/app/media') else os.path.join(BASE_DIR, 'media')
MEDIA_ROOT = _media_path

# WhiteNoise: serve static files without caching manifest (simpler, avoids stale cache issues)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# WhiteNoise: ensure JSON files are served with correct content type
WHITENOISE_MIMETYPES = {
    '.json': 'application/json',
}

# WhiteNoise: don't skip any static files
WHITENOISE_SKIP_COMPRESS_EXTENSIONS = []

# WhiteNoise: Add headers to prevent Cloudflare caching stale files
WHITENOISE_ADD_HEADERS_FUNCTION = None  # Use default headers

# CORS settings for Cloudflare/proxy compatibility
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['Content-Type', 'Content-Length']

# Use database-backed sessions for reliability (persists across container restarts)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Session cookie settings for kiosk reliability
SESSION_COOKIE_NAME = 'kiosk_session'
SESSION_COOKIE_AGE = 14400  # 4 hours for kiosk sessions (guests may take time)
SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session expiry on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session alive even if browser closes

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
