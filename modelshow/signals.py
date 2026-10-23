from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from processing.storage import delete_prefix

from .models import Model3D


def _tiles_folder( tileset_path ):
	"""The folder that holds a model's tiles: tiles/<id>/ for new uploads, Data/<name>/ for 2019 uploads."""
	parts = tileset_path.split( '/' )
	if len( parts ) >= 3 and parts[0] in ( 'tiles', 'Data' ):
		return f'{parts[0]}/{parts[1]}'
	return None


@receiver( post_delete, sender = Model3D )
def delete_model_files( sender, instance, **kwargs ):
	files = [ f for f in ( instance.source_file, instance.thumbnail ) if f ]
	folders = { f'tiles/{instance.pk}' }
	if instance.tileset_path and ( legacy := _tiles_folder( instance.tileset_path ) ):
		folders.add( legacy )

	def cleanup():
		for f in files:
			f.storage.delete( f.name )
		for folder in folders:
			delete_prefix( folder )

	# only remove files once the database delete has really happened
	transaction.on_commit( cleanup )
