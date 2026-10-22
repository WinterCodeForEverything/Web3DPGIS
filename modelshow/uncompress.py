import os
import threading
import zipfile
import tarfile
from unrar import rarfile
#from django.http import JsonResponse



BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
package_path = os.path.join( BASE_DIR, 'media/package' ).replace( '\\', '/' )
uncomp_path = os.path.join( BASE_DIR, 'media/Data' ).replace( '\\', '/' )

def uncompressThreading( name ):
	t = threading.Thread( target = uncompress, args = ( name, ) )
	t.start()

def uncompress( name ):
	_, com_name = os.path.split( name )
	unc_title, unc_ext = os.path.splitext( com_name )
	data_path = os.path.join( uncomp_path, unc_title ).replace( '\\', '/' )
	unc_name = os.path.join( package_path, com_name ).replace( '\\', '/' )
	if not os.path.exists( data_path ):
		os.makedirs( data_path )
		if '.zip' == unc_ext:
			zip_file = zipfile.ZipFile( unc_name )
			for names in zip_file.namelist():
				zip_file.extract( names, data_path + '/' )
			zip_file.close()
		elif '.tar' == unc_ext:
			tar_file = tarfile.open( unc_name )
			for names in tar_file.getnames():
				tar_file.extract( name, data_path + '/' )
			tar_file.close()
		elif '.rar' == unc_ext:
			rar_file = rarfile.RarFile( unc_name )
			rar_file.extractall( data_path )
			rar_file.close()
