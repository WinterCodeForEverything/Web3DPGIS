from rest_framework.test import APIClient

from core.testing import APITestBase


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
		self.assertEqual( client.post( '/api/v1/auth/logout/' ).status_code, 403 )
		token = client.get( '/api/v1/auth/me/' ).cookies['csrftoken'].value
		self.assertEqual( client.post( '/api/v1/auth/logout/', HTTP_X_CSRFTOKEN = token ).status_code, 204 )

	def test_token_auth( self ):
		r = self.client.post( '/api/v1/auth/token/', { 'username': 'alice', 'password': 'Sm0ke-pass-1' } )
		client = APIClient()
		client.credentials( HTTP_AUTHORIZATION = 'Token ' + r.data['token'] )
		self.assertEqual( client.get( '/api/v1/auth/me/' ).data['username'], 'alice' )
