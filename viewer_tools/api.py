"""Viewer tools that save to the database: /api/v1/flight-paths/, /api/v1/measurements/"""
from django.db import transaction
from rest_framework import mixins, permissions, serializers, viewsets

from catalog.access import EditableModelField, ModelChildSerializerMixin, readable_models
from core.api_fields import GeoPointField, Vector3Field
from core.permissions import IsCreatorOrStaff, IsOwnerOrReadOnly

from . import measurement_math
from .models import FlightPath, FlightPoint, Measurement


class FlightPointSerializer( serializers.ModelSerializer ):
	position = GeoPointField()
	direction = Vector3Field()
	up = Vector3Field()

	class Meta:
		model = FlightPoint
		fields = [ 'position', 'direction', 'up' ]


class FlightPathSerializer( ModelChildSerializerMixin, serializers.ModelSerializer ):
	model = EditableModelField()
	points = FlightPointSerializer( many = True )

	class Meta:
		model = FlightPath
		fields = [ 'id', 'model', 'name', 'points' ]
		validators = []    # name uniqueness is checked in validate() with a clearer message

	def validate_points( self, points ):
		if len( points ) < 2:
			raise serializers.ValidationError( 'A flight path needs at least two camera poses.' )
		return points

	def validate( self, attrs ):
		model = attrs.get( 'model', getattr( self.instance, 'model', None ) )
		name = attrs.get( 'name', getattr( self.instance, 'name', None ) )
		clash = FlightPath.objects.filter( model = model, name = name )
		if self.instance is not None:
			clash = clash.exclude( pk = self.instance.pk )
		if clash.exists():
			raise serializers.ValidationError( { 'name': 'This model already has a flight path with that name.' } )
		return attrs

	def _save_points( self, path, points ):
		path.points.all().delete()
		FlightPoint.objects.bulk_create( [ FlightPoint( path = path, order = i, **p ) for i, p in enumerate( points ) ] )

	@transaction.atomic
	def create( self, validated_data ):
		points = validated_data.pop( 'points' )
		path = FlightPath.objects.create( **validated_data )
		self._save_points( path, points )
		return path

	@transaction.atomic
	def update( self, instance, validated_data ):
		points = validated_data.pop( 'points', None )
		instance = super().update( instance, validated_data )
		if points is not None:
			self._save_points( instance, points )
		return instance


class MeasurementSerializer( serializers.ModelSerializer ):
	"""A measurement is sent as its kind and clicked points; the server stores them as one geometry and works out the results."""
	model = EditableModelField()
	points = serializers.ListField( child = GeoPointField(), write_only = True )
	results = serializers.JSONField( read_only = True )

	class Meta:
		model = Measurement
		fields = [ 'id', 'model', 'kind', 'name', 'points', 'results', 'created_at' ]
		read_only_fields = [ 'results', 'created_at' ]

	def to_representation( self, instance ):
		data = super().to_representation( instance )
		data['points'] = [ { 'longitude': x, 'latitude': y, 'height': z } for x, y, z in measurement_math.measured_points( instance.geometry ) ]
		return data

	def validate( self, attrs ):
		kind, points = attrs['kind'], attrs['points']
		fewest, most = measurement_math.POINT_COUNTS[ kind ]
		if not fewest <= len( points ) <= most:
			count = str( fewest ) if fewest == most else f'{fewest} to {most}'
			raise serializers.ValidationError( { 'points': f'A {kind} measurement takes {count} points.' } )
		attrs['geometry'], attrs['results'] = measurement_math.build_measurement( kind, [ p.coords for p in points ] )
		del attrs['points']
		return attrs


class FlightPathViewSet( viewsets.ModelViewSet ):
	"""Saved camera tours; filter with ?model=<id>. Saving replaces all of a path's points."""
	serializer_class = FlightPathSerializer
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_fields = [ 'model' ]

	def get_queryset( self ):
		return FlightPath.objects.filter( model__in = readable_models( self.request.user ) ).prefetch_related( 'points' )


class MeasurementViewSet( mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
						mixins.DestroyModelMixin, viewsets.GenericViewSet ):
	"""Your saved measurements; filter with ?model=<id> and ?kind=. Anyone signed in can measure models they can see."""
	serializer_class = MeasurementSerializer
	permission_classes = [ permissions.IsAuthenticated, IsCreatorOrStaff ]
	filterset_fields = [ 'model', 'kind' ]
	queryset = Measurement.objects.none()    # for schema generation; real rows come from get_queryset

	def get_queryset( self ):
		user = self.request.user
		if getattr( self, 'swagger_fake_view', False ):
			return Measurement.objects.all()
		measurements = Measurement.objects.filter( model__in = readable_models( user ) )
		return measurements if user.is_staff else measurements.filter( created_by = user )

	def perform_create( self, serializer ):
		serializer.save( created_by = self.request.user )


routes = [ ( 'flight-paths', FlightPathViewSet, 'flight-path' ), ( 'measurements', MeasurementViewSet, 'measurement' ) ]
