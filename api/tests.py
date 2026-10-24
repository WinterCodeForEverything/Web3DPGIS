import math
import shutil
import tempfile

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from addlabel.models import Label, LabelIcon
from modelshow.models import Model3D
from processing.geodesy import ecef_to_geodetic, geodetic_to_ecef
from viewermode.models import FlightPath, Measurement

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


def enu_point( base, east, north, up ):
	"""(lon, lat, height) of the point east/north/up metres from base (lon, lat, height)."""
	lon, lat = math.radians( base[0] ), math.radians( base[1] )
	e = ( -math.sin( lon ), math.cos( lon ), 0.0 )
	n = ( -math.sin( lat ) * math.cos( lon ), -math.sin( lat ) * math.sin( lon ), math.cos( lat ) )
	u = ( math.cos( lat ) * math.cos( lon ), math.cos( lat ) * math.sin( lon ), math.sin( lat ) )
	o = geodetic_to_ecef( *base )
	return ecef_to_geodetic( *( o[i] + east * e[i] + north * n[i] + up * u[i] for i in range( 3 ) ) )


def geo( p ):
	return { 'longitude': p[0], 'latitude': p[1], 'height': p[2] }


class MeasurementTests( APITestBase ):
	def setUp( self ):
		super().setUp()
		self.model = self.make_model( self.alice )
		self.base = ( *GUANGZHOU, 10.0 )
		at = lambda e, n, u = 0: geo( enu_point( self.base, e, n, u ) )
		# a 30 m + 40 m + 12 m path, and a 100 m x 50 m rectangle tilted up 50 m along its north side
		self.path = [ at( 0, 0 ), at( 30, 0 ), at( 30, 40 ), at( 30, 40, 12 ) ]
		self.roof = [ at( 0, 0 ), at( 100, 0 ), at( 100, 50, 50 ), at( 0, 50, 50 ) ]

	def post( self, user, kind, points, **extra ):
		return self.as_user( user ).post( '/api/v1/measurements/', { 'model': self.model.pk, 'kind': kind, 'points': points, **extra }, format = 'json' )

	def test_distance_is_one_linestring_with_per_segment_lengths( self ):
		r = self.post( self.alice, 'distance', self.path, name = 'fence' )
		self.assertEqual( r.status_code, 201, r.data )
		m = Measurement.objects.get()
		self.assertEqual( ( m.geometry.geom_type, m.geometry.hasz, len( m.geometry.coords ) ), ( 'LineString', True, 4 ) )
		self.assertEqual( m.created_by, self.alice )
		for got, want in zip( r.data['results']['segment_lengths_m'], [ 30, 40, 12 ] ):
			self.assertAlmostEqual( got, want, places = 3 )
		self.assertAlmostEqual( r.data['results']['length_m'], 82, places = 3 )
		self.assertEqual( len( r.data['points'] ), 4 )
		self.assertAlmostEqual( r.data['points'][3]['height'], self.path[3]['height'], places = 6 )

	def test_area_is_a_closed_polygon_with_surface_and_plan_area( self ):
		r = self.post( self.alice, 'area', self.roof )
		self.assertEqual( r.status_code, 201, r.data )
		ring = Measurement.objects.get().geometry.exterior_ring.coords
		self.assertEqual( ( len( ring ), ring[0] == ring[-1] ), ( 5, True ) )
		results = r.data['results']
		self.assertAlmostEqual( results['plan_area_m2'], 5000, delta = 1 )
		self.assertAlmostEqual( results['area_m2'], 100 * math.hypot( 50, 50 ), delta = 1 )
		self.assertEqual( len( results['edge_lengths_m'] ), 4 )
		self.assertAlmostEqual( results['perimeter_m'], 200 + 2 * math.hypot( 50, 50 ), delta = 0.01 )
		self.assertEqual( len( r.data['points'] ), 4 )    # the closing vertex is not repeated

	def test_other_kinds( self ):
		point = self.post( self.alice, 'point', self.path[:1] )
		self.assertEqual( ( point.status_code, Measurement.objects.get( pk = point.data['id'] ).geometry.geom_type ), ( 201, 'Point' ) )
		height = self.post( self.alice, 'height', [ self.path[0], self.path[3] ] ).data['results']
		self.assertAlmostEqual( height['vertical_m'], 12, places = 3 )
		self.assertAlmostEqual( height['horizontal_m'], 50, places = 3 )
		circle = self.post( self.alice, 'circle', self.path[:2] ).data['results']
		self.assertAlmostEqual( circle['radius_m'], 30, places = 3 )

	def test_point_counts_are_checked( self ):
		self.assertIn( 'points', self.post( self.alice, 'distance', self.path[:1] ).data )
		self.assertIn( 'points', self.post( self.alice, 'area', self.path[:2] ).data )
		self.assertIn( 'points', self.post( self.alice, 'height', self.path[:3] ).data )
		self.assertIn( 'kind', self.post( self.alice, 'volume', self.path ).data )
		self.assertEqual( self.post( self.alice, 'distance', [ self.path[0], { 'longitude': 300, 'latitude': 0 } ] ).status_code, 400 )

	def test_measurements_are_personal( self ):
		self.post( self.alice, 'distance', self.path )
		mine = self.post( self.bob, 'distance', self.path )    # anyone signed in can measure a public model
		self.assertEqual( mine.status_code, 201, mine.data )
		self.assertEqual( self.as_user( self.alice ).get( '/api/v1/measurements/', { 'model': self.model.pk } ).data['count'], 1 )
		self.assertEqual( self.as_user( self.alice ).delete( f'/api/v1/measurements/{mine.data["id"]}/' ).status_code, 404 )
		self.assertEqual( self.as_user( self.bob ).delete( f'/api/v1/measurements/{mine.data["id"]}/' ).status_code, 204 )
		self.assertIn( APIClient().get( '/api/v1/measurements/' ).status_code, ( 401, 403 ) )

	def test_private_models_cannot_be_measured_by_others( self ):
		self.model.is_public = False
		self.model.save()
		self.assertIn( 'model', self.post( self.bob, 'distance', self.path ).data )

	def test_deleting_the_model_deletes_its_measurements( self ):
		self.post( self.alice, 'area', self.roof )
		self.model.delete()
		self.assertEqual( Measurement.objects.count(), 0 )


class SchemaTests( APITestBase ):
	def test_openapi_schema_and_docs( self ):
		self.assertEqual( self.client.get( '/api/schema/' ).status_code, 200 )
		self.assertEqual( self.client.get( '/api/docs/' ).status_code, 200 )
