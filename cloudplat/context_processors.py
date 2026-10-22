from django.conf import settings


def cesium( request ):
	return { 'cesium_ion_token' : settings.CESIUM_ION_TOKEN }
