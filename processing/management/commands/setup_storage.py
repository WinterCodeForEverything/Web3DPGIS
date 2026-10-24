"""Prepare the S3 bucket: create it, let browsers read tiles from it (public read + CORS), then check that works."""
import json
import urllib.error
import urllib.request

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from core import storage


class Command( BaseCommand ):
	help = 'Create and configure the S3 bucket used with STORAGE_BACKEND=s3 (public read for tiles, CORS), then verify it.'

	def add_arguments( self, parser ):
		parser.add_argument( '--no-policy', action = 'store_true', help = 'Do not set the public-read bucket policy (configure access yourself)' )
		parser.add_argument( '--no-cors', action = 'store_true', help = 'Do not set CORS rules' )
		parser.add_argument( '--no-check', action = 'store_true', help = 'Skip the anonymous read check' )

	def handle( self, *args, **options ):
		if storage.is_local_storage():
			self.stdout.write( 'STORAGE_BACKEND is "local": files live in MEDIA_ROOT, nothing to set up.' )
			return
		client = default_storage.connection.meta.client
		bucket = default_storage.bucket_name

		try:
			client.head_bucket( Bucket = bucket )
			self.stdout.write( f'Bucket {bucket} exists.' )
		except ClientError as exc:
			if exc.response.get( 'Error', {} ).get( 'Code' ) not in ( '404', 'NoSuchBucket', 'NotFound' ):
				raise CommandError( f'Cannot reach bucket {bucket}: {exc}' )
			region = default_storage.region_name
			kwargs = { 'CreateBucketConfiguration': { 'LocationConstraint': region } } if region and region != 'us-east-1' else {}
			client.create_bucket( Bucket = bucket, **kwargs )
			self.stdout.write( self.style.SUCCESS( f'Created bucket {bucket}.' ) )

		if not options['no_policy']:
			policy = { 'Version': '2012-10-17', 'Statement': [ {
				'Sid': 'PublicReadForTilesAndImages', 'Effect': 'Allow', 'Principal': '*', 'Action': [ 's3:GetObject' ],
				'Resource': [ f'arn:aws:s3:::{bucket}/{prefix}*' for prefix in settings.STORAGE_PUBLIC_PREFIXES ],
			} ] }
			self._apply_setting( 'public-read policy for ' + ', '.join( settings.STORAGE_PUBLIC_PREFIXES ),
				lambda: client.put_bucket_policy( Bucket = bucket, Policy = json.dumps( policy ) ) )

		if not options['no_cors']:
			cors = { 'CORSRules': [ {
				'AllowedOrigins': settings.STORAGE_CORS_ORIGINS, 'AllowedMethods': [ 'GET', 'HEAD' ],
				'AllowedHeaders': [ '*' ], 'ExposeHeaders': [ 'ETag', 'Content-Length' ], 'MaxAgeSeconds': 3600,
			} ] }
			self._apply_setting( 'CORS for ' + ', '.join( settings.STORAGE_CORS_ORIGINS ), lambda: client.put_bucket_cors( Bucket = bucket, CORSConfiguration = cors ) )

		if not options['no_check']:
			self._check_public_read()

	def _apply_setting( self, what, call ):
		try:
			call()
			self.stdout.write( self.style.SUCCESS( f'Set {what}.' ) )
		except ClientError as exc:
			self.stdout.write( self.style.WARNING( f'Could not set {what}: {exc}. Configure it in your storage provider instead.' ) )

	def _check_public_read( self ):
		"""Read a probe file the way a browser on the app's origin would: anonymously, with an Origin header."""
		name = default_storage.save( 'tiles/_setup_check.json', ContentFile( b'{"ok": true}' ) )
		try:
			request = urllib.request.Request( default_storage.url( name ), headers = { 'Origin': settings.STORAGE_CORS_ORIGINS[0] } )
			try:
				with urllib.request.urlopen( request, timeout = 10 ) as response:
					allowed = response.headers.get( 'Access-Control-Allow-Origin' )
			except urllib.error.HTTPError as exc:
				raise CommandError( f'Browsers cannot read tiles yet: GET {request.full_url} returned {exc.code}. '
					'Allow anonymous read on the public prefixes in your storage provider.' )
			self.stdout.write( self.style.SUCCESS( f'Anonymous read works: {request.full_url}' ) )
			if allowed in ( '*', settings.STORAGE_CORS_ORIGINS[0] ):
				self.stdout.write( self.style.SUCCESS( f'CORS allows {settings.STORAGE_CORS_ORIGINS[0]}.' ) )
			else:
				self.stdout.write( self.style.WARNING( f'No CORS header for {settings.STORAGE_CORS_ORIGINS[0]}; the viewer will not load tiles from another origin.' ) )
		finally:
			default_storage.delete( name )
