"""Celery app. Run a worker with:  celery -A config worker -l info"""
import os

from celery import Celery

os.environ.setdefault( 'DJANGO_SETTINGS_MODULE', 'config.settings' )

app = Celery( '3dpgis' )
app.config_from_object( 'django.conf:settings', namespace = 'CELERY' )
app.autodiscover_tasks()
