from django.shortcuts import render, HttpResponse
from django.http import HttpResponseRedirect
from modelshow.models import SearchModels

# Create your views here.

def otherTools( request ):
	return render( request, 'othertools/othertools.html' )


def getHeightHtml( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		return render( request, 'othertools/adjustheight.html' )
		
def adjustHeight( request ):
	if not request.session.get('username', False):
		return HttpResponseRedirect( reverse( 'login' ) )
	else:
		model_id = request.POST.get('model_id', -1 )
		relativeheight = request.POST.get('relativeheight', -1000 )
		if -1 != model_id and -1000 != relativeheight:
			SearchModels.objects.filter( id = model_id ).update( relativeheight = relativeheight )
			return HttpResponse('{"status":"success"}', content_type='application/json')
		return HttpResponse('{"status":"failure"}', content_type='application/json')
