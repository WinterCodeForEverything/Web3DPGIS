"""End-to-end pipeline tests: upload through the API, run the real converters, check the tileset."""
import json
import math
import os
import errno
import io
import shutil
import tarfile
import tempfile
import zipfile
from collections import namedtuple
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Model3D

from . import pipeline, storage, test_fixtures
from .converters import ConversionError, _run
from .errors import TransientError, is_transient
from .geodesy import ecef_to_geodetic
from .tilesets import tileset_location

GUANGZHOU = { 'longitude': 113.26, 'latitude': 23.13, 'height': 15.0 }


@override_settings( CELERY_TASK_ALWAYS_EAGER = True )
class PipelineTestBase( TestCase ):
	"""Temporary MEDIA_ROOT, a signed-in user, and helpers to upload and check results."""

	@classmethod
	def setUpClass( cls ):
		super().setUpClass()
		cls._media = tempfile.mkdtemp()
		cls._override = override_settings( MEDIA_ROOT = cls._media )
		cls._override.enable()

	@classmethod
	def tearDownClass( cls ):
		cls._override.disable()
		shutil.rmtree( cls._media, ignore_errors = True )
		super().tearDownClass()

	def setUp( self ):
		self.user = User.objects.create_user( 'alice', 'alice@example.com', 'Sm0ke-pass-1' )
		self.client = APIClient()
		self.client.force_authenticate( self.user )

	def upload( self, filename, data, **fields ):
		payload = { 'name': filename, 'source_file': SimpleUploadedFile( filename, data ) }
		for key, value in fields.items():
			payload[key] = json.dumps( value ) if isinstance( value, dict ) else value
		with self.captureOnCommitCallbacks( execute = True ):
			r = self.client.post( '/api/v1/models/', payload, format = 'multipart' )
		self.assertEqual( r.status_code, 201, r.data )
		return Model3D.objects.get( pk = r.data['id'] )

	def assert_ready_near( self, model, lon, lat, tolerance_m = 50 ):
		job = model.jobs.get()
		self.assertEqual( ( model.status, job.status, job.progress ), ( 'ready', 'succeeded', 100 ), job.message + '\n' + job.log )
		self.assertTrue( default_storage.exists( model.tileset_path ), model.tileset_path )
		tileset = default_storage.path( model.tileset_path ) if storage.is_local_storage() else model.tileset_path
		got_lon, got_lat, _ = model.location.coords
		dx = ( got_lon - lon ) * 111320 * math.cos( math.radians( lat ) )
		dy = ( got_lat - lat ) * 110540
		self.assertLess( math.hypot( dx, dy ), tolerance_m, model.location.coords )
		self.assertEqual( model.tileset_url, default_storage.url( model.tileset_path ) )
		return tileset


class PipelineTests( PipelineTestBase ):
	def test_georeferenced_3d_tiles_keep_their_position( self ):
		model = self.upload( 'beijing.zip', test_fixtures.tiles_zip( lon = 116.4, lat = 39.9 ), placement = GUANGZHOU )
		self.assert_ready_near( model, 116.4, 39.9 )
		self.assertTrue( model.tileset_path.startswith( f'tiles/{model.pk}/' ) )

	def test_local_3d_tiles_are_placed( self ):
		model = self.upload( 'local.zip', test_fixtures.tiles_zip(), placement = GUANGZHOU )
		tileset = self.assert_ready_near( model, 113.26, 23.13 )
		self.assertTrue( tileset.endswith( 'tileset.root.json' ) )

	def test_glb( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle(), placement = GUANGZHOU )
		tileset = self.assert_ready_near( model, 113.26, 23.13 )
		with open( tileset ) as f:
			self.assertEqual( json.load( f )['root']['content']['uri'], 'model.glb' )

	def test_obj_with_obj2gltf( self ):
		self.assert_ready_near( self.upload( 'cube.obj', test_fixtures.obj_cube(), placement = GUANGZHOU ), 113.26, 23.13 )

	def test_ply_with_assimp( self ):
		self.assert_ready_near( self.upload( 'cube.ply', test_fixtures.ply_cube(), placement = GUANGZHOU ), 113.26, 23.13 )

	def test_zipped_obj( self ):
		data = test_fixtures.zip_of( { 'export/readme.txt': b'hi', 'export/cube.obj': test_fixtures.obj_cube() } )
		self.assert_ready_near( self.upload( 'export.zip', data, placement = GUANGZHOU ), 113.26, 23.13 )

	def test_default_location_when_no_placement( self ):
		with self.settings( DEFAULT_MODEL_LOCATION = ( -75.16, 39.95, 0.0 ) ):
			self.assert_ready_near( self.upload( 'tri.glb', test_fixtures.glb_triangle() ), -75.16, 39.95 )

	def test_las_point_cloud_with_py3dtiles( self ):
		data = test_fixtures.las_points( 113.26, 23.13, 32649 )   # WGS 84 / UTM zone 49N
		model = self.upload( 'scan.las', data, source_srs = 'EPSG:32649' )
		self.assert_ready_near( model, 113.26, 23.13, tolerance_m = 30 )

	def test_upload_is_public_and_visible_unless_told_otherwise( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		self.assertEqual( ( model.is_public, model.is_visible ), ( True, True ) )
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle(), is_public = 'false' )
		self.assertEqual( ( model.is_public, model.is_visible ), ( False, True ) )

	def test_unsupported_extension_is_rejected( self ):
		r = self.client.post( '/api/v1/models/', { 'name': 'x', 'source_file': SimpleUploadedFile( 'notes.txt', b'x' ) }, format = 'multipart' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'source_file', r.data )

	def test_archive_without_models_fails_with_message( self ):
		model = self.upload( 'empty.zip', test_fixtures.zip_of( { 'readme.txt': b'nothing here' } ) )
		job = model.jobs.get()
		self.assertEqual( ( model.status, job.status ), ( 'failed', 'failed' ) )
		self.assertIn( 'No 3D Tiles, model or point-cloud file', job.message )
		self.assertEqual( job.attempts, 1 )   # bad input is never retried

	def test_zip_slip_is_blocked( self ):
		model = self.upload( 'evil.zip', test_fixtures.zip_of( { '../../escaped.txt': b'x', 'cube.obj': test_fixtures.obj_cube() } ) )
		self.assertEqual( model.status, 'failed' )
		self.assertIn( 'Unsafe path', model.jobs.get().message )
		self.assertFalse( os.path.exists( os.path.join( os.path.dirname( self._media ), 'escaped.txt' ) ) )

	def test_job_is_visible_to_owner_only( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		job_id = model.jobs.get().pk
		r = self.client.get( f'/api/v1/jobs/{job_id}/' )
		self.assertEqual( r.data['status'], 'succeeded' )
		self.assertIn( 'createTilesetJson', r.data['log'] )
		bob = APIClient()
		bob.force_authenticate( User.objects.create_user( 'bob', 'b@example.com', 'Sm0ke-pass-2' ) )
		self.assertEqual( bob.get( f'/api/v1/jobs/{job_id}/' ).status_code, 404 )

	def test_reprocess( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		with self.captureOnCommitCallbacks( execute = True ):
			r = self.client.post( f'/api/v1/models/{model.pk}/reprocess/' )
		self.assertEqual( r.status_code, 202 )
		self.assertEqual( model.jobs.count(), 2 )

	def test_delete_removes_files( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		source = model.source_file.path
		tiles = os.path.join( self._media, 'tiles', str( model.pk ) )
		self.assertTrue( os.path.exists( source ) and os.path.isdir( tiles ) )
		with self.captureOnCommitCallbacks( execute = True ):
			self.assertEqual( self.client.delete( f'/api/v1/models/{model.pk}/' ).status_code, 204 )
		self.assertFalse( os.path.exists( source ) or os.path.exists( tiles ) )


class GeodesyTests( TestCase ):
	def test_tileset_location_region( self ):
		with tempfile.NamedTemporaryFile( 'w', suffix = '.json', delete = False ) as f:
			json.dump( { 'root': { 'boundingVolume': { 'region': [ math.radians( 10 ), math.radians( 20 ), math.radians( 12 ), math.radians( 22 ), 0, 100 ] } } }, f )
		self.assertEqual( [ round( v, 6 ) for v in tileset_location( f.name ) ], [ 11.0, 21.0, 50.0 ] )
		os.remove( f.name )

	def test_poles_and_centre( self ):
		lon, lat, h = ecef_to_geodetic( 0, 0, 6356752.314245 + 100 )
		self.assertAlmostEqual( lat, 90 )
		self.assertAlmostEqual( h, 100, places = 3 )


def zeros_zip( size, name = 'model.obj' ):
	"""A zip whose one entry is `size` zero bytes: tiny when packed, the classic zip bomb shape."""
	buf = io.BytesIO()
	with zipfile.ZipFile( buf, 'w', zipfile.ZIP_DEFLATED ) as z:
		with z.open( name, 'w' ) as f:
			for _ in range( size // 65536 ):
				f.write( bytes( 65536 ) )
	return buf.getvalue()


DiskUsage = namedtuple( 'DiskUsage', 'total used free' )


# eager mode only re-runs a retried task when Retry is not re-raised to the caller
@override_settings( CELERY_TASK_ALWAYS_EAGER = True, CELERY_TASK_EAGER_PROPAGATES = False, PIPELINE_RETRY_BACKOFF = 0, PIPELINE_MAX_RETRIES = 3 )
class LimitsAndRetryTests( PipelineTestBase ):
	"""Archive limits are enforced before extraction; only temporary failures are retried."""

	def failed_job( self, model ):
		job = model.jobs.get()
		self.assertEqual( ( model.status, job.status ), ( 'failed', 'failed' ), job.message )
		return job

	@override_settings( PIPELINE_MAX_EXTRACTED_SIZE = 500_000 )
	def test_oversized_archive_fails_before_extracting( self ):
		with mock.patch( 'zipfile.ZipFile.extractall' ) as extractall:
			job = self.failed_job( self.upload( 'big.zip', zeros_zip( 1024 ** 2 ) ) )
		extractall.assert_not_called()
		self.assertIn( 'unpacks to 1.0 MB; the limit is 488.3 KB', job.message )
		self.assertEqual( job.attempts, 1 )

	@override_settings( PIPELINE_MAX_ARCHIVE_FILES = 5 )
	def test_too_many_files( self ):
		data = test_fixtures.zip_of( { f'part{i}.txt': b'x' for i in range( 10 ) } )
		self.assertIn( 'holds 10 files; the limit is 5', self.failed_job( self.upload( 'many.zip', data ) ).message )

	def test_zip_bomb_ratio( self ):
		with mock.patch( 'processing.archives.RATIO_CHECK_FROM', 1024 ):
			job = self.failed_job( self.upload( 'bomb.zip', zeros_zip( 2 * 1024 ** 2 ) ) )
		self.assertIn( 'zip bomb', job.message )

	def test_tar_gz_bomb_ratio( self ):
		buf = io.BytesIO()
		with tarfile.open( fileobj = buf, mode = 'w:gz' ) as tar:
			info = tarfile.TarInfo( 'model.obj' )
			info.size = 2 * 1024 ** 2
			tar.addfile( info, io.BytesIO( bytes( info.size ) ) )
		with mock.patch( 'processing.archives.RATIO_CHECK_FROM', 1024 ):
			job = self.failed_job( self.upload( 'bomb.tar.gz', buf.getvalue() ) )
		self.assertIn( 'zip bomb', job.message )

	def test_damaged_archive( self ):
		job = self.failed_job( self.upload( 'broken.zip', b'PK\x03\x04 not really a zip' ) )
		self.assertIn( 'damaged', job.message )
		self.assertEqual( job.attempts, 1 )

	def test_ordinary_archives_still_work( self ):
		self.assert_ready_near( self.upload( 'site.zip', test_fixtures.tiles_zip( lon = 116.4, lat = 39.9 ) ), 116.4, 39.9 )

	def test_temporary_failure_is_retried_then_succeeds( self ):
		real_run_job = pipeline.run_job
		calls = []

		def flaky( job ):
			calls.append( job.attempts )
			if len( calls ) == 1:
				raise TransientError( 'tool was stopped by signal 9' )
			return real_run_job( job )

		with mock.patch( 'processing.tasks.run_job', side_effect = flaky ):
			model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		job = model.jobs.get()
		self.assertEqual( ( model.status, job.status, job.attempts ), ( 'ready', 'succeeded', 2 ) )
		self.assertEqual( calls, [ 1, 2 ] )
		self.assertIn( 'Attempt 1 failed: tool was stopped by signal 9', job.log )

	def test_out_of_disk_space_retries_then_gives_up( self ):
		with mock.patch( 'processing.archives.shutil.disk_usage', return_value = DiskUsage( 10 ** 9, 10 ** 9, 1000 ) ):
			job = self.failed_job( self.upload( 'site.zip', test_fixtures.tiles_zip() ) )
		self.assertEqual( job.attempts, 4 )   # 1 try + PIPELINE_MAX_RETRIES
		self.assertIn( 'Not enough disk space', job.message )
		self.assertIn( 'gave up after 4 attempts', job.message )

	def test_retry_message_while_waiting( self ):
		job = self.upload( 'tri.glb', test_fixtures.glb_triangle() ).jobs.get()
		job.attempts = 1
		pipeline.mark_retrying( job, TransientError( 'database went away' ), 60, 4 )
		r = self.client.get( f'/api/v1/jobs/{job.pk}/' )
		self.assertEqual( ( r.data['status'], r.data['stage'], r.data['attempts'] ), ( 'queued', 'waiting to retry', 1 ) )
		self.assertIn( 'Retrying in 60 s (attempt 2 of 4)', r.data['message'] )


class ErrorClassificationTests( TestCase ):
	def test_is_transient( self ):
		self.assertTrue( is_transient( TransientError( 'x' ) ) )
		self.assertTrue( is_transient( OperationalError( 'connection lost' ) ) )
		self.assertTrue( is_transient( OSError( errno.ENOSPC, 'No space left on device' ) ) )
		self.assertFalse( is_transient( ConversionError( 'bad file' ) ) )
		self.assertFalse( is_transient( FileNotFoundError( 'gone' ) ) )
		self.assertFalse( is_transient( ValueError( 'bug' ) ) )

	def test_converter_killed_by_signal_is_transient( self ):
		with self.assertRaises( TransientError ):
			_run( [ 'sh', '-c', 'kill -9 $$' ], lambda text: None )

	def test_converter_error_exit_is_permanent( self ):
		with self.assertRaises( ConversionError ):
			_run( [ 'sh', '-c', 'exit 3' ], lambda text: None )


S3_STORAGES = {
	'default': { 'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
		'bucket_name': 'test-3dpgis', 'region_name': 'us-east-1', 'access_key': 'testing', 'secret_key': 'testing',
		'querystring_auth': False, 'default_acl': None, 'file_overwrite': False,
		'object_parameters': { 'CacheControl': 'public, max-age=86400' } } },
	'staticfiles': { 'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage' },
}


@override_settings( STORAGES = S3_STORAGES, STORAGE_BACKEND = 's3' )
class S3StorageTests( PipelineTestBase ):
	"""The same pipeline with an S3 bucket (moto's in-process S3) instead of the media folder."""

	def setUp( self ):
		from moto import mock_aws
		self.aws = mock_aws()
		self.aws.start()
		self.addCleanup( self.aws.stop )
		default_storage.connection.meta.client.create_bucket( Bucket = 'test-3dpgis' )
		super().setUp()

	def keys( self, prefix = '' ):
		return sorted( o.key for o in default_storage.bucket.objects.filter( Prefix = prefix ) )

	def head( self, key ):
		return default_storage.connection.meta.client.head_object( Bucket = 'test-3dpgis', Key = key )

	def test_upload_lives_in_the_bucket_and_tiles_are_published_there( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle(), placement = GUANGZHOU )
		self.assert_ready_near( model, 113.26, 23.13 )
		self.assertTrue( model.source_file.name.startswith( 'package/' ) )
		self.assertIn( model.source_file.name, self.keys( 'package/' ) )
		self.assertEqual( self.keys( f'tiles/{model.pk}/' ), [ f'tiles/{model.pk}/model.glb', f'tiles/{model.pk}/tileset.json' ] )
		self.assertEqual( model.tileset_url, f'https://test-3dpgis.s3.amazonaws.com/tiles/{model.pk}/tileset.json' )
		self.assertEqual( self.head( f'tiles/{model.pk}/tileset.json' )['ContentType'], 'application/json' )
		glb = self.head( f'tiles/{model.pk}/model.glb' )
		self.assertEqual( ( glb['ContentType'], glb['CacheControl'] ), ( 'model/gltf-binary', 'public, max-age=86400' ) )
		# nothing was written to the local media folder
		self.assertEqual( [ f for _, _, files in os.walk( self._media ) for f in files ], [] )

	def test_archive_is_downloaded_from_the_bucket( self ):
		model = self.upload( 'site.zip', test_fixtures.tiles_zip( lon = 116.4, lat = 39.9 ) )
		self.assert_ready_near( model, 116.4, 39.9 )
		self.assertIn( f'tiles/{model.pk}/tri.glb', self.keys( 'tiles/' ) )
		self.assertIn( 'Downloading site', model.jobs.get().log )

	def test_reprocess_replaces_old_tiles( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		default_storage.bucket.put_object( Key = f'tiles/{model.pk}/stale.b3dm', Body = b'old' )
		with self.captureOnCommitCallbacks( execute = True ):
			self.client.post( f'/api/v1/models/{model.pk}/reprocess/' )
		self.assertNotIn( f'tiles/{model.pk}/stale.b3dm', self.keys( 'tiles/' ) )
		self.assertIn( f'tiles/{model.pk}/tileset.json', self.keys( 'tiles/' ) )

	def test_delete_removes_upload_and_tiles_from_the_bucket( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		other = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		with self.captureOnCommitCallbacks( execute = True ):
			self.assertEqual( self.client.delete( f'/api/v1/models/{model.pk}/' ).status_code, 204 )
		self.assertEqual( self.keys( f'tiles/{model.pk}/' ), [] )
		self.assertNotIn( model.source_file.name, self.keys() )
		# the other model, uploaded under the same file name, is untouched
		self.assertIn( other.source_file.name, self.keys() )
		self.assertNotEqual( model.source_file.name, other.source_file.name )
		self.assertEqual( len( self.keys( f'tiles/{other.pk}/' ) ), 2 )

	def test_missing_upload_fails_clearly( self ):
		model = self.upload( 'tri.glb', test_fixtures.glb_triangle() )
		default_storage.delete( model.source_file.name )
		with self.captureOnCommitCallbacks( execute = True ):
			self.client.post( f'/api/v1/models/{model.pk}/reprocess/' )
		job = model.jobs.order_by( '-id' ).first()
		self.assertEqual( job.status, 'failed' )
		self.assertIn( 'uploaded file is missing', job.message )

	def test_setup_storage_creates_and_configures_the_bucket( self ):
		from django.core.management import call_command
		with self.settings( STORAGES = { **S3_STORAGES, 'default': { **S3_STORAGES['default'], 'OPTIONS': { **S3_STORAGES['default']['OPTIONS'], 'bucket_name': 'fresh-bucket' } } },
				STORAGE_CORS_ORIGINS = [ 'https://3d.example.com' ] ):
			out = io.StringIO()
			call_command( 'setup_storage', '--no-check', stdout = out )
			client = default_storage.connection.meta.client
			policy = json.loads( client.get_bucket_policy( Bucket = 'fresh-bucket' )['Policy'] )
			cors = client.get_bucket_cors( Bucket = 'fresh-bucket' )['CORSRules'][0]
		self.assertIn( 'Created bucket fresh-bucket', out.getvalue() )
		resources = policy['Statement'][0]['Resource']
		self.assertIn( 'arn:aws:s3:::fresh-bucket/tiles/*', resources )
		self.assertNotIn( 'arn:aws:s3:::fresh-bucket/package/*', resources )   # original uploads stay private
		self.assertEqual( ( cors['AllowedOrigins'], cors['AllowedMethods'] ), ( [ 'https://3d.example.com' ], [ 'GET', 'HEAD' ] ) )

	def test_copy_media_to_storage( self ):
		from django.core.management import call_command
		media = tempfile.mkdtemp()   # its own folder, so other tests still see an empty media root
		self.addCleanup( shutil.rmtree, media, True )
		for name, data in ( ( 'Data/old/inner/tileset.json', b'{}' ), ( 'image/a.png', b'png' ), ( 'tmp/scratch', b'x' ), ( 'package/.gitkeep', b'' ) ):
			path = os.path.join( media, name )
			os.makedirs( os.path.dirname( path ), exist_ok = True )
			with open( path, 'wb' ) as f:
				f.write( data )
		out = io.StringIO()
		with self.settings( MEDIA_ROOT = media ):
			call_command( 'copy_media_to_storage', stdout = out )
			self.assertEqual( self.keys(), [ 'Data/old/inner/tileset.json', 'image/a.png' ] )
			self.assertEqual( self.head( 'Data/old/inner/tileset.json' )['ContentType'], 'application/json' )
			call_command( 'copy_media_to_storage', stdout = out )
		self.assertIn( 'Copied 0 files', out.getvalue() )
