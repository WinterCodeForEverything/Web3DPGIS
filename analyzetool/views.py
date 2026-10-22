from django.shortcuts import render, HttpResponse
from django.http import HttpResponseRedirect
from modelshow.models import SearchModels

# Create your views here.

def analyzetool( request ):
	return render( request, 'analyzetool/analyzetool.html' )
