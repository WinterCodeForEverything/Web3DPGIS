#!/usr/bin/env python3
"""Run the reconstruction pipeline by hand on a folder of photos and measure each stage (milestone M1).

Photos → COLMAP (features, matching, sparse model, georeference, undistort) → OpenMVS (densify, mesh, texture)
→ Obj2Tiles (3D Tiles with levels of detail). Each stage writes a .done marker in the work folder, so running the
script again skips finished stages, as the reconstruction job will. Stage times, peak memory and disk use go to
<work>/benchmark.json.

    scripts/reconstruct_by_hand.py --images ~/recon-data/odm_data_aukerman/images --count 50 --preset preview \\
        --work ~/recon-work/aukerman-50-preview --tools ~/recon-tools

--tools holds openmvs/ (InterfaceCOLMAP, DensifyPointCloud, …) and obj2tiles/Obj2Tiles; COLMAP comes from PATH.

How the cameras are solved depends on what is known (the mode is chosen automatically and recorded in the report):

  photos only        self-calibration from feature matches; "up" found from the photos; scale unknown
  photos with GPS    GPS positions are priors while solving; result in east-north-up metres, placed at their centre
  --poses centres    a file of camera centres in any local system ("name x y z"); they are priors while solving and
                     the result is in that system and its units
  --poses full       full poses in COLMAP's convention ("name qw qx qy qz tx ty tz", world to camera); cameras are
                     not solved at all, only the 3D points are triangulated

Known camera intrinsics can be given in any mode (--camera-model, --camera-params) and held fixed (--fix-intrinsics);
otherwise they start from EXIF (focal length and sensor size) and are refined from the matches.
"""
import argparse
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import struct
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


# --- known camera positions and poses ---------------------------------------------

def quat_to_matrix( qw, qx, qy, qz ):
	return [ [ 1 - 2 * ( qy * qy + qz * qz ), 2 * ( qx * qy - qz * qw ), 2 * ( qx * qz + qy * qw ) ],
		[ 2 * ( qx * qy + qz * qw ), 1 - 2 * ( qx * qx + qz * qz ), 2 * ( qy * qz - qx * qw ) ],
		[ 2 * ( qx * qz - qy * qw ), 2 * ( qy * qz + qx * qw ), 1 - 2 * ( qx * qx + qy * qy ) ] ]


def read_poses( path ):
	"""Camera centres per photo name, and full poses ( q, t ) when every line has one.

	A line is "name x y z" (camera centre) or "name qw qx qy qz tx ty tz" (COLMAP: rotation and translation from world
	to camera, so the centre is -R^T t). Blank lines and lines starting with # are skipped."""
	centres, full = {}, {}
	for number, line in enumerate( Path( path ).read_text().splitlines(), 1 ):
		parts = line.split()
		if not parts or parts[0].startswith( '#' ):
			continue
		name, values = parts[0], [ float( v ) for v in parts[1:] ]
		if len( values ) == 3:
			centres[ name ] = tuple( values )
		elif len( values ) == 7:
			q, t = values[:4], values[4:]
			R = quat_to_matrix( *q )
			centres[ name ] = tuple( -sum( R[r][c] * t[r] for r in range( 3 ) ) for c in range( 3 ) )
			full[ name ] = ( q, t )
		else:
			sys.exit( f'{path}:{number}: expected "name x y z" or "name qw qx qy qz tx ty tz"' )
	return centres, ( full if len( full ) == len( centres ) else {} )


CARTESIAN = 1   # COLMAP's PosePrior::CoordinateSystem (WGS84 = 0)


def write_position_priors( db, positions, std ):
	"""Replace the database's pose priors (COLMAP stores EXIF GPS as WGS84) with Cartesian positions in our local
	frame, each with standard deviations std = ( x, y, z ) in that frame's units; return how many photos got one."""
	con = sqlite3.connect( db )
	ids = { name: ( image_id, camera_id ) for image_id, name, camera_id in con.execute( 'select image_id, name, camera_id from images' ) }
	con.execute( 'delete from pose_priors' )
	sx, sy, sz = ( s * s for s in std )
	covariance = struct.pack( '9d', sx, 0, 0, 0, sy, 0, 0, 0, sz )
	no_gravity = struct.pack( '3d', math.nan, math.nan, math.nan )
	count = 0
	for name, xyz in positions.items():
		if name in ids:
			image_id, camera_id = ids[ name ]
			con.execute( 'insert into pose_priors ( corr_data_id, corr_sensor_id, corr_sensor_type, position, position_covariance, gravity, coordinate_system ) values ( ?, ?, 0, ?, ?, ?, ? )',
				( image_id, camera_id, struct.pack( '3d', *xyz ), covariance, no_gravity, CARTESIAN ) )
			count += 1
	con.commit()
	con.close()
	return count


def write_known_model( db, poses, folder ):
	"""A COLMAP text model with the given poses and the database's cameras, for point_triangulator."""
	folder.mkdir( parents = True, exist_ok = True )
	con = sqlite3.connect( db )
	model_names = { 0: 'SIMPLE_PINHOLE', 1: 'PINHOLE', 2: 'SIMPLE_RADIAL', 3: 'RADIAL', 4: 'OPENCV', 5: 'OPENCV_FISHEYE', 6: 'FULL_OPENCV' }
	with open( folder / 'cameras.txt', 'w' ) as out:
		for camera_id, model, width, height, params in con.execute( 'select camera_id, model, width, height, params from cameras' ):
			values = struct.unpack( f'{len( params ) // 8}d', params )
			out.write( f'{camera_id} {model_names[ model ]} {width} {height} ' + ' '.join( repr( v ) for v in values ) + '\n' )
	with open( folder / 'images.txt', 'w' ) as out:
		for image_id, name, camera_id in con.execute( 'select image_id, name, camera_id from images' ):
			if name in poses:
				q, t = poses[ name ]
				out.write( f'{image_id} ' + ' '.join( map( repr, q + t ) ) + f' {camera_id} {name}\n\n' )
	( folder / 'points3D.txt' ).write_text( '' )
	con.close()


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
	known = ap.add_argument_group( 'what is known about the cameras' )
	known.add_argument( '--camera-model', default = 'SIMPLE_RADIAL', help = 'COLMAP camera model, e.g. SIMPLE_RADIAL, OPENCV, RADIAL' )
	known.add_argument( '--camera-params', help = 'known intrinsics for that model, comma-separated (e.g. f,cx,cy,k)' )
	known.add_argument( '--fix-intrinsics', action = 'store_true', help = 'hold the intrinsics fixed instead of refining them' )
	known.add_argument( '--poses', type = Path, help = 'camera centres or full poses in a local system (see above)' )
	known.add_argument( '--prior-std', type = float, default = 0.1, help = 'uncertainty of --poses centres, in their units (default 0.1)' )
	known.add_argument( '--gps-std', default = '3,5', help = 'GPS uncertainty in metres, horizontal,vertical (default 3,5)' )
	known.add_argument( '--ignore-gps', action = 'store_true', help = 'do not use GPS from the photos' )
	known.add_argument( '--placement', help = 'longitude,latitude,height for a model without GPS (default 0,0,0)' )
	known.add_argument( '--up-method', choices = [ 'IMAGE-ORIENTATION', 'MANHATTAN-WORLD' ], default = 'IMAGE-ORIENTATION',
		help = 'how "up" is found without GPS or poses: upright photos, or the lines of buildings' )
	args = ap.parse_args()
	if args.fix_intrinsics and not args.camera_params:
		sys.exit( '--fix-intrinsics needs --camera-params' )
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
	refine = '0' if args.fix_intrinsics else '1'
	fixed = lambda prefix: [ f'--{prefix}.ba_refine_focal_length', refine, f'--{prefix}.ba_refine_extra_params', refine,
		f'--{prefix}.ba_refine_principal_point', '0' ]

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
		names = { p.name for p in photos }
		gps, origin = ( None, None ) if args.ignore_gps else enu_positions( photos )
		report.update( photos = len( photos ), photos_with_gps = len( gps or {} ) )
		if args.poses:
			centres, full = read_poses( args.poses )
			positions = { n: c for n, c in centres.items() if n in names }
			if len( positions ) < 3:
				sys.exit( f'{args.poses} gives positions for only {len( positions )} of the photos; at least 3 are needed' )
			mode, std = ( 'full poses' if full else 'local positions' ), ( args.prior_std, ) * 3
			report.update( scale = 'units of the poses file' )
			if full:
				( work / 'known_poses.json' ).write_text( json.dumps( { n: full[ n ] for n in positions } ) )
		elif gps:
			positions, mode = gps, 'gps'
			h, v = ( float( x ) for x in args.gps_std.split( ',' ) )
			std = ( h, h, v )
			report.update( scale = 'metres (from GPS)', enu_origin = origin )
		else:
			positions, mode, std = None, 'photos only', None
			report.update( scale = 'unknown (no GPS or poses)' )
		report.update( mode = mode, positions_known = len( positions or {} ), prior_std = std )
		if positions:
			( work / 'reference_positions.txt' ).write_text( ''.join( f'{n} {x:.4f} {y:.4f} {z:.4f}\n' for n, ( x, y, z ) in positions.items() ) )
		return time.monotonic() - start, None
	stage( 'prepare', prepare )

	# 2. COLMAP
	db = work / 'database.db'
	reference = work / 'reference_positions.txt'

	def priors():
		"""Our reference positions become the pose priors; without any, COLMAP's raw EXIF GPS priors are removed."""
		positions = { l.split()[0]: tuple( map( float, l.split()[1:4] ) ) for l in reference.read_text().splitlines() } if reference.exists() else {}
		report[ 'priors_written' ] = write_position_priors( db, positions, report['prior_std'] or ( 1, 1, 1 ) )
		return 0.0, None
	stage( 'features', [ colmap, 'feature_extractor', '--database_path', db, '--image_path', images,
		'--ImageReader.camera_model', args.camera_model, '--ImageReader.single_camera', '1',
		*( [ '--ImageReader.camera_params', args.camera_params ] if args.camera_params else [] ),
		'--FeatureExtraction.use_gpu', gpu, '--FeatureExtraction.max_image_size', preset['max_image_size'] ], priors )
	stage( 'matching', [ colmap, 'exhaustive_matcher', '--database_path', db, '--FeatureMatching.use_gpu', gpu ] )

	def best_model():
		models = sorted( ( model_stats( colmap, m ), m ) for m in sparse.iterdir() if ( m / 'images.bin' ).exists() )
		return models[-1] if models else ( ( 0, None ), None )

	def mapping():
		"""Solve the cameras with whatever is known; fall back to the next method when too few photos are placed."""
		mode = report['mode']
		base = [ '--database_path', db, '--image_path', images, '--output_path', sparse ]
		if mode == 'full poses':
			known_model = work / 'known_model'
			write_known_model( db, { n: tuple( v ) for n, v in json.loads( ( work / 'known_poses.json' ).read_text() ).items() }, known_model )
			( sparse / '0' ).mkdir( parents = True, exist_ok = True )
			attempts = [ ( 'triangulated from the given poses', [ colmap, 'point_triangulator', '--database_path', db, '--image_path', images,
				'--input_path', known_model, '--output_path', sparse / '0', '--refine_intrinsics', refine ] ) ]
		elif mode in ( 'gps', 'local positions' ):
			attempts = [ ( 'incremental with position priors', [ colmap, 'pose_prior_mapper', *base, '--use_robust_loss_on_prior_position', '1', *fixed( 'Mapper' ) ] ),
				( 'global, priors used only to align', [ colmap, 'global_mapper', *base, *fixed( 'GlobalMapper' ) ] ) ]
		else:
			attempts = [ ( 'global', [ colmap, 'global_mapper', *base, *fixed( 'GlobalMapper' ) ] ),
				( 'incremental', [ colmap, 'mapper', *base, *fixed( 'Mapper' ) ] ) ]
		seconds, peak = 0.0, 0
		for label, cmd in attempts:
			if sparse.exists() and mode != 'full poses':
				shutil.rmtree( sparse )
			sparse.mkdir( exist_ok = True )
			s, mb = timed( cmd, log )
			seconds, peak = seconds + s, max( peak, mb or 0 )
			( registered, error ), best = best_model()
			report[ 'mapper' ] = label
			if registered >= 0.5 * report['photos']:
				break
		report.update( registered_photos = registered, reprojection_error_px = error, sparse_model = str( best ) )
		return seconds, peak
	stage( 'sparse', mapping )

	aligned = work / 'aligned'
	def georeference():
		"""Put the model in its final frame: the reference positions' (GPS or local), or upright for photos only."""
		aligned.mkdir( exist_ok = True )
		mode = report['mode']
		report[ 'georeferenced' ] = mode == 'gps'
		if mode == 'full poses':
			shutil.copytree( report['sparse_model'], aligned, dirs_exist_ok = True )   # already in the poses' frame
			return 0.0, None
		if mode == 'photos only':
			# no positions: rotate the model so "up" is +Z; position and scale stay arbitrary
			return timed( [ colmap, 'model_orientation_aligner', '--image_path', images, '--input_path', report['sparse_model'],
				'--output_path', aligned, '--method', args.up_method ], log )
		# RANSAC threshold: three standard deviations of the positions' uncertainty
		return timed( [ colmap, 'model_aligner', '--input_path', report['sparse_model'], '--output_path', aligned,
			'--ref_images_path', reference, '--ref_is_gps', '0', '--alignment_type', 'custom',
			'--alignment_max_error', 3 * max( report['prior_std'] ) ], log )
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

	# 4. 3D Tiles with levels of detail, placed at the east-north-up origin, or where the user says
	if report.get( 'enu_origin' ):
		lon, lat, alt = report['enu_origin']
	else:
		lon, lat, alt = ( float( v ) for v in args.placement.split( ',' ) ) if args.placement else ( 0.0, 0.0, 0.0 )
		if not args.placement:
			print( 'note: no GPS and no --placement; the tiles are placed at longitude 0, latitude 0' )
	# OpenMVS writes a Z-up OBJ (east, north, up); Obj2Tiles assumes Y-up unless told, and the model would stand on its edge
	stage( 'tiling', [ obj2tiles, '--y-up-to-z-up', '--lods', preset['lods'], '--divisions', 2, '--lat', lat, '--lon', lon, '--alt', alt,
		dense / 'model.obj', tiles ] )

	report[ 'total_seconds' ] = round( sum( s['seconds'] for s in report['stages'].values() ), 1 )
	report[ 'tiles_mb' ] = disk_mb( tiles ) if tiles.exists() else None
	report_path.write_text( json.dumps( report, indent = 2 ) )
	print( json.dumps( { k: v for k, v in report.items() if k != 'stages' }, indent = 2 ) )


if __name__ == '__main__':
	main()
