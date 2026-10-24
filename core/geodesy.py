"""WGS84 conversions between Earth-centred (ECEF, EPSG:4978) and geodetic coordinates.

Cesium works in ECEF metres; the database stores longitude, latitude and ellipsoidal height.
"""
import math

A = 6378137.0                   # WGS84 semi-major axis (m)
F = 1 / 298.257223563           # flattening
B = A * ( 1 - F )
E2 = F * ( 2 - F )              # first eccentricity squared
EP2 = ( A * A - B * B ) / ( B * B )


def ecef_to_geodetic( x, y, z ):
	"""Return (longitude, latitude, height) in degrees and metres."""
	lon = math.atan2( y, x )
	p = math.hypot( x, y )
	if p < 1e-9:
		lat = math.copysign( math.pi / 2, z )
		return math.degrees( lon ), math.degrees( lat ), abs( z ) - B
	# Bowring's initial guess, then a few fixed-point iterations (converges to < 1 mm)
	theta = math.atan2( z * A, p * B )
	lat = math.atan2( z + EP2 * B * math.sin( theta ) ** 3, p - E2 * A * math.cos( theta ) ** 3 )
	for _ in range( 5 ):
		n = A / math.sqrt( 1 - E2 * math.sin( lat ) ** 2 )
		h = p / math.cos( lat ) - n
		lat = math.atan2( z, p * ( 1 - E2 * n / ( n + h ) ) )
	n = A / math.sqrt( 1 - E2 * math.sin( lat ) ** 2 )
	h = p / math.cos( lat ) - n
	return math.degrees( lon ), math.degrees( lat ), h


def geodetic_to_ecef( lon, lat, h = 0.0 ):
	"""Return ECEF (x, y, z) in metres for longitude/latitude in degrees and height in metres."""
	lon, lat = math.radians( lon ), math.radians( lat )
	n = A / math.sqrt( 1 - E2 * math.sin( lat ) ** 2 )
	x = ( n + h ) * math.cos( lat ) * math.cos( lon )
	y = ( n + h ) * math.cos( lat ) * math.sin( lon )
	z = ( n * ( 1 - E2 ) + h ) * math.sin( lat )
	return x, y, z


def enu_to_ecef_matrix( lon, lat, h = 0.0 ):
	"""Column-major 4x4 transform from a local east-north-up frame at (lon, lat, h) to ECEF.

	This is the layout 3D Tiles uses for a tile's `transform`.
	"""
	lo, la = math.radians( lon ), math.radians( lat )
	east = ( -math.sin( lo ), math.cos( lo ), 0.0 )
	north = ( -math.sin( la ) * math.cos( lo ), -math.sin( la ) * math.sin( lo ), math.cos( la ) )
	up = ( math.cos( la ) * math.cos( lo ), math.cos( la ) * math.sin( lo ), math.sin( la ) )
	x, y, z = geodetic_to_ecef( lon, lat, h )
	return [ *east, 0.0, *north, 0.0, *up, 0.0, x, y, z, 1.0 ]
