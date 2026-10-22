from django.urls import path
from . import views

urlpatterns = [
	#path( 'showLabel/', views.showLabel, name = 'showLabel' ),
	path( 'addLabel/', views.addLabel, name = 'addLabel' ),
	path( 'addLabelBase/', views.addLabelBase, name = 'addLabelBase' ),
	path( 'label_upload/', views.uploadLabel, name = 'label_upload' ),
	path( 'getDataDictionary/', views.getDataDictionary, name = 'getDataDictionary' ),
	path( 'getLabelData/', views.getLabelData, name = 'getLabelData' ),
	path( 'deleteAllLabel/', views.deleteAllLabel, name = 'deleteAllLabel' ),
	path( 'deleteLabelBase/', views.deleteLabelBase, name = 'deleteLabelBase' )
]