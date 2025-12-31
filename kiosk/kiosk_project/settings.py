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

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'kiosk',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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

# SQLite database for test deployment
# Use /app/data path if it exists (Docker), otherwise use BASE_DIR
import os as _os
_db_path = Path('/app/data/db.sqlite3') if _os.path.isdir('/app/data') else BASE_DIR / 'db.sqlite3'
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

# WhiteNoise: enable compressed files and caching for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Use signed cookie sessions so the app does not require DB-backed sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
