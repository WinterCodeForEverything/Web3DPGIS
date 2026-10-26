"""3D reconstruction from photos: /api/v1/reconstructions/

    POST   /reconstructions/                     name, preset, options, placement → a new model and its reconstruction
    POST   /reconstructions/<id>/photos/          multipart `photos` files; or JSON {"photos": [{"name", "size"}]} on S3
                                                  storage, answered with presigned PUT URLs …
    POST   /reconstructions/<id>/photos/confirm/  … and {"names": […]} once those uploads are done
    DELETE /reconstructions/<id>/photos/          {"names": […]}
    POST   /reconstructions/<id>/masks/           multipart `masks` files named <photo name>.png (or <photo stem>.png)
    POST   /reconstructions/<id>/poses/           multipart `file`: camera centres or full poses; DELETE removes it
    POST   /reconstructions/<id>/start/           queue the job; it hands its mesh to the tiling job when done
    POST   /reconstructions/<id>/cancel/
    GET    /reconstructions/<id>/                 status: photos, latest job, how the cameras were solved, statistics

Changing photos, masks, poses or options forgets the checkpoints of earlier runs; nothing can change while a job runs.
"""
import mimetypes
import os
import tempfile

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from catalog.models import Model3D
from core import storage
from core.api_fields import GeoPointField
from processing.api import JobSerializer
from processing.jobs import JobConflict, mark_finished, start_job
from processing.models import Job

from . import camera_inputs as ci
from .job import clear_checkpoints
from .models import Photo, Reconstruction, _mask_path, _photo_path
from .stages import PHOTO_TYPES, PRESETS

ACTIVE = [ Job.Status.QUEUED, Job.Status.RUNNING ]


class JobInProgress( APIException ):
	status_code = status.HTTP_409_CONFLICT
	default_detail = 'A job is in progress on this reconstruction; wait for it or cancel it first.'


class OptionsSerializer( serializers.Serializer ):
	"""What is known about the cameras. Everything is optional: from photos alone the cameras are solved too."""
	camera_model = serializers.ChoiceField( choices = list( ci.CAMERA_PARAM_COUNTS ), default = 'SIMPLE_RADIAL' )
	camera_params = serializers.ListField( child = serializers.FloatField(), required = False,
		help_text = "Known intrinsics in COLMAP's order for the camera model, e.g. OPENCV: fx, fy, cx, cy, k1, k2, p1, p2 (pixels)" )
	fix_intrinsics = serializers.BooleanField( default = False, help_text = 'Hold the given intrinsics fixed instead of refining them' )
	prior_std = serializers.FloatField( min_value = 1e-6, default = 0.1, help_text = 'Uncertainty of the poses file, in its units' )
	gps_std = serializers.ListField( child = serializers.FloatField( min_value = 0.01 ), min_length = 2, max_length = 2, default = [ 3.0, 5.0 ],
		help_text = 'GPS uncertainty in metres: horizontal, vertical' )
	ignore_gps = serializers.BooleanField( default = False )
	altitude_reference = serializers.ChoiceField( choices = [ 'sea-level', 'ellipsoid' ], default = 'sea-level',
		help_text = "What the photos' EXIF altitudes are relative to" )
	full_resolution = serializers.BooleanField( default = False, help_text = 'Features at full image size, for small or distant objects' )
	sift_threshold = serializers.FloatField( min_value = 1e-5, max_value = 0.1, required = False, allow_null = True,
		help_text = 'Lower finds more features in dark or low-contrast photos (default 0.00667)' )
	min_track = serializers.IntegerField( min_value = 2, max_value = 10, default = 2, help_text = 'Keep 3D points seen in at least this many photos' )
	units_to_metres = serializers.FloatField( min_value = 1e-9, default = 1.0, help_text = 'Scale of the poses file to metres, e.g. 0.001 for mm' )
	up_axis = serializers.ChoiceField( choices = list( ci.UP_AXES ), default = '+z', help_text = 'Axis of the poses frame that points up' )
	up_method = serializers.ChoiceField( choices = [ 'IMAGE-ORIENTATION', 'MANHATTAN-WORLD' ], default = 'IMAGE-ORIENTATION',
		help_text = 'How "up" is found from photos alone: upright photos, or the lines of buildings' )

	def validate( self, data ):
		data.setdefault( 'camera_model', 'SIMPLE_RADIAL' )
		params = data.get( 'camera_params' )
		if params:
			expected = ci.CAMERA_PARAM_COUNTS[ data['camera_model'] ]
			if len( params ) != expected:
				raise ValidationError( { 'camera_params': f'{data["camera_model"]} takes {expected} parameters; got {len( params )}.' } )
			data['camera_params'] = ','.join( repr( v ) for v in params )   # the pipeline passes them on to COLMAP as text
		elif data.get( 'fix_intrinsics' ):
			raise ValidationError( { 'fix_intrinsics': 'Fixed intrinsics need camera_params.' } )
		return data

	def to_representation( self, value ):
		value = dict( value )
		if isinstance( value.get( 'camera_params' ), str ):
			value['camera_params'] = [ float( v ) for v in value['camera_params'].split( ',' ) ]
		return value


class ReconstructionSerializer( serializers.ModelSerializer ):
	name = serializers.CharField( source = 'model.name', max_length = 128 )
	is_public = serializers.BooleanField( source = 'model.is_public', default = True )
	placement = GeoPointField( source = 'model.origin', required = False, allow_null = True,
		help_text = 'Where to put a result that has no GPS; with GPS the photos place it' )
	options = OptionsSerializer( required = False )
	status = serializers.CharField( source = 'model.status', read_only = True )
	photos = serializers.SerializerMethodField()
	has_poses = serializers.SerializerMethodField()
	latest_job = serializers.SerializerMethodField()

	class Meta:
		model = Reconstruction
		fields = [ 'id', 'model', 'name', 'is_public', 'preset', 'options', 'placement', 'status', 'photos', 'has_poses', 'mode', 'stats',
			'resolution_shift', 'cancel_requested', 'latest_job', 'created_at', 'started_at' ]
		read_only_fields = [ 'model', 'mode', 'stats', 'resolution_shift', 'cancel_requested', 'created_at', 'started_at' ]

	def get_photos( self, obj ) -> dict:
		photos = obj.photos.all()
		return { 'uploaded': photos.filter( uploaded = True ).count(), 'pending': photos.filter( uploaded = False ).count(),
			'masks': photos.exclude( mask = '' ).count() }

	def get_has_poses( self, obj ) -> bool:
		return bool( obj.poses )

	def get_latest_job( self, obj ) -> dict | None:
		job = obj.model.jobs.order_by( '-id' ).first()
		return JobSerializer( job ).data if job else None

	@transaction.atomic
	def create( self, validated_data ):
		model_data = validated_data.pop( 'model' )
		model = Model3D.objects.create( owner = self.context['request'].user, name = model_data['name'],
			is_public = model_data.get( 'is_public', True ), origin = model_data.get( 'origin' ), location = model_data.get( 'origin' ) )
		return Reconstruction.objects.create( model = model, preset = validated_data.get( 'preset', 'standard' ),
			options = validated_data.get( 'options' ) or OptionsSerializer().run_validation( {} ) )

	@transaction.atomic
	def update( self, instance, validated_data ):
		model_data = validated_data.pop( 'model', {} )
		if 'options' in validated_data:
			# a PATCH may send only the options that change; the rest keep their values
			merged = { **OptionsSerializer( instance.options ).data, **self.initial_data['options'] }
			options = OptionsSerializer( data = merged )
			options.is_valid( raise_exception = True )
			validated_data['options'] = options.validated_data
		for field, value in model_data.items():
			setattr( instance.model, field, value )
		if 'origin' in model_data and instance.model.status != instance.model.Status.READY:
			instance.model.location = model_data['origin']   # shown on the map until the result has its own centre
		instance.model.save()
		for field, value in validated_data.items():
			setattr( instance, field, value )
		instance.save()
		if validated_data or 'origin' in model_data:
			_changed( instance )
		return instance


def _changed( recon ):
	"""The inputs changed: earlier checkpoints no longer apply."""
	clear_checkpoints( recon )
	Reconstruction.objects.filter( pk = recon.pk ).update( resolution_shift = 0, cancel_requested = False )
	recon.resolution_shift, recon.cancel_requested = 0, False


def _photo_name( name ):
	name = os.path.basename( str( name ) )
	if not name or name.startswith( '.' ) or len( name ) > 200 or any( c in name for c in '\\\0' ):
		raise ValidationError( f'{name!r} is not a usable photo name.' )
	if not name.lower().endswith( PHOTO_TYPES ):
		raise ValidationError( f'{name}: photos must be one of {", ".join( PHOTO_TYPES )}.' )
	return name


def _replace( name, src ):
	"""Store src under exactly this name (storage would otherwise add a suffix to a name that exists)."""
	if default_storage.exists( name ):
		default_storage.delete( name )
	return default_storage.save( name, src )


class ReconstructionViewSet( viewsets.ModelViewSet ):
	"""Reconstructions of your own; each one makes a 3D model that gets its tiles when the job is done."""
	serializer_class = ReconstructionSerializer
	permission_classes = [ permissions.IsAuthenticated ]
	queryset = Reconstruction.objects.none()    # for schema generation; real rows come from get_queryset
	http_method_names = [ 'get', 'post', 'patch', 'delete', 'head', 'options' ]

	def get_queryset( self ):
		recons = Reconstruction.objects.select_related( 'model' )
		if getattr( self, 'swagger_fake_view', False ):
			return recons
		if not self.request.user.is_staff:
			recons = recons.filter( model__owner = self.request.user )
		model = self.request.query_params.get( 'model' )
		if model:   # the reconstruction behind a model in the model list
			recons = recons.filter( model_id = int( model ) if model.isdigit() else -1 )
		return recons

	@action( detail = False, methods = [ 'get' ], permission_classes = [ permissions.AllowAny ] )
	def limits( self, request ):
		"""What this server accepts, so a client can check photos and options before uploading."""
		return Response( {
			'min_photos': settings.RECONSTRUCTION_MIN_PHOTOS, 'max_photos': settings.RECONSTRUCTION_MAX_PHOTOS,
			'max_photo_size': settings.RECONSTRUCTION_MAX_PHOTO_SIZE, 'photo_types': list( PHOTO_TYPES ),
			'direct_upload': not storage.is_local_storage(),   # presigned PUT + confirm instead of multipart
			'presets': { name: { 'max_image_size': p['max_image_size'], 'levels_of_detail': p['lods'] } for name, p in PRESETS.items() },
			'camera_models': ci.CAMERA_PARAM_COUNTS,
		} )

	def _editable( self ):
		"""The reconstruction, once it is clear no job is changing it."""
		recon = self.get_object()
		if recon.model.jobs.filter( status__in = ACTIVE ).exists():
			raise JobInProgress()
		return recon

	def perform_update( self, serializer ):
		self._editable()
		serializer.save()

	def destroy( self, request, pk = None ):
		recon = self._editable()
		recon.model.delete()    # the reconstruction and its files go with it
		return Response( status = status.HTTP_204_NO_CONTENT )

	# --- photos -------------------------------------------------------------------

	@extend_schema( request = { 'multipart/form-data': { 'type': 'object', 'properties': { 'photos': { 'type': 'array', 'items': { 'type': 'string', 'format': 'binary' } } } },
		'application/json': { 'type': 'object', 'properties': { 'photos': { 'type': 'array', 'items': { 'type': 'object' } } } } } )
	@action( detail = True, methods = [ 'get', 'post', 'delete' ] )
	def photos( self, request, pk = None ):
		"""GET lists the photos; POST adds or replaces photos; DELETE removes the photos in {"names": […]}."""
		if request.method == 'GET':
			recon = self.get_object()
			return Response( [ { 'name': p.name, 'size': p.size, 'uploaded': p.uploaded, 'mask': bool( p.mask ) } for p in recon.photos.all() ] )
		recon = self._editable()
		if request.method == 'DELETE':
			names = request.data.get( 'names' ) or []
			removed = 0
			for photo in recon.photos.filter( name__in = names ):
				for f in ( photo.file, photo.mask ):
					if f:
						f.storage.delete( f.name )
				photo.delete()
				removed += 1
			if removed:
				_changed( recon )
			return Response( { 'removed': removed } )
		if request.FILES:
			return self._upload_photos( recon, request.FILES.getlist( 'photos' ) )
		return self._presign_photos( recon, request.data.get( 'photos' ) or [] )

	def _check_count( self, recon, new_names ):
		total = recon.photos.exclude( name__in = new_names ).count() + len( new_names )
		if total > settings.RECONSTRUCTION_MAX_PHOTOS:
			raise ValidationError( f'At most {settings.RECONSTRUCTION_MAX_PHOTOS} photos per reconstruction.' )

	def _check_size( self, name, size ):
		if size > settings.RECONSTRUCTION_MAX_PHOTO_SIZE:
			raise ValidationError( f'{name} is larger than {settings.RECONSTRUCTION_MAX_PHOTO_SIZE // 2 ** 20} MB.' )

	def _upload_photos( self, recon, files ):
		if not files:
			raise ValidationError( 'Send the photos as multipart/form-data files named "photos".' )
		names = [ _photo_name( f.name ) for f in files ]
		self._check_count( recon, names )
		for name, f in zip( names, files ):
			self._check_size( name, f.size )
		for name, f in zip( names, files ):
			photo, _ = Photo.objects.get_or_create( reconstruction = recon, name = name )
			photo.file.name = _replace( _photo_path( photo, name ), f )
			photo.size, photo.uploaded = f.size, True
			photo.save()
		_changed( recon )
		return Response( { 'uploaded': names }, status = status.HTTP_201_CREATED )

	def _presign_photos( self, recon, items ):
		"""S3 storage: the browser puts each photo into the bucket itself, then confirms."""
		if storage.is_local_storage():
			raise ValidationError( 'This server stores files locally: send the photos as multipart/form-data files named "photos".' )
		if not isinstance( items, list ) or not items:
			raise ValidationError( 'Expected {"photos": [{"name": …, "size": …}, …]}.' )
		names = [ _photo_name( item.get( 'name' ) if isinstance( item, dict ) else None ) for item in items ]
		self._check_count( recon, names )
		uploads = []
		for name, item in zip( names, items ):
			self._check_size( name, int( item.get( 'size' ) or 0 ) )
			photo, _ = Photo.objects.get_or_create( reconstruction = recon, name = name )
			photo.file.name, photo.uploaded, photo.size = _photo_path( photo, name ), False, 0
			photo.save()
			content_type = mimetypes.guess_type( name )[0] or 'application/octet-stream'
			uploads.append( { 'name': name, 'method': 'PUT', 'content_type': content_type,
				'url': storage.presigned_upload( photo.file.name, content_type, settings.RECONSTRUCTION_UPLOAD_URL_EXPIRES ) } )
		_changed( recon )
		return Response( { 'uploads': uploads, 'expires_in': settings.RECONSTRUCTION_UPLOAD_URL_EXPIRES }, status = status.HTTP_201_CREATED )

	@extend_schema( request = { 'application/json': { 'type': 'object', 'properties': { 'names': { 'type': 'array', 'items': { 'type': 'string' } } } } } )
	@action( detail = True, methods = [ 'post' ], url_path = 'photos/confirm' )
	def confirm_photos( self, request, pk = None ):
		"""Mark presigned uploads as done once the bucket has them."""
		recon = self._editable()
		confirmed, missing, too_large = [], [], []
		for photo in recon.photos.filter( name__in = request.data.get( 'names' ) or [], uploaded = False ):
			if not default_storage.exists( photo.file.name ):
				missing.append( photo.name )
				continue
			photo.size = default_storage.size( photo.file.name )
			if photo.size > settings.RECONSTRUCTION_MAX_PHOTO_SIZE:
				default_storage.delete( photo.file.name )
				photo.delete()
				too_large.append( photo.name )
				continue
			photo.uploaded = True
			photo.save( update_fields = [ 'size', 'uploaded' ] )
			confirmed.append( photo.name )
		return Response( { 'confirmed': confirmed, 'missing': missing, 'too_large': too_large } )

	# --- masks and poses -------------------------------------------------------------

	@extend_schema( request = { 'multipart/form-data': { 'type': 'object', 'properties': { 'masks': { 'type': 'array', 'items': { 'type': 'string', 'format': 'binary' } } } } } )
	@action( detail = True, methods = [ 'post' ] )
	def masks( self, request, pk = None ):
		"""Masks as PNG files named <photo name>.png or <photo stem>.png; black areas get no features or depth."""
		recon = self._editable()
		files = request.FILES.getlist( 'masks' )
		if not files:
			raise ValidationError( 'Send the masks as multipart/form-data files named "masks".' )
		photos = { p.name: p for p in recon.photos.all() }
		by_stem = { os.path.splitext( n )[0]: p for n, p in photos.items() }
		matched, unmatched = [], []
		for f in files:
			name = os.path.basename( f.name )
			base = name[:-4] if name.lower().endswith( '.png' ) else None
			photo = photos.get( base ) or by_stem.get( base ) if base else None
			if photo is None:
				unmatched.append( name )
				continue
			photo.mask.name = _replace( _mask_path( photo, name ), f )
			photo.save( update_fields = [ 'mask' ] )
			matched.append( photo.name )
		if matched:
			_changed( recon )
		return Response( { 'matched': matched, 'unmatched': unmatched }, status = status.HTTP_201_CREATED if matched else status.HTTP_400_BAD_REQUEST )

	@extend_schema( request = { 'multipart/form-data': { 'type': 'object', 'properties': { 'file': { 'type': 'string', 'format': 'binary' } } } } )
	@action( detail = True, methods = [ 'post', 'delete' ] )
	def poses( self, request, pk = None ):
		"""Camera centres ("name x y z") or full COLMAP poses ("name qw qx qy qz tx ty tz", world to camera), one photo per line."""
		recon = self._editable()
		if request.method == 'DELETE':
			if recon.poses:
				recon.poses.delete( save = True )
				_changed( recon )
			return Response( status = status.HTTP_204_NO_CONTENT )
		upload = request.FILES.get( 'file' )
		if upload is None:
			raise ValidationError( 'Send the poses as a multipart/form-data file named "file".' )
		if upload.size > 10 * 2 ** 20:
			raise ValidationError( 'The poses file is larger than 10 MB.' )
		centres, full = _read_poses_upload( upload )
		upload.seek( 0 )
		if recon.poses:
			recon.poses.delete( save = False )
		recon.poses.save( 'poses.txt', upload, save = True )
		_changed( recon )
		return Response( { 'poses': len( centres ), 'kind': 'full poses' if full else 'camera centres' }, status = status.HTTP_201_CREATED )

	# --- running ------------------------------------------------------------------

	@extend_schema( request = None, responses = { 202: JobSerializer, 400: OpenApiResponse( description = 'Not ready to run' ),
		409: OpenApiResponse( description = 'A job is in progress' ) } )
	@action( detail = True, methods = [ 'post' ] )
	def start( self, request, pk = None ):
		"""Queue the reconstruction; a retry after a failure resumes after the last finished stage."""
		recon = self._editable()
		_check_ready( recon )
		recon.cancel_requested = False
		recon.save( update_fields = [ 'cancel_requested' ] )
		try:
			job = start_job( recon.model, 'reconstruction' )
		except JobConflict:
			raise JobInProgress() from None
		return Response( JobSerializer( job ).data, status = status.HTTP_202_ACCEPTED )

	@extend_schema( request = None, responses = { 202: JobSerializer, 409: OpenApiResponse( description = 'No reconstruction job to cancel' ) } )
	@action( detail = True, methods = [ 'post' ] )
	def cancel( self, request, pk = None ):
		"""Stop the reconstruction job: a queued one at once, a running one within seconds (its checkpoints are kept)."""
		recon = self.get_object()
		job = recon.model.jobs.filter( status__in = ACTIVE ).first()
		if job is None or job.kind != 'reconstruction':
			return Response( { 'detail': 'No reconstruction is in progress.' }, status = status.HTTP_409_CONFLICT )
		recon.cancel_requested = True
		recon.save( update_fields = [ 'cancel_requested' ] )
		with transaction.atomic():
			job = Job.objects.select_for_update().get( pk = job.pk )
			if job.status == Job.Status.QUEUED:
				mark_finished( job, error = 'Cancelled.' )
		return Response( JobSerializer( job ).data, status = status.HTTP_202_ACCEPTED )


def _read_poses_upload( upload ):
	with tempfile.NamedTemporaryFile( suffix = '.txt' ) as tmp:
		for chunk in upload.chunks():
			tmp.write( chunk )
		tmp.flush()
		try:
			return ci.read_poses( tmp.name )
		except ci.PoseFileError as exc:
			raise ValidationError( { 'file': f'Camera poses file: {exc}.' } ) from None


def _check_ready( recon ):
	"""Catch what would make the job fail at once, with a message that says what to do."""
	uploaded = set( recon.photos.filter( uploaded = True ).values_list( 'name', flat = True ) )
	pending = recon.photos.filter( uploaded = False ).count()
	if pending:
		raise ValidationError( f'{pending} photos are still uploading; confirm or remove them first.' )
	if len( uploaded ) < settings.RECONSTRUCTION_MIN_PHOTOS:
		raise ValidationError( f'At least {settings.RECONSTRUCTION_MIN_PHOTOS} photos are needed; {len( uploaded )} uploaded.' )
	if recon.poses:
		with recon.poses.open( 'rb' ) as f:
			centres, full = _read_poses_upload( f )
		named = uploaded & set( centres )
		if full and named != uploaded:
			missing = sorted( uploaded - named )
			raise ValidationError( f'The full poses file has no pose for {len( missing )} photos, for example {", ".join( missing[:5] )}. '
				'Add them, remove those photos, or upload camera centres only.' )
		if len( named ) < 3:
			raise ValidationError( f'The poses file names only {len( named )} of the uploaded photos; at least 3 are needed. '
				'The names must match the photo file names.' )


routes = [ ( 'reconstructions', ReconstructionViewSet, 'reconstruction' ) ]
