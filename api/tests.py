import shutil
import tempfile

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from addlabel.models import Label, LabelIcon
from modelshow.models import Model3D
from viewermode.models import FlightPath

GUANGZHOU = ( 113.26, 23.13 )
BEIJING = ( 116.40, 39.90 )
PHILADELPHIA = ( -75.16, 39.95 )


class APITestBase( APITestCase ):
	@classmethod
	def setUpClass( cls ):
		super().setUpClass()
		cls._media = tempfile.mkdtemp()
		cls._override = override_settings( MEDIA_ROOT = cls._media )
		cls._override.enable()

	@classmethod
	def tearDownClass( cls ):
		cls._override.disable()
		shutil.rmtree( cls._media, ignore_errors = True )
		super().tearDownClass()

	def setUp( self ):
		self.alice = User.objects.create_user( 'alice', 'alice@example.com', 'Sm0ke-pass-1' )
		self.bob = User.objects.create_user( 'bob', 'bob@example.com', 'Sm0ke-pass-2' )

	def make_model( self, owner, name = 'site', where = GUANGZHOU, **kwargs ):
		return Model3D.objects.create( name = name, owner = owner, source_file = 'package/x.zip', status = 'ready',
			tileset_path = f'tiles/{name}/tileset.json', location = Point( *where, 10.0, srid = 4326 ), **kwargs )

	def as_user( self, user ):
		client = APIClient()
		client.force_authenticate( user )
		return client


class AuthTests( APITestBase ):
	def test_register_logs_in( self ):
		r = self.client.post( '/api/v1/auth/register/', { 'username': 'carol', 'email': 'carol@example.com', 'password': 'Tr1cky-pass' } )
		self.assertEqual( r.status_code, 201, r.data )
		self.assertEqual( self.client.get( '/api/v1/auth/me/' ).data['username'], 'carol' )

	def test_register_rejects_duplicates_and_weak_passwords( self ):
		r = self.client.post( '/api/v1/auth/register/', { 'username': 'ALICE', 'email': 'new@example.com', 'password': 'Tr1cky-pass' } )
		self.assertIn( 'username', r.data )
		r = self.client.post( '/api/v1/auth/register/', { 'username': 'dave', 'email': 'alice@example.com', 'password': 'Tr1cky-pass' } )
		self.assertIn( 'email', r.data )
		r = self.client.post( '/api/v1/auth/register/', { 'username': 'dave', 'email': 'dave@example.com', 'password': '123' } )
		self.assertEqual( r.status_code, 400 )

	def test_login_with_username_or_email( self ):
		for login in ( 'alice', 'alice@example.com', 'ALICE@example.com' ):
			client = APIClient()
			r = client.post( '/api/v1/auth/login/', { 'login': login, 'password': 'Sm0ke-pass-1' } )
			self.assertEqual( r.status_code, 200, login )
			self.assertEqual( client.get( '/api/v1/auth/me/' ).data['username'], 'alice' )

	def test_wrong_password( self ):
		r = self.client.post( '/api/v1/auth/login/', { 'login': 'alice', 'password': 'nope' } )
		self.assertEqual( r.status_code, 400 )
		self.assertIsNone( self.client.get( '/api/v1/auth/me/' ).data )

	def test_logout( self ):
		self.client.post( '/api/v1/auth/login/', { 'login': 'alice', 'password': 'Sm0ke-pass-1' } )
		self.client.post( '/api/v1/auth/logout/' )
		self.assertIsNone( self.client.get( '/api/v1/auth/me/' ).data )

	def test_session_writes_need_csrf_token( self ):
		client = APIClient( enforce_csrf_checks = True )
		client.login( username = 'alice', password = 'Sm0ke-pass-1' )
		model = self.make_model( self.alice )
		self.assertEqual( client.patch( f'/api/v1/models/{model.pk}/', { 'name': 'x' } ).status_code, 403 )
		token = client.get( '/api/v1/auth/me/' ).cookies['csrftoken'].value
		r = client.patch( f'/api/v1/models/{model.pk}/', { 'name': 'x' }, HTTP_X_CSRFTOKEN = token )
		self.assertEqual( r.status_code, 200 )

	def test_token_auth( self ):
		r = self.client.post( '/api/v1/auth/token/', { 'username': 'alice', 'password': 'Sm0ke-pass-1' } )
		client = APIClient()
		client.credentials( HTTP_AUTHORIZATION = 'Token ' + r.data['token'] )
		self.assertEqual( client.get( '/api/v1/auth/me/' ).data['username'], 'alice' )


class ModelPermissionTests( APITestBase ):
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


class SpatialSearchTests( APITestBase ):
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


class LabelTests( APITestBase ):
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


class FlightPathTests( APITestBase ):
	def setUp( self ):
		super().setUp()
		self.model = self.make_model( self.alice )
		pose = lambda h: { 'position': { 'longitude': 113.26, 'latitude': 23.13, 'height': h }, 'direction': [ 0, 0, -1 ], 'up': [ 0, 1, 0 ] }
		self.payload = { 'model': self.model.pk, 'name': 'tour', 'points': [ pose( 100 ), pose( 200 ), pose( 300 ) ] }

	def test_create_and_read_back_in_order( self ):
		alice = self.as_user( self.alice )
		r = alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' )
		self.assertEqual( r.status_code, 201, r.data )
		r = alice.get( f'/api/v1/flight-paths/{r.data["id"]}/' )
		self.assertEqual( [ p['position']['height'] for p in r.data['points'] ], [ 100, 200, 300 ] )

	def test_update_replaces_points( self ):
		alice = self.as_user( self.alice )
		path_id = alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' ).data['id']
		self.payload['points'] = self.payload['points'][:2]
		alice.put( f'/api/v1/flight-paths/{path_id}/', self.payload, format = 'json' )
		self.assertEqual( FlightPath.objects.get().points.count(), 2 )

	def test_validation( self ):
		alice = self.as_user( self.alice )
		alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' )
		self.assertIn( 'name', alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' ).data )
		self.payload.update( name = 'short', points = self.payload['points'][:1] )
		self.assertIn( 'points', alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' ).data )
		self.payload['points'][0]['direction'] = [ 1, 2 ]
		self.assertEqual( alice.post( '/api/v1/flight-paths/', self.payload, format = 'json' ).status_code, 400 )

	def test_others_cannot_add_paths( self ):
		self.assertEqual( self.as_user( self.bob ).post( '/api/v1/flight-paths/', self.payload, format = 'json' ).status_code, 400 )


class SchemaTests( APITestBase ):
	def test_openapi_schema_and_docs( self ):
		self.assertEqual( self.client.get( '/api/schema/' ).status_code, 200 )
		self.assertEqual( self.client.get( '/api/docs/' ).status_code, 200 )
