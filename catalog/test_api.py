from django.contrib.auth.models import User
from rest_framework.test import APIClient

from .models import Model3D
from .testing import BEIJING, GUANGZHOU, PHILADELPHIA, ModelTestBase


class ModelPermissionTests( ModelTestBase ):
	def test_visibility_rules( self ):
		public = self.make_model( self.alice, 'public' )
		private = self.make_model( self.alice, 'private', is_public = False )
		hidden = self.make_model( self.alice, 'hidden', is_visible = False )
		names = lambda client: { m['name'] for m in client.get( '/api/v1/models/' ).data['results'] }
		self.assertEqual( names( APIClient() ), { 'public' } )
		self.assertEqual( names( self.as_user( self.bob ) ), { 'public' } )
		self.assertEqual( names( self.as_user( self.alice ) ), { 'public', 'private', 'hidden' } )
		self.assertEqual( APIClient().get( f'/api/v1/models/{private.pk}/' ).status_code, 404 )
		self.assertEqual( self.as_user( self.bob ).get( f'/api/v1/models/{hidden.pk}/' ).status_code, 404 )
		self.assertTrue( self.as_user( self.alice ).get( f'/api/v1/models/{public.pk}/' ).data['can_edit'] )
		self.assertFalse( self.as_user( self.bob ).get( f'/api/v1/models/{public.pk}/' ).data['can_edit'] )

	def test_only_owner_can_change_or_delete( self ):
		model = self.make_model( self.alice )
		bob = self.as_user( self.bob )
		self.assertEqual( bob.patch( f'/api/v1/models/{model.pk}/', { 'is_visible': False } ).status_code, 403 )
		self.assertEqual( bob.delete( f'/api/v1/models/{model.pk}/' ).status_code, 403 )
		self.assertEqual( APIClient().delete( f'/api/v1/models/{model.pk}/' ).status_code, 403 )
		alice = self.as_user( self.alice )
		self.assertEqual( alice.patch( f'/api/v1/models/{model.pk}/', { 'height_offset': 12.5 } ).data['height_offset'], 12.5 )
		self.assertEqual( alice.delete( f'/api/v1/models/{model.pk}/' ).status_code, 204 )
		self.assertFalse( Model3D.objects.filter( pk = model.pk ).exists() )

	def test_staff_can_manage_everything( self ):
		model = self.make_model( self.alice, is_public = False )
		staff = User.objects.create_user( 'admin', 'a@example.com', 'Sm0ke-pass-3', is_staff = True )
		self.assertEqual( self.as_user( staff ).delete( f'/api/v1/models/{model.pk}/' ).status_code, 204 )

	def test_get_never_changes_data( self ):
		model = self.make_model( self.alice )
		self.as_user( self.alice ).get( f'/api/v1/models/{model.pk}/', { 'is_visible': 'false', 'delete': '1' } )
		model.refresh_from_db()
		self.assertTrue( model.is_visible )

	def test_owner_and_status_are_read_only( self ):
		model = self.make_model( self.alice )
		self.as_user( self.alice ).patch( f'/api/v1/models/{model.pk}/', { 'owner': 'bob', 'status': 'failed' } )
		model.refresh_from_db()
		self.assertEqual( ( model.owner, model.status ), ( self.alice, 'ready' ) )


class SpatialSearchTests( ModelTestBase ):
	def setUp( self ):
		super().setUp()
		self.make_model( self.alice, 'guangzhou', GUANGZHOU )
		self.make_model( self.alice, 'beijing', BEIJING )
		self.make_model( self.alice, 'philadelphia', PHILADELPHIA )

	def test_near_sorts_by_distance_within_radius( self ):
		r = self.client.get( '/api/v1/models/', { 'near': '113.30,23.10', 'radius': 50000 } )
		self.assertEqual( [ m['name'] for m in r.data['results'] ], [ 'guangzhou' ] )
		self.assertAlmostEqual( r.data['results'][0]['distance_m'], 5200, delta = 300 )
		r = self.client.get( '/api/v1/models/', { 'near': '113.30,23.10', 'radius': 3_000_000 } )
		self.assertEqual( [ m['name'] for m in r.data['results'] ], [ 'guangzhou', 'beijing' ] )

	def test_bbox( self ):
		r = self.client.get( '/api/v1/models/', { 'bbox': '100,20,120,45' } )
		self.assertEqual( { m['name'] for m in r.data['results'] }, { 'guangzhou', 'beijing' } )

	def test_bad_coordinates( self ):
		self.assertEqual( self.client.get( '/api/v1/models/', { 'bbox': '1,2,3' } ).status_code, 400 )
		self.assertEqual( self.client.get( '/api/v1/models/', { 'near': 'abc' } ).status_code, 400 )

	def test_location_is_lon_lat_height( self ):
		r = self.client.get( '/api/v1/models/', { 'search': 'guang' } )
		self.assertEqual( r.data['results'][0]['location'], { 'longitude': 113.26, 'latitude': 23.13, 'height': 10.0 } )
