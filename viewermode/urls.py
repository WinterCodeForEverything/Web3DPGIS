from django.urls import path
from . import views

urlpatterns = [
	path( 'saveFlightPath/', views.saveFlightPath, name = 'saveFlightPath'),
	path( 'deleteFlightPath/', views.deleteFlightPath, name = 'deleteFlightPath'),
	path( 'getFlightPoints/', views.getFlightPoints, name = 'getFlightPoints'),
	path( 'viewing/', views.viewer, name = 'viewing'),
]