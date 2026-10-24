from django.contrib.gis import admin

from .models import FlightPath, FlightPoint, Measurement


class FlightPointInline( admin.TabularInline ):
	model = FlightPoint
	extra = 0


@admin.register( FlightPath )
class FlightPathAdmin( admin.ModelAdmin ):
	list_display = ( 'name', 'model' )
	inlines = [ FlightPointInline ]


@admin.register( Measurement )
class MeasurementAdmin( admin.GISModelAdmin ):
	list_display = ( 'kind', 'name', 'model', 'created_by', 'created_at' )
	list_filter = ( 'kind', 'model' )
	readonly_fields = ( 'results', 'created_at' )
