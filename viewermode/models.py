from django.db import models
from modelshow.models import SearchModels

# Create your models here.

		
class FlightPath( models.Model ):
	class Meta:
		verbose_name = 'FlightPath'
		
	name = models.CharField(  max_length = 128 )
	model = models.ForeignKey( SearchModels, related_name = 'model_path', on_delete = models.CASCADE )
	

class FlightPoint( models.Model ):
	class Meta:
		verbose_name = 'FlightPoint'
	
	#point_id = models.IntegerField( )
	position_x = models.DecimalField( max_digits = 32, decimal_places = 16 )
	position_y = models.DecimalField( max_digits = 32, decimal_places = 16 )
	position_z = models.DecimalField( max_digits = 32, decimal_places = 16 )
	direction_x = models.DecimalField( max_digits = 32, decimal_places = 16 )
	direction_y = models.DecimalField( max_digits = 32, decimal_places = 16 )
	direction_z = models.DecimalField( max_digits = 32, decimal_places = 16 )
	up_x = models.DecimalField( max_digits = 32, decimal_places = 16 )
	up_y = models.DecimalField( max_digits = 32, decimal_places = 16 )
	up_z = models.DecimalField( max_digits = 32, decimal_places = 16 )
	path = models.ForeignKey( FlightPath, related_name = 'path_point', on_delete = models.CASCADE )
