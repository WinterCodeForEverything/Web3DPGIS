"""Reconstruction API and job wrapper, without running COLMAP or OpenMVS (the pipeline is replaced where a job runs)."""
import json
import os
import zipfile
from pathlib import Path
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from catalog.models import Model3D
from core.storage import list_prefix
from core.testing import APITestBase
from processing.errors import PipelineError, TransientError
from processing.jobs import JobReporter
from processing.models import Job

from . import job as recon_job
from .models import Reconstruction
from .stages import OutOfMemory, ReconstructionError

URL = '/api/v1/reconstructions/'


def photo( name, size = 100 ):
	return SimpleUploadedFile( name, b'\xff\xd8' + b'x' * ( size - 2 ), content_type = 'image/jpeg' )


def poses_file( lines ):
	return SimpleUploadedFile( 'poses.txt', '\n'.join( lines ).encode(), content_type = 'text/plain' )


class ReconstructionAPITests( APITestBase ):

	def setUp( self ):
		super().setUp()
		self.client = self.as_user( self.alice )

	def create( self, **data ):
		r = self.client.post( URL, { 'name': 'site', **data }, format = 'json' )
		self.assertEqual( r.status_code, 201, r.data )
		return r.data

	def upload( self, rid, *names ):
		return self.client.post( f'{URL}{rid}/photos/', { 'photos': [ photo( n ) for n in names ] }, format = 'multipart' )

	def test_create_makes_a_model_with_placement_and_default_options( self ):
		data = self.create( preset = 'preview', placement = { 'longitude': 113.26, 'latitude': 23.13, 'height': 5 } )
		model = Model3D.objects.get( pk = data['model'] )
		self.assertEqual( ( model.owner, model.name, model.location.coords ), ( self.alice, 'site', ( 113.26, 23.13, 5.0 ) ) )
		self.assertEqual( ( data['preset'], data['options']['camera_model'], data['options']['min_track'] ), ( 'preview', 'SIMPLE_RADIAL', 2 ) )
		self.assertEqual( data['photos'], { 'uploaded': 0, 'pending': 0, 'masks': 0 } )

	def test_intrinsics_are_checked_against_the_camera_model( self ):
		r = self.client.post( URL, { 'name': 's', 'options': { 'camera_model': 'PINHOLE', 'camera_params': [ 1, 2, 3 ] } }, format = 'json' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'PINHOLE takes 4 parameters', str( r.data ) )
		r = self.client.post( URL, { 'name': 's', 'options': { 'fix_intrinsics': True } }, format = 'json' )
		self.assertIn( 'need camera_params', str( r.data ) )
		data = self.create( options = { 'camera_model': 'PINHOLE', 'camera_params': [ 1000, 1000, 640, 480 ], 'fix_intrinsics': True } )
		self.assertEqual( data['options']['camera_params'], [ 1000.0, 1000.0, 640.0, 480.0 ] )
		self.assertEqual( Reconstruction.objects.get( pk = data['id'] ).options['camera_params'], '1000.0,1000.0,640.0,480.0' )

	def test_patching_options_keeps_the_others( self ):
		rid = self.create( options = { 'camera_model': 'PINHOLE', 'camera_params': [ 1, 1, 1, 1 ] } )['id']
		r = self.client.patch( f'{URL}{rid}/', { 'options': { 'min_track': 3 } }, format = 'json' )
		self.assertEqual( r.status_code, 200, r.data )
		self.assertEqual( ( r.data['options']['camera_model'], r.data['options']['min_track'] ), ( 'PINHOLE', 3 ) )

	def test_photos_are_stored_under_the_reconstruction( self ):
		rid = self.create()['id']
		r = self.upload( rid, 'a.jpg', 'b.JPG', 'c.png' )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( list_prefix( f'recon/{rid}/photos' ), [ f'recon/{rid}/photos/{n}' for n in ( 'a.jpg', 'b.JPG', 'c.png' ) ] )
		self.upload( rid, 'a.jpg' )   # the same name replaces the photo instead of adding a copy
		self.assertEqual( len( list_prefix( f'recon/{rid}/photos' ) ), 3 )
		self.assertEqual( self.upload( rid, 'notes.txt' ).status_code, 400 )
		r = self.client.delete( f'{URL}{rid}/photos/', { 'names': [ 'c.png' ] }, format = 'json' )
		self.assertEqual( r.data, { 'removed': 1 } )
		self.assertEqual( [ p['name'] for p in self.client.get( f'{URL}{rid}/photos/' ).data ], [ 'a.jpg', 'b.JPG' ] )

	@override_settings( RECONSTRUCTION_MAX_PHOTOS = 2, RECONSTRUCTION_MAX_PHOTO_SIZE = 1000 )
	def test_photo_limits( self ):
		rid = self.create()['id']
		self.assertIn( 'At most 2 photos', str( self.upload( rid, 'a.jpg', 'b.jpg', 'c.jpg' ).data ) )
		r = self.client.post( f'{URL}{rid}/photos/', { 'photos': [ photo( 'big.jpg', 2000 ) ] }, format = 'multipart' )
		self.assertIn( 'larger than', str( r.data ) )

	def test_presigned_uploads_need_s3_storage( self ):
		rid = self.create()['id']
		r = self.client.post( f'{URL}{rid}/photos/', { 'photos': [ { 'name': 'a.jpg', 'size': 10 } ] }, format = 'json' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'multipart', str( r.data ) )

	def test_masks_match_photos_by_name_or_stem( self ):
		rid = self.create()['id']
		self.upload( rid, 'a.jpg', 'b.jpg' )
		masks = [ SimpleUploadedFile( n, b'png', content_type = 'image/png' ) for n in ( 'a.jpg.png', 'b.png', 'zzz.png' ) ]
		r = self.client.post( f'{URL}{rid}/masks/', { 'masks': masks }, format = 'multipart' )
		self.assertEqual( ( r.data['matched'], r.data['unmatched'] ), ( [ 'a.jpg', 'b.jpg' ], [ 'zzz.png' ] ) )
		self.assertEqual( list_prefix( f'recon/{rid}/masks' ), [ f'recon/{rid}/masks/a.jpg.png', f'recon/{rid}/masks/b.jpg.png' ] )

	def test_poses_file_is_validated( self ):
		rid = self.create()['id']
		r = self.client.post( f'{URL}{rid}/poses/', { 'file': poses_file( [ 'a.jpg 1 2' ] ) }, format = 'multipart' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'line 1', str( r.data ) )
		r = self.client.post( f'{URL}{rid}/poses/', { 'file': poses_file( [ 'a.jpg 2 0 0 0 0 0 0', 'b.jpg 0 0 0', 'c.jpg 0 1 0' ] ) }, format = 'multipart' )
		self.assertIn( 'not a unit quaternion', str( r.data ) )
		r = self.client.post( f'{URL}{rid}/poses/', { 'file': poses_file( [ '# centres', 'a.jpg 0 0 0', 'b.jpg 1 0 0', 'c.jpg 2 0 0' ] ) }, format = 'multipart' )
		self.assertEqual( ( r.status_code, r.data ), ( 201, { 'poses': 3, 'kind': 'camera centres' } ) )
		self.assertEqual( list_prefix( f'recon/{rid}/inputs' ), [ f'recon/{rid}/inputs/poses.txt' ] )

	def test_start_says_what_is_missing( self ):
		rid = self.create()['id']
		self.upload( rid, 'a.jpg', 'b.jpg' )
		r = self.client.post( f'{URL}{rid}/start/' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'At least 3 photos', str( r.data ) )
		self.upload( rid, 'c.jpg', 'd.jpg' )
		self.client.post( f'{URL}{rid}/poses/', { 'file': poses_file( [ f'{n} 1 0 0 0 0 0 {i}' for i, n in enumerate( 'abc' ) ] ) }, format = 'multipart' )
		r = self.client.post( f'{URL}{rid}/start/' )
		self.assertIn( 'no pose for 4 photos', str( r.data ) )   # the names lack .jpg
		self.client.post( f'{URL}{rid}/poses/', { 'file': poses_file( [ 'a.jpg 0 0 0', 'x.jpg 1 0 0', 'y.jpg 2 0 0' ] ) }, format = 'multipart' )
		self.assertIn( 'names only 1 of the uploaded photos', str( self.client.post( f'{URL}{rid}/start/' ).data ) )

	def test_start_queues_one_job_then_edits_wait_and_cancel_stops_it( self ):
		rid = self.create()['id']
		self.upload( rid, 'a.jpg', 'b.jpg', 'c.jpg' )
		with mock.patch( 'processing.tasks.process_job.apply_async' ) as queued, self.captureOnCommitCallbacks( execute = True ):
			r = self.client.post( f'{URL}{rid}/start/' )
		self.assertEqual( ( r.status_code, r.data['kind'], r.data['status'] ), ( 202, 'reconstruction', 'queued' ) )
		self.assertEqual( queued.call_args.kwargs['queue'], 'reconstruction' )
		self.assertEqual( self.client.post( f'{URL}{rid}/start/' ).status_code, 409 )
		self.assertEqual( self.upload( rid, 'd.jpg' ).status_code, 409 )
		self.assertEqual( self.client.patch( f'{URL}{rid}/', { 'preset': 'high' }, format = 'json' ).status_code, 409 )
		r = self.client.post( f'{URL}{rid}/cancel/' )
		self.assertEqual( ( r.status_code, r.data['status'], r.data['message'] ), ( 202, 'failed', 'Cancelled.' ) )
		self.assertEqual( self.client.post( f'{URL}{rid}/cancel/' ).status_code, 409 )
		self.assertEqual( self.upload( rid, 'd.jpg' ).status_code, 201 )

	def test_only_the_owner_sees_a_reconstruction( self ):
		rid = self.create()['id']
		bob = self.as_user( self.bob )
		self.assertEqual( bob.get( f'{URL}{rid}/' ).status_code, 404 )
		self.assertEqual( bob.post( f'{URL}{rid}/photos/', { 'photos': [ photo( 'a.jpg' ) ] }, format = 'multipart' ).status_code, 404 )
		self.assertEqual( bob.get( URL ).data['results'] if isinstance( bob.get( URL ).data, dict ) else bob.get( URL ).data, [] )
		self.assertIn( self.client.__class__().post( URL, { 'name': 'x' }, format = 'json' ).status_code, ( 401, 403 ) )

	def test_limits_and_lookup_by_model( self ):
		limits = self.client.__class__().get( f'{URL}limits/' ).data
		self.assertEqual( ( limits['min_photos'], limits['direct_upload'], limits['camera_models']['OPENCV'] ), ( 3, False, 8 ) )
		self.assertEqual( set( limits['presets'] ), { 'preview', 'standard', 'high' } )
		data = self.create()
		self.create()
		self.assertEqual( [ r['id'] for r in self.client.get( f'{URL}?model={data["model"]}' ).data['results'] ], [ data['id'] ] )

	def test_a_draft_is_hidden_from_others_until_it_has_a_result( self ):
		data = self.create()   # public by default
		self.assertEqual( self.as_user( self.bob ).get( f'/api/v1/models/{data["model"]}/' ).status_code, 404 )
		self.assertEqual( self.client.get( f'/api/v1/models/{data["model"]}/' ).status_code, 200 )
		Model3D.objects.filter( pk = data['model'] ).update( source_file = f'recon/{data["id"]}/result/model.zip' )
		self.assertEqual( self.as_user( self.bob ).get( f'/api/v1/models/{data["model"]}/' ).status_code, 200 )

	def test_deleting_removes_the_model_and_files( self ):
		data = self.create()
		self.upload( data['id'], 'a.jpg' )
		with self.captureOnCommitCallbacks( execute = True ):
			self.assertEqual( self.client.delete( f'{URL}{data["id"]}/' ).status_code, 204 )
		self.assertFalse( Model3D.objects.filter( pk = data['model'] ).exists() )
		self.assertEqual( list_prefix( f'recon/{data["id"]}' ), [] )


class ReconstructionJobTests( APITestBase ):
	"""run_reconstruction with a stand-in for the pipeline."""

	def setUp( self ):
		super().setUp()
		self.model = Model3D.objects.create( name = 'site', owner = self.alice )
		self.recon = Reconstruction.objects.create( model = self.model, preset = 'preview', options = { 'gps_std': [ 2, 4 ], 'min_track': 3 } )
		for n in ( 'a.jpg', 'b.jpg', 'c.jpg' ):
			self.recon.photos.create( name = n, file = default_storage.save( f'recon/{self.recon.pk}/photos/{n}', photo( n ) ), uploaded = True )
		self.job = Job.objects.create( model = self.model, kind = 'reconstruction', status = Job.Status.RUNNING )

	def fake_pipeline( self, error = None ):
		test = self

		class FakePipeline:
			def __init__( self, images, work, tools, options, **kwargs ):
				test.seen = { 'images': images, 'work': work, 'options': options }
				self.work, self.report = Path( work ), { 'mode': 'gps', 'photos': 3, 'registered_photos': 3, 'stages': { 'prepare': { 'seconds': 1.0 } } }

			def run( self ):
				if error:
					raise error
				( self.work / 'result' ).mkdir( parents = True )
				( self.work / 'result' / 'model.obj' ).write_text( 'v 0 0 0\n' )
				( self.work / 'result' / 'model.mtl' ).write_text( '' )
				return { **self.report, 'placement': [ -83.8, 41.3, 250.0 ] }
		return mock.patch.object( recon_job, 'Pipeline', FakePipeline )

	def run_job( self ):
		with mock.patch.object( recon_job, 'start_job' ) as follow_up:
			recon_job.run_reconstruction( self.job, JobReporter( self.job ) )
		return follow_up

	def test_success_hands_a_zipped_mesh_to_tiling( self ):
		with self.fake_pipeline():
			follow_up = self.run_job()
		follow_up.assert_called_once_with( self.model, 'tiling', follow_up_of = self.job )
		self.model.refresh_from_db(); self.recon.refresh_from_db()
		self.assertEqual( self.model.source_file.name, f'recon/{self.recon.pk}/result/model.zip' )
		with zipfile.ZipFile( self.model.source_file.path ) as z:
			self.assertEqual( sorted( z.namelist() ), [ 'model.mtl', 'model.obj', 'tiling.json' ] )
			self.assertEqual( json.loads( z.read( 'tiling.json' ) ), { 'lods': 3 } )
		self.assertEqual( self.model.location.coords, ( -83.8, 41.3, 250.0 ) )
		self.assertEqual( self.model.origin.coords, ( -83.8, 41.3, 250.0 ) )   # tiling anchors the mesh here
		self.assertEqual( ( self.recon.mode, self.recon.stats['registered_photos'], self.recon.stats['stages'] ), ( 'gps', 3, { 'prepare': 1.0 } ) )
		options = self.seen['options']
		self.assertEqual( ( options.preset, options.gps_std, options.min_track, options.masks ), ( 'preview', ( 2, 4 ), 3, None ) )
		self.assertEqual( self.seen['images'], Path( default_storage.path( f'recon/{self.recon.pk}/photos' ) ) )
		self.assertFalse( os.path.exists( self.seen['work'] ), 'checkpoints are removed after success' )

	def test_out_of_memory_retries_smaller_then_gives_up( self ):
		with self.fake_pipeline( OutOfMemory( 'densify', 'DensifyPointCloud' ) ):
			for shift in ( 1, 2 ):
				with self.assertRaisesMessage( TransientError, 'trying again at a lower resolution' ):
					self.run_job()
				self.recon.refresh_from_db()
				self.assertEqual( self.recon.resolution_shift, shift )
			with self.assertRaisesMessage( PipelineError, 'even at a lower resolution' ):
				self.run_job()
		self.assertEqual( self.seen['options'].resolution_shift, 2 )
		self.assertEqual( self.seen['options'].image_size, round( 1600 * 0.49 ) )

	def test_input_problems_fail_with_the_pipelines_message( self ):
		with self.fake_pipeline( ReconstructionError( 'Only 1 of 3 photos could be placed.' ) ):
			with self.assertRaisesMessage( PipelineError, 'Only 1 of 3 photos could be placed.' ):
				self.run_job()
		self.recon.refresh_from_db()
		self.assertEqual( self.recon.mode, 'gps' )   # what was learned before the failure is kept

	def test_a_cancelled_reconstruction_does_not_start( self ):
		Reconstruction.objects.filter( pk = self.recon.pk ).update( cancel_requested = True )
		with self.fake_pipeline(), self.assertRaisesMessage( PipelineError, 'Cancelled.' ):
			self.run_job()
