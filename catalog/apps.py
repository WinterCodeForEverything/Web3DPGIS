from django.apps import AppConfig


class CatalogConfig( AppConfig ):
	name = 'catalog'
	# the app's original label, so its tables (e.g. modelshow_…) and migration history stay as they are
	label = 'modelshow'
	verbose_name = '3D models'

	def ready( self ):
		from . import signals  # noqa: F401
