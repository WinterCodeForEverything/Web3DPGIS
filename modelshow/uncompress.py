import os
import threading
import zipfile
import tarfile
import logging
import rarfile



BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
package_path = os.path.join( BASE_DIR, 'media/package' ).replace( '\\', '/' )
uncomp_path = os.path.join( BASE_DIR, 'media/Data' ).replace( '\\', '/' )

logger = logging.getLogger( __name__ )

def uncompressThreading( name ):
	t = threading.Thread( target = uncompress, args = ( name, ), daemon = True )
	t.start()

def _check_members( names, data_path ):
	# reject archive entries that would be written outside data_path ("zip slip")
	root = os.path.realpath( data_path )
	for member in names:
		target = os.path.realpath( os.path.join( root, member ) )
		if target != root and not target.startswith( root + os.sep ):
			raise ValueError( 'Unsafe path in archive: %s' % member )

def uncompress( name ):
	_, com_name = os.path.split( name )
	unc_title, unc_ext = os.path.splitext( com_name )
	unc_ext = unc_ext.lower()
	data_path = os.path.join( uncomp_path, unc_title ).replace( '\\', '/' )
	unc_name = os.path.join( package_path, com_name ).replace( '\\', '/' )
	if not os.path.exists( data_path ):
		os.makedirs( data_path )
		try:
			if '.zip' == unc_ext:
				with zipfile.ZipFile( unc_name ) as zip_file:
					_check_members( zip_file.namelist(), data_path )
					zip_file.extractall( data_path )
			elif '.tar' == unc_ext or com_name.lower().endswith( ( '.tar.gz', '.tgz' ) ):
				with tarfile.open( unc_name ) as tar_file:
					tar_file.extractall( data_path, filter = 'data' )
			elif '.rar' == unc_ext:
				# requires the `unrar` (or `bsdtar`) command-line tool
				with rarfile.RarFile( unc_name ) as rar_file:
					_check_members( rar_file.namelist(), data_path )
					rar_file.extractall( data_path )
		except Exception:
			logger.exception( 'Failed to uncompress %s', unc_name )
