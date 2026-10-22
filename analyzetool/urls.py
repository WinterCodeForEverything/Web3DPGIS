from django.urls import path
from . import views

urlpatterns = [
	path( 'analyzetool/', views.analyzetool, name = 'analyzetool' ),
]