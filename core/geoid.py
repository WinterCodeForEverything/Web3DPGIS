"""Geoid heights from the EGM96 model: how far mean sea level lies above the WGS84 ellipsoid.

GPS photos record altitude above sea level, while the platform stores heights above the ellipsoid:
ellipsoid height = altitude + N. pyproj reads the grid; with download on it fetches it once from the PROJ CDN
(cdn.proj.org) and caches it for later runs.
"""
from functools import lru_cache

DEFAULT_GRID = 'us_nga_egm96_15.tif'


@lru_cache( maxsize = 4 )
def _transformer( grid, download ):
	from pyproj import Transformer, network
	if download:
		network.set_network_enabled( True )
	# z_out = z_in + multiplier × grid value, so a height of 0 comes out as N
	return Transformer.from_pipeline( '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad '
		f'+step +proj=vgridshift +grids={grid} +multiplier=1 +step +proj=unitconvert +xy_in=rad +xy_out=deg' )


def geoid_height( lon, lat, grid = DEFAULT_GRID, download = True ):
	"""N in metres at ( lon, lat ) in degrees, or None when the grid is not available."""
	try:
		_, _, n = _transformer( grid, download ).transform( lon, lat, 0.0 )
	except Exception:   # pyproj raises its own errors when the grid cannot be found or fetched
		return None
	return n if abs( n ) < 200 else None    # inf or nonsense when the grid did not apply
