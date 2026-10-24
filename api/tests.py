from core.testing import APITestBase


class SchemaTests( APITestBase ):
	def test_openapi_schema_and_docs( self ):
		self.assertEqual( self.client.get( '/api/schema/' ).status_code, 200 )
		self.assertEqual( self.client.get( '/api/docs/' ).status_code, 200 )
