import os
import shutil
import tempfile
from io import BytesIO

from django.contrib.gis.geos import Point
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from PIL import Image
from rest_framework.test import APIClient

from catalog.testing import ModelTestBase

from .models import Label, LabelIcon


class LabelTests( ModelTestBase ):
	def setUp( self ):
		super().setUp()
		self.model = self.make_model( self.alice )
		self.icon = LabelIcon.objects.create( name = 'pin', image = 'label/pin.png' )
		self.payload = { 'model': self.model.pk, 'name': 'Gate', 'icon': self.icon.pk,
			'position': { 'longitude': 113.2601, 'latitude': 23.1302, 'height': 21.5 }, 'properties': { 'floor': 2 } }

	def test_owner_creates_label_as_postgis_point( self ):
		r = self.as_user( self.alice ).post( '/api/v1/labels/', self.payload, format = 'json' )
		self.assertEqual( r.status_code, 201, r.data )
		label = Label.objects.get()
		self.assertEqual( ( label.position.x, label.position.y, label.position.z ), ( 113.2601, 23.1302, 21.5 ) )
		self.assertEqual( label.properties, { 'floor': 2 } )

	def test_others_cannot_label_my_model( self ):
		r = self.as_user( self.bob ).post( '/api/v1/labels/', self.payload, format = 'json' )
		self.assertEqual( r.status_code, 400 )
		self.assertIn( 'model', r.data )

	def test_others_cannot_edit_or_delete_labels( self ):
		label = Label.objects.create( model = self.model, name = 'Gate', position = Point( 113, 23, 0, srid = 4326 ) )
		bob = self.as_user( self.bob )
		self.assertEqual( bob.patch( f'/api/v1/labels/{label.pk}/', { 'name': 'x' } ).status_code, 403 )
		self.assertEqual( bob.delete( f'/api/v1/labels/{label.pk}/' ).status_code, 403 )

	def test_labels_follow_model_visibility( self ):
		Label.objects.create( model = self.model, name = 'Gate', position = Point( 113, 23, 0, srid = 4326 ) )
		self.assertEqual( APIClient().get( '/api/v1/labels/', { 'model': self.model.pk } ).data['count'], 1 )
		self.model.is_public = False
		self.model.save()
		self.assertEqual( APIClient().get( '/api/v1/labels/' ).data['count'], 0 )

	def test_invalid_position( self ):
		self.payload['position'] = { 'longitude': 200, 'latitude': 0 }
		r = self.as_user( self.alice ).post( '/api/v1/labels/', self.payload, format = 'json' )
		self.assertIn( 'position', r.data )

	def test_icons_shared_and_private( self ):
		LabelIcon.objects.create( name = 'bob icon', image = 'label/b.png', owner = self.bob )
		names = { i['name'] for i in self.as_user( self.alice ).get( '/api/v1/label-icons/' ).data['results'] }
		self.assertEqual( names, { 'pin' } )
		self.assertEqual( self.as_user( self.alice ).delete( f'/api/v1/label-icons/{self.icon.pk}/' ).status_code, 403 )


class LabelShapeTests( ModelTestBase ):
	def setUp( self ):
		super().setUp()
		self.model = self.make_model( self.alice )
		self.client = self.as_user( self.alice )
		self.corners = [ { 'longitude': 113.26, 'latitude': 23.13, 'height': 10 }, { 'longitude': 113.2602, 'latitude': 23.13, 'height': 12 },
			{ 'longitude': 113.2602, 'latitude': 23.1302, 'height': 11 } ]

	def post( self, **fields ):
		return self.client.post( '/api/v1/labels/', { 'model': self.model.pk, 'name': 'Shape', **fields }, format = 'json' )

	def test_existing_style_label_is_a_point( self ):
		r = self.post( position = self.corners[0] )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( ( r.data['kind'], r.data['points'], r.data['radius'], r.data['height'] ), ( 'point', [], None, None ) )

	def test_polygon_is_stored_as_closed_ring_and_named_at_its_middle( self ):
		r = self.post( kind = 'polygon', points = self.corners, color = '#ff8800' )
		self.assertEqual( r.status_code, 201, r.data )
		label = Label.objects.get()
		self.assertEqual( label.geometry.geom_type, 'Polygon' )
		self.assertEqual( len( label.geometry.exterior_ring.coords ), 4 )
		self.assertEqual( r.data['points'], self.corners )
		self.assertEqual( r.data['color'], '#ff8800' )
		self.assertAlmostEqual( r.data['position']['longitude'], 113.2601 )
		self.assertEqual( r.data['position']['height'], 12 )

	def test_wall_needs_two_points_and_a_height( self ):
		self.assertIn( 'points', self.post( kind = 'wall', points = self.corners[:1], height = 5 ).data )
		self.assertIn( 'height', self.post( kind = 'wall', points = self.corners[:2] ).data )
		r = self.post( kind = 'wall', points = self.corners[:2], height = 5 )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( Label.objects.get().geometry.geom_type, 'LineString' )

	def test_rectangle_and_cuboid_take_four_corners( self ):
		corners = self.corners + [ { 'longitude': 113.26, 'latitude': 23.1302, 'height': 10 } ]
		r = self.post( kind = 'rectangle', points = self.corners )
		self.assertEqual( r.data['points'], [ 'A rectangle label takes 4 points.' ] )
		r = self.post( kind = 'rectangle', points = corners )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( Label.objects.get( pk = r.data['id'] ).geometry.geom_type, 'Polygon' )
		self.assertEqual( r.data['points'], corners )
		self.assertIn( 'height', self.post( kind = 'cuboid', points = corners ).data )
		r = self.post( kind = 'cuboid', points = corners, height = 12 )
		self.assertEqual( ( r.status_code, r.data['height'] ), ( 201, 12 ) )

	def test_round_shapes_need_a_centre_and_their_sizes( self ):
		centre = self.corners[0]
		self.assertIn( 'radius', self.post( kind = 'sphere', position = centre ).data )
		self.assertIn( 'height', self.post( kind = 'cone', position = centre, radius = 3 ).data )
		self.assertIn( 'height', self.post( kind = 'circle', position = centre, radius = 3, height = 2 ).data )
		self.assertIn( 'points', self.post( kind = 'circle', position = centre, radius = 3, points = self.corners ).data )
		self.assertIn( 'position', self.post( kind = 'circle', radius = 3 ).data )
		r = self.post( kind = 'cylinder', position = centre, radius = 3, height = 8 )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( ( r.data['radius'], r.data['height'] ), ( 3, 8 ) )

	def test_shape_is_fixed_but_name_and_colour_can_change( self ):
		label_id = self.post( kind = 'polyline', points = self.corners[:2] ).data['id']
		r = self.client.patch( f'/api/v1/labels/{label_id}/', { 'points': self.corners }, format = 'json' )
		self.assertEqual( r.status_code, 400 )
		r = self.client.patch( f'/api/v1/labels/{label_id}/', { 'name': 'Fence', 'color': '#00ff00' }, format = 'json' )
		self.assertEqual( ( r.status_code, r.data['name'], r.data['color'] ), ( 200, 'Fence', '#00ff00' ) )
		self.assertEqual( len( r.data['points'] ), 2 )

	def test_invalid_colour( self ):
		self.assertIn( 'color', self.post( position = self.corners[0], color = 'red' ).data )


class LabelIconStorageTests( ModelTestBase ):
	"""Icons are written to the label icon storage (assets/label-icons/ by default), here a temporary folder."""

	def setUp( self ):
		super().setUp()
		self.root = tempfile.mkdtemp()
		self.addCleanup( shutil.rmtree, self.root )
		# the field resolves its storage once, when models load, so the test swaps it on the field itself
		field = LabelIcon._meta.get_field( 'image' )
		original = field.storage
		field.storage = FileSystemStorage( location = self.root, base_url = '/label-icons/' )
		self.addCleanup( setattr, field, 'storage', original )

	def png( self ):
		buffer = BytesIO()
		Image.new( 'RGBA', ( 4, 4 ), ( 255, 0, 0, 255 ) ).save( buffer, 'PNG' )
		buffer.seek( 0 )
		buffer.name = 'my pin.png'
		return buffer

	def test_uploaded_icon_is_saved_in_the_icon_folder_and_served_from_label_icons( self ):
		r = self.as_user( self.alice ).post( '/api/v1/label-icons/', { 'name': 'My pin', 'image': self.png() }, format = 'multipart' )
		self.assertEqual( r.status_code, 201, r.data )
		icon = LabelIcon.objects.get()
		self.assertTrue( os.path.isfile( os.path.join( self.root, icon.image.name ) ) )
		self.assertIn( '/label-icons/', r.data['image'] )
		self.assertEqual( r.data['owner'], 'alice' )

	def test_add_label_icons_shares_files_once( self ):
		path = os.path.join( self.root, 'site.png' )
		with open( path, 'wb' ) as f:
			f.write( self.png().read() )
		call_command( 'add_label_icons', path, stdout = open( os.devnull, 'w' ) )
		call_command( 'add_label_icons', path, stdout = open( os.devnull, 'w' ) )
		icon = LabelIcon.objects.get()
		self.assertEqual( ( icon.name, icon.image.name, icon.owner ), ( 'site', 'site.png', None ) )
