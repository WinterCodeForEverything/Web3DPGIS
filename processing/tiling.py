"""The tiling job: turn a model's source file into a georeferenced 3D Tiles tileset and publish it.

The source is unpacked if it is an archive, then the first input handler that finds something it can use builds the
tileset. Handlers are tried in order: an existing 3D Tiles tileset, a point cloud, a large OBJ mesh (levels of detail,
lod_tiling.py), any other mesh (one tile). Another module can add one,
e.g. for a new file format:

    register_input_handler( InputHandler( 'e57', ( '.e57', ), find = …, build = … ), before = 'mesh' )
"""
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.contrib.gis.geos import Point

from core import storage
from core.geodesy import enu_to_ecef_matrix

from . import converters, lod_tiling
from .archives import ARCHIVE_EXTENSIONS, Limits, ensure_free_space, extract, is_archive
from .errors import PipelineError
from .jobs import JobReporter
from .tilesets import find_tileset, tileset_location


@dataclass( frozen = True )
class TilingInput:
	"""What an input handler gets to build a tileset from."""
	path: str                 # what the handler's find() returned
	input_dir: str            # the unpacked upload
	work_dir: str             # scratch space, removed after the job
	out_dir: str              # where the tileset goes; everything in it is published
	placement: tuple          # longitude, latitude, height for inputs without a georeference
	source_srs: str           # CRS of the source coordinates, if the user gave one
	report: JobReporter


@dataclass( frozen = True )
class InputHandler:
	name: str
	extensions: tuple[ str, ... ]                # single files of these types may be uploaded (archives always may)
	find: Callable[ [ str ], str | None ]        # the file to use in the unpacked input folder, or None
	build: Callable[ [ TilingInput ], str ]      # write the tileset into out_dir; return the path of its root JSON


_handlers: list[ InputHandler ] = []


def register_input_handler( handler, *, before = None ):
	"""Add an input handler; with `before`, it is tried ahead of the handler of that name."""
	if any( h.name == handler.name for h in _handlers ):
		raise ValueError( f'Input handler {handler.name!r} is already registered' )
	names = [ h.name for h in _handlers ]
	_handlers.insert( names.index( before ) if before in names else len( _handlers ), handler )


def input_handlers():
	return list( _handlers )


def supported_extensions():
	"""File types that can be uploaded: archives plus whatever the input handlers accept."""
	return ARCHIVE_EXTENSIONS + tuple( ext for h in _handlers for ext in h.extensions )


def tiles_prefix( model ):
	"""Storage prefix holding a model's tileset."""
	return f'tiles/{model.pk}'


def find_first_file( directory, extensions ):
	"""The first file (in sorted order) under directory whose name ends with one of extensions."""
	for root, dirs, files in sorted( os.walk( directory ) ):
		dirs.sort()
		for name in sorted( files ):
			if name.lower().endswith( extensions ):
				return os.path.join( root, name )
	return None


# --- built-in input handlers ------------------------------------------------------

def _georeference_tileset( tileset, out_dir, location ):
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


def _copy_tileset( src: TilingInput ):
	src.report.step( 'copying 3D Tiles', 40 )
	src.report.log( f'Found 3D Tiles: {os.path.relpath( src.path, src.input_dir )}' )
	shutil.copytree( os.path.dirname( src.path ), src.out_dir )
	tileset = os.path.join( src.out_dir, 'tileset.json' )
	if tileset_location( tileset ) is None:
		src.report.log( 'Tileset has no georeference; placing it at ' + ', '.join( f'{v:.6f}' for v in src.placement ) )
		tileset = _georeference_tileset( tileset, src.out_dir, src.placement )
	return tileset


POINTCLOUD_EXTENSIONS = ( '.las', '.laz' )


def _tile_point_cloud( src: TilingInput ):
	src.report.step( 'tiling point cloud', 30 )
	converters.pointcloud_to_tileset( src.path, src.out_dir, src.source_srs, src.report.log )
	return os.path.join( src.out_dir, 'tileset.json' )


# which converter turns each mesh format into GLB
MESH_EXTENSIONS = {
	'.glb': 'glb',
	'.gltf': 'gltf',
	'.obj': 'obj',
	'.fbx': 'assimp', '.dae': 'assimp', '.3ds': 'assimp', '.ply': 'assimp', '.stl': 'assimp',
}


def _tile_mesh( src: TilingInput ):
	kind = MESH_EXTENSIONS[ os.path.splitext( src.path )[1].lower() ]
	glb = os.path.join( src.work_dir, 'model.glb' )
	src.report.step( f'converting {kind.upper()} to glTF', 30 )
	if kind == 'glb':
		shutil.copy( src.path, glb )
	elif kind == 'gltf':
		converters.gltf_to_glb( src.path, glb, src.report.log )
	elif kind == 'obj':
		converters.obj_to_glb( src.path, glb, src.report.log )
	else:
		converters.assimp_to_glb( src.path, glb, src.report.log )
	src.report.step( 'building tileset', 70 )
	converters.glb_to_tileset( glb, src.out_dir, src.placement, src.report.log )
	return os.path.join( src.out_dir, 'tileset.json' )


# a JSON file next to the mesh may ask for its own number of levels, e.g. {"lods": 4} from a High reconstruction
TILING_HINTS = 'tiling.json'


def _find_large_obj( directory ):
	"""An OBJ big enough to be worth levels of detail, when Obj2Tiles is configured."""
	obj = find_first_file( directory, ( '.obj', ) )
	if obj and settings.PIPELINE_OBJ2TILES and os.path.getsize( obj ) >= settings.PIPELINE_LOD_MIN_SIZE:
		return obj
	return None


def _tile_lod_mesh( src: TilingInput ):
	hints_path = os.path.join( os.path.dirname( src.path ), TILING_HINTS )
	try:
		with open( hints_path, encoding = 'utf-8' ) as f:
			hints = json.load( f )
	except ( OSError, ValueError ):
		hints = {}
	lods = int( hints.get( 'lods' ) or settings.PIPELINE_LOD_LEVELS )
	size_mb = os.path.getsize( src.path ) / 2 ** 20
	src.report.step( f'building {lods} levels of detail', 30 )
	src.report.log( f'{os.path.basename( src.path )} is {size_mb:.0f} MB: tiling it with levels of detail' )
	try:
		return lod_tiling.obj_to_lod_tileset( settings.PIPELINE_OBJ2TILES, src.path, src.out_dir, src.placement, src.report.log,
			lods = lods, divisions = settings.PIPELINE_LOD_DIVISIONS, max_texture_size = settings.PIPELINE_LOD_MAX_TEXTURE_SIZE,
			texture_quality = settings.PIPELINE_LOD_TEXTURE_QUALITY, run = lambda args: converters._run( args, src.report.log, timeout = settings.PIPELINE_LOD_TIMEOUT ) )
	except ( converters.ConversionError, FileNotFoundError, ValueError ) as exc:
		# a temporary failure (the tool was killed) is raised on for a retry; anything else falls back to one tile
		src.report.log( f'Levels of detail failed ({exc}); building a single tile instead' )
		shutil.rmtree( src.out_dir, ignore_errors = True )
		return _tile_mesh( src )


register_input_handler( InputHandler( '3d-tiles', (), find_tileset, _copy_tileset ) )
register_input_handler( InputHandler( 'point-cloud', POINTCLOUD_EXTENSIONS, lambda d: find_first_file( d, POINTCLOUD_EXTENSIONS ), _tile_point_cloud ) )
# OBJ only: Obj2Tiles reads nothing else; smaller meshes and other formats become a single tile
register_input_handler( InputHandler( 'lod-mesh', (), _find_large_obj, _tile_lod_mesh ) )
register_input_handler( InputHandler( 'mesh', tuple( MESH_EXTENSIONS ), lambda d: find_first_file( d, tuple( MESH_EXTENSIONS ) ), _tile_mesh ) )


# --- the job --------------------------------------------------------------------

def _prepare_input( model, work, report ):
	"""Copy or download the source file into work/input, unpacking it if it is an archive; return that folder."""
	if not model.source_file or not model.source_file.storage.exists( model.source_file.name ):
		raise PipelineError( 'The uploaded file is missing; please upload it again.' )
	limits = Limits.from_settings()
	input_dir = os.path.join( work, 'input' )
	archive = is_archive( model.source_file.name )
	if storage.is_local_storage( model.source_file.storage ):
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
	return input_dir


def run_tiling( job, report ):
	"""Build and publish the tileset for job.model; raises on failure (the task records it)."""
	model = job.model
	placement = model.location.coords if model.location else settings.DEFAULT_MODEL_LOCATION
	if len( placement ) == 2:
		placement = ( *placement, 0.0 )

	# everything is built in a local temp folder (converters need real files), then published to storage
	work = tempfile.mkdtemp( prefix = f'job{job.pk}-', dir = settings.PIPELINE_WORK_DIR )
	out_dir = os.path.join( work, 'out' )
	try:
		report.step( 'preparing input', 5 )
		input_dir = _prepare_input( model, work, report )

		for handler in _handlers:
			found = handler.find( input_dir )
			if found:
				tileset = handler.build( TilingInput( found, input_dir, work, out_dir, placement, model.source_srs, report ) )
				break
		else:
			raise converters.ConversionError( 'No 3D Tiles, model or point-cloud file found in the upload. Supported: ' + ', '.join( supported_extensions() ) )

		report.step( 'finishing', 95 )
		location = tileset_location( tileset )
		if location is None and os.path.basename( tileset ) != 'tileset.root.json':
			raise converters.ConversionError( 'The generated tileset has no position on the globe.' )
		report.step( 'publishing tiles', 97 )
		prefix = tiles_prefix( model )
		storage.publish_directory( out_dir, prefix, report.log )
		model.tileset_path = prefix + '/' + os.path.relpath( tileset, out_dir ).replace( os.sep, '/' )
		model.location = Point( *( location or placement ), srid = 4326 )
		model.status = model.Status.READY
		model.save( update_fields = [ 'tileset_path', 'location', 'status', 'updated_at' ] )
		report.log( f'Tileset ready: {model.tileset_path}' )
	finally:
		shutil.rmtree( work, ignore_errors = True )
