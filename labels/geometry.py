"""The shapes a label can have, and how their points are stored.

  point                          a marker at `position`
  polyline, polygon, wall        vertices in `geometry` (LineString Z, or Polygon Z with the ring closed); `position`
                                 is where the name is shown, by default the middle of the vertices
  circle, sphere, cylinder, cone centred on `position` (the base centre for cylinders and cones), sized by `radius`

`height` is how far a wall, cylinder or cone rises above its base, in metres.
"""
from django.contrib.gis.geos import LineString, Point, Polygon

# kind: ( fewest vertices, most vertices ), for kinds drawn through a list of vertices
VERTEX_COUNTS = { 'polyline': ( 2, 1000 ), 'polygon': ( 3, 1000 ), 'wall': ( 2, 1000 ) }
NEEDS_RADIUS = { 'circle', 'sphere', 'cylinder', 'cone' }
NEEDS_HEIGHT = { 'wall', 'cylinder', 'cone' }


def build_geometry( kind, coords ):
	"""The stored geometry of a label's vertices (lon, lat, height tuples)."""
	if kind == 'polygon':
		return Polygon( list( coords ) + [ coords[0] ], srid = 4326 )
	return LineString( list( coords ), srid = 4326 )


def vertices( geometry ):
	"""A stored geometry's vertices, without the polygon's closing vertex."""
	if geometry is None:
		return []
	if geometry.geom_type == 'Polygon':
		return list( geometry.exterior_ring.coords )[:-1]
	return list( geometry.coords )


def middle( coords ):
	"""Where a shape's name goes when none is given: the centre of its vertices, at the highest of them."""
	lons, lats, heights = zip( *coords )
	return Point( ( min( lons ) + max( lons ) ) / 2, ( min( lats ) + max( lats ) ) / 2, max( heights ), srid = 4326 )
