"""Celery app. Run a worker with:  celery -A cloudplat worker -l info"""
import os

from celery import Celery

os.environ.setdefault( 'DJANGO_SETTINGS_MODULE', 'cloudplat.settings' )

app = Celery( 'cloudplat' )
app.config_from_object( 'django.conf:settings', namespace = 'CELERY' )
app.autodiscover_tasks()
