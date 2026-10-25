#!/usr/bin/env python3
"""Run the reconstruction pipeline by hand on a folder of photos and measure each stage (milestone M1).

Photos → COLMAP (features, matching, sparse model, georeference, undistort) → OpenMVS (densify, mesh, texture)
→ Obj2Tiles (3D Tiles with levels of detail). Each stage writes a .done marker in the work folder, so running the
script again skips finished stages, as the reconstruction job will. Stage times, peak memory and disk use go to
<work>/benchmark.json.

    scripts/reconstruct_by_hand.py --images ~/recon-data/odm_data_aukerman/images --count 50 --preset preview \\
        --work ~/recon-work/aukerman-50-preview --tools ~/recon-tools

--tools holds openmvs/ (InterfaceCOLMAP, DensifyPointCloud, …) and obj2tiles/Obj2Tiles; COLMAP comes from PATH.
"""
import argparse
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from core.geodesy import geodetic_to_ecef  # noqa: E402  (plain maths, no Django needed)

# image sizes are capped for the development Mac's 8 GB; the cloud server will use larger ones
PRESETS = {
	'preview': { 'max_image_size': 1600, 'densify_level': 1, 'mesh_decimate': 0.5, 'refine': False, 'lods': 3 },
	'standard': { 'max_image_size': 2000, 'densify_level': 1, 'mesh_decimate': 1.0, 'refine': False, 'lods': 3 },
	'high': { 'max_image_size': 3200, 'densify_level': 0, 'mesh_decimate': 1.0, 'refine': True, 'lods': 4 },
}
PHOTO_TYPES = ( '.jpg', '.jpeg', '.tif', '.tiff', '.png' )
# OpenMVS 2.4.0's macOS arm64 build breaks texture seam levelling (global: black patches, local: coloured borders),
# so it is turned off there; patches then keep their own photo's colours
SEAM_LEVELING = platform.system() != 'Darwin'


# --- EXIF GPS → local east-north-up metres ---------------------------------------

def exif_gps( path ):
	"""(longitude, latitude, altitude) from a photo's EXIF, or None."""
	from PIL import Image
	with Image.open( path ) as img:
		gps = img.getexif().get_ifd( 0x8825 )
	if not gps or 2 not in gps or 4 not in gps:
		return None
	dms = lambda v: float( v[0] ) + float( v[1] ) / 60 + float( v[2] ) / 3600
	lat = dms( gps[2] ) * ( -1 if gps.get( 1 ) == 'S' else 1 )
	lon = dms( gps[4] ) * ( -1 if gps.get( 3 ) == 'W' else 1 )
	alt = float( gps.get( 6, 0 ) ) * ( -1 if gps.get( 5 ) == 1 else 1 )
	return lon, lat, alt


def enu_positions( photos ):
	"""The photos' GPS as east-north-up metres around their mean position, and that origin (lon, lat, alt)."""
	gps = { p.name: g for p in photos if ( g := exif_gps( p ) ) }
	if len( gps ) < 3:
		return None, None
	origin = tuple( sum( g[i] for g in gps.values() ) / len( gps ) for i in range( 3 ) )
	lon0, lat0 = map( math.radians, origin[:2] )
	cos, sin = math.cos, math.sin
	east = ( -sin( lon0 ), cos( lon0 ), 0.0 )
	north = ( -sin( lat0 ) * cos( lon0 ), -sin( lat0 ) * sin( lon0 ), cos( lat0 ) )
	up = ( cos( lat0 ) * cos( lon0 ), cos( lat0 ) * sin( lon0 ), sin( lat0 ) )
	o = geodetic_to_ecef( *origin )
	out = {}
	for name, g in gps.items():
		d = [ a - b for a, b in zip( geodetic_to_ecef( *g ), o ) ]
		out[ name ] = tuple( sum( d[i] * axis[i] for i in range( 3 ) ) for axis in ( east, north, up ) )
	return out, origin


# --- running and measuring commands ------------------------------------------------

def timed( cmd, log ):
	"""Run cmd in the log's folder (OpenMVS writes its own log files into the current folder), append its output
	to log; return ( seconds, peak resident memory in MB )."""
	wrapper = [ '/usr/bin/time', '-l' ] if platform.system() == 'Darwin' else [ '/usr/bin/time', '-v' ]
	start = time.monotonic()
	with open( log, 'a' ) as out:
		out.write( '\n$ ' + ' '.join( map( str, cmd ) ) + '\n' )
		out.flush()
		proc = subprocess.run( wrapper + [ str( c ) for c in cmd ], cwd = Path( log ).parent, stdout = out, stderr = subprocess.PIPE, text = True )
		out.write( proc.stderr )
	seconds = time.monotonic() - start
	if proc.returncode:
		raise RuntimeError( f'{cmd[0]} failed with exit code {proc.returncode}; see {log}' )
	m = re.search( r'(\d+)\s+maximum resident set size', proc.stderr ) or re.search( r'Maximum resident set size \(kbytes\): (\d+)', proc.stderr )
	scale = 1 / 2 ** 20 if platform.system() == 'Darwin' else 1 / 1024
	return seconds, round( int( m.group( 1 ) ) * scale ) if m else None


def disk_mb( path ):
	return round( sum( f.stat().st_size for f in Path( path ).rglob( '*' ) if f.is_file() ) / 2 ** 20 )


def model_stats( colmap, model ):
	"""Registered images and mean reprojection error of a COLMAP model folder."""
	text = subprocess.run( [ colmap, 'model_analyzer', '--path', model ], capture_output = True, text = True ).stderr
	reg = re.search( r'Registered images:\s*(\d+)', text )
	err = re.search( r'Mean reprojection error:\s*([\d.]+)', text )
	return int( reg.group( 1 ) ) if reg else 0, float( err.group( 1 ) ) if err else None


def main():
	ap = argparse.ArgumentParser( description = __doc__, formatter_class = argparse.RawDescriptionHelpFormatter )
	ap.add_argument( '--images', required = True, type = Path )
	ap.add_argument( '--count', type = int, help = 'use the first N photos (sorted by name)' )
	ap.add_argument( '--preset', choices = PRESETS, default = 'preview' )
	ap.add_argument( '--work', required = True, type = Path )
	ap.add_argument( '--tools', required = True, type = Path )
	ap.add_argument( '--use-gpu', action = 'store_true', help = 'COLMAP on the GPU (needs a CUDA build)' )
	args = ap.parse_args()
	preset = PRESETS[ args.preset ]
	colmap = shutil.which( 'colmap' ) or sys.exit( 'colmap is not on PATH' )
	mvs = lambda name: args.tools / 'openmvs' / name
	obj2tiles = args.tools / 'obj2tiles' / 'Obj2Tiles'
	gpu = '1' if args.use_gpu else '0'

	work = args.work.resolve()
	images, sparse, dense, tiles = work / 'images', work / 'sparse', work / 'dense', work / 'tiles'
	log, report_path = work / 'commands.log', work / 'benchmark.json'
	work.mkdir( parents = True, exist_ok = True )
	report = json.loads( report_path.read_text() ) if report_path.exists() else { 'stages': {} }
	report.update( preset = args.preset, settings = { **preset, 'seam_leveling': SEAM_LEVELING }, host = f'{platform.machine()} {platform.system()} {os.cpu_count()} cores' )

	def stage( name, *cmds ):
		"""Run a stage's commands unless its .done marker exists; record time, memory and disk use."""
		marker = work / f'{name}.done'
		if marker.exists():
			print( f'{name}: done before, skipped' )
			return
		print( f'{name}: running …', flush = True )
		total, peak = 0.0, 0
		for cmd in cmds:
			seconds, mb = cmd() if callable( cmd ) else timed( cmd, log )
			total += seconds
			peak = max( peak, mb or 0 )
		report[ 'stages' ][ name ] = { 'seconds': round( total, 1 ), 'peak_memory_mb': peak, 'work_disk_mb': disk_mb( work ) }
		report_path.write_text( json.dumps( report, indent = 2 ) )
		marker.touch()
		print( f'{name}: {total:.0f} s, peak {peak} MB', flush = True )

	# 1. photos
	def prepare():
		start = time.monotonic()
		photos = sorted( p for p in args.images.iterdir() if p.suffix.lower() in PHOTO_TYPES )[: args.count]
		images.mkdir( exist_ok = True )
		for p in photos:
			if not ( images / p.name ).exists():
				os.link( p, images / p.name ) if p.stat().st_dev == work.stat().st_dev else shutil.copy2( p, images )
		positions, origin = enu_positions( photos )
		report.update( photos = len( photos ), photos_with_gps = len( positions or {} ), enu_origin = origin )
		if positions:
			( work / 'gps_enu.txt' ).write_text( ''.join( f'{n} {e:.3f} {nn:.3f} {u:.3f}\n' for n, ( e, nn, u ) in positions.items() ) )
		return time.monotonic() - start, None
	stage( 'prepare', prepare )

	# 2. COLMAP
	db = work / 'database.db'
	stage( 'features', [ colmap, 'feature_extractor', '--database_path', db, '--image_path', images,
		'--ImageReader.camera_model', 'SIMPLE_RADIAL', '--ImageReader.single_camera', '1',
		'--FeatureExtraction.use_gpu', gpu, '--FeatureExtraction.max_image_size', preset['max_image_size'] ] )
	stage( 'matching', [ colmap, 'exhaustive_matcher', '--database_path', db, '--FeatureMatching.use_gpu', gpu ] )

	def mapping():
		sparse.mkdir( exist_ok = True )
		seconds, mb = timed( [ colmap, 'global_mapper', '--database_path', db, '--image_path', images, '--output_path', sparse ], log )
		models = sorted( ( model_stats( colmap, m ), m ) for m in sparse.iterdir() if ( m / 'images.bin' ).exists() )
		( registered, error ), best = models[-1] if models else ( ( 0, None ), None )
		report[ 'mapper' ] = 'global'
		if registered < 0.5 * report['photos']:
			# the global mapper placed too few photos: fall back to incremental mapping
			shutil.rmtree( sparse ); sparse.mkdir()
			s2, mb2 = timed( [ colmap, 'mapper', '--database_path', db, '--image_path', images, '--output_path', sparse ], log )
			seconds, mb = seconds + s2, max( mb or 0, mb2 or 0 )
			models = sorted( ( model_stats( colmap, m ), m ) for m in sparse.iterdir() if ( m / 'images.bin' ).exists() )
			( registered, error ), best = models[-1]
			report[ 'mapper' ] = 'incremental (global placed too few photos)'
		report.update( registered_photos = registered, reprojection_error_px = error, sparse_model = str( best ) )
		return seconds, mb
	stage( 'sparse', mapping )

	aligned = work / 'aligned'
	def georeference():
		aligned.mkdir( exist_ok = True )
		if not ( work / 'gps_enu.txt' ).exists():
			report[ 'georeferenced' ] = False
			shutil.copytree( report['sparse_model'], aligned, dirs_exist_ok = True )
			return 0.0, None
		report[ 'georeferenced' ] = True
		return timed( [ colmap, 'model_aligner', '--input_path', report['sparse_model'], '--output_path', aligned,
			'--ref_images_path', work / 'gps_enu.txt', '--ref_is_gps', '0', '--alignment_type', 'custom',
			'--alignment_max_error', '5' ], log )
	stage( 'georeference', georeference )
	stage( 'undistort', [ colmap, 'image_undistorter', '--image_path', images, '--input_path', aligned,
		'--output_path', dense, '--output_type', 'COLMAP', '--max_image_size', preset['max_image_size'] ] )

	# 3. OpenMVS
	scene = dense / 'scene.mvs'
	stage( 'densify',
		[ mvs( 'InterfaceCOLMAP' ), '-i', dense, '-o', scene, '--image-folder', dense / 'images' ],
		[ mvs( 'DensifyPointCloud' ), '-i', scene, '-w', dense, '--resolution-level', preset['densify_level'],
			'--max-resolution', preset['max_image_size'] ] )
	mesh_cmds = [ [ mvs( 'ReconstructMesh' ), '-i', dense / 'scene_dense.mvs', '-w', dense, '--decimate', preset['mesh_decimate'] ] ]
	if preset['refine']:
		mesh_cmds.append( [ mvs( 'RefineMesh' ), '-i', dense / 'scene_dense.mvs', '-m', dense / 'scene_dense_mesh.ply', '-w', dense,
			'-o', dense / 'scene_dense_mesh_refine.mvs' ] )
	stage( 'mesh', *mesh_cmds )
	mesh = dense / ( 'scene_dense_mesh_refine.ply' if preset['refine'] else 'scene_dense_mesh.ply' )
	stage( 'texture', [ mvs( 'TextureMesh' ), '-i', dense / 'scene_dense.mvs', '-m', mesh, '-w', dense,
		'-o', dense / 'model.mvs', '--export-type', 'obj',
		'--global-seam-leveling', int( SEAM_LEVELING ), '--local-seam-leveling', int( SEAM_LEVELING ) ] )

	# 4. 3D Tiles with levels of detail, placed at the east-north-up origin
	lon, lat, alt = report.get( 'enu_origin' ) or ( 0.0, 0.0, 0.0 )
	# OpenMVS writes a Z-up OBJ (east, north, up); Obj2Tiles assumes Y-up unless told, and the model would stand on its edge
	stage( 'tiling', [ obj2tiles, '--y-up-to-z-up', '--lods', preset['lods'], '--divisions', 2, '--lat', lat, '--lon', lon, '--alt', alt,
		dense / 'model.obj', tiles ] )

	report[ 'total_seconds' ] = round( sum( s['seconds'] for s in report['stages'].values() ), 1 )
	report[ 'tiles_mb' ] = disk_mb( tiles ) if tiles.exists() else None
	report_path.write_text( json.dumps( report, indent = 2 ) )
	print( json.dumps( { k: v for k, v in report.items() if k != 'stages' }, indent = 2 ) )


if __name__ == '__main__':
	main()
