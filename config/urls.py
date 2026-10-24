"""URL configuration.

/api/v1/  JSON API (see api/urls.py), with OpenAPI docs at /api/docs/
/admin/   Django admin
/media/   uploaded files and generated 3D Tiles with local storage (served by nginx in production)
anything else: the Vue single-page app (frontend/)
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from . import views

urlpatterns = [
	path( 'admin/', admin.site.urls ),
	path( 'api/', include( 'api.urls' ) ),
]

if settings.STORAGE_BACKEND == 'local':
	# development convenience; in production nginx serves /media/ (or the bucket serves files with S3 storage)
	urlpatterns += static( settings.MEDIA_URL, document_root = settings.MEDIA_ROOT )

urlpatterns += [
	re_path( r'^(?!api/|admin/|media/|static/)(?P<path>.*)$', views.serve_frontend, name = 'frontend' ),
]
