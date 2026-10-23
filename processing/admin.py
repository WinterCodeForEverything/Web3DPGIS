from django.contrib import admin

from .models import Job


@admin.register( Job )
class JobAdmin( admin.ModelAdmin ):
	list_display = ( 'id', 'model', 'status', 'stage', 'progress', 'created_at', 'finished_at' )
	list_filter = ( 'status', )
	readonly_fields = ( 'log', )
