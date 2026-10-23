import json

from django.contrib.gis.geos import Point
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


@extend_schema_field( {
	'type': 'object',
	'properties': {
		'longitude': { 'type': 'number', 'minimum': -180, 'maximum': 180 },
		'latitude': { 'type': 'number', 'minimum': -90, 'maximum': 90 },
		'height': { 'type': 'number', 'description': 'Ellipsoidal height in metres' },
	},
	'required': [ 'longitude', 'latitude' ],
} )
class GeoPointField( serializers.Field ):
	"""A WGS84 point exchanged as {"longitude", "latitude", "height"} (degrees, degrees, metres)."""

	default_error_messages = {
		'invalid': 'Expected an object with numeric longitude, latitude and optional height.',
		'range': 'Longitude must be within [-180, 180] and latitude within [-90, 90].',
	}

	def to_representation( self, value ):
		if value is None:
			return None
		return { 'longitude': value.x, 'latitude': value.y, 'height': value.z if value.hasz else 0.0 }

	def to_internal_value( self, data ):
		if isinstance( data, str ):
			# multipart uploads send nested values as a JSON string
			try:
				data = json.loads( data )
			except ValueError:
				self.fail( 'invalid' )
		try:
			lon = float( data['longitude'] )
			lat = float( data['latitude'] )
			height = float( data.get( 'height', 0.0 ) or 0.0 )
		except ( TypeError, KeyError, ValueError, AttributeError ):
			self.fail( 'invalid' )
		if not ( -180 <= lon <= 180 and -90 <= lat <= 90 ):
			self.fail( 'range' )
		return Point( lon, lat, height, srid = 4326 )


class Vector3Field( serializers.ListField ):
	"""Three floats, e.g. an ECEF unit vector."""

	def __init__( self, **kwargs ):
		super().__init__( child = serializers.FloatField(), min_length = 3, max_length = 3, **kwargs )
