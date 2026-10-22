from django.db import models
from modelshow.models import SearchModels
# Create your models here.

class LabelBase( models.Model ):
	source = models.CharField( max_length = 128 )
	

class ModelLabel( models.Model ):
	name = models.CharField( max_length = 128 )
	coord_x = models.FloatField()
	coord_y = models.FloatField()
	coord_z = models.FloatField()
	property_url = models.CharField( max_length = 128 )
	model = models.ForeignKey( SearchModels, on_delete = models.CASCADE )
	labelbase = models.ForeignKey( LabelBase, on_delete = models.CASCADE )

	