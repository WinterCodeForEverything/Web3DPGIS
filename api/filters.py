from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from modelshow.models import Model3D


def _floats( value, count, name ):
	try:
		numbers = [ float( v ) for v in value.split( ',' ) ]
	except ValueError:
		numbers = []
	if len( numbers ) != count:
		raise ValidationError( { name: f'Expected {count} comma-separated numbers.' } )
	return numbers


class Model3DFilter( filters.FilterSet ):
	mine = filters.BooleanFilter( method = 'filter_mine', help_text = 'Only models owned by the current user' )
	search = filters.CharFilter( field_name = 'name', lookup_expr = 'icontains' )
	status = filters.ChoiceFilter( choices = Model3D.Status.choices )
	bbox = filters.CharFilter( method = 'filter_bbox', help_text = 'min_lon,min_lat,max_lon,max_lat' )
	near = filters.CharFilter( method = 'filter_near', help_text = 'lon,lat; results are sorted by distance and limited by radius' )
	radius = filters.NumberFilter( method = 'filter_noop', help_text = 'Search radius in metres for `near` (default 10000)' )

	class Meta:
		model = Model3D
		fields = [ 'mine', 'search', 'status', 'bbox', 'near', 'radius' ]

	def filter_noop( self, queryset, name, value ):
		return queryset

	def filter_mine( self, queryset, name, value ):
		user = self.request.user
		if value and user.is_authenticated:
			return queryset.filter( owner = user )
		return queryset

	def filter_bbox( self, queryset, name, value ):
		min_lon, min_lat, max_lon, max_lat = _floats( value, 4, 'bbox' )
		return queryset.filter( location__intersects = Polygon.from_bbox( ( min_lon, min_lat, max_lon, max_lat ) ) )

	def filter_near( self, queryset, name, value ):
		lon, lat = _floats( value, 2, 'near' )
		radius = float( self.data.get( 'radius' ) or 10000 )
		centre = Point( lon, lat, srid = 4326 )
		return ( queryset.filter( location__distance_lte = ( centre, D( m = radius ) ) )
			.annotate( distance = Distance( 'location', centre ) ).order_by( 'distance' ) )
