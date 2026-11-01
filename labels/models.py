from django.conf import settings
from django.contrib.gis.db import models
from django.core.files.storage import storages
from catalog.models import Model3D


def label_icon_storage():
	"""Where icon images are kept: assets/label-icons/ with local storage, the bucket's label/ prefix with S3 (settings.STORAGES)."""
	return storages['label_icons']


class LabelIcon( models.Model ):
	"""An icon in the label library; icons without an owner are shared with everyone."""
	name = models.CharField( max_length = 128, blank = True )
	image = models.ImageField( storage = label_icon_storage )
	owner = models.ForeignKey( settings.AUTH_USER_MODEL, related_name = 'label_icons', on_delete = models.CASCADE, null = True, blank = True )

	def __str__( self ):
		return self.name or self.image.name


class Label( models.Model ):
	"""A named marker or shape on a model: a point, a 2D shape (polyline, polygon, circle) or a 3D one (wall, sphere,
	cylinder, cone). See labels.geometry for how each kind uses `position`, `geometry`, `radius` and `height`."""

	class Kind( models.TextChoices ):
		POINT = 'point', 'Point'
		POLYLINE = 'polyline', 'Polyline'
		POLYGON = 'polygon', 'Polygon'
		CIRCLE = 'circle', 'Circle'
		WALL = 'wall', 'Wall'
		SPHERE = 'sphere', 'Sphere'
		CYLINDER = 'cylinder', 'Cylinder'
		CONE = 'cone', 'Cone'

	name = models.CharField( max_length = 128 )
	model = models.ForeignKey( Model3D, related_name = 'labels', on_delete = models.CASCADE )
	kind = models.CharField( max_length = 16, choices = Kind.choices, default = Kind.POINT )
	icon = models.ForeignKey( LabelIcon, related_name = 'labels', on_delete = models.SET_NULL, null = True, blank = True )
	# longitude, latitude, ellipsoidal height (metres)
	position = models.PointField( srid = 4326, dim = 3, spatial_index = True )
	# the vertices of polylines, polygons and walls (EPSG:4326, 3D)
	geometry = models.GeometryField( srid = 4326, dim = 3, null = True, blank = True )
	radius = models.FloatField( null = True, blank = True )
	height = models.FloatField( null = True, blank = True )
	color = models.CharField( max_length = 7, default = '#1e90ff' )
	properties = models.JSONField( default = dict, blank = True )

	class Meta:
		ordering = [ 'id' ]

	def __str__( self ):
		return self.name
