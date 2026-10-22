import os
import shutil
import threading
import json
from django.shortcuts import render, HttpResponse
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import SearchModels
from addlabel.models import ModelLabel
from .forms import AddItemsForm
from .uncompress import uncompressThreading
# Create your views here.

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	
def publicItems( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		models = SearchModels.objects.filter( isPublic = True )
		return render( request, 'modelshow/main.html', {'publicModels' : models})
		
		
def addItems( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		if request.method == 'POST':
			form = AddItemsForm( request.POST, request.FILES )
			if form.is_valid():
				SearchModels.objects.create( 	name = form.cleaned_data['name'],
												image = form.cleaned_data['image'],
												data = form.cleaned_data['data'],
												builder = request.session.get('username'),	#form.cleaned_data['builder'],
												isPublic = 1,
												canSee = 1,
												relativeheight = 0,
											)
				models = SearchModels.objects.filter( builder = request.session.get('username') )   #cleaned_data['builder']
				count = models.count()
				uncompressThreading( str( models[count - 1].data ) )
				return HttpResponseRedirect( reverse( 'main' ) )
		else:
			form = AddItemsForm()
			
		return render(request, 'modelshow/newItems.html', {'form': form})
		
	
def show( request ):
	model_id = request.GET.get( 'id' )
	models = SearchModels.objects.filter( id = model_id )
	viewpath =  request.GET.get( 'path', False )
	manageFlag = False
	if models:
		if viewpath:
			if not request.session.get('username', False):
				return HttpResponseRedirect( reverse( 'login' ) )
			else:
				manageFlag = True
		if manageFlag or ( ( not viewpath ) and models[0].canSee ):
			# load model
			_, file_name = os.path.split( str(models[0].data) )
			file_title, _  = os.path.splitext( file_name )
			# model_url is the folder holding tileset.json; the template appends '/tileset.json'
			url = None
			for root, _, files in os.walk( os.path.join( BASE_DIR, 'media', 'Data', file_title ) ):
				if 'tileset.json' in files:
					url = '/media/' + os.path.relpath( root, os.path.join( BASE_DIR, 'media' ) ).replace( '\\', '/' )
					break
			if url is None:
				return HttpResponse('模型正在解压或缺少 tileset.json，请稍候再试！')
			# load label
			labels = ModelLabel.objects.filter( model = models[0] )
			return render( request, 'modelshow/modelshow.html', { 'model_url' : url, 
																  'relativeheight' : models[0].relativeheight, 
																   'labels' : labels } ) 
		else:
			return HttpResponse('当前模型不可见，请联系管理员！')
	else:
		return HttpResponse('当前模型不存在，请联系管理员！')
		
def canSee( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		model_id = request.GET.get('id')
		isSeen =  request.GET.get('isSeen')
		SearchModels.objects.filter( id = model_id ).update( canSee = isSeen )
		return HttpResponse('{"status":"success"}', content_type='application/json')

def deleteThread( package_dir, image_dir, data_dir ):
	if os.path.exists( package_dir ):
		os.remove( package_dir )
	if os.path.exists( image_dir ):
		os.remove( image_dir )
	if os.path.exists( data_dir ):
		shutil.rmtree( data_dir )
		
def delete( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		model_id = request.GET.get('id')
		model_del = SearchModels.objects.filter( id = model_id )
		# delete model files, image and package
		if model_del:
			package_dir = os.path.join( BASE_DIR, 'media', str(model_del[0].data) )
			image_dir = os.path.join( BASE_DIR, 'media', str(model_del[0].image) )
			_, file_name = os.path.split( str(model_del[0].data) )
			file_title, _  = os.path.splitext( file_name )
			data_dir = os.path.join( BASE_DIR, 'media/Data', file_title )
			threading.Thread( target = deleteThread, args = ( package_dir, image_dir,  data_dir, ) ).start()
			model_del.delete()
			return HttpResponse('{"status":"success"}', content_type='application/json')
		return HttpResponse('{"status":"failure"}', content_type='application/json')
		
def help( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		return render(request, 'modelshow/help.html')
		


def measure( request ):
	return render( request, 'modelshow/measuring.html' )
