"""3D models: /api/v1/models/ (upload, list, spatial search, edit, reprocess)."""
import os

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api_fields import GeoPointField
from core.permissions import IsOwnerOrReadOnly, can_edit
from processing.api import JobSerializer
from processing.jobs import JobConflict, start_job
from processing.tiling import supported_extensions

from .access import readable_models
from .filters import Model3DFilter
from .models import Model3D


class Model3DSerializer( serializers.ModelSerializer ):
	owner = serializers.CharField( source = 'owner.username', read_only = True, default = None )
	tileset_url = serializers.CharField( read_only = True )
	location = GeoPointField( read_only = True )
	source_name = serializers.SerializerMethodField()
	latest_job = serializers.SerializerMethodField()
	can_edit = serializers.SerializerMethodField()
	distance_m = serializers.SerializerMethodField()

	class Meta:
		model = Model3D
		fields = [ 'id', 'name', 'owner', 'thumbnail', 'source_name', 'status', 'tileset_url', 'location', 'height_offset',
			'is_public', 'is_visible', 'created_at', 'updated_at', 'latest_job', 'can_edit', 'distance_m' ]
		read_only_fields = [ 'status', 'created_at', 'updated_at' ]

	def get_source_name( self, obj ) -> str | None:
		return os.path.basename( obj.source_file.name ) if obj.source_file else None

	def get_latest_job( self, obj ) -> dict | None:
		job = obj.jobs.order_by( '-id' ).first()
		return JobSerializer( job ).data if job else None

	def get_can_edit( self, obj ) -> bool:
		return can_edit( self.context['request'].user, obj )

	def get_distance_m( self, obj ) -> float | None:
		distance = getattr( obj, 'distance', None )
		return round( distance.m, 1 ) if distance is not None else None


class Model3DCreateSerializer( Model3DSerializer ):
	"""Upload a file; processing starts in the background."""
	source_file = serializers.FileField( write_only = True, help_text = 'Archive with 3D Tiles, or a model / point-cloud file: ' + ', '.join( supported_extensions() ) )
	placement = GeoPointField( write_only = True, required = False, help_text = 'Where to place a model that has no georeference' )
	source_srs = serializers.CharField( write_only = True, required = False, allow_blank = True, help_text = 'CRS of point-cloud input, e.g. EPSG:4547' )

	class Meta( Model3DSerializer.Meta ):
		fields = Model3DSerializer.Meta.fields + [ 'source_file', 'placement', 'source_srs' ]

	def validate_source_file( self, value ):
		name = value.name.lower()
		if not any( name.endswith( ext ) for ext in supported_extensions() ):
			raise serializers.ValidationError( 'Unsupported file type. Supported: ' + ', '.join( supported_extensions() ) )
		if value.size > settings.MAX_UPLOAD_SIZE:
			raise serializers.ValidationError( 'File is larger than the upload limit.' )
		return value

	def create( self, validated_data ):
		placement = validated_data.pop( 'placement', None )
		# DRF reads an omitted boolean in a multipart form as False (checkbox semantics); omitted means "use the default"
		for flag in ( 'is_public', 'is_visible' ):
			if flag not in self.initial_data:
				validated_data[flag] = True
		model = Model3D( **validated_data )
		if placement is not None:
			model.location = placement
		model.save()
		return model


class Model3DViewSet( viewsets.ModelViewSet ):
	"""3D models. Uploading creates the model and starts background processing."""
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_class = Model3DFilter

	def get_queryset( self ):
		return readable_models( self.request.user ).select_related( 'owner' )

	def get_serializer_class( self ):
		return Model3DCreateSerializer if self.action == 'create' else Model3DSerializer

	def perform_create( self, serializer ):
		model = serializer.save( owner = self.request.user )
		start_job( model, 'tiling' )

	@extend_schema( request = None, responses = { 202: JobSerializer, 409: OpenApiResponse( description = 'The model already has a job in progress' ) } )
	@action( detail = True, methods = [ 'post' ] )
	def reprocess( self, request, pk = None ):
		"""Run the processing pipeline again on the stored upload."""
		model = self.get_object()
		try:
			job = start_job( model, 'tiling' )
		except JobConflict:
			return Response( { 'detail': 'This model already has a job in progress.' }, status = status.HTTP_409_CONFLICT )
		return Response( JobSerializer( job ).data, status = status.HTTP_202_ACCEPTED )


routes = [ ( 'models', Model3DViewSet, 'model' ) ]
