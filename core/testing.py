"""Test helpers shared by the apps' API tests."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase


class APITestBase( APITestCase ):
	"""Two users, alice and bob, and a throwaway MEDIA_ROOT."""

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

	def as_user( self, user ):
		client = APIClient()
		client.force_authenticate( user )
		return client
