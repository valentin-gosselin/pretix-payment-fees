"""
Minimal Django settings for tests.
"""
import os

SECRET_KEY = 'test-secret-key-for-testing-only'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

USE_TZ = True
TIME_ZONE = 'UTC'

# Minimal configuration to avoid Django import errors
ROOT_URLCONF = []
MIDDLEWARE = []