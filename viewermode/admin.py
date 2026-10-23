from django.contrib import admin

from .models import FlightPath, FlightPoint


class FlightPointInline( admin.TabularInline ):
	model = FlightPoint
	extra = 0


@admin.register( FlightPath )
class FlightPathAdmin( admin.ModelAdmin ):
	list_display = ( 'name', 'model' )
	inlines = [ FlightPointInline ]
