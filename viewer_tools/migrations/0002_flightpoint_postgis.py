import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields
import django.db.models.deletion
from django.contrib.gis.geos import Point
from django.db import migrations, models


def forwards( apps, schema_editor ):
	from processing.geodesy import ecef_to_geodetic

	FlightPoint = apps.get_model( 'viewermode', 'FlightPoint' )
	for order, p in enumerate( FlightPoint.objects.order_by( 'path_id', 'id' ) ):
		p.position = Point( *ecef_to_geodetic( float( p.position_x ), float( p.position_y ), float( p.position_z ) ), srid = 4326 )
		p.direction = [ float( p.direction_x ), float( p.direction_y ), float( p.direction_z ) ]
		p.up = [ float( p.up_x ), float( p.up_y ), float( p.up_z ) ]
		p.order = order
		p.save()


def backwards( apps, schema_editor ):
	from processing.geodesy import geodetic_to_ecef

	FlightPoint = apps.get_model( 'viewermode', 'FlightPoint' )
	for p in FlightPoint.objects.all():
		p.position_x, p.position_y, p.position_z = geodetic_to_ecef( p.position.x, p.position.y, p.position.z )
		p.direction_x, p.direction_y, p.direction_z = p.direction
		p.up_x, p.up_y, p.up_z = p.up
		p.save()


OLD_FIELDS = [ 'position_x', 'position_y', 'position_z', 'direction_x', 'direction_y', 'direction_z', 'up_x', 'up_y', 'up_z' ]


class Migration( migrations.Migration ):

	dependencies = [
		( 'viewermode', '0001_initial' ),
		( 'modelshow', '0013_model3d_ownership_and_location' ),
	]

	operations = [
		migrations.AlterField( 'FlightPath', 'model', models.ForeignKey( on_delete = django.db.models.deletion.CASCADE, related_name = 'flight_paths', to = 'modelshow.model3d' ) ),
		migrations.AlterField( 'FlightPoint', 'path', models.ForeignKey( on_delete = django.db.models.deletion.CASCADE, related_name = 'points', to = 'viewermode.flightpath' ) ),
		migrations.AddField( 'FlightPoint', 'order', models.PositiveIntegerField( default = 0 ) ),
		migrations.AddField( 'FlightPoint', 'position', django.contrib.gis.db.models.fields.PointField( dim = 3, null = True, srid = 4326 ) ),
		migrations.AddField( 'FlightPoint', 'direction', django.contrib.postgres.fields.ArrayField( base_field = models.FloatField(), null = True, size = 3 ) ),
		migrations.AddField( 'FlightPoint', 'up', django.contrib.postgres.fields.ArrayField( base_field = models.FloatField(), null = True, size = 3 ) ),
		# nullable first, so migrating backwards can re-add the columns before refilling them
		*[ migrations.AlterField( 'FlightPoint', name, models.DecimalField( decimal_places = 16, max_digits = 32, null = True ) ) for name in OLD_FIELDS ],
		migrations.RunPython( forwards, backwards ),
		migrations.AlterField( 'FlightPoint', 'position', django.contrib.gis.db.models.fields.PointField( dim = 3, srid = 4326 ) ),
		migrations.AlterField( 'FlightPoint', 'direction', django.contrib.postgres.fields.ArrayField( base_field = models.FloatField(), size = 3 ) ),
		migrations.AlterField( 'FlightPoint', 'up', django.contrib.postgres.fields.ArrayField( base_field = models.FloatField(), size = 3 ) ),
		*[ migrations.RemoveField( 'FlightPoint', name ) for name in OLD_FIELDS ],
		migrations.AlterModelOptions( 'FlightPath', { 'ordering': [ 'id' ] } ),
		migrations.AlterModelOptions( 'FlightPoint', { 'ordering': [ 'path', 'order' ] } ),
		migrations.AddConstraint( 'FlightPath', models.UniqueConstraint( fields = [ 'model', 'name' ], name = 'unique_flight_path_name_per_model' ) ),
	]
