"""/api/v1/: every installed app that has an `api` module contributes to it.

An app's api.py may define
  routes       [ ( prefix, viewset, basename ), … ]  registered on the shared router, e.g. /api/v1/models/
  urlpatterns  plain Django paths under /api/v1/, e.g. auth/login/
so a new module (e.g. reconstruction) adds its endpoints without touching this file.
"""
from importlib import import_module
from importlib.util import find_spec

from django.apps import apps
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter


def app_api_modules():
	"""The `api` module of each installed app that has one, in INSTALLED_APPS order."""
	for config in apps.get_app_configs():
		name = f'{config.name}.api'
		if find_spec( name ) is not None:
			yield import_module( name )


router = DefaultRouter()
v1 = []
for module in app_api_modules():
	for prefix, viewset, basename in getattr( module, 'routes', [] ):
		router.register( prefix, viewset, basename = basename )
	v1 += getattr( module, 'urlpatterns', [] )

urlpatterns = [
	path( 'v1/', include( router.urls ) ),
	path( 'v1/', include( v1 ) ),
	path( 'v1/auth/token/', obtain_auth_token, name = 'auth-token' ),
	path( 'schema/', SpectacularAPIView.as_view(), name = 'api-schema' ),
	path( 'docs/', SpectacularSwaggerView.as_view( url_name = 'api-schema' ), name = 'api-docs' ),
]
