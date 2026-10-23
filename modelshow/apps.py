from django.apps import AppConfig


class ModelshowConfig( AppConfig ):
	name = 'modelshow'
	verbose_name = '3D models'

	def ready( self ):
		from . import signals  # noqa: F401
