"""Level-of-detail 3D Tiles from a large OBJ mesh with Obj2Tiles: simplified copies of the mesh for distant views and
spatial tiles for close ones, so a viewer loads only what is in view.

Obj2Tiles 1.6.2 reads every OBJ as Y-up when it places the tileset (its --y-up-to-z-up flag changes nothing), but it
splits the mesh along the OBJ's x and y axes. For a Y-up mesh that cuts terrain into upper and lower slabs instead of
north and south tiles. So the mesh is rewritten Z-up first (horizontal splits), and the root transform of the result
is turned back by the same quarter turn. Free of Django, so the reconstruction script can use it too.
"""
import json
import os
import shutil
import subprocess

# what a viewer sees in the tileset frame after Obj2Tiles, given a Z-up OBJ: (east, -up, north). This column-major
# matrix maps that back to (east, north, up); the root transform is multiplied by it.
_UNDO_Y_UP = [ 1, 0, 0, 0,  0, 0, -1, 0,  0, 1, 0, 0,  0, 0, 0, 1 ]
IDENTITY = [ 1, 0, 0, 0,  0, 1, 0, 0,  0, 0, 1, 0,  0, 0, 0, 1 ]


def y_up_to_z_up( src, dst ):
	"""Copy an OBJ with its vertices and normals turned from Y-up to Z-up: ( x, y, z ) → ( x, -z, y ).
	dst sits next to src so the material and texture paths still resolve."""
	with open( src, encoding = 'utf-8', errors = 'surrogateescape' ) as f, \
			open( dst, 'w', encoding = 'utf-8', errors = 'surrogateescape' ) as out:
		for line in f:
			if line.startswith( ( 'v ', 'vn ' ) ):
				parts = line.split()
				x, y, z = parts[1:4]
				rest = ' '.join( parts[4:] )   # vertex colours, if any
				neg = z[1:] if z.startswith( '-' ) else '-' + z
				line = f'{parts[0]} {x} {neg} {y}' + ( f' {rest}' if rest else '' ) + '\n'
			out.write( line )


def _matmul( a, b ):
	"""Product of two column-major 4x4 matrices."""
	return [ sum( a[ k * 4 + r ] * b[ c * 4 + k ] for k in range( 4 ) ) for c in range( 4 ) for r in range( 4 ) ]


def _drop_null_children( tile ):
	# Obj2Tiles writes "children": null on leaf tiles; 3D Tiles allows only an array there
	if tile.get( 'children' ) is None:
		tile.pop( 'children', None )
	for child in tile.get( 'children', [] ):
		_drop_null_children( child )


def undo_y_up( tileset_path ):
	"""Turn the tileset's root by a quarter turn about east, after tiling a Z-up OBJ (see the module docstring),
	and tidy what Obj2Tiles writes against the 3D Tiles spec."""
	with open( tileset_path, encoding = 'utf-8' ) as f:
		tileset = json.load( f )
	root = tileset['root']
	root['transform'] = _matmul( root.get( 'transform' ) or IDENTITY, _UNDO_Y_UP )
	_drop_null_children( root )
	with open( tileset_path, 'w', encoding = 'utf-8' ) as f:
		json.dump( tileset, f )


def obj_to_lod_tileset( obj2tiles, obj, out_dir, location, log = print, lods = 3, divisions = 2, max_texture_size = 2048,
		texture_quality = 75, run = None ):
	"""Write out_dir/tileset.json for a Y-up OBJ in metres, placed with its origin at location ( lon, lat, height ).
	`run( args )` runs the command and raises on failure (default: subprocess, output to log)."""
	lon, lat, height = location
	zup = os.path.join( os.path.dirname( obj ), '_zup_' + os.path.basename( obj ) )
	log( f'Rewriting {os.path.basename( obj )} Z-up for horizontal tiles' )
	y_up_to_z_up( obj, zup )
	shutil.rmtree( out_dir, ignore_errors = True )
	args = [ obj2tiles, '--lods', lods, '--divisions', divisions, '--octree', '--lat', lat, '--lon', lon, '--alt', height,
		'--max-texture-size', max_texture_size, '--texture-quality', texture_quality, zup, out_dir ]
	try:
		( run or _default_run( log ) )( [ str( a ) for a in args ] )
	finally:
		os.remove( zup )
	tileset = os.path.join( out_dir, 'tileset.json' )
	undo_y_up( tileset )
	return tileset


def _default_run( log ):
	def run( args ):
		log( '$ ' + ' '.join( args ) )
		result = subprocess.run( args, capture_output = True, text = True )
		if result.returncode:
			log( ( result.stdout + result.stderr ).strip()[-4000:] )
			raise RuntimeError( f'Obj2Tiles failed (exit code {result.returncode})' )
	return run
