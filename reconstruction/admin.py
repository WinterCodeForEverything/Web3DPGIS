from django.contrib import admin

from .models import Photo, Reconstruction


class PhotoInline( admin.TabularInline ):
	model = Photo
	fields = ( 'name', 'size', 'uploaded', 'mask' )
	readonly_fields = fields
	extra = 0
	can_delete = False


@admin.register( Reconstruction )
class ReconstructionAdmin( admin.ModelAdmin ):
	list_display = ( 'id', 'model', 'preset', 'mode', 'resolution_shift', 'created_at', 'started_at' )
	list_filter = ( 'preset', 'mode' )
	search_fields = ( 'model__name', 'model__owner__username' )
	readonly_fields = ( 'model', 'mode', 'stats', 'created_at', 'started_at' )
	inlines = [ PhotoInline ]
