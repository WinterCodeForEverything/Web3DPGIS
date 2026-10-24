from django.apps import AppConfig


class ProcessingConfig( AppConfig ):
	name = 'processing'
	verbose_name = 'Processing jobs'

	def ready( self ):
		from .jobs import register_job_kind
		from .tiling import run_tiling

		register_job_kind( 'tiling', run_tiling, title = 'Build 3D Tiles', done_message = 'Ready to view.' )
