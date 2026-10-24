from django.contrib.gis.geos import Point

from core.testing import APITestBase

from .models import Model3D

GUANGZHOU = ( 113.26, 23.13 )
BEIJING = ( 116.40, 39.90 )
PHILADELPHIA = ( -75.16, 39.95 )


class ModelTestBase( APITestBase ):
	"""APITestBase plus a quick way to make a ready model."""

	def make_model( self, owner, name = 'site', where = GUANGZHOU, **kwargs ):
		return Model3D.objects.create( name = name, owner = owner, source_file = 'package/x.zip', status = 'ready',
			tileset_path = f'tiles/{name}/tileset.json', location = Point( *where, 10.0, srid = 4326 ), **kwargs )
