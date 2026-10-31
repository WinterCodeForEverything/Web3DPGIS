import math

from rest_framework.test import APIClient

from catalog.testing import GUANGZHOU, ModelTestBase
from core.geodesy import ecef_to_geodetic, geodetic_to_ecef

from .models import FlightPath, Measurement


class FlightPathTests( ModelTestBase ):
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


class MeasurementTests( ModelTestBase ):
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

	def test_name_and_annotation_can_be_changed_but_not_the_points( self ):
		m = self.post( self.alice, 'distance', self.path ).data
		self.assertEqual( ( m['name'], m['annotation'] ), ( '', '' ) )
		url = f'/api/v1/measurements/{m["id"]}/'
		r = self.as_user( self.alice ).patch( url, { 'name': 'Fence', 'annotation': 'North side, to the gate.' }, format = 'json' )
		self.assertEqual( ( r.status_code, r.data['name'], r.data['annotation'] ), ( 200, 'Fence', 'North side, to the gate.' ), r.data )
		self.assertEqual( len( r.data['points'] ), 4 )
		r = self.as_user( self.alice ).patch( url, { 'points': self.path[:2], 'kind': 'area' }, format = 'json' )
		self.assertEqual( ( r.status_code, set( r.data ) ), ( 400, { 'points', 'kind' } ) )
		self.assertEqual( self.as_user( self.bob ).patch( url, { 'name': 'Mine' }, format = 'json' ).status_code, 404 )
		missing = self.as_user( self.alice ).post( '/api/v1/measurements/', { 'model': self.model.pk, 'kind': 'distance' }, format = 'json' )
		self.assertIn( 'points', missing.data )    # points are still needed to create one

	def test_list_filters_by_kind( self ):
		self.post( self.alice, 'distance', self.path )
		self.post( self.alice, 'point', self.path[:1] )
		r = self.as_user( self.alice ).get( '/api/v1/measurements/', { 'model': self.model.pk, 'kind': 'point' } )
		self.assertEqual( [ m['kind'] for m in r.data['results'] ], [ 'point' ] )

	def test_deleting_the_model_deletes_its_measurements( self ):
		self.post( self.alice, 'area', self.roof )
		self.model.delete()
		self.assertEqual( Measurement.objects.count(), 0 )
