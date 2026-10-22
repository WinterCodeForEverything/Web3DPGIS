from django.contrib import admin
from .models import SearchModels
# Register your models here.

class ModelAdmin( admin.ModelAdmin ):
	list_display = ( 'name', 'image', 'data', 'canSee' )  #, 'builder', 'isPublic'

admin.site.register( SearchModels, ModelAdmin )
