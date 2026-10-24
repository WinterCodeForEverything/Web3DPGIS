import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import migrations, models


def forwards( apps, schema_editor ):
	from core.geodesy import ecef_to_geodetic

	LabelIcon = apps.get_model( 'addlabel', 'LabelIcon' )
	Label = apps.get_model( 'addlabel', 'Label' )
	for icon in LabelIcon.objects.all():
		icon.image = 'label/' + icon.source
		icon.name = icon.source.rsplit( '.', 1 )[0]
		icon.save()
	for label in Label.objects.all():
		label.position = Point( *ecef_to_geodetic( label.coord_x, label.coord_y, label.coord_z ), srid = 4326 )
		if label.property_url:
			label.properties = { 'property_url': label.property_url }
		label.save()


def backwards( apps, schema_editor ):
	from core.geodesy import geodetic_to_ecef

	LabelIcon = apps.get_model( 'addlabel', 'LabelIcon' )
	Label = apps.get_model( 'addlabel', 'Label' )
	for icon in LabelIcon.objects.all():
		icon.source = icon.image.name.rsplit( '/', 1 )[-1]
		icon.save()
	for label in Label.objects.all():
		label.coord_x, label.coord_y, label.coord_z = geodetic_to_ecef( label.position.x, label.position.y, label.position.z )
		label.property_url = label.properties.get( 'property_url', '' )
		label.save()


class Migration( migrations.Migration ):

	dependencies = [
		migrations.swappable_dependency( settings.AUTH_USER_MODEL ),
		( 'contenttypes', '0002_remove_content_type_name' ),
		( 'addlabel', '0006_auto_20190412_1508' ),
		( 'modelshow', '0013_model3d_ownership_and_location' ),
	]

	operations = [
		migrations.RenameModel( 'LabelBase', 'LabelIcon' ),
		migrations.RenameModel( 'ModelLabel', 'Label' ),
		migrations.AddField( 'LabelIcon', 'name', models.CharField( blank = True, max_length = 128 ) ),
		migrations.AddField( 'LabelIcon', 'image', models.ImageField( default = '', upload_to = 'label' ), preserve_default = False ),
		migrations.AddField( 'LabelIcon', 'owner', models.ForeignKey( blank = True, null = True, on_delete = django.db.models.deletion.CASCADE, related_name = 'label_icons', to = settings.AUTH_USER_MODEL ) ),
		migrations.RenameField( 'Label', 'labelbase', 'icon' ),
		migrations.AlterField( 'Label', 'icon', models.ForeignKey( blank = True, null = True, on_delete = django.db.models.deletion.SET_NULL, related_name = 'labels', to = 'addlabel.labelicon' ) ),
		migrations.AlterField( 'Label', 'model', models.ForeignKey( on_delete = django.db.models.deletion.CASCADE, related_name = 'labels', to = 'modelshow.model3d' ) ),
		migrations.AddField( 'Label', 'position', django.contrib.gis.db.models.fields.PointField( dim = 3, null = True, srid = 4326 ) ),
		migrations.AddField( 'Label', 'properties', models.JSONField( blank = True, default = dict ) ),
		# nullable first, so migrating backwards can re-add the columns before refilling them
		migrations.AlterField( 'LabelIcon', 'source', models.CharField( max_length = 128, null = True ) ),
		migrations.AlterField( 'Label', 'coord_x', models.FloatField( null = True ) ),
		migrations.AlterField( 'Label', 'coord_y', models.FloatField( null = True ) ),
		migrations.AlterField( 'Label', 'coord_z', models.FloatField( null = True ) ),
		migrations.AlterField( 'Label', 'property_url', models.CharField( max_length = 128, null = True ) ),
		migrations.RunPython( forwards, backwards ),
		migrations.AlterField( 'Label', 'position', django.contrib.gis.db.models.fields.PointField( dim = 3, srid = 4326 ) ),
		migrations.RemoveField( 'LabelIcon', 'source' ),
		migrations.RemoveField( 'Label', 'coord_x' ),
		migrations.RemoveField( 'Label', 'coord_y' ),
		migrations.RemoveField( 'Label', 'coord_z' ),
		migrations.RemoveField( 'Label', 'property_url' ),
		migrations.AlterModelOptions( 'Label', { 'ordering': [ 'id' ] } ),
	]
