from django.urls import path
from . import views

urlpatterns = [
	path( 'othertools/', views.otherTools, name = 'othertools' ),
	path( 'adjustheight/', views.adjustHeight, name = 'adjustheight' ),
	path( 'getHeightHtml/', views.getHeightHtml, name = 'getHeightHtml' ),
]