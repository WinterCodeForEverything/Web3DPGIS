from django.apps import AppConfig
from django.conf import settings


class ReconstructionConfig( AppConfig ):
	name = 'reconstruction'
	verbose_name = '3D reconstruction'

	def ready( self ):
		from processing.jobs import register_job_kind

		from . import signals  # noqa: F401
		from .job import run_reconstruction

		# heavy and long: its own queue, so only workers started with -Q …,reconstruction take it
		register_job_kind( 'reconstruction', run_reconstruction, title = 'Reconstruct from photos', queue = settings.RECONSTRUCTION_QUEUE,
			done_message = 'Reconstructed; building 3D Tiles.' )
