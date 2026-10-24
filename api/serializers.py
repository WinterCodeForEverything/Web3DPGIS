import os

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from addlabel.models import Label, LabelIcon
from modelshow.models import Model3D
from processing.models import Job
from processing.pipeline import SUPPORTED_EXTENSIONS
from user_login.models import UserProfile
from viewermode import measure
from viewermode.models import FlightPath, FlightPoint, Measurement

from .fields import GeoPointField, Vector3Field
from .permissions import can_edit, readable_models


# --- accounts ---------------------------------------------------------------

class UserSerializer( serializers.ModelSerializer ):
	class Meta:
		model = User
		fields = [ 'id', 'username', 'email', 'is_staff' ]
		read_only_fields = fields


class RegisterSerializer( serializers.Serializer ):
	username = serializers.RegexField( r'^[\w.@+-]{3,50}$', error_messages = { 'invalid': '3 to 50 letters, digits or . @ + - _' } )
	email = serializers.EmailField()
	password = serializers.CharField( write_only = True, style = { 'input_type': 'password' } )

	def validate_username( self, value ):
		if User.objects.filter( username__iexact = value ).exists():
			raise serializers.ValidationError( 'This username is already taken.' )
		return value

	def validate_email( self, value ):
		if User.objects.filter( email__iexact = value ).exists():
			raise serializers.ValidationError( 'This email is already registered.' )
		return value

	def validate( self, attrs ):
		password_validation.validate_password( attrs['password'], User( username = attrs['username'], email = attrs['email'] ) )
		return attrs

	@transaction.atomic
	def create( self, validated_data ):
		user = User.objects.create_user( **validated_data )
		UserProfile.objects.create( user = user )
		return user


class LoginSerializer( serializers.Serializer ):
	login = serializers.CharField( help_text = 'Username or email' )
	password = serializers.CharField( write_only = True, style = { 'input_type': 'password' } )


# --- jobs ---------------------------------------------------------------------

class JobSerializer( serializers.ModelSerializer ):
	class Meta:
		model = Job
		fields = [ 'id', 'model', 'status', 'progress', 'attempts', 'stage', 'message', 'created_at', 'started_at', 'finished_at' ]
		read_only_fields = fields


class JobDetailSerializer( JobSerializer ):
	class Meta( JobSerializer.Meta ):
		fields = JobSerializer.Meta.fields + [ 'log' ]
		read_only_fields = fields


# --- models -------------------------------------------------------------------

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
	source_file = serializers.FileField( write_only = True, help_text = 'Archive with 3D Tiles, or a model / point-cloud file: ' + ', '.join( SUPPORTED_EXTENSIONS ) )
	placement = GeoPointField( write_only = True, required = False, help_text = 'Where to place a model that has no georeference' )
	source_srs = serializers.CharField( write_only = True, required = False, allow_blank = True, help_text = 'CRS of point-cloud input, e.g. EPSG:4547' )

	class Meta( Model3DSerializer.Meta ):
		fields = Model3DSerializer.Meta.fields + [ 'source_file', 'placement', 'source_srs' ]

	def validate_source_file( self, value ):
		name = value.name.lower()
		if not any( name.endswith( ext ) for ext in SUPPORTED_EXTENSIONS ):
			raise serializers.ValidationError( 'Unsupported file type. Supported: ' + ', '.join( SUPPORTED_EXTENSIONS ) )
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


# --- labels ---------------------------------------------------------------------

class LabelIconSerializer( serializers.ModelSerializer ):
	owner = serializers.CharField( source = 'owner.username', read_only = True, default = None )
	can_edit = serializers.SerializerMethodField()

	class Meta:
		model = LabelIcon
		fields = [ 'id', 'name', 'image', 'owner', 'can_edit' ]

	def get_can_edit( self, obj ) -> bool:
		user = self.context['request'].user
		return user.is_authenticated and ( user.is_staff or obj.owner_id == user.id )


class EditableModelField( serializers.PrimaryKeyRelatedField ):
	"""A model the requesting user may see; writing to it is checked in validate_model."""

	def get_queryset( self ):
		return readable_models( self.context['request'].user )


class ModelChildSerializerMixin:
	def validate_model( self, model ):
		if not can_edit( self.context['request'].user, model ):
			raise serializers.ValidationError( 'You can only change models you own.' )
		return model


class LabelSerializer( ModelChildSerializerMixin, serializers.ModelSerializer ):
	model = EditableModelField()
	position = GeoPointField()
	icon_url = serializers.ImageField( source = 'icon.image', read_only = True, default = None )

	class Meta:
		model = Label
		fields = [ 'id', 'model', 'name', 'icon', 'icon_url', 'position', 'properties' ]

	def validate_icon( self, icon ):
		user = self.context['request'].user
		if icon is not None and icon.owner_id not in ( None, user.id ) and not user.is_staff:
			raise serializers.ValidationError( 'Unknown icon.' )
		return icon


# --- flight paths ---------------------------------------------------------------

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


# --- measurements ---------------------------------------------------------------

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
		data['points'] = [ { 'longitude': x, 'latitude': y, 'height': z } for x, y, z in measure.points_of( instance.geometry ) ]
		return data

	def validate( self, attrs ):
		kind, points = attrs['kind'], attrs['points']
		fewest, most = measure.POINT_COUNTS[ kind ]
		if not fewest <= len( points ) <= most:
			count = str( fewest ) if fewest == most else f'{fewest} to {most}'
			raise serializers.ValidationError( { 'points': f'A {kind} measurement takes {count} points.' } )
		attrs['geometry'], attrs['results'] = measure.build( kind, [ p.coords for p in points ] )
		del attrs['points']
		return attrs
