from django.contrib.gis import admin

from .models import Model3D


@admin.register( Model3D )
class Model3DAdmin( admin.GISModelAdmin ):
	list_display = ( 'name', 'owner', 'status', 'is_public', 'is_visible', 'created_at' )
	list_filter = ( 'status', 'is_public', 'is_visible' )
	search_fields = ( 'name', 'owner__username' )
	readonly_fields = ( 'created_at', 'updated_at' )
