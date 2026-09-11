"""
Campus Lost and Found Portal – Django Settings
"""

from pathlib import Path
import os
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() in ('1', 'true', 'yes')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '').strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-development-only-change-before-production'
    else:
        raise RuntimeError('DJANGO_SECRET_KEY must be configured in production.')

ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get(
        'DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1'
    ).split(',') if host.strip()
]

BASE_INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'lost_and_found',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'campus_lnf.urls'

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
                'lost_and_found.context_processors.notification_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'campus_lnf.wsgi.application'

MONGODB_URI = os.environ.get('MONGODB_URI', '').strip()
MONGODB_DB_NAME = os.environ.get('MONGODB_DB_NAME', 'campus_lnf').strip()


def database_config():
    """Choose MongoDB, PostgreSQL, or local SQLite from environment settings."""
    if MONGODB_URI:
        return {
            'ENGINE': 'django_mongodb_backend',
            'HOST': MONGODB_URI,
            'NAME': MONGODB_DB_NAME,
        }

    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        if not DEBUG:
            raise RuntimeError(
                'Configure DATABASE_URL or MONGODB_URI for the shared production database.'
            )
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }

    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('DATABASE_URL must use a postgresql:// or postgres:// URL.')

    query = parse_qs(parsed.query)
    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': 600,
    }
    if query.get('sslmode'):
        config['OPTIONS'] = {'sslmode': query['sslmode'][0]}
    return config


DATABASES = {'default': database_config()}

if not DEBUG and not os.environ.get('DJANGO_ALLOWED_HOSTS', '').strip():
    raise RuntimeError('DJANGO_ALLOWED_HOSTS must be configured in production.')

if MONGODB_URI:
    # Django's contrib models must use MongoDB ObjectIds as their primary keys.
    INSTALLED_APPS = [
        'campus_lnf.apps.MongoAdminConfig',
        'campus_lnf.apps.MongoAuthConfig',
        'campus_lnf.apps.MongoContentTypesConfig',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'lost_and_found',
        'django_mongodb_backend',
    ]
else:
    INSTALLED_APPS = BASE_INSTALLED_APPS

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
# Display all report and claim timestamps in the campus's local timezone.
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'lost_and_found' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if MONGODB_URI:
    # ImageField and avatar uploads are stored in MongoDB GridFS rather than
    # the server disk, so every deployed app instance sees the same files.
    STORAGES = {
        'default': {'BACKEND': 'lost_and_found.storage.GridFSStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

DEFAULT_AUTO_FIELD = (
    'django_mongodb_backend.fields.ObjectIdAutoField'
    if MONGODB_URI else 'django.db.models.BigAutoField'
)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True

# Auth redirects
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# ── College email domain whitelist ──────────────────────────────────────────
# Add all domains your campus uses. Checked in the signup form validator.
ALLOWED_EMAIL_DOMAINS = ['college.edu', 'university.edu', 'campus.ac.in']

# Web Push is optional locally, but required for notifications outside the app.
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '').strip()
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@example.com').strip()
