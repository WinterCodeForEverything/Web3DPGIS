import json
from django.shortcuts import render, HttpResponse
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import FlightPath, FlightPoint
from modelshow.models import SearchModels

# Create your views here.


def saveFlightPath( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		pointsArray = request.POST.getlist( 'pointsArray', [] )
		path_name = request.POST.get( 'path_name', False )
		model_id =  request.POST.get( 'model_id', -1 )
		flightpath = None
		if path_name and -1 != model_id:
			flightpath = FlightPath.objects.create(
				name = path_name,
				model = SearchModels.objects.get( id = int(model_id) ),
			)
		if len(pointsArray) and flightpath:
			for point in pointsArray:
				pointElem = point.split(',')
				FlightPoint.objects.create(
					position_x = float( pointElem[0] ),
					position_y = float( pointElem[1] ),
					position_z = float( pointElem[2] ),
					direction_x = float( pointElem[3] ),
					direction_y = float( pointElem[4] ),
					direction_z = float( pointElem[5] ),
					up_x = float( pointElem[6] ),
					up_y = float( pointElem[7] ),
					up_z = float( pointElem[8] ),
					path = flightpath,
				)	
			return HttpResponse('{"status":"success"}', content_type='application/json' )
		return HttpResponse('{"status":"failure"}', content_type='application/json' )
	
def deleteFlightPath( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		model_id = request.POST.get('model_id', -1 )
		path_name = request.POST.get('path_name', False )
		if model_id != -1 and path_name:
			FlightPath.objects.filter( model = SearchModels.objects.get( id = int(model_id) ), name = path_name ).delete()
			return 	HttpResponse( json.dumps({'status' : 'success'}) )
		return 	HttpResponse( json.dumps({'status' : 'failure'}) )
	
def getFlightPoints( request ):
	model_id = request.POST.get('model_id', -1 )
	path_name = request.POST.get('path_name', False )
	if model_id != -1 and not path_name:
		flight_path = FlightPath.objects.filter( model = SearchModels.objects.get( id = int(model_id) ) )
		path_name = []
		for path in flight_path:
			path_name.append( path.name )
		return 	HttpResponse( json.dumps({'status' : 'success', 'model_path' : path_name}) )
	elif model_id != -1 and path_name:
		flight_path = FlightPath.objects.filter( model = SearchModels.objects.get( id = int(model_id) ), name = path_name )
		if len(flight_path):
			pointsArray = FlightPoint.objects.filter( path = flight_path[0] )
			pointsResponse = []
			for point in pointsArray: 
				pointsResponse.append([ str(x) for x in [ point.position_x, point.position_y, point.position_z,
														point.direction_x, point.direction_y, point.direction_z,
														point.up_x, point.up_y, point.up_z ]
									])
			return 	HttpResponse( json.dumps({'status' : 'success', 'pointsResponse' : pointsResponse}) )
	return 	HttpResponse( json.dumps({'status' : 'failure'}) )

def viewer( request ):
		return render( request, 'viewermode/viewing.html')
