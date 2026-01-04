"""
Django settings for Smart Hotel Dashboard
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['*']
# Trusted origins for CSRF (add external domains here)
CSRF_TRUSTED_ORIGINS = [
    'https://saddevsatator.qzz.io',
    'https://*.saddevastator.qzz.io',
]

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'mozilla_django_oidc',
    'accounts',
    'rooms',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'mozilla_django_oidc.middleware.SessionRefresh',
]

ROOT_URLCONF = 'smart_hotel.urls'

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

WSGI_APPLICATION = 'smart_hotel.wsgi.application'
ASGI_APPLICATION = 'smart_hotel.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Database - use PostgreSQL in Docker, SQLite locally
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'smarthotel'),
            'USER': os.environ.get('POSTGRES_USER', 'smarthotel'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'smarthotel'),
            'HOST': os.environ.get('POSTGRES_HOST', 'postgres'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'accounts.User'

# ==============================================================================
# Session Configuration
# ==============================================================================
# Session cookie age in seconds (default 7 days for hotel guests)
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', 604800))

# Session engine - use database for persistence
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Session cookie settings
SESSION_COOKIE_SECURE = not DEBUG  # Use secure cookies in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Save session on every request to extend lifetime
SESSION_SAVE_EVERY_REQUEST = True

# Authentication backends - Authentik OIDC + Django ModelBackend fallback
AUTHENTICATION_BACKENDS = [
    'accounts.oidc_backend.AuthentikOIDCBackend',
    'django.contrib.auth.backends.ModelBackend',  # Fallback for admin access
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# InfluxDB Configuration
INFLUX_URL = os.environ.get('INFLUX_URL', 'http://influxdb:8086')
INFLUX_TOKEN = os.environ.get('INFLUX_TOKEN', 'admin-token')
INFLUX_ORG = os.environ.get('INFLUX_ORG', 'org')
INFLUX_BUCKET = os.environ.get('INFLUX_BUCKET', 'bucket')

# MQTT Configuration
MQTT_BROKER = os.environ.get('MQTT_BROKER', 'mosquitto')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Node-RED SMS Gateway
NODERED_URL = os.environ.get('NODERED_URL', 'http://nodered:1880')

# Guest account settings
GUEST_ACCOUNT_EXPIRY_HOURS = 24

# ==============================================================================
# Authentik OIDC Configuration
# ==============================================================================

# Authentik server URL (base URL without trailing slash)
AUTHENTIK_URL = os.environ.get('AUTHENTIK_URL', 'https://auth.example.com')

# OIDC Endpoints - use explicit endpoints from environment or fall back to constructed URLs
# This allows working even when discovery endpoint is unavailable
OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ.get(
    'OIDC_OP_AUTHORIZATION_ENDPOINT', 
    f"{AUTHENTIK_URL}/application/o/authorize/"
)
OIDC_OP_TOKEN_ENDPOINT = os.environ.get(
    'OIDC_OP_TOKEN_ENDPOINT',
    f"{AUTHENTIK_URL}/application/o/token/"
)
OIDC_OP_USER_ENDPOINT = os.environ.get(
    'OIDC_OP_USER_ENDPOINT',
    f"{AUTHENTIK_URL}/application/o/userinfo/"
)
OIDC_OP_JWKS_ENDPOINT = os.environ.get(
    'OIDC_OP_JWKS_ENDPOINT',
    f"{AUTHENTIK_URL}/application/o/smart-hotel/jwks/"
)

# Client credentials from Authentik OAuth2/OIDC Provider
OIDC_RP_CLIENT_ID = os.environ.get('OIDC_RP_CLIENT_ID', os.environ.get('OIDC_CLIENT_ID', 'smart-hotel'))
OIDC_RP_CLIENT_SECRET = os.environ.get('OIDC_RP_CLIENT_SECRET', os.environ.get('OIDC_CLIENT_SECRET', ''))

# Signing algorithm (Authentik uses RS256 by default)
OIDC_RP_SIGN_ALGO = os.environ.get('OIDC_SIGN_ALGO', 'RS256')

# Scopes to request - include 'groups' for role mapping
OIDC_RP_SCOPES = 'openid email profile groups'

# Store OIDC tokens in session for logout
OIDC_STORE_ID_TOKEN = True

# Logout configuration
OIDC_OP_LOGOUT_ENDPOINT = f"{AUTHENTIK_URL}/application/o/smart-hotel/end-session/"
OIDC_OP_LOGOUT_URL_METHOD = 'accounts.oidc_logout.get_logout_url'

# Redirect URIs (update these for your domain)
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Use OIDC login as default (now at root /oidc/)
LOGIN_URL = '/oidc/authenticate/'

# Session settings for OIDC
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = int(os.environ.get('OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS', 900))  # Default: 15 minutes

# Custom claims for user attributes
OIDC_CLAIM_USERNAME = 'preferred_username'
OIDC_CLAIM_EMAIL = 'email'
OIDC_CLAIM_GROUPS = 'groups'

# Group mappings for roles (customize these to match your Authentik groups)
OIDC_ADMIN_GROUPS = os.environ.get('OIDC_ADMIN_GROUPS', 'smart-hotel-admins,admins').split(',')
OIDC_MONITOR_GROUPS = os.environ.get('OIDC_MONITOR_GROUPS', 'smart-hotel-monitors,monitors').split(',')
OIDC_GUEST_GROUPS = os.environ.get('OIDC_GUEST_GROUPS', 'smart-hotel-guests,guests').split(',')

# Allow creating new users on first OIDC login
OIDC_CREATE_USER = True

# Verify SSL in production (set to False only for development with self-signed certs)
OIDC_VERIFY_SSL = os.environ.get('OIDC_VERIFY_SSL', 'True').lower() == 'true'
