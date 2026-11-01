"""Label icons move from media/label/ to their own storage (assets/label-icons/, or the bucket's label/ prefix with S3).

Stored names lose their "label/" prefix. With local storage the files are copied across; with S3 the new storage's
location is label/, so the objects stay where they are.
"""
from django.conf import settings
from django.core.files.storage import default_storage, storages
from django.db import migrations, models

import labels.models

PREFIX = 'label/'


def forwards( apps, schema_editor ):
	LabelIcon = apps.get_model( 'addlabel', 'LabelIcon' )
	target = storages['label_icons']
	for icon in LabelIcon.objects.filter( image__startswith = PREFIX ):
		old = icon.image.name
		new = old[len( PREFIX ):]
		if settings.STORAGE_BACKEND == 'local' and default_storage.exists( old ) and not target.exists( new ):
			with default_storage.open( old ) as f:
				new = target.save( new, f )
		icon.image.name = new
		icon.save( update_fields = [ 'image' ] )


def backwards( apps, schema_editor ):
	LabelIcon = apps.get_model( 'addlabel', 'LabelIcon' )
	source = storages['label_icons']
	for icon in LabelIcon.objects.exclude( image__startswith = PREFIX ):
		new = PREFIX + icon.image.name
		if settings.STORAGE_BACKEND == 'local' and source.exists( icon.image.name ) and not default_storage.exists( new ):
			with source.open( icon.image.name ) as f:
				new = default_storage.save( new, f )
		icon.image.name = new
		icon.save( update_fields = [ 'image' ] )


class Migration( migrations.Migration ):

	dependencies = [
		( 'addlabel', '0008_label_shapes' ),
	]

	operations = [
		migrations.AlterField( 'labelicon', 'image', models.ImageField( storage = labels.models.label_icon_storage, upload_to = '' ) ),
		migrations.RunPython( forwards, backwards ),
	]
