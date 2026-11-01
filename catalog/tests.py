"""The 2019 → PostGIS data migrations, run forwards, backwards and forwards again on real rows."""
import json
import os
import shutil
import tempfile

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from core.geodesy import enu_to_ecef_matrix, geodetic_to_ecef

OLD_SCHEMA = [ ( 'modelshow', '0012_auto_20181212_0906' ), ( 'addlabel', '0006_auto_20190412_1508' ), ( 'viewermode', '0001_initial' ) ]
GATE = ( 113.26, 23.13, 20.0 )   # where the 2019 label and camera pose sit


class MigrationRoundTripTests( TransactionTestCase ):

	def setUp( self ):
		self.media = tempfile.mkdtemp()
		self.addCleanup( shutil.rmtree, self.media, True )
		override = override_settings( MEDIA_ROOT = self.media )
		override.enable()
		self.addCleanup( override.disable )
		# a 2019 upload extracted to media/Data/<archive name>/…/tileset.json, georeferenced at Guangzhou
		folder = os.path.join( self.media, 'Data', 'site', 'inner' )
		os.makedirs( folder )
		with open( os.path.join( folder, 'tileset.json' ), 'w' ) as f:
			json.dump( { 'asset': { 'version': '1.0' }, 'geometricError': 10,
				'root': { 'boundingVolume': { 'sphere': [ 0, 0, 0, 20 ] }, 'geometricError': 0, 'transform': enu_to_ecef_matrix( 113.26, 23.13, 15.0 ) } }, f )

	def tearDown( self ):
		# leave the schema at the latest migrations for the tests that run after this one
		self.migrate( self.latest() )

	def migrate( self, targets ):
		executor = MigrationExecutor( connection )
		executor.loader.build_graph()
		# the whole project's state after migrating (all apps), as historical models
		return executor.migrate( targets ).apps

	def latest( self ):
		executor = MigrationExecutor( connection )
		return executor.loader.graph.leaf_nodes()

	def assert_new_schema( self, apps ):
		Model3D = apps.get_model( 'modelshow', 'Model3D' )
		Label = apps.get_model( 'addlabel', 'Label' )
		FlightPoint = apps.get_model( 'viewermode', 'FlightPoint' )
		m = Model3D.objects.get()
		self.assertEqual( ( m.name, m.owner.username, m.is_visible, m.height_offset, m.status ), ( 'Old model', 'olduser', False, 12.0, 'ready' ) )
		self.assertEqual( m.tileset_path, 'Data/site/inner/tileset.json' )
		for got, want in zip( m.location.coords, ( 113.26, 23.13, 15.0 ) ):
			self.assertAlmostEqual( got, want, places = 6 )
		label = Label.objects.get()
		for got, want in zip( label.position.coords, GATE ):
			self.assertAlmostEqual( got, want, places = 6 )
		# icons live in their own storage since labels 0009 (assets/label-icons/), so the name loses its old label/ folder
		self.assertEqual( ( label.name, label.icon.image.name, label.properties ), ( 'Gate', 'pin.png', { 'property_url': '/media/label/1/1.json' } ) )
		point = FlightPoint.objects.get()
		self.assertEqual( ( point.direction, point.up, point.order ), ( [ 0.0, 0.0, -1.0 ], [ 0.0, 1.0, 0.0 ], 0 ) )
		for got, want in zip( point.position.coords, GATE ):
			self.assertAlmostEqual( got, want, places = 6 )

	def test_forwards_backwards_forwards( self ):
		old = self.migrate( OLD_SCHEMA )
		x, y, z = geodetic_to_ecef( *GATE )
		user = old.get_model( 'auth', 'User' ).objects.create( username = 'olduser', email = 'o@example.com' )
		model = old.get_model( 'modelshow', 'SearchModels' ).objects.create(
			name = 'Old model', image = 'image/a.png', data = 'package/site.zip', builder = user.username, isPublic = True, canSee = 0, relativeheight = 12 )
		base = old.get_model( 'addlabel', 'LabelBase' ).objects.create( source = 'pin.png' )
		old.get_model( 'addlabel', 'ModelLabel' ).objects.create(
			name = 'Gate', coord_x = x, coord_y = y, coord_z = z, property_url = '/media/label/1/1.json', model = model, labelbase = base )
		path = old.get_model( 'viewermode', 'FlightPath' ).objects.create( name = 'tour', model = model )
		old.get_model( 'viewermode', 'FlightPoint' ).objects.create( path = path, position_x = x, position_y = y, position_z = z,
			direction_x = 0, direction_y = 0, direction_z = -1, up_x = 0, up_y = 1, up_z = 0 )

		self.assert_new_schema( self.migrate( self.latest() ) )

		old = self.migrate( OLD_SCHEMA )
		m = old.get_model( 'modelshow', 'SearchModels' ).objects.get()
		self.assertEqual( ( m.builder, m.canSee, m.relativeheight ), ( 'olduser', 0, 12 ) )
		self.assertEqual( old.get_model( 'addlabel', 'LabelBase' ).objects.get().source, 'pin.png' )
		label = old.get_model( 'addlabel', 'ModelLabel' ).objects.get()
		for got, want in zip( ( label.coord_x, label.coord_y, label.coord_z ), ( x, y, z ) ):
			self.assertAlmostEqual( got, want, places = 3 )
		self.assertEqual( label.property_url, '/media/label/1/1.json' )
		point = old.get_model( 'viewermode', 'FlightPoint' ).objects.get()
		self.assertAlmostEqual( float( point.position_x ), x, places = 3 )
		self.assertEqual( float( point.up_y ), 1.0 )

		self.assert_new_schema( self.migrate( self.latest() ) )
