from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from modelshow.models import Model3D


class FlightPath( models.Model ):
	"""A named camera tour over a model."""
	name = models.CharField( max_length = 128 )
	model = models.ForeignKey( Model3D, related_name = 'flight_paths', on_delete = models.CASCADE )

	class Meta:
		ordering = [ 'id' ]
		constraints = [ models.UniqueConstraint( fields = [ 'model', 'name' ], name = 'unique_flight_path_name_per_model' ) ]

	def __str__( self ):
		return self.name


class FlightPoint( models.Model ):
	"""One camera pose: where the camera is and which way it looks."""
	path = models.ForeignKey( FlightPath, related_name = 'points', on_delete = models.CASCADE )
	order = models.PositiveIntegerField( default = 0 )
	# camera position as longitude, latitude, ellipsoidal height (metres)
	position = models.PointField( srid = 4326, dim = 3 )
	# camera orientation as Earth-centred (ECEF) unit vectors, as Cesium's camera uses them
	direction = ArrayField( models.FloatField(), size = 3 )
	up = ArrayField( models.FloatField(), size = 3 )

	class Meta:
		ordering = [ 'path', 'order' ]


class Measurement( models.Model ):
	"""A measurement taken in the viewer, kept for the user who took it.

	`geometry` holds the clicked points in order as longitude, latitude, ellipsoidal height (EPSG:4326, 3D):
	  point     Point Z
	  distance  LineString Z: one segment between each pair of consecutive vertices, so a path of any length is one row
	  area      Polygon Z: the outline as a closed ring (first vertex repeated at the end)
	  height    LineString Z from the first to the second point
	  circle    LineString Z from the centre to a point on the edge
	`results` holds the values worked out from it on the server (see viewermode.measure).
	"""

	class Kind( models.TextChoices ):
		POINT = 'point', 'Coordinates'
		DISTANCE = 'distance', 'Distance'
		AREA = 'area', 'Area'
		HEIGHT = 'height', 'Height difference'
		CIRCLE = 'circle', 'Circle'

	model = models.ForeignKey( Model3D, related_name = 'measurements', on_delete = models.CASCADE )
	created_by = models.ForeignKey( settings.AUTH_USER_MODEL, related_name = 'measurements', on_delete = models.CASCADE )
	kind = models.CharField( max_length = 16, choices = Kind.choices )
	name = models.CharField( max_length = 128, blank = True )
	geometry = models.GeometryField( srid = 4326, dim = 3, spatial_index = True )
	results = models.JSONField( default = dict, blank = True )
	created_at = models.DateTimeField( auto_now_add = True )

	class Meta:
		ordering = [ '-id' ]
		indexes = [ models.Index( fields = [ 'model', 'created_by' ] ) ]

	def __str__( self ):
		return self.name or f'{self.get_kind_display()} on {self.model}'
