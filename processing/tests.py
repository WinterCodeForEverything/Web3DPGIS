"""End-to-end pipeline tests: upload through the API, run the real converters, check the tileset."""
import json
import math
import os
import errno
import io
import shutil
import tarfile
import tempfile
import time
import unittest
import zipfile
from collections import namedtuple
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Model3D

from core import storage
from core.geodesy import ecef_to_geodetic, enu_to_ecef_matrix

from . import converters, jobs, lod_tiling, tasks, test_fixtures, tiling
from .converters import ConversionError, _run
from .errors import TransientError, is_transient
from .models import Job
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
		real_run_job = jobs.run_job
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
		jobs.mark_retrying( job, TransientError( 'database went away' ), 60, 4 )
		r = self.client.get( f'/api/v1/jobs/{job.pk}/' )
		self.assertEqual( ( r.data['status'], r.data['stage'], r.data['attempts'] ), ( 'queued', 'waiting to retry', 1 ) )
		self.assertIn( 'Retrying in 60 s (attempt 2 of 4)', r.data['message'] )


class ExtensionPointTests( PipelineTestBase ):
	"""How another module plugs in: its own job kind that hands over to tiling, and new input formats."""

	def test_a_new_job_kind_can_hand_its_result_to_tiling( self ):
		# like reconstruction (registered under its own name): the job produces a mesh as the model's source, then the tiling job publishes it
		def reconstruct( job, report ):
			report.step( 'reconstructing', 50 )
			job.model.source_file.save( 'reconstructed.glb', ContentFile( test_fixtures.glb_triangle() ), save = True )
			jobs.start_job( job.model, 'tiling', follow_up_of = job )

		with mock.patch.dict( jobs._kinds ), mock.patch.object( tasks.process_job, 'apply_async', wraps = tasks.process_job.apply_async ) as queued:
			jobs.register_job_kind( 'photo-mesh', reconstruct, queue = 'gpu' )
			model = Model3D.objects.create( name = 'photos', owner = self.user, source_file = 'package/photos.zip' )
			with self.captureOnCommitCallbacks( execute = True ):
				jobs.start_job( model, 'photo-mesh' )
		model.refresh_from_db()
		self.assertEqual( [ ( j.kind, j.status ) for j in model.jobs.order_by( 'id' ) ], [ ( 'photo-mesh', 'succeeded' ), ( 'tiling', 'succeeded' ) ] )
		self.assertEqual( model.status, 'ready' )
		self.assertEqual( [ c.kwargs['queue'] for c in queued.call_args_list ], [ 'gpu', 'celery' ] )

	def test_unknown_job_kind( self ):
		model = Model3D.objects.create( name = 'x', owner = self.user, source_file = 'package/x.zip' )
		with self.assertRaisesMessage( LookupError, "No job kind 'nope'" ):
			jobs.start_job( model, 'nope' )

	def test_a_new_input_format_can_be_uploaded_and_tiled( self ):
		def build( src ):
			# pretend .tri files are GLB under another name
			glb = os.path.join( src.work_dir, 'model.glb' )
			shutil.copy( src.path, glb )
			converters.glb_to_tileset( glb, src.out_dir, src.placement, src.report.log )
			return os.path.join( src.out_dir, 'tileset.json' )

		with mock.patch.object( tiling, '_handlers', list( tiling._handlers ) ):
			tiling.register_input_handler( tiling.InputHandler( 'tri', ( '.tri', ), lambda d: tiling.find_first_file( d, ( '.tri', ) ), build ), before = 'mesh' )
			self.assertEqual( [ h.name for h in tiling.input_handlers() ], [ '3d-tiles', 'point-cloud', 'lod-mesh', 'tri', 'mesh' ] )
			model = self.upload( 'shape.tri', test_fixtures.glb_triangle(), placement = GUANGZHOU )
		self.assert_ready_near( model, 113.26, 23.13 )
		self.assertNotIn( '.tri', tiling.supported_extensions() )


def tile_names( tileset ):
	"""Content URIs of every tile under the tileset's root."""
	def walk( tile ):
		yield from ( [ tile['content']['uri'] ] if 'content' in tile else [] )
		for child in tile.get( 'children' ) or []:
			yield from walk( child )
	with open( tileset ) as f:
		return list( walk( json.load( f )['root'] ) )


@unittest.skipUnless( os.path.exists( settings.PIPELINE_OBJ2TILES or '/nonexistent' ), 'Obj2Tiles is not installed' )
@override_settings( PIPELINE_LOD_MIN_SIZE = 1 )
class LevelOfDetailTests( PipelineTestBase ):
	"""Large OBJ meshes go through Obj2Tiles; the threshold is set to 1 byte so a test cube counts as large."""

	def test_large_obj_gets_levels_of_detail( self ):
		model = self.upload( 'box.obj', test_fixtures.obj_tall_box(), placement = GUANGZHOU )
		tileset = self.assert_ready_near( model, 113.26, 23.13 )
		names = tile_names( tileset )
		self.assertTrue( any( n.startswith( 'LOD-0/' ) for n in names ) and any( n.startswith( 'LOD-1/' ) for n in names ), names )
		self.assertIn( 'levels of detail', model.jobs.get().log )
		self.assertNotIn( 'root.b3dm', names )   # the root has no content of its own: the coarsest level shows first
		self.assertFalse( os.path.exists( os.path.join( os.path.dirname( tileset ), 'root.b3dm' ) ) )

	def test_the_tileset_stands_upright( self ):
		# 2 m east, 4 m north, 10 m up; Obj2Tiles alone would lay it 10 m long towards the south
		work = tempfile.mkdtemp()
		self.addCleanup( shutil.rmtree, work, True )
		obj = os.path.join( work, 'box.obj' )
		with open( obj, 'wb' ) as f:
			f.write( test_fixtures.obj_tall_box() )
		tileset = lod_tiling.obj_to_lod_tileset( settings.PIPELINE_OBJ2TILES, obj, os.path.join( work, 'out' ), ( 113.26, 23.13, 0 ),
			log = lambda s: None, lods = 2, divisions = 1 )
		with open( tileset ) as f:
			root = json.load( f )['root']
		m, box, enu = root['transform'], root['boundingVolume']['box'], enu_to_ecef_matrix( 113.26, 23.13, 0 )
		axes = [ [ sum( m[ k * 4 + i ] * box[ 3 + 3 * j + k ] for k in range( 3 ) ) for i in range( 3 ) ] for j in range( 3 ) ]
		extent = [ round( sum( abs( sum( a[i] * enu[ c * 4 + i ] for i in range( 3 ) ) ) for a in axes ) * 2, 3 ) for c in range( 3 ) ]
		self.assertEqual( extent, [ 2, 4, 10 ] )   # east, north, up
		# errors from the mesh: the root about four triangle edges (≈ 4 × 6.5 m here), the tileset its diagonal
		with open( tileset ) as f:
			whole = json.load( f )
		self.assertLess( min( c['geometricError'] for c in root['children'] ), 20 )
		self.assertEqual( root['geometricError'], whole['geometricError'] )   # the empty root always refines
		self.assertAlmostEqual( whole['geometricError'], math.sqrt( 2 ** 2 + 4 ** 2 + 10 ** 2 ), places = 2 )
		# split horizontally: the root's children sit side by side at one height, not one above the other
		up = lambda c: sum( sum( m[ k * 4 + i ] * c[k] for k in range( 3 ) ) * enu[ 8 + i ] for i in range( 3 ) )
		heights = { round( up( child['boundingVolume']['box'][:3] ), 3 ) for child in root['children'] }
		self.assertEqual( ( len( root['children'] ), len( heights ) ), ( 4, 1 ) )

	def test_hints_next_to_the_mesh_set_the_levels( self ):
		data = test_fixtures.zip_of( { 'model.obj': test_fixtures.obj_tall_box(), 'tiling.json': b'{"lods": 2}' } )
		model = self.upload( 'mesh.zip', data, placement = GUANGZHOU )
		self.assert_ready_near( model, 113.26, 23.13 )
		self.assertIn( '--lods 2 ', model.jobs.get().log )

	@override_settings( PIPELINE_OBJ2TILES = '/nonexistent/Obj2Tiles' )
	def test_a_failure_falls_back_to_one_tile( self ):
		model = self.upload( 'box.obj', test_fixtures.obj_tall_box(), placement = GUANGZHOU )
		tileset = self.assert_ready_near( model, 113.26, 23.13 )
		self.assertEqual( tile_names( tileset ), [ 'model.glb' ] )
		self.assertIn( 'Levels of detail failed', model.jobs.get().log )

	@override_settings( PIPELINE_LOD_MIN_SIZE = 10 ** 9 )
	def test_small_meshes_stay_one_tile( self ):
		model = self.upload( 'box.obj', test_fixtures.obj_tall_box(), placement = GUANGZHOU )
		self.assertEqual( tile_names( self.assert_ready_near( model, 113.26, 23.13 ) ), [ 'model.glb' ] )


class YUpToZUpTests( TestCase ):
	def test_vertices_and_normals_turn_other_lines_stay( self ):
		work = tempfile.mkdtemp()
		self.addCleanup( shutil.rmtree, work, True )
		src, dst = os.path.join( work, 'a.obj' ), os.path.join( work, 'b.obj' )
		with open( src, 'w' ) as f:
			f.write( 'mtllib a.mtl\nv 1 2 3\nv 1.5 -2 -3 0.5 0.5 0.5\nvt 0.1 0.2\nvn 0 1 0\nf 1/1/1 2/1/1 1/1/1\n' )
		lod_tiling.y_up_to_z_up( src, dst )
		with open( dst ) as f:
			self.assertEqual( f.read(), 'mtllib a.mtl\nv 1 -3 2\nv 1.5 3 -2 0.5 0.5 0.5\nvt 0.1 0.2\nvn 0 -0 1\nf 1/1/1 2/1/1 1/1/1\n' )


class JobGuardTests( PipelineTestBase ):
	"""A job runs once: one queued or running job per model, and repeated deliveries of a task are dropped."""

	def make_model( self ):
		return Model3D.objects.create( name = 'site', owner = self.user, source_file = 'package/x.zip' )

	def test_one_job_per_model( self ):
		model = self.make_model()
		first = jobs.start_job( model, 'tiling' )
		with self.assertRaises( jobs.JobConflict ):
			jobs.start_job( model, 'tiling' )
		follow_up = jobs.start_job( model, 'tiling', follow_up_of = first )   # a job's own next step is allowed
		Job.objects.filter( pk__in = [ first.pk, follow_up.pk ] ).update( status = Job.Status.SUCCEEDED )
		self.assertEqual( jobs.start_job( model, 'tiling' ).status, Job.Status.QUEUED )

	def test_reprocess_refuses_while_a_job_is_in_progress( self ):
		model = self.make_model()
		Job.objects.create( model = model, status = Job.Status.RUNNING )
		r = self.client.post( f'/api/v1/models/{model.pk}/reprocess/' )
		self.assertEqual( r.status_code, 409, r.data )
		self.assertEqual( model.jobs.count(), 1 )

	def deliver( self, job ):
		with mock.patch( 'processing.tasks.run_job' ) as run:
			tasks.process_job.apply( args = ( job.pk, ) )
		return run

	def test_repeated_delivery_of_a_finished_job_is_ignored( self ):
		job = Job.objects.create( model = self.make_model(), status = Job.Status.SUCCEEDED, attempts = 1 )
		self.assertFalse( self.deliver( job ).called )
		job.refresh_from_db()
		self.assertEqual( ( job.status, job.attempts ), ( 'succeeded', 1 ) )

	def test_a_job_still_running_elsewhere_is_not_started_twice( self ):
		job = Job.objects.create( model = self.make_model(), status = Job.Status.RUNNING, attempts = 1, heartbeat_at = timezone.now() )
		self.assertFalse( self.deliver( job ).called )
		self.assertEqual( Job.objects.get( pk = job.pk ).attempts, 1 )

	def test_a_job_whose_worker_died_is_picked_up_again( self ):
		stale = timezone.now() - jobs.STALE_AFTER - timedelta( seconds = 1 )
		job = Job.objects.create( model = self.make_model(), status = Job.Status.RUNNING, attempts = 1, heartbeat_at = stale )
		self.assertTrue( self.deliver( job ).called )
		job.refresh_from_db()
		self.assertEqual( ( job.status, job.attempts ), ( 'succeeded', 2 ) )


class HeartbeatTests( TransactionTestCase ):
	"""The heartbeat thread uses its own database connection, so its writes need committed rows."""

	def test_heartbeat_is_written_while_the_job_runs( self ):
		user = User.objects.create_user( 'carol', 'carol@example.com', 'Sm0ke-pass-3' )
		model = Model3D.objects.create( name = 'site', owner = user, source_file = 'package/x.zip' )
		job = Job.objects.create( model = model, status = Job.Status.RUNNING )
		with mock.patch.object( jobs, 'HEARTBEAT_INTERVAL', timedelta( milliseconds = 20 ) ), jobs.Heartbeat( job ):
			time.sleep( 0.3 )
		self.assertIsNotNone( Job.objects.get( pk = job.pk ).heartbeat_at )


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
