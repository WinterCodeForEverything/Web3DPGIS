"""Wrappers around the command-line tools that turn uploads into 3D Tiles.

  OBJ                       -> obj2gltf          -> GLB
  glTF                      -> gltf-pipeline     -> GLB
  FBX, DAE, 3DS, PLY, STL   -> assimp            -> GLB
  GLB                       -> 3d-tiles-tools createTilesetJson -> tileset.json (placed on the globe)
  LAS, LAZ                  -> py3dtiles convert -> point-cloud tileset
"""
import os
import subprocess
import sys

from django.conf import settings

from .errors import PipelineError, TransientError


class ConversionError( PipelineError ):
	pass


def _run( args, log, cwd = None, timeout = 3600 ):
	log( '$ ' + ' '.join( str( a ) for a in args ) )
	try:
		result = subprocess.run( [ str( a ) for a in args ], cwd = cwd, capture_output = True, text = True, timeout = timeout )
	except FileNotFoundError as exc:
		raise ConversionError( f'Converter not installed: {args[0]}' ) from exc
	except subprocess.TimeoutExpired as exc:
		raise ConversionError( f'{os.path.basename( str( args[0] ) )} timed out after {timeout} s' ) from exc
	output = ( result.stdout + result.stderr ).strip()
	# drop noisy native-library warnings printed by sharp/libvips on macOS
	output = '\n'.join( line for line in output.splitlines() if not line.startswith( 'objc[' ) )
	if output:
		log( output[-4000:] )
	if result.returncode < 0:
		# killed by a signal (e.g. the system ran out of memory): worth another try later
		raise TransientError( f'{os.path.basename( str( args[0] ) )} was stopped by signal {-result.returncode}' )
	if result.returncode != 0:
		raise ConversionError( f'{os.path.basename( str( args[0] ) )} failed (exit code {result.returncode})' )


def _node_tool( name ):
	return os.path.join( settings.PIPELINE_NODE_BIN, name )


def obj_to_glb( src, dst, log ):
	_run( [ _node_tool( 'obj2gltf' ), '-i', src, '-o', dst, '--binary' ], log )


def gltf_to_glb( src, dst, log ):
	_run( [ _node_tool( 'gltf-pipeline' ), '-i', src, '-o', dst, '--binary' ], log )


def assimp_to_glb( src, dst, log ):
	_run( [ settings.PIPELINE_ASSIMP, 'export', src, dst, '-fglb2' ], log )


def glb_to_tileset( glb, out_dir, location, log ):
	"""Write out_dir/tileset.json with the GLB as its single tile, placed at location (lon, lat, height)."""
	os.makedirs( out_dir, exist_ok = True )
	content = os.path.join( out_dir, 'model.glb' )
	if os.path.abspath( glb ) != os.path.abspath( content ):
		os.replace( glb, content )
	lon, lat, height = location
	_run( [ _node_tool( '3d-tiles-tools' ), 'createTilesetJson', '-i', content, '-o', os.path.join( out_dir, 'tileset.json' ),
		'--cartographicPositionDegrees', lon, lat, height, '-f' ], log )


def pointcloud_to_tileset( src, out_dir, srs_in, log ):
	args = [ os.path.join( os.path.dirname( sys.executable ), 'py3dtiles' ), 'convert', src, '--out', out_dir, '--overwrite', '--srs_out', '4978' ]
	if srs_in:
		args += [ '--srs_in', srs_in.upper().removeprefix( 'EPSG:' ) ]
	_run( args, log )
