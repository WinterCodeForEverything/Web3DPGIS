"""Copy files from the local media/ folder into the S3 bucket, keeping their names (for moving an existing install)."""
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from processing import storage


class Command( BaseCommand ):
	help = 'Upload everything under MEDIA_ROOT to the S3 bucket under the same names, so existing models keep working.'

	def add_arguments( self, parser ):
		parser.add_argument( '--overwrite', action = 'store_true', help = 'Replace files that already exist in the bucket' )
		parser.add_argument( '--dry-run', action = 'store_true', help = 'Only list what would be copied' )

	def handle( self, *args, **options ):
		if storage.is_local_storage():
			raise CommandError( 'Set STORAGE_BACKEND=s3 (and the S3_* settings) first.' )
		root = str( settings.MEDIA_ROOT )
		bucket = default_storage.bucket
		existing = { o.key for o in bucket.objects.all() } if not options['overwrite'] else set()
		copied = skipped = 0
		for directory, _, files in os.walk( root ):
			for f in files:
				if f == '.gitkeep':
					continue
				path = os.path.join( directory, f )
				key = os.path.relpath( path, root ).replace( os.sep, '/' )
				if key.startswith( 'tmp/' ) or key in existing:
					skipped += 1
					continue
				if not options['dry_run']:
					bucket.upload_file( path, key, ExtraArgs = { **default_storage.object_parameters, 'ContentType': storage.content_type_for( path ) } )
				copied += 1
				if options['verbosity'] > 1:
					self.stdout.write( key )
		verb = 'Would copy' if options['dry_run'] else 'Copied'
		self.stdout.write( self.style.SUCCESS( f'{verb} {copied} files to bucket {default_storage.bucket_name}; {skipped} already there or skipped.' ) )
