"""Add image files to the label icon library as shared icons (no owner), named after the files.

    manage.py add_label_icons assets/label-icons/*.png

A file already in the icon storage folder (assets/label-icons/ with local storage) is used where it is; any other file is
copied into the icon storage. A file whose stored name is already an icon is skipped, so running it again is harmless.
"""
import os

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from labels.models import LabelIcon


class Command( BaseCommand ):
	help = 'Add image files to the label icon library as icons shared with everyone.'

	def add_arguments( self, parser ):
		parser.add_argument( 'files', nargs = '+', help = 'Image files (PNG, JPEG, SVG …)' )

	def handle( self, *args, files, **options ):
		storage = LabelIcon._meta.get_field( 'image' ).storage
		root = os.path.realpath( storage.location ) if hasattr( storage, 'path' ) else None
		for path in files:
			if not os.path.isfile( path ):
				raise CommandError( f'Not a file: {path}' )
			full = os.path.realpath( path )
			name = os.path.relpath( full, root ) if root and full.startswith( root + os.sep ) else os.path.basename( full )
			label = os.path.splitext( os.path.basename( full ) )[0].replace( '-', ' ' ).replace( '_', ' ' )
			if LabelIcon.objects.filter( image = name ).exists():
				self.stdout.write( f'skipped {name}: already an icon' )
				continue
			if not ( root and full.startswith( root + os.sep ) ):
				with open( full, 'rb' ) as f:
					name = storage.save( name, File( f ) )
			LabelIcon.objects.create( name = label, image = name )
			self.stdout.write( self.style.SUCCESS( f'added "{label}" ({storage.url( name )})' ) )
