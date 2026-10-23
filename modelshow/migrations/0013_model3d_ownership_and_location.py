import os

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import migrations, models


def forwards( apps, schema_editor ):
	from processing.tilesets import find_tileset, tileset_location

	Model3D = apps.get_model( 'modelshow', 'Model3D' )
	User = apps.get_model( *settings.AUTH_USER_MODEL.split( '.' ) )
	media_root = str( settings.MEDIA_ROOT )
	for m in Model3D.objects.all():
		m.owner = User.objects.filter( username = m.builder ).first()
		m.is_visible = bool( m.canSee )
		title = os.path.splitext( os.path.basename( m.source_file.name ) )[0]
		tileset = find_tileset( os.path.join( media_root, 'Data', title ) )
		if tileset:
			m.tileset_path = os.path.relpath( tileset, media_root ).replace( '\\', '/' )
			m.status = 'ready'
			location = tileset_location( tileset )
			if location:
				m.location = Point( *location, srid = 4326 )
		else:
			m.status = 'failed'
		m.save()


def backwards( apps, schema_editor ):
	Model3D = apps.get_model( 'modelshow', 'Model3D' )
	for m in Model3D.objects.all():
		m.builder = m.owner.username if m.owner else ''
		m.canSee = 1 if m.is_visible else 0
		m.save()


class Migration( migrations.Migration ):

	dependencies = [
		migrations.swappable_dependency( settings.AUTH_USER_MODEL ),
		( 'contenttypes', '0002_remove_content_type_name' ),
		( 'modelshow', '0012_auto_20181212_0906' ),
		( 'addlabel', '0006_auto_20190412_1508' ),
		( 'viewermode', '0001_initial' ),
	]

	operations = [
		migrations.RenameModel( 'SearchModels', 'Model3D' ),
		migrations.RenameField( 'Model3D', 'image', 'thumbnail' ),
		migrations.RenameField( 'Model3D', 'data', 'source_file' ),
		migrations.RenameField( 'Model3D', 'isPublic', 'is_public' ),
		migrations.RenameField( 'Model3D', 'relativeheight', 'height_offset' ),
		migrations.AlterField( 'Model3D', 'name', models.CharField( max_length = 128 ) ),
		migrations.AlterField( 'Model3D', 'is_public', models.BooleanField( default = True ) ),
		migrations.AlterField( 'Model3D', 'height_offset', models.FloatField( default = 0.0, help_text = 'Metres added to the model height' ) ),
		migrations.AddField( 'Model3D', 'owner', models.ForeignKey( null = True, on_delete = django.db.models.deletion.CASCADE, related_name = 'models3d', to = settings.AUTH_USER_MODEL ) ),
		migrations.AddField( 'Model3D', 'is_visible', models.BooleanField( default = True ) ),
		migrations.AddField( 'Model3D', 'source_srs', models.CharField( blank = True, help_text = 'CRS of point-cloud input, e.g. EPSG:4547', max_length = 64 ) ),
		migrations.AddField( 'Model3D', 'status', models.CharField( choices = [ ( 'pending', 'Pending' ), ( 'processing', 'Processing' ), ( 'ready', 'Ready' ), ( 'failed', 'Failed' ) ], default = 'pending', max_length = 16 ) ),
		migrations.AddField( 'Model3D', 'tileset_path', models.CharField( blank = True, help_text = 'Path of tileset.json relative to MEDIA_ROOT', max_length = 512 ) ),
		migrations.AddField( 'Model3D', 'location', django.contrib.gis.db.models.fields.PointField( blank = True, dim = 3, null = True, srid = 4326 ) ),
		migrations.AddField( 'Model3D', 'created_at', models.DateTimeField( auto_now_add = True, null = True ) ),
		migrations.AddField( 'Model3D', 'updated_at', models.DateTimeField( auto_now = True, null = True ) ),
		# nullable first, so migrating backwards can re-add the columns before refilling them
		migrations.AlterField( 'Model3D', 'builder', models.CharField( max_length = 50, null = True ) ),
		migrations.AlterField( 'Model3D', 'canSee', models.IntegerField( null = True ) ),
		migrations.RunPython( forwards, backwards ),
		migrations.RemoveField( 'Model3D', 'builder' ),
		migrations.RemoveField( 'Model3D', 'canSee' ),
		migrations.AlterModelOptions( 'Model3D', { 'ordering': [ '-id' ], 'verbose_name': '3D model' } ),
	]
