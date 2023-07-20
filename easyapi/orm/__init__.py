import os

import django

DJANGO_SETTINGS_MODULE = os.getenv('DJANGO_SETTINGS_MODULE')
if not DJANGO_SETTINGS_MODULE:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.settings')

django.setup()
