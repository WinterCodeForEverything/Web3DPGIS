import os
import json
from PIL import Image  
#import datatime
from django.shortcuts import render, HttpResponse
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from .models import ModelLabel, LabelBase
#from .form import ImageLabelForm
from modelshow.models import SearchModels


# Create your views here.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def is_ajax( request ):
	# replacement for HttpRequest.is_ajax(), removed in Django 4.0
	return request.headers.get( 'x-requested-with' ) == 'XMLHttpRequest'

def showLabel( request ):
	model_id = request.GET.get( 'id' )
	model = SearchModels.objects.get( id = model_id )
	labels = ModelLabel.objects.filter( model = model )
	return render( request, 'addLabel/showLabel.html', { 'labels' : labels } )
	

def addLabel( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		labelbase = LabelBase.objects.filter()	
		return render( request, 'addLabel/addLabel.html', { 'labelbase' : labelbase } )

def deleteAllLabel( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		model_id = request.GET.get('id', False )
		if model_id:
			model = SearchModels.objects.get( id = model_id )
			ModelLabel.objects.filter( model = model ).delete()
			return JsonResponse({"status":"success"})
		return JsonResponse({"status":"failure"})
		
def addLabelBase( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		if request.method == 'POST': #request.is_ajax() and 
			label_image = request.FILES['image']
			image_name = os.path.basename( request.FILES['image'].name )
			if label_image:
				#uploadname = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
				label_dir = os.path.join( BASE_DIR, 'media', 'label' )
				os.makedirs( label_dir, exist_ok = True )
				Image.open( label_image ).save( os.path.join( label_dir, image_name ) )
				LabelBase.objects.create( source = image_name )
				return JsonResponse({"status":"success"})
		return JsonResponse({"status":"failure"})
		
def deleteLabelBase( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		label_id = request.GET.get('id', False )
		if label_id:
			label = LabelBase.objects.get( id = label_id )
			image_file = os.path.join( BASE_DIR, 'media/label', label.source )
			if os.path.exists( image_file ):
				os.remove( image_file )
			label.delete()
			return JsonResponse({"status":"success"})
		return JsonResponse({"status":"failure"})
		
def uploadLabel( request ):
	if not request.session.get( 'username', False ):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		if is_ajax( request ) and request.method == 'POST':
			labelArray = request.POST.getlist( 'labelArray' )
			for label in labelArray:
				labelitem = label.split(',')
				ModelLabel.objects.create(
					name = labelitem[0],
					coord_x = float(labelitem[1]),
					coord_y = float(labelitem[2]),
					coord_z = float(labelitem[3]),
					property_url = labelitem[4],
					model = SearchModels.objects.get( id = int(labelitem[5]) ),
					labelbase = LabelBase.objects.get( id = int(labelitem[6]) ),
				)
			return JsonResponse({"status":"success"})
		return JsonResponse({"status":"failure"})

def getDataDictionary(request):
	dictionary_path = os.path.join( BASE_DIR, 'static', 'dictionary' , 'data_dictionary.json')
	f = open( dictionary_path,'r', encoding="utf-8")
	result = f.read()
	f.close()
	return JsonResponse({"status":"success","data":result})

		
def getLabelData( request ):
	#if not request.session.get('username', False):
	#	return HttpResponseRedirect( reverse( 'login' ) )
	#else:
	if is_ajax( request ):
		if request.method == 'POST':
			try:
				labelId = int( request.POST.get( 'label_id', -1 ) )
				modelId = int( request.POST.get( 'model_id', -1 ) )
			except ValueError:
				return JsonResponse({"status":"failure"})
			data_path = os.path.join( BASE_DIR, 'media', 'label' , str(modelId) , str(labelId)+'.json')
			if not os.path.exists( data_path ):
				return JsonResponse({"status":"failure"})
			f = open(data_path,'r',encoding="utf-8")
			result = f.read()
			f.close()
			return JsonResponse({"status":"success","data":result})
	return JsonResponse({"status":"failure"})
