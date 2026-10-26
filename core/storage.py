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


def is_local_storage( storage = None ):
	# default_storage is a lazy proxy; isinstance sees through it to the configured class
	return isinstance( storage or default_storage, FileSystemStorage )


def content_type_for( name ):
	ext = os.path.splitext( name )[1].lower()
	return CONTENT_TYPES.get( ext ) or mimetypes.guess_type( name )[0] or 'application/octet-stream'


def local_copy( field_file, directory ):
	"""A local path holding field_file's contents: the file itself on local disk, else a download into directory."""
	if is_local_storage( field_file.storage ):
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
	if is_local_storage( storage ):
		shutil.rmtree( storage.path( prefix ), ignore_errors = True )
	else:
		storage.bucket.objects.filter( Prefix = prefix + '/' ).delete()


def list_prefix( prefix, storage = None ):
	"""Names of stored files under prefix/, for tests and maintenance."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	if is_local_storage( storage ):
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
	if is_local_storage( storage ):
		shutil.copytree( local_dir, storage.path( prefix ) )
	else:
		bucket = storage.bucket
		extra = dict( getattr( storage, 'object_parameters', {} ) )

		def upload( path ):
			key = prefix + '/' + os.path.relpath( path, local_dir ).replace( os.sep, '/' )
			bucket.upload_file( path, key, ExtraArgs = { **extra, 'ContentType': content_type_for( path ) } )

		with ThreadPoolExecutor( max_workers = 8 ) as pool:
			list( pool.map( upload, files ) )
	if log:
		log( f'Published {len( files )} files to {"media" if is_local_storage( storage ) else "bucket " + storage.bucket_name}/{prefix}/' )
	return len( files )


def presigned_upload( name, content_type, expires = 3600, storage = None ):
	"""A URL the browser can PUT name's contents to directly (S3 storage), or None on local storage."""
	storage = storage or default_storage
	if is_local_storage( storage ):
		return None
	key = storage._normalize_name( storage._clean_name( name ) )   # django-storages: adds the bucket location prefix
	return storage.bucket.meta.client.generate_presigned_url( 'put_object', ExpiresIn = expires,
		Params = { 'Bucket': storage.bucket_name, 'Key': key, 'ContentType': content_type } )


def upload_directory( local_dir, prefix, skip = (), storage = None ):
	"""Copy files under local_dir to prefix/ when missing there or of a different size, e.g. a job's checkpoints.
	Top-level folders named in skip are left out. Returns the number of files copied."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	copied = 0
	for d, dirs, names in os.walk( local_dir ):
		if os.path.samefile( d, local_dir ):
			dirs[:] = [ x for x in dirs if x not in skip ]
		for f in names:
			path = os.path.join( d, f )
			name = prefix + '/' + os.path.relpath( path, local_dir ).replace( os.sep, '/' )
			if storage.exists( name ) and storage.size( name ) == os.path.getsize( path ):
				continue
			if storage.exists( name ):
				storage.delete( name )
			with open( path, 'rb' ) as src:
				storage.save( name, src )
			copied += 1
	return copied


def download_prefix( prefix, local_dir, storage = None ):
	"""Copy every stored file under prefix/ into local_dir, keeping the folder structure. Returns the number of files."""
	storage = storage or default_storage
	prefix = prefix.strip( '/' )
	names = list_prefix( prefix, storage )
	for name in names:
		target = os.path.join( local_dir, os.path.relpath( name, prefix ) )
		os.makedirs( os.path.dirname( target ), exist_ok = True )
		with storage.open( name, 'rb' ) as src, open( target, 'wb' ) as dst:
			shutil.copyfileobj( src, dst, 1024 * 1024 )
	return len( names )
