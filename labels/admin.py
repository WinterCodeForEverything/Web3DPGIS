from django.contrib.gis import admin

from .models import Label, LabelIcon


@admin.register( LabelIcon )
class LabelIconAdmin( admin.ModelAdmin ):
	list_display = ( 'name', 'image', 'owner' )


@admin.register( Label )
class LabelAdmin( admin.GISModelAdmin ):
	list_display = ( 'name', 'kind', 'model', 'icon' )
	list_filter = ( 'kind', 'model' )
