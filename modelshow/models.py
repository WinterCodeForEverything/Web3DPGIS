from django.db import models

# Create your models here.

class SearchModels( models.Model ):
	class Meta:
		verbose_name = 'Search_Models'
	
	name = models.CharField(  max_length = 50 )
	#url = models.CharField(  max_length = 100 )
	image = models.ImageField( upload_to = 'image', blank = True )
	data = models.FileField( upload_to = 'package' )
	builder = models.CharField( max_length = 50 )
	isPublic = models.BooleanField( )
	canSee = models.IntegerField( )
	relativeheight = models.IntegerField( )

	#def __str__(self):
		#return self.__str__()
