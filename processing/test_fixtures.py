"""Small generated 3D files for tests (no binary fixtures in the repo)."""
import io
import json
import struct
import zipfile

from core.geodesy import enu_to_ecef_matrix


def glb_triangle():
	"""A minimal valid GLB: one 10 m triangle."""
	positions = struct.pack( '<9f', 0, 0, 0, 10, 0, 0, 0, 10, 0 )
	gltf = {
		'asset': { 'version': '2.0' }, 'scene': 0, 'scenes': [ { 'nodes': [ 0 ] } ], 'nodes': [ { 'mesh': 0 } ],
		'meshes': [ { 'primitives': [ { 'attributes': { 'POSITION': 0 } } ] } ],
		'buffers': [ { 'byteLength': len( positions ) } ],
		'bufferViews': [ { 'buffer': 0, 'byteLength': len( positions ) } ],
		'accessors': [ { 'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [ 0, 0, 0 ], 'max': [ 10, 10, 0 ] } ],
	}
	chunk = json.dumps( gltf ).encode()
	chunk += b' ' * ( -len( chunk ) % 4 )
	total = 12 + 8 + len( chunk ) + 8 + len( positions )
	return ( struct.pack( '<4sII', b'glTF', 2, total ) + struct.pack( '<I4s', len( chunk ), b'JSON' ) + chunk
		+ struct.pack( '<I4s', len( positions ), b'BIN\x00' ) + positions )


CUBE_VERTICES = [ ( x, y, z ) for x in ( 0, 4 ) for y in ( 0, 4 ) for z in ( 0, 4 ) ]
CUBE_FACES = [ ( 0, 1, 3, 2 ), ( 4, 6, 7, 5 ), ( 0, 4, 5, 1 ), ( 2, 3, 7, 6 ), ( 0, 2, 6, 4 ), ( 1, 5, 7, 3 ) ]


def obj_cube():
	lines = [ 'v %d %d %d' % v for v in CUBE_VERTICES ] + [ 'f ' + ' '.join( str( i + 1 ) for i in f ) for f in CUBE_FACES ]
	return ( '\n'.join( lines ) + '\n' ).encode()


def ply_cube():
	header = [ 'ply', 'format ascii 1.0', f'element vertex {len( CUBE_VERTICES )}', 'property float x', 'property float y',
		'property float z', f'element face {len( CUBE_FACES )}', 'property list uchar int vertex_indices', 'end_header' ]
	body = [ '%d %d %d' % v for v in CUBE_VERTICES ] + [ '4 ' + ' '.join( str( i ) for i in f ) for f in CUBE_FACES ]
	return ( '\n'.join( header + body ) + '\n' ).encode()


def tileset_json( lon = None, lat = None, height = 0.0 ):
	"""A tileset whose one tile holds tri.glb; georeferenced when lon/lat are given."""
	root = { 'boundingVolume': { 'sphere': [ 5, 5, 0, 20 ] }, 'geometricError': 0, 'refine': 'ADD', 'content': { 'uri': 'tri.glb' } }
	if lon is not None:
		root['transform'] = enu_to_ecef_matrix( lon, lat, height )
	return json.dumps( { 'asset': { 'version': '1.1' }, 'geometricError': 100, 'root': root } )


def tiles_zip( folder = 'site', lon = None, lat = None, height = 0.0 ):
	buf = io.BytesIO()
	with zipfile.ZipFile( buf, 'w' ) as z:
		z.writestr( f'{folder}/tileset.json', tileset_json( lon, lat, height ) )
		z.writestr( f'{folder}/tri.glb', glb_triangle() )
	return buf.getvalue()


def zip_of( files ):
	buf = io.BytesIO()
	with zipfile.ZipFile( buf, 'w' ) as z:
		for name, data in files.items():
			z.writestr( name, data )
	return buf.getvalue()


def las_points( lon, lat, epsg, count = 2000 ):
	"""A LAS 1.4 point cloud: a 20 m x 20 m patch around (lon, lat), coordinates in the given EPSG."""
	import laspy
	import numpy as np
	from pyproj import Transformer

	cx, cy = Transformer.from_crs( 4326, epsg, always_xy = True ).transform( lon, lat )
	rng = np.random.default_rng( 1 )
	las = laspy.LasData( laspy.LasHeader( point_format = 3, version = '1.4' ) )
	las.header.offsets = [ cx, cy, 0 ]
	las.header.scales = [ 0.001, 0.001, 0.001 ]
	las.x = cx + rng.uniform( -10, 10, count )
	las.y = cy + rng.uniform( -10, 10, count )
	las.z = rng.uniform( 0, 5, count )
	buf = io.BytesIO()
	las.write( buf )
	return buf.getvalue()
