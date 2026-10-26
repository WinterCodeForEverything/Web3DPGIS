"""Keeps the modules independent: each app may import only the apps listed for it here.

core            shared building blocks; imports no app
processing      job engine and tiling; knows models only through its Job.model foreign key
catalog         3D models; starts processing jobs
labels, viewer_tools, …   features attached to a model
reconstruction  photos to a model; a job kind that hands its mesh to the tiling job
api             only puts the apps' own api modules together

A new app (e.g. reconstruction) gets an entry here; tests and migrations are not checked.
"""
import ast
import os

from django.conf import settings
from django.test import SimpleTestCase

ALLOWED = {
	'config': set(),
	'core': set(),
	'api': { 'core' },
	'accounts': { 'core' },
	'processing': { 'core' },
	'catalog': { 'core', 'processing' },
	'labels': { 'core', 'catalog' },
	'viewer_tools': { 'core', 'catalog' },
	'reconstruction': { 'core', 'catalog', 'processing' },
}


def imported_apps( path, apps ):
	tree = ast.parse( open( path, encoding = 'utf-8' ).read(), path )
	for node in ast.walk( tree ):
		names = [ a.name for a in node.names ] if isinstance( node, ast.Import ) else [ node.module ] if isinstance( node, ast.ImportFrom ) and node.level == 0 and node.module else []
		for name in names:
			top = name.split( '.' )[0]
			if top in apps:
				yield top, node.lineno


class DependencyRuleTests( SimpleTestCase ):
	def test_every_app_has_a_rule( self ):
		ours = { a.split( '.' )[0] for a in settings.INSTALLED_APPS if os.path.isdir( settings.BASE_DIR / a.split( '.' )[0] ) }
		self.assertEqual( ours - set( ALLOWED ), set(), 'Add the new app to ALLOWED in core/test_architecture.py' )

	def test_apps_import_only_what_they_may( self ):
		problems = []
		for app, allowed in ALLOWED.items():
			for root, dirs, files in os.walk( settings.BASE_DIR / app ):
				dirs[:] = [ d for d in dirs if d not in ( 'migrations', '__pycache__' ) ]
				for name in files:
					if not name.endswith( '.py' ) or name.startswith( 'test' ):
						continue
					path = os.path.join( root, name )
					for other, line in imported_apps( path, set( ALLOWED ) - { app } ):
						if other not in allowed:
							problems.append( f'{os.path.relpath( path, settings.BASE_DIR )}:{line} imports {other}' )
		self.assertEqual( problems, [], 'Imports that break the dependency rules' )
