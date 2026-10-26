from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.storage import delete_prefix

from .models import Reconstruction, recon_prefix


@receiver( post_delete, sender = Reconstruction )
def delete_reconstruction_files( sender, instance, **kwargs ):
	"""Photos, masks, inputs, checkpoints and the result go with the reconstruction (and with its model)."""
	prefix = recon_prefix( instance.pk )
	transaction.on_commit( lambda: delete_prefix( prefix ) )
