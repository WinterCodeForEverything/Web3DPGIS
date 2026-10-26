"""The reconstruction job: photos → textured mesh (stages.Pipeline) → model.zip, then a tiling job builds the 3D Tiles.

Checkpoints: the pipeline marks each finished stage in its work folder, and a retry resumes after the last one. On local
storage the work folder is recon/<id>/work/ in the media folder itself; with S3 storage it is a local folder that is
copied to recon/<id>/work/ after every stage and restored from there, so another worker can carry on.
"""
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.files.storage import default_storage
from django.utils import timezone

from core import storage
from core.geoid import geoid_height
from processing.errors import PipelineError, TransientError
from processing.jobs import start_job
from processing.tiling import TILING_HINTS

from .models import Reconstruction
from .stages import PRESETS, STAGES, Cancelled, Options, OutOfMemory, Pipeline, ReconstructionError, TemporaryError, Tools

# after running out of memory twice at smaller sizes, more of the same will not help
MAX_RESOLUTION_SHIFT = 2
CANCEL_CHECK_SECONDS = 5
# settings that belong to the worker, not to the user's request
WORKER_OPTIONS = ( 'max_image_size', 'use_gpu', 'seam_leveling', 'resolution_shift', 'poses', 'masks', 'placement', 'count', 'preset' )


def tools():
	return Tools( colmap = settings.RECONSTRUCTION_COLMAP, openmvs = settings.RECONSTRUCTION_TOOLS_DIR / 'openmvs',
		obj2tiles = settings.RECONSTRUCTION_TOOLS_DIR / 'obj2tiles' / 'Obj2Tiles' )


def local_folders( recon ):
	"""( photos, masks, inputs, work ) folders the pipeline runs on."""
	if storage.is_local_storage():
		root = Path( default_storage.path( recon.prefix ) )
	else:
		root = Path( settings.RECONSTRUCTION_WORK_DIR ) / str( recon.pk )
	return root / 'photos', root / 'masks', root / 'inputs', root / 'work'


def clear_checkpoints( recon ):
	"""Forget finished stages, e.g. after the photos or options changed."""
	*_, work = local_folders( recon )
	shutil.rmtree( work, ignore_errors = True )
	if not storage.is_local_storage():
		storage.delete_prefix( f'{recon.prefix}/work' )


def _download_inputs( recon, photos, masks, inputs, report ):
	"""S3 storage: fetch the photos, masks and poses file the worker does not have yet."""
	fetched = 0
	for photo in recon.photos.filter( uploaded = True ):
		for field, folder, name in ( ( photo.file, photos, photo.name ), ( photo.mask, masks, f'{photo.name}.png' ) ):
			target = folder / name
			if field and not ( target.exists() and target.stat().st_size == field.size ):
				folder.mkdir( parents = True, exist_ok = True )
				with field.open( 'rb' ) as src, open( target, 'wb' ) as dst:
					shutil.copyfileobj( src, dst, 1024 * 1024 )
				fetched += 1
	if recon.poses:
		inputs.mkdir( parents = True, exist_ok = True )
		storage.local_copy( recon.poses, inputs )
	if fetched:
		report.log( f'Downloaded {fetched} photos and masks' )


def _restore_images( photos, work ):
	"""work/images holds links to the photos; it is not copied to storage, so it is rebuilt after a restore."""
	images = work / 'images'
	if ( work / 'prepare.done' ).exists() and images.exists():
		return
	if ( work / 'prepare.done' ).exists():
		images.mkdir()
		for p in photos.iterdir():
			os.link( p, images / p.name )


def _options( recon, model, masks, poses ):
	"""The user's camera options (validated by the API) plus what this worker and the stored inputs decide."""
	values = { k: v for k, v in recon.options.items() if k not in WORKER_OPTIONS }
	if 'gps_std' in values:
		values['gps_std'] = tuple( values['gps_std'] )
	return Options.from_dict( { **values, 'preset': recon.preset, 'resolution_shift': recon.resolution_shift,
		'max_image_size': settings.RECONSTRUCTION_MAX_IMAGE_SIZE, 'use_gpu': settings.RECONSTRUCTION_USE_GPU,
		'seam_leveling': settings.RECONSTRUCTION_SEAM_LEVELING, 'poses': poses,
		'masks': masks if recon.photos.exclude( mask = '' ).exists() else None,
		'placement': tuple( model.origin.coords ) if model.origin else None } )


def _cancel_check( recon ):
	"""cancelled() for the pipeline: reads the flag from the database at most every CANCEL_CHECK_SECONDS."""
	state = { 'at': 0.0, 'value': False }

	def cancelled():
		if time.monotonic() - state['at'] >= CANCEL_CHECK_SECONDS:
			state['at'] = time.monotonic()
			state['value'] = Reconstruction.objects.filter( pk = recon.pk, cancel_requested = True ).exists()
		return state['value']
	return cancelled


def _forget_partial_output( work, stage ):
	"""Before trying a stage again at a lower resolution, drop what it left at the old one."""
	if stage == 'features':
		( work / 'database.db' ).unlink( missing_ok = True )
	elif stage in ( 'undistort', 'densify' ):
		for f in ( work / 'dense' ).glob( '*.dmap' ):
			f.unlink()


def _publish_result( recon, model, work ):
	"""Zip result/ (model.obj, its material and textures, plus tiling hints) into recon/<id>/result/model.zip and make it the model's source."""
	archive = work / 'model.zip'
	with zipfile.ZipFile( archive, 'w', zipfile.ZIP_DEFLATED ) as z:
		for f in sorted( ( work / 'result' ).iterdir() ):
			z.write( f, f.name )
		# the preset's levels of detail, for the tiling job when the mesh is large enough for them
		z.writestr( TILING_HINTS, json.dumps( { 'lods': PRESETS[ recon.preset ]['lods'] } ) )
	name = f'{recon.prefix}/result/model.zip'
	if default_storage.exists( name ):
		default_storage.delete( name )
	with open( archive, 'rb' ) as src:
		model.source_file.name = default_storage.save( name, src )   # not source_file.save(), which would put it under package/
	archive.unlink()


def run_reconstruction( job, report ):
	model = job.model
	recon = Reconstruction.objects.get( model = model )
	if recon.cancel_requested:
		raise PipelineError( 'Cancelled.' )
	remote = not storage.is_local_storage()
	photos, masks, inputs, work = local_folders( recon )
	if remote:
		if not ( work / 'report.json' ).exists() and storage.download_prefix( f'{recon.prefix}/work', work ):
			report.log( 'Restored the checkpoints of an earlier attempt' )
		_download_inputs( recon, photos, masks, inputs, report )
		_restore_images( photos, work )
	poses = ( inputs / 'poses.txt' if remote else Path( recon.poses.path ) ) if recon.poses else None
	recon.started_at = recon.started_at or timezone.now()
	recon.save( update_fields = [ 'started_at' ] )

	def stage_done( name ):
		if remote:
			storage.upload_directory( work, f'{recon.prefix}/work', skip = ( 'images', ) )

	pipeline = Pipeline( photos, work, tools(), _options( recon, model, masks, poses ), log = report.log,
		progress = lambda stage, fraction: report.step( stage, round( fraction * 100 ) ), cancelled = _cancel_check( recon ),
		geoid = lambda lon, lat: geoid_height( lon, lat, settings.RECONSTRUCTION_GEOID_GRID, settings.RECONSTRUCTION_GEOID_DOWNLOAD ),
		on_stage_done = stage_done )
	try:
		result = pipeline.run()
	except OutOfMemory as exc:
		if recon.resolution_shift >= MAX_RESOLUTION_SHIFT:
			raise PipelineError( f'{exc}, even at a lower resolution. Try the preview preset or fewer photos, or run it on a worker '
				'with more memory.' ) from None
		recon.resolution_shift += 1
		recon.save( update_fields = [ 'resolution_shift' ] )
		_forget_partial_output( work, exc.stage )
		raise TransientError( f'{exc}; trying again at a lower resolution' ) from None
	except Cancelled:
		raise PipelineError( 'Cancelled.' ) from None
	except ReconstructionError as exc:
		raise PipelineError( str( exc ) ) from None
	except TemporaryError as exc:
		raise TransientError( str( exc ) ) from None
	finally:
		_save_stats( recon, pipeline.report )

	report.step( 'publishing the mesh', 99 )
	_publish_result( recon, model, work )
	# the mesh's (0, 0, 0): the GPS origin, or the placement the user gave; tiling anchors it there on every run
	placement = result.get( 'placement' ) or ( tuple( model.origin.coords ) if model.origin else settings.DEFAULT_MODEL_LOCATION )
	model.origin = model.location = Point( *( list( placement ) + [ 0.0 ] )[:3], srid = 4326 )
	model.save( update_fields = [ 'source_file', 'origin', 'location', 'updated_at' ] )
	start_job( model, 'tiling', follow_up_of = job )
	clear_checkpoints( recon )
	if remote:
		shutil.rmtree( work.parent, ignore_errors = True )


def _save_stats( recon, result ):
	keys = ( 'photos', 'photos_with_gps', 'masks', 'registered_photos', 'reprojection_error_px', 'position_residual_median',
		'position_outliers', 'points', 'scale', 'georeferenced', 'geoid_corrected', 'total_seconds', 'result_mb' )
	recon.mode = result.get( 'mode', '' )
	recon.stats = { **{ k: result[ k ] for k in keys if k in result },
		'stages': { s: result['stages'][ s ]['seconds'] for s in STAGES if s in result.get( 'stages', {} ) } }
	recon.save( update_fields = [ 'mode', 'stats' ] )
