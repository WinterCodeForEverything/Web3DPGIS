"""Helpers for reading 3D Tiles tilesets on disk."""
import json
import math
import os

from .geodesy import ecef_to_geodetic


def find_tileset( directory ):
	"""Return the path of the shallowest tileset.json under directory, or None."""
	if not os.path.isdir( directory ):
		return None
	for root, dirs, files in os.walk( directory ):
		dirs.sort()
		if 'tileset.json' in files:
			return os.path.join( root, 'tileset.json' )
	return None


def _apply_matrix( m, p ):
	# m is a column-major 4x4 matrix
	x, y, z = p
	return (
		m[0] * x + m[4] * y + m[8] * z + m[12],
		m[1] * x + m[5] * y + m[9] * z + m[13],
		m[2] * x + m[6] * y + m[10] * z + m[14],
	)


def tileset_location( path ):
	"""Return (longitude, latitude, height) of the tileset's root bounding-volume centre, or None.

	Handles `box`, `sphere` (both in the root transform's frame) and `region` (radians).
	"""
	with open( path, encoding = 'utf-8' ) as f:
		root = json.load( f ).get( 'root', {} )
	volume = root.get( 'boundingVolume', {} )
	if 'region' in volume:
		west, south, east, north, low, high = volume['region'][:6]
		return math.degrees( ( west + east ) / 2 ), math.degrees( ( south + north ) / 2 ), ( low + high ) / 2
	if 'box' in volume:
		centre = volume['box'][:3]
	elif 'sphere' in volume:
		centre = volume['sphere'][:3]
	else:
		return None
	transform = root.get( 'transform' )
	if transform and len( transform ) == 16:
		centre = _apply_matrix( transform, centre )
	if math.hypot( *centre ) < 1000.0:
		# a local, non-georeferenced tileset (near the Earth's centre)
		return None
	return ecef_to_geodetic( *centre )
