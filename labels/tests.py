from django.contrib.gis.geos import Point
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
