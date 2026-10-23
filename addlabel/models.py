from django.conf import settings
from django.contrib.gis.db import models
from modelshow.models import Model3D


class LabelIcon( models.Model ):
	"""An icon in the label library; icons without an owner are shared with everyone."""
	name = models.CharField( max_length = 128, blank = True )
	image = models.ImageField( upload_to = 'label' )
	owner = models.ForeignKey( settings.AUTH_USER_MODEL, related_name = 'label_icons', on_delete = models.CASCADE, null = True, blank = True )

	def __str__( self ):
		return self.name or self.image.name


class Label( models.Model ):
	"""A named marker pinned to a point on a model."""
	name = models.CharField( max_length = 128 )
	model = models.ForeignKey( Model3D, related_name = 'labels', on_delete = models.CASCADE )
	icon = models.ForeignKey( LabelIcon, related_name = 'labels', on_delete = models.SET_NULL, null = True, blank = True )
	# longitude, latitude, ellipsoidal height (metres)
	position = models.PointField( srid = 4326, dim = 3, spatial_index = True )
	properties = models.JSONField( default = dict, blank = True )

	class Meta:
		ordering = [ 'id' ]

	def __str__( self ):
		return self.name
