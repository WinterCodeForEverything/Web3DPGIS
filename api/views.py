from django.contrib import auth
from django.contrib.auth.models import User
from django.db.models import Q
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from addlabel.models import Label, LabelIcon
from processing.models import Job
from processing.pipeline import start_processing
from viewermode.models import FlightPath, Measurement

from .filters import Model3DFilter
from .permissions import IsCreatorOrStaff, IsOwnerOrReadOnly, can_edit, readable_models
from .serializers import (
	FlightPathSerializer, JobDetailSerializer, JobSerializer, LabelIconSerializer, LabelSerializer, LoginSerializer,
	MeasurementSerializer, Model3DCreateSerializer, Model3DSerializer, RegisterSerializer, UserSerializer,
)


# --- accounts ---------------------------------------------------------------

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


# --- models -------------------------------------------------------------------

class Model3DViewSet( viewsets.ModelViewSet ):
	"""3D models. Uploading creates the model and starts background processing."""
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_class = Model3DFilter

	def get_queryset( self ):
		return readable_models( self.request.user ).select_related( 'owner' )

	def get_serializer_class( self ):
		return Model3DCreateSerializer if self.action == 'create' else Model3DSerializer

	def perform_create( self, serializer ):
		model = serializer.save( owner = self.request.user )
		start_processing( model )

	@extend_schema( request = None, responses = { 202: JobSerializer } )
	@action( detail = True, methods = [ 'post' ] )
	def reprocess( self, request, pk = None ):
		"""Run the processing pipeline again on the stored upload."""
		model = self.get_object()
		job = start_processing( model )
		return Response( JobSerializer( job ).data, status = status.HTTP_202_ACCEPTED )


# --- labels ---------------------------------------------------------------------

class LabelIconViewSet( mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
						mixins.DestroyModelMixin, viewsets.GenericViewSet ):
	"""Label icons: shared icons (no owner) plus your own."""
	serializer_class = LabelIconSerializer

	def get_queryset( self ):
		user = self.request.user
		mine = Q( owner = user ) if user.is_authenticated else Q( pk__in = [] )
		return LabelIcon.objects.filter( Q( owner__isnull = True ) | mine ).order_by( 'id' )

	def perform_create( self, serializer ):
		serializer.save( owner = self.request.user )

	def perform_destroy( self, instance ):
		user = self.request.user
		if not ( user.is_staff or instance.owner_id == user.id ):
			raise PermissionDenied( 'Only the owner can delete this icon.' )
		instance.delete()


class LabelViewSet( viewsets.ModelViewSet ):
	"""Labels on models; filter with ?model=<id>."""
	serializer_class = LabelSerializer
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_fields = [ 'model' ]

	def get_queryset( self ):
		return Label.objects.filter( model__in = readable_models( self.request.user ) ).select_related( 'icon' )


class FlightPathViewSet( viewsets.ModelViewSet ):
	"""Saved camera tours; filter with ?model=<id>. Saving replaces all of a path's points."""
	serializer_class = FlightPathSerializer
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_fields = [ 'model' ]

	def get_queryset( self ):
		return FlightPath.objects.filter( model__in = readable_models( self.request.user ) ).prefetch_related( 'points' )


# --- measurements ---------------------------------------------------------------

class MeasurementViewSet( mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
						mixins.DestroyModelMixin, viewsets.GenericViewSet ):
	"""Your saved measurements; filter with ?model=<id> and ?kind=. Anyone signed in can measure models they can see."""
	serializer_class = MeasurementSerializer
	permission_classes = [ permissions.IsAuthenticated, IsCreatorOrStaff ]
	filterset_fields = [ 'model', 'kind' ]
	queryset = Measurement.objects.none()    # for schema generation; real rows come from get_queryset

	def get_queryset( self ):
		user = self.request.user
		if getattr( self, 'swagger_fake_view', False ):
			return Measurement.objects.all()
		measurements = Measurement.objects.filter( model__in = readable_models( user ) )
		return measurements if user.is_staff else measurements.filter( created_by = user )

	def perform_create( self, serializer ):
		serializer.save( created_by = self.request.user )


# --- jobs ---------------------------------------------------------------------

class JobViewSet( viewsets.ReadOnlyModelViewSet ):
	"""Processing jobs for your models; filter with ?model=<id>."""
	permission_classes = [ permissions.IsAuthenticated ]
	filterset_fields = [ 'model', 'status' ]
	queryset = Job.objects.none()    # for schema generation; real rows come from get_queryset

	def get_queryset( self ):
		jobs = Job.objects.all()
		if getattr( self, 'swagger_fake_view', False ):
			return jobs
		if not self.request.user.is_staff:
			jobs = jobs.filter( model__owner = self.request.user )
		return jobs

	def get_serializer_class( self ):
		return JobDetailSerializer if self.action == 'retrieve' else JobSerializer
