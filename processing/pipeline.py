"""The processing pipeline: turn an uploaded file into a georeferenced 3D Tiles tileset.

start_processing() is called by the API; run_job() does the work inside a Celery worker.
"""
import json
import os
import shutil
import tempfile

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from . import converters, storage
from .archives import ARCHIVE_EXTENSIONS, Limits, ensure_free_space, extract, is_archive
from .errors import PipelineError
from .geodesy import enu_to_ecef_matrix
from .tilesets import find_tileset, tileset_location

MESH_EXTENSIONS = {
	'.glb': 'glb',
	'.gltf': 'gltf',
	'.obj': 'obj',
	'.fbx': 'assimp', '.dae': 'assimp', '.3ds': 'assimp', '.ply': 'assimp', '.stl': 'assimp',
}
POINTCLOUD_EXTENSIONS = ( '.las', '.laz' )
SUPPORTED_EXTENSIONS = ARCHIVE_EXTENSIONS + tuple( MESH_EXTENSIONS ) + POINTCLOUD_EXTENSIONS


def tiles_dir( model ):
	"""Storage prefix holding a model's tileset."""
	return f'tiles/{model.pk}'


def start_processing( model ):
	"""Create a Job for model and queue it once the current transaction commits."""
	from .models import Job
	from .tasks import process_job

	job = Job.objects.create( model = model, stage = 'queued' )
	model.status = model.Status.PENDING
	model.save( update_fields = [ 'status', 'updated_at' ] )
	transaction.on_commit( lambda: process_job.delay( job.pk ) )
	return job


class JobReporter:
	"""Writes progress, stage and log lines to the Job row as the pipeline runs."""

	def __init__( self, job ):
		self.job = job

	def step( self, stage, progress ):
		self.job.stage, self.job.progress = stage, progress
		self.job.save( update_fields = [ 'stage', 'progress' ] )

	def log( self, text ):
		self.job.log = ( self.job.log + text.rstrip() + '\n' )[-100_000:]
		self.job.save( update_fields = [ 'log' ] )


def _find_first( directory, extensions ):
	for root, dirs, files in sorted( os.walk( directory ) ):
		dirs.sort()
		for name in sorted( files ):
			if name.lower().endswith( extensions ):
				return os.path.join( root, name )
	return None


def _wrap_local_tileset( tileset, out_dir, location ):
	"""Place a tileset that has no georeference by pointing a new root tileset at it with a transform."""
	with open( tileset, encoding = 'utf-8' ) as f:
		inner = json.load( f )
	inner_root = inner.get( 'root', {} )
	wrapper = {
		'asset': { 'version': inner.get( 'asset', {} ).get( 'version', '1.0' ) },
		'geometricError': inner.get( 'geometricError', 500 ),
		'root': {
			'transform': enu_to_ecef_matrix( *location ),
			'boundingVolume': inner_root.get( 'boundingVolume' ),
			'geometricError': inner.get( 'geometricError', 500 ),
			'refine': 'ADD',
			'content': { 'uri': os.path.relpath( tileset, out_dir ).replace( os.sep, '/' ) },
		},
	}
	path = os.path.join( out_dir, 'tileset.root.json' )
	with open( path, 'w', encoding = 'utf-8' ) as f:
		json.dump( wrapper, f )
	return path


def run_job( job ):
	"""Run the whole pipeline for job; raises on failure (the task records it)."""
	model = job.model
	report = JobReporter( job )
	placement = model.location.coords if model.location else settings.DEFAULT_MODEL_LOCATION
	if len( placement ) == 2:
		placement = ( *placement, 0.0 )

	# everything is built in a local temp folder (converters need real files), then published to storage
	work = tempfile.mkdtemp( prefix = f'job{job.pk}-', dir = settings.PIPELINE_WORK_DIR )
	out_dir = os.path.join( work, 'out' )
	try:
		report.step( 'preparing input', 5 )
		if not model.source_file or not model.source_file.storage.exists( model.source_file.name ):
			raise PipelineError( 'The uploaded file is missing; please upload it again.' )
		limits = Limits.from_settings()
		input_dir = os.path.join( work, 'input' )
		archive = is_archive( model.source_file.name )
		if storage.is_local( model.source_file.storage ):
			source = model.source_file.path
			if not archive:
				ensure_free_space( work, os.path.getsize( source ), limits )
				os.makedirs( input_dir )
				shutil.copy( source, input_dir )
		else:
			# a single model file is downloaded straight into the input folder; an archive next to it
			ensure_free_space( work, model.source_file.size, limits )
			report.log( f'Downloading {os.path.basename( model.source_file.name )}' )
			source = storage.local_copy( model.source_file, os.path.join( work, 'download' ) if archive else input_dir )
		if archive:
			report.log( f'Extracting {os.path.basename( source )}' )
			extract( source, input_dir, limits )

		tileset = find_tileset( input_dir )
		if tileset:
			report.step( 'copying 3D Tiles', 40 )
			report.log( f'Found 3D Tiles: {os.path.relpath( tileset, input_dir )}' )
			shutil.copytree( os.path.dirname( tileset ), out_dir )
			tileset = os.path.join( out_dir, 'tileset.json' )
			if tileset_location( tileset ) is None:
				report.log( 'Tileset has no georeference; placing it at ' + ', '.join( f'{v:.6f}' for v in placement ) )
				tileset = _wrap_local_tileset( tileset, out_dir, placement )
		elif ( cloud := _find_first( input_dir, POINTCLOUD_EXTENSIONS ) ):
			report.step( 'tiling point cloud', 30 )
			converters.pointcloud_to_tileset( cloud, out_dir, model.source_srs, report.log )
			tileset = os.path.join( out_dir, 'tileset.json' )
		elif ( mesh := _find_first( input_dir, tuple( MESH_EXTENSIONS ) ) ):
			kind = MESH_EXTENSIONS[ os.path.splitext( mesh )[1].lower() ]
			glb = os.path.join( work, 'model.glb' )
			report.step( f'converting {kind.upper()} to glTF', 30 )
			if kind == 'glb':
				shutil.copy( mesh, glb )
			elif kind == 'gltf':
				converters.gltf_to_glb( mesh, glb, report.log )
			elif kind == 'obj':
				converters.obj_to_glb( mesh, glb, report.log )
			else:
				converters.assimp_to_glb( mesh, glb, report.log )
			report.step( 'building tileset', 70 )
			converters.glb_to_tileset( glb, out_dir, placement, report.log )
			tileset = os.path.join( out_dir, 'tileset.json' )
		else:
			raise converters.ConversionError( 'No 3D Tiles, model or point-cloud file found in the upload. Supported: ' + ', '.join( SUPPORTED_EXTENSIONS ) )

		report.step( 'finishing', 95 )
		location = tileset_location( tileset )
		if location is None and os.path.basename( tileset ) != 'tileset.root.json':
			raise converters.ConversionError( 'The generated tileset has no position on the globe.' )
		report.step( 'publishing tiles', 97 )
		prefix = tiles_dir( model )
		storage.publish_directory( out_dir, prefix, report.log )
		model.tileset_path = prefix + '/' + os.path.relpath( tileset, out_dir ).replace( os.sep, '/' )
		model.location = Point( *( location or placement ), srid = 4326 )
		model.status = model.Status.READY
		model.save( update_fields = [ 'tileset_path', 'location', 'status', 'updated_at' ] )
		report.log( f'Tileset ready: {model.tileset_path}' )
	finally:
		shutil.rmtree( work, ignore_errors = True )


def mark_started( job ):
	job.attempts += 1
	job.status, job.started_at, job.progress = job.Status.RUNNING, timezone.now(), 0
	job.save( update_fields = [ 'status', 'started_at', 'progress', 'attempts' ] )
	job.model.status = job.model.Status.PROCESSING
	job.model.save( update_fields = [ 'status', 'updated_at' ] )


def mark_retrying( job, error, delay, max_attempts ):
	"""A temporary failure: put the job back in the queue and say when it runs again."""
	job.status, job.stage = job.Status.QUEUED, 'waiting to retry'
	job.message = f'Temporary problem: {str( error ).rstrip( "." )}. Retrying in {delay} s (attempt {job.attempts + 1} of {max_attempts}).'
	job.log = ( job.log + f'Attempt {job.attempts} failed: {error}\n' )[-100_000:]
	job.save( update_fields = [ 'status', 'stage', 'message', 'log' ] )
	job.model.status = job.model.Status.PENDING
	job.model.save( update_fields = [ 'status', 'updated_at' ] )


def mark_finished( job, error = None ):
	job.finished_at = timezone.now()
	if error is None:
		job.status, job.progress, job.stage, job.message = job.Status.SUCCEEDED, 100, 'done', 'Ready to view.'
	else:
		job.status, job.message = job.Status.FAILED, str( error )
		job.model.status = job.model.Status.FAILED
		job.model.save( update_fields = [ 'status', 'updated_at' ] )
	job.save()
