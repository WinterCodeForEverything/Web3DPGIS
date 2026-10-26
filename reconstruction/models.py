from django.db import models

from .stages import PRESETS


def recon_prefix( reconstruction_id ):
	"""Storage folder of a reconstruction: photos/, masks/, inputs/, work/ (checkpoints) and result/."""
	return f'recon/{reconstruction_id}'


def _poses_path( instance, filename ):
	return f'{recon_prefix( instance.pk )}/inputs/poses.txt'


def _photo_path( instance, filename ):
	return f'{recon_prefix( instance.reconstruction_id )}/photos/{instance.name}'


def _mask_path( instance, filename ):
	# the pipeline looks for <photo name>.png, e.g. IMG_0001.JPG.png
	return f'{recon_prefix( instance.reconstruction_id )}/masks/{instance.name}.png'


class Reconstruction( models.Model ):
	"""Photos turned into a 3D model: the model is created up front and gets its tiles once the job is done."""

	Preset = models.TextChoices( 'Preset', [ ( p, p.capitalize() ) for p in PRESETS ] )

	# by label, so the catalog app does not need to know about reconstructions
	model = models.OneToOneField( 'modelshow.Model3D', related_name = 'reconstruction', on_delete = models.CASCADE )
	preset = models.CharField( max_length = 16, choices = Preset.choices, default = 'standard' )
	options = models.JSONField( default = dict, blank = True, help_text = 'What is known about the cameras; see stages.Options' )
	poses = models.FileField( upload_to = _poses_path, max_length = 255, blank = True,
		help_text = 'Camera centres ("name x y z") or full poses ("name qw qx qy qz tx ty tz") in a local system' )
	mode = models.CharField( max_length = 32, blank = True, help_text = 'What the cameras were solved from: photos only, gps, camera centres, full poses' )
	stats = models.JSONField( default = dict, blank = True, help_text = 'Summary of the last run: photos placed, errors, stage times' )
	resolution_shift = models.PositiveSmallIntegerField( default = 0, help_text = 'Steps down in resolution after running out of memory' )
	cancel_requested = models.BooleanField( default = False )
	created_at = models.DateTimeField( auto_now_add = True )
	started_at = models.DateTimeField( null = True, blank = True )

	class Meta:
		ordering = [ '-id' ]

	def __str__( self ):
		return f'Reconstruction {self.pk} of {self.model}'

	@property
	def prefix( self ):
		return recon_prefix( self.pk )


class Photo( models.Model ):
	reconstruction = models.ForeignKey( Reconstruction, related_name = 'photos', on_delete = models.CASCADE )
	name = models.CharField( max_length = 200 )
	file = models.FileField( upload_to = _photo_path, max_length = 255 )
	mask = models.FileField( upload_to = _mask_path, max_length = 255, blank = True, help_text = 'Black areas get no features or depth' )
	size = models.BigIntegerField( default = 0 )
	# False while the browser is still putting the photo into the bucket with a presigned URL
	uploaded = models.BooleanField( default = False )

	class Meta:
		ordering = [ 'name' ]
		constraints = [ models.UniqueConstraint( fields = [ 'reconstruction', 'name' ], name = 'unique_photo_name' ) ]

	def __str__( self ):
		return self.name
