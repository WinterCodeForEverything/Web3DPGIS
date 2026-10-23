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
