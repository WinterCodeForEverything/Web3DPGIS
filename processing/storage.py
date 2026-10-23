"""File storage for uploads and generated tiles, on local disk or in an S3-compatible bucket.

Converters need real files, so the pipeline works in a local temp folder and moves files in and out of
storage with the helpers here; everything else goes through Django's `default_storage`.
"""
import mimetypes
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from django.core.files.storage import FileSystemStorage, default_storage

CONTENT_TYPES = {
	'.json': 'application/json',
	'.glb': 'model/gltf-binary',
	'.gltf': 'model/gltf+json',
	'.b3dm': 'application/octet-stream',
	'.i3dm': 'application/octet-stream',
	'.pnts': 'application/octet-stream',
	'.cmpt': 'application/octet-stream',
	'.subtree': 'application/octet-stream',
}


def is_local( storage = None ):
	# default_storage is a lazy proxy; isinstance sees through it to the configured class
	return isinstance( storage or default_storage, FileSystemStorage )


def content_type( name ):
	ext = os.path.splitext( name )[1].lower()
	return CONTENT_TYPES.get( ext ) or mimetypes.guess_type( name )[0] or 'application/octet-stream'


def local_copy( field_file, directory ):
	"""A local path holding field_file's contents: the file itself on local disk, else a download into directory."""
	if is_local( field_file.storage ):
		return field_file.path
	os.makedirs( directory, exist_ok = True )
	target = os.path.join( directory, os.path.basename( field_file.name ) )
	with field_file.storage.open( field_file.name, 'rb' ) as src, open( target, 'wb' ) as dst:
		shutil.copyfileobj( src, dst, 1024 * 1024 )
	return target


def delete_prefix( prefix, storage = None ):
	"""Delete every stored file whose name starts with prefix/ (a model's tiles folder)."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	if not prefix:
		raise ValueError( 'Refusing to delete the whole storage' )
	if is_local( storage ):
		shutil.rmtree( storage.path( prefix ), ignore_errors = True )
	else:
		storage.bucket.objects.filter( Prefix = prefix + '/' ).delete()


def list_prefix( prefix, storage = None ):
	"""Names of stored files under prefix/, for tests and maintenance."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	if is_local( storage ):
		root = storage.path( prefix )
		return sorted( os.path.relpath( os.path.join( d, f ), storage.path( '' ) ).replace( os.sep, '/' )
			for d, _, files in os.walk( root ) for f in files )
	return sorted( o.key for o in storage.bucket.objects.filter( Prefix = prefix + '/' ) )


def publish_directory( local_dir, prefix, log = None, storage = None ):
	"""Replace everything under prefix/ in storage with the contents of local_dir. Returns the number of files."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	files = [ os.path.join( d, f ) for d, _, names in os.walk( local_dir ) for f in names ]
	delete_prefix( prefix, storage )
	if is_local( storage ):
		shutil.copytree( local_dir, storage.path( prefix ) )
	else:
		bucket = storage.bucket
		extra = dict( getattr( storage, 'object_parameters', {} ) )

		def upload( path ):
			key = prefix + '/' + os.path.relpath( path, local_dir ).replace( os.sep, '/' )
			bucket.upload_file( path, key, ExtraArgs = { **extra, 'ContentType': content_type( path ) } )

		with ThreadPoolExecutor( max_workers = 8 ) as pool:
			list( pool.map( upload, files ) )
	if log:
		log( f'Published {len( files )} files to {"media" if is_local( storage ) else "bucket " + storage.bucket_name}/{prefix}/' )
	return len( files )


def url( name, storage = None ):
	return ( storage or default_storage ).url( name )
