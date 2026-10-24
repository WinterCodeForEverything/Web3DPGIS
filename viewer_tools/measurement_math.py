"""Measurement maths on WGS84 points, the same formulas as the viewer's frontend/src/geo/geometry.ts.

Points are (longitude, latitude, height) in degrees and metres; the maths runs on Earth-centred (ECEF) metres.
"""
import math

from django.contrib.gis.geos import LineString, Point, Polygon

from processing.geodesy import A, E2, geodetic_to_ecef

# how many points each kind takes: (fewest, most)
POINT_COUNTS = {
	'point': ( 1, 1 ),
	'distance': ( 2, 1000 ),
	'area': ( 3, 1000 ),
	'height': ( 2, 2 ),
	'circle': ( 2, 2 ),
}


def _sub( a, b ):
	return ( a[0] - b[0], a[1] - b[1], a[2] - b[2] )


def _dot( a, b ):
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length( a ):
	return math.sqrt( _dot( a, a ) )


def _surface_normal( p ):
	"""Geodetic surface normal at an ECEF point."""
	b2 = A * A * ( 1 - E2 )
	n = ( p[0] / ( A * A ), p[1] / ( A * A ), p[2] / b2 )
	length = _length( n )
	return tuple( c / length for c in n )


def _east_north_axes( p ):
	up = _surface_normal( p )
	east = ( -up[1], up[0], 0.0 )
	length = _length( east ) or 1.0
	east = ( east[0] / length, east[1] / length, 0.0 )
	north = ( up[1] * east[2] - up[2] * east[1], up[2] * east[0] - up[0] * east[2], up[0] * east[1] - up[1] * east[0] )
	return east, north


def segment_lengths( points ):
	"""Straight-line length in metres of each segment between consecutive ECEF points."""
	return [ _length( _sub( b, a ) ) for a, b in zip( points, points[1:] ) ]


def plan_area( points ):
	"""Area in m² of a polygon measured flat in the local horizontal plane at its centroid."""
	centroid = tuple( sum( p[i] for p in points ) / len( points ) for i in range( 3 ) )
	east, north = _east_north_axes( centroid )
	local = [ ( _dot( _sub( p, centroid ), east ), _dot( _sub( p, centroid ), north ) ) for p in points ]
	twice = sum( x1 * y2 - x2 * y1 for ( x1, y1 ), ( x2, y2 ) in zip( local, local[1:] + local[:1] ) )
	return abs( twice ) / 2


def surface_area( points ):
	"""True area in m² of a roughly planar polygon in 3D, e.g. a wall or a sloping roof (Newell's method)."""
	o = points[0]
	n = [ 0.0, 0.0, 0.0 ]
	for p, q in zip( points, points[1:] + points[:1] ):
		a, b = _sub( p, o ), _sub( q, o )
		n[0] += ( a[1] - b[1] ) * ( a[2] + b[2] )
		n[1] += ( a[2] - b[2] ) * ( a[0] + b[0] )
		n[2] += ( a[0] - b[0] ) * ( a[1] + b[1] )
	return _length( n ) / 2


def height_difference( a, b ):
	"""Horizontal, vertical and straight-line distance from a to b."""
	d = _sub( b, a )
	vertical = _dot( d, _surface_normal( a ) )
	slant = _length( d )
	return math.sqrt( max( slant * slant - vertical * vertical, 0.0 ) ), vertical, slant


def build_measurement( kind, coords ):
	"""The geometry and results for a measurement of `kind` through `coords` [(lon, lat, height), …]."""
	ecef = [ geodetic_to_ecef( *c ) for c in coords ]
	if kind == 'point':
		return Point( *coords[0], srid = 4326 ), {}
	if kind == 'distance':
		segments = segment_lengths( ecef )
		return LineString( coords, srid = 4326 ), { 'length_m': sum( segments ), 'segment_lengths_m': segments }
	if kind == 'area':
		edges = segment_lengths( ecef + ecef[:1] )
		return Polygon( list( coords ) + [ coords[0] ], srid = 4326 ), {
			'area_m2': surface_area( ecef ), 'plan_area_m2': plan_area( ecef ), 'perimeter_m': sum( edges ), 'edge_lengths_m': edges,
		}
	if kind == 'height':
		horizontal, vertical, slant = height_difference( *ecef )
		return LineString( coords, srid = 4326 ), { 'horizontal_m': horizontal, 'vertical_m': vertical, 'slant_m': slant }
	if kind == 'circle':
		radius = height_difference( *ecef )[0]
		return LineString( coords, srid = 4326 ), { 'radius_m': radius, 'area_m2': math.pi * radius * radius }
	raise ValueError( f'Unknown measurement kind: {kind}' )


def measured_points( geometry ):
	"""The measured points of a stored geometry, without the polygon's closing vertex."""
	if geometry.geom_type == 'Point':
		return [ geometry.coords ]
	if geometry.geom_type == 'Polygon':
		return list( geometry.exterior_ring.coords )[:-1]
	return list( geometry.coords )
