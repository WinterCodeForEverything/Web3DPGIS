"""What is known about the cameras, in the forms COLMAP needs: GPS from EXIF, pose files, position priors,
a fixed-pose model, and epipolar-guided matching when the poses are known. Plain Python (and numpy), no Django,
so the command-line script can use it too.
"""
import math
import sqlite3
import struct
from pathlib import Path

from core.geodesy import geodetic_to_ecef

CARTESIAN = 1   # COLMAP's PosePrior::CoordinateSystem (WGS84 = 0)
COLMAP_CAMERA_MODELS = { 0: 'SIMPLE_PINHOLE', 1: 'PINHOLE', 2: 'SIMPLE_RADIAL', 3: 'RADIAL', 4: 'OPENCV', 5: 'OPENCV_FISHEYE', 6: 'FULL_OPENCV' }
# number of intrinsic parameters per camera model, for validating user input
CAMERA_PARAM_COUNTS = { 'SIMPLE_PINHOLE': 3, 'PINHOLE': 4, 'SIMPLE_RADIAL': 4, 'RADIAL': 5, 'OPENCV': 8 }


class PoseFileError( ValueError ):
	"""A camera poses file that cannot be read; the message says which line and why."""


# --- GPS from EXIF ----------------------------------------------------------------

def exif_gps( path ):
	"""( longitude, latitude, altitude ) from a photo's EXIF, or None. EXIF altitude is above sea level."""
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


def enu_positions( photos, geoid = None ):
	"""The photos' GPS as east-north-up metres around their mean position, and that origin ( lon, lat, height ).

	geoid( lon, lat ) gives the geoid height N in metres: EXIF altitudes are above sea level, so ellipsoid height
	= altitude + N. Without it the altitudes are used as they are."""
	gps = { p.name: g for p in photos if ( g := exif_gps( p ) ) }
	if len( gps ) < 3:
		return None, None
	if geoid is not None:
		lon0, lat0 = ( sum( g[i] for g in gps.values() ) / len( gps ) for i in range( 2 ) )
		n = geoid( lon0, lat0 )   # varies by centimetres over a photo set, so one value is enough
		gps = { name: ( lon, lat, alt + n ) for name, ( lon, lat, alt ) in gps.items() }
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


# --- rotations --------------------------------------------------------------------

def quat_to_matrix( qw, qx, qy, qz ):
	return [ [ 1 - 2 * ( qy * qy + qz * qz ), 2 * ( qx * qy - qz * qw ), 2 * ( qx * qz + qy * qw ) ],
		[ 2 * ( qx * qy + qz * qw ), 1 - 2 * ( qx * qx + qz * qz ), 2 * ( qy * qz - qx * qw ) ],
		[ 2 * ( qx * qz - qy * qw ), 2 * ( qy * qz + qx * qw ), 1 - 2 * ( qx * qx + qy * qy ) ] ]


def matrix_to_quat( R ):
	"""Rotation matrix to ( qw, qx, qy, qz )."""
	t = R[0][0] + R[1][1] + R[2][2]
	if t > 0:
		s = math.sqrt( t + 1 ) * 2
		return ( s / 4, ( R[2][1] - R[1][2] ) / s, ( R[0][2] - R[2][0] ) / s, ( R[1][0] - R[0][1] ) / s )
	i = max( range( 3 ), key = lambda k: R[k][k] ); j, k = ( i + 1 ) % 3, ( i + 2 ) % 3
	s = math.sqrt( 1 + R[i][i] - R[j][j] - R[k][k] ) * 2
	q = [ 0.0, 0.0, 0.0, 0.0 ]
	q[0] = ( R[k][j] - R[j][k] ) / s; q[ i + 1 ] = s / 4; q[ j + 1 ] = ( R[j][i] + R[i][j] ) / s; q[ k + 1 ] = ( R[k][i] + R[i][k] ) / s
	return tuple( q )


def camera_centre( q, t ):
	"""Camera centre -R^T t of a COLMAP world-to-camera pose."""
	R = quat_to_matrix( *q )
	return tuple( -sum( R[r][c] * t[r] for r in range( 3 ) ) for c in range( 3 ) )


# --- pose files ---------------------------------------------------------------------

def read_poses( path ):
	"""Camera centres per photo name, and full poses ( q, t ) when every line has one.

	A line is "name x y z" (camera centre) or "name qw qx qy qz tx ty tz" (COLMAP: rotation and translation from world
	to camera). Blank lines and lines starting with # are skipped. Raises PoseFileError."""
	centres, full = {}, {}
	for number, line in enumerate( Path( path ).read_text( encoding = 'utf-8', errors = 'replace' ).splitlines(), 1 ):
		parts = line.split()
		if not parts or parts[0].startswith( '#' ):
			continue
		try:
			name, values = parts[0], [ float( v ) for v in parts[1:] ]
		except ValueError:
			raise PoseFileError( f'line {number}: numbers expected after the photo name' ) from None
		if len( values ) == 3:
			centres[ name ] = tuple( values )
		elif len( values ) == 7:
			q, t = tuple( values[:4] ), tuple( values[4:] )
			if abs( math.sqrt( sum( v * v for v in q ) ) - 1 ) > 1e-3:
				raise PoseFileError( f'line {number}: the quaternion qw qx qy qz is not a unit quaternion' )
			centres[ name ] = camera_centre( q, t )
			full[ name ] = ( q, t )
		else:
			raise PoseFileError( f'line {number}: expected "name x y z" or "name qw qx qy qz tx ty tz"' )
	if len( centres ) < 3:
		raise PoseFileError( 'at least 3 camera poses are needed' )
	return centres, ( full if len( full ) == len( centres ) else {} )


# --- COLMAP database: priors, fixed poses, guided matching --------------------------

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


def verified_pairs( db, min_matches = 15 ):
	"""Photo pairs with at least min_matches geometrically verified matches."""
	con = sqlite3.connect( db )
	n = con.execute( 'select count(*) from two_view_geometries where rows >= ?', ( min_matches, ) ).fetchone()[0]
	con.close()
	return n


def write_known_model( db, poses, folder ):
	"""A COLMAP text model with the given poses and the database's cameras, for point_triangulator."""
	folder.mkdir( parents = True, exist_ok = True )
	con = sqlite3.connect( db )
	with open( folder / 'cameras.txt', 'w' ) as out:
		for camera_id, model, width, height, params in con.execute( 'select camera_id, model, width, height, params from cameras' ):
			values = struct.unpack( f'{len( params ) // 8}d', params )
			out.write( f'{camera_id} {COLMAP_CAMERA_MODELS[ model ]} {width} {height} ' + ' '.join( repr( v ) for v in values ) + '\n' )
	with open( folder / 'images.txt', 'w' ) as out:
		for image_id, name, camera_id in con.execute( 'select image_id, name, camera_id from images' ):
			if name in poses:
				q, t = poses[ name ]
				out.write( f'{image_id} ' + ' '.join( map( repr, tuple( q ) + tuple( t ) ) ) + f' {camera_id} {name}\n\n' )
	( folder / 'points3D.txt' ).write_text( '' )
	con.close()


def normalized( model, params, uv ):
	"""Pixel positions to undistorted normalized image coordinates (rows of x, y, 1) for COLMAP camera models 0–4;
	also returns the focal length in pixels."""
	import numpy as np
	if model in ( 0, 2, 3 ):        # SIMPLE_PINHOLE, SIMPLE_RADIAL, RADIAL: f, cx, cy, [k1, [k2]]
		fx = fy = params[0]; cx, cy = params[1:3]; k1, k2 = ( list( params[3:] ) + [ 0, 0 ] )[:2]; p1 = p2 = 0
	elif model in ( 1, 4 ):         # PINHOLE, OPENCV: fx, fy, cx, cy, [k1, k2, p1, p2]
		fx, fy, cx, cy = params[:4]; k1, k2, p1, p2 = ( list( params[4:] ) + [ 0, 0, 0, 0 ] )[:4]
	else:
		raise ValueError( f'camera model {COLMAP_CAMERA_MODELS.get( model, model )} is not supported for pose-guided matching' )
	x = ( uv[:, 0] - cx ) / fx; y = ( uv[:, 1] - cy ) / fy; xu, yu = x.copy(), y.copy()
	for _ in range( 10 ):           # fixed-point removal of the distortion
		r2 = xu * xu + yu * yu; radial = 1 + k1 * r2 + k2 * r2 * r2
		xu = ( x - ( 2 * p1 * xu * yu + p2 * ( r2 + 2 * xu * xu ) ) ) / radial
		yu = ( y - ( p1 * ( r2 + 2 * yu * yu ) + 2 * p2 * xu * yu ) ) / radial
	return np.stack( [ xu, yu, np.ones_like( xu ) ], 1 ), fx


def match_with_known_poses( db, poses, max_error_px = 4.0, max_angle = 75.0, ratio = 0.8, min_matches = 15 ):
	"""Epipolar-guided matching: for each feature, only features near its epipolar line in the other photo (from the
	known poses) are candidates; the best descriptor match among them is kept if it passes a ratio test and a mutual
	check. Replaces COLMAP's photo-based verified matches, which accept chance matches on smooth or symmetric objects.
	Returns ( pairs kept, matches kept )."""
	import numpy as np
	con = sqlite3.connect( db )
	cams = { cid: ( model, struct.unpack( f'{len( p ) // 8}d', p ) ) for cid, model, p in con.execute( 'select camera_id, model, params from cameras' ) }
	images = { iid: ( name, cid ) for iid, name, cid in con.execute( 'select image_id, name, camera_id from images' ) if name in poses }
	kp = { iid: np.frombuffer( d, np.float32 ).reshape( r, c )[:, :2].astype( float ) for iid, r, c, d in con.execute( 'select image_id, rows, cols, data from keypoints' ) if iid in images }
	desc = { iid: np.frombuffer( d, np.uint8 ).reshape( r, c ).astype( np.float32 ) for iid, r, c, d in con.execute( 'select image_id, rows, cols, data from descriptors' ) if iid in images }
	norm = { iid: normalized( *cams[ images[ iid ][1] ], kp[ iid ] ) for iid in images if iid in kp }
	w2c = { iid: ( np.array( quat_to_matrix( *poses[ name ][0] ) ), np.array( poses[ name ][1] ) ) for iid, ( name, _ ) in images.items() }
	skew = lambda v: np.array( [ [ 0, -v[2], v[1] ], [ v[2], 0, -v[0] ], [ -v[1], v[0], 0 ] ] )
	con.execute( 'delete from two_view_geometries' )
	con.execute( 'delete from matches' )
	pairs_kept = matches_kept = 0
	ids = sorted( norm )
	for a_index, i1 in enumerate( ids ):
		for i2 in ids[ a_index + 1: ]:
			( R1, t1 ), ( R2, t2 ) = w2c[ i1 ], w2c[ i2 ]
			R = R2 @ R1.T; t = t2 - R @ t1
			if np.degrees( np.arccos( np.clip( ( np.trace( R ) - 1 ) / 2, -1, 1 ) ) ) > max_angle:
				continue                    # the photos see different sides of the object
			E = skew( t ) @ R
			( x1, _ ), ( x2, f2 ) = norm[ i1 ], norm[ i2 ]
			lines = x1 @ E.T
			epi = np.abs( lines @ x2.T ) / np.linalg.norm( lines[:, :2], axis = 1, keepdims = True ) * f2   # pixels in photo 2
			d1, d2 = desc[ i1 ], desc[ i2 ]
			dist = np.sqrt( np.maximum( ( d1 * d1 ).sum( 1 )[:, None] + ( d2 * d2 ).sum( 1 )[None, :] - 2 * d1 @ d2.T, 0 ) )
			dist[ epi > max_error_px ] = np.inf
			best12 = np.argmin( dist, 1 ); best21 = np.argmin( dist, 0 )
			order = np.sort( dist, 1 )
			ok = np.isfinite( order[:, 0] ) & ( ( order[:, 0] < ratio * order[:, 1] ) | ~np.isfinite( order[:, 1] ) )
			ok &= best21[ best12 ] == np.arange( len( best12 ) )                          # mutual best
			m = np.stack( [ np.nonzero( ok )[0], best12[ ok ] ], 1 ).astype( np.uint32 )
			if len( m ) < min_matches:
				continue
			pair_id = i1 * 2147483647 + i2
			con.execute( 'insert into matches values ( ?, ?, 2, ? )', ( pair_id, len( m ), m.tobytes() ) )
			con.execute( 'insert into two_view_geometries ( pair_id, rows, cols, data, config, F, E, H, qvec, tvec ) values ( ?, ?, 2, ?, 2, ?, ?, ?, ?, ? )',
				( pair_id, len( m ), m.tobytes(), np.eye( 3 ).tobytes(), E.astype( np.float64 ).tobytes(), np.eye( 3 ).tobytes(),
				np.array( matrix_to_quat( R ), np.float64 ).tobytes(), t.astype( np.float64 ).tobytes() ) )
			pairs_kept += 1; matches_kept += len( m )
	con.commit(); con.close()
	return pairs_kept, matches_kept


# --- reading a COLMAP text model ----------------------------------------------------------

def read_model_centres( images_txt ):
	"""Camera centres per photo name from a COLMAP images.txt."""
	lines = [ l for l in Path( images_txt ).read_text().splitlines() if not l.startswith( '#' ) ]
	out = {}
	for head in lines[0::2]:
		p = head.split()
		if len( p ) >= 10:
			out[ p[9] ] = camera_centre( tuple( map( float, p[1:5] ) ), tuple( map( float, p[5:8] ) ) )
	return out


def position_outliers( centres, reference, factor = 3.0, floor = 1.0 ):
	"""Photos whose distance to their reference position is more than factor × the median distance (and more than
	floor, in the reference units): their GPS or given position does not fit the others."""
	residuals = { n: math.dist( centres[ n ], reference[ n ] ) for n in centres if n in reference }
	if len( residuals ) < 4:
		return {}, residuals
	median = sorted( residuals.values() )[ len( residuals ) // 2 ]
	limit = max( factor * median, floor )
	return { n: r for n, r in residuals.items() if r > limit }, residuals


# --- final orientation and units -------------------------------------------------------------

# rotations that turn the named axis into +Z (all proper rotations, so nothing is mirrored)
UP_AXES = {
	'+z': ( ( 1, 0, 0 ), ( 0, 1, 0 ), ( 0, 0, 1 ) ), '-z': ( ( 1, 0, 0 ), ( 0, -1, 0 ), ( 0, 0, -1 ) ),
	'+y': ( ( 1, 0, 0 ), ( 0, 0, -1 ), ( 0, 1, 0 ) ), '-y': ( ( 1, 0, 0 ), ( 0, 0, 1 ), ( 0, -1, 0 ) ),
	'+x': ( ( 0, 0, -1 ), ( 0, 1, 0 ), ( 1, 0, 0 ) ), '-x': ( ( 0, 0, 1 ), ( 0, 1, 0 ), ( -1, 0, 0 ) ),
}
Z_UP_TO_Y_UP = ( ( 1, 0, 0 ), ( 0, 0, 1 ), ( 0, -1, 0 ) )   # (east, north, up) → (x, y, z) with y up, as OBJ files expect


def transform_obj( src, dst, scale = 1.0, up = '+z', y_up = False ):
	"""Copy an OBJ with its vertices scaled (e.g. to metres) and rotated so `up` becomes +Z; with y_up the result is
	then written Y-up, the usual OBJ convention. Materials and texture coordinates are untouched, so dst must sit next
	to the original's .mtl and textures."""
	R = UP_AXES[ up ]
	if y_up:
		R = tuple( tuple( sum( Z_UP_TO_Y_UP[r][k] * R[k][c] for k in range( 3 ) ) for c in range( 3 ) ) for r in range( 3 ) )
	turn = lambda v: [ sum( R[r][c] * v[c] for c in range( 3 ) ) for r in range( 3 ) ]
	with open( src ) as fin, open( dst, 'w' ) as fout:
		for line in fin:
			if line.startswith( 'v ' ):
				x, y, z = turn( [ float( v ) * scale for v in line.split()[1:4] ] )
				fout.write( f'v {x:.6f} {y:.6f} {z:.6f}\n' )
			elif line.startswith( 'vn ' ):
				x, y, z = turn( [ float( v ) for v in line.split()[1:4] ] )
				fout.write( f'vn {x:.6f} {y:.6f} {z:.6f}\n' )
			else:
				fout.write( line )
