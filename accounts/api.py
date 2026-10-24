"""Sign up, log in, log out and the current user: /api/v1/auth/…"""
from django.contrib import auth
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile


class UserSerializer( serializers.ModelSerializer ):
	class Meta:
		model = User
		fields = [ 'id', 'username', 'email', 'is_staff' ]
		read_only_fields = fields


class RegisterSerializer( serializers.Serializer ):
	username = serializers.RegexField( r'^[\w.@+-]{3,50}$', error_messages = { 'invalid': '3 to 50 letters, digits or . @ + - _' } )
	email = serializers.EmailField()
	password = serializers.CharField( write_only = True, style = { 'input_type': 'password' } )

	def validate_username( self, value ):
		if User.objects.filter( username__iexact = value ).exists():
			raise serializers.ValidationError( 'This username is already taken.' )
		return value

	def validate_email( self, value ):
		if User.objects.filter( email__iexact = value ).exists():
			raise serializers.ValidationError( 'This email is already registered.' )
		return value

	def validate( self, attrs ):
		password_validation.validate_password( attrs['password'], User( username = attrs['username'], email = attrs['email'] ) )
		return attrs

	@transaction.atomic
	def create( self, validated_data ):
		user = User.objects.create_user( **validated_data )
		UserProfile.objects.create( user = user )
		return user


class LoginSerializer( serializers.Serializer ):
	login = serializers.CharField( help_text = 'Username or email' )
	password = serializers.CharField( write_only = True, style = { 'input_type': 'password' } )


@method_decorator( ensure_csrf_cookie, name = 'get' )
class MeView( APIView ):
	"""The signed-in user (null when anonymous). Also sets the CSRF cookie the browser app needs."""
	permission_classes = [ permissions.AllowAny ]

	@extend_schema( responses = UserSerializer )
	def get( self, request ):
		return Response( UserSerializer( request.user ).data if request.user.is_authenticated else None )


class RegisterView( APIView ):
	permission_classes = [ permissions.AllowAny ]

	@extend_schema( request = RegisterSerializer, responses = { 201: UserSerializer } )
	def post( self, request ):
		serializer = RegisterSerializer( data = request.data )
		serializer.is_valid( raise_exception = True )
		user = serializer.save()
		auth.login( request, user )
		return Response( UserSerializer( user ).data, status = status.HTTP_201_CREATED )


class LoginView( APIView ):
	"""Sign in with a username or an email address."""
	permission_classes = [ permissions.AllowAny ]

	@extend_schema( request = LoginSerializer, responses = UserSerializer )
	def post( self, request ):
		serializer = LoginSerializer( data = request.data )
		serializer.is_valid( raise_exception = True )
		login, password = serializer.validated_data['login'], serializer.validated_data['password']
		account = User.objects.filter( Q( username__iexact = login ) | Q( email__iexact = login ) ).first()
		user = auth.authenticate( request, username = account.username, password = password ) if account else None
		if user is None or not user.is_active:
			return Response( { 'detail': 'Wrong username, email or password.' }, status = status.HTTP_400_BAD_REQUEST )
		auth.login( request, user )
		return Response( UserSerializer( user ).data )


class LogoutView( APIView ):
	@extend_schema( request = None, responses = { 204: None } )
	def post( self, request ):
		auth.logout( request )
		return Response( status = status.HTTP_204_NO_CONTENT )


urlpatterns = [
	path( 'auth/me/', MeView.as_view(), name = 'auth-me' ),
	path( 'auth/register/', RegisterView.as_view(), name = 'auth-register' ),
	path( 'auth/login/', LoginView.as_view(), name = 'auth-login' ),
	path( 'auth/logout/', LogoutView.as_view(), name = 'auth-logout' ),
]
