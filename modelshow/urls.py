from django.urls import path
from . import views
#from django.conf import settings  
#from django.conf.urls.static import static  

urlpatterns = [
	path( 'main/', views.publicItems, name = 'main' ),
	path( 'newItems/', views.addItems, name = 'newItems' ),
	path( 'show/', views.show, name = 'show' ),
	path( 'canSee/', views.canSee, name = 'canSee' ),
	path( 'delete/', views.delete, name = 'delete' ),
	path( 'help/', views.help, name = 'help'),
	path( 'measuring/', views.measure, name = 'measuring' ),

]