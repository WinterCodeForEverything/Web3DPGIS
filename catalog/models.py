from django.conf import settings
from django.contrib.gis.db import models
from django.core.files.storage import default_storage


class Model3D( models.Model ):
	"""An uploaded 3D model and the 3D Tiles produced from it."""

	class Status( models.TextChoices ):
		PENDING = 'pending', 'Pending'
		PROCESSING = 'processing', 'Processing'
		READY = 'ready', 'Ready'
		FAILED = 'failed', 'Failed'

	name = models.CharField( max_length = 128 )
	owner = models.ForeignKey( settings.AUTH_USER_MODEL, related_name = 'models3d', on_delete = models.CASCADE, null = True )
	thumbnail = models.ImageField( upload_to = 'image', blank = True )
	source_file = models.FileField( upload_to = 'package' )
	source_srs = models.CharField( max_length = 64, blank = True, help_text = 'CRS of point-cloud input, e.g. EPSG:4547' )
	is_public = models.BooleanField( default = True )
	is_visible = models.BooleanField( default = True )
	height_offset = models.FloatField( default = 0.0, help_text = 'Metres added to the model height' )

	status = models.CharField( max_length = 16, choices = Status.choices, default = Status.PENDING )
	tileset_path = models.CharField( max_length = 512, blank = True, help_text = 'Storage name of tileset.json, e.g. tiles/12/tileset.json' )
	# Centre of the model as longitude, latitude, ellipsoidal height (metres)
	location = models.PointField( srid = 4326, dim = 3, null = True, blank = True, spatial_index = True )
	# Where the source's own (0, 0, 0) is put on the globe when it has no georeference: the placement given at upload, or
	# the GPS origin of a reconstruction. Tiling uses it every time; `location` becomes the tileset's centre afterwards,
	# so placing by `location` would move a mesh on every reprocess.
	origin = models.PointField( srid = 4326, dim = 3, null = True, blank = True, spatial_index = False )

	created_at = models.DateTimeField( auto_now_add = True, null = True )
	updated_at = models.DateTimeField( auto_now = True, null = True )

	class Meta:
		verbose_name = '3D model'
		ordering = [ '-id' ]

	def __str__( self ):
		return self.name

	@property
	def tileset_url( self ):
		# /media/… on local disk, a bucket or CDN URL with S3 storage
		return default_storage.url( self.tileset_path ) if self.tileset_path else None
