from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register( 'models', views.Model3DViewSet, basename = 'model' )
router.register( 'labels', views.LabelViewSet, basename = 'label' )
router.register( 'label-icons', views.LabelIconViewSet, basename = 'label-icon' )
router.register( 'flight-paths', views.FlightPathViewSet, basename = 'flight-path' )
router.register( 'measurements', views.MeasurementViewSet, basename = 'measurement' )
router.register( 'jobs', views.JobViewSet, basename = 'job' )

urlpatterns = [
	path( 'v1/', include( router.urls ) ),
	path( 'v1/auth/me/', views.MeView.as_view(), name = 'auth-me' ),
	path( 'v1/auth/register/', views.RegisterView.as_view(), name = 'auth-register' ),
	path( 'v1/auth/login/', views.LoginView.as_view(), name = 'auth-login' ),
	path( 'v1/auth/logout/', views.LogoutView.as_view(), name = 'auth-logout' ),
	path( 'v1/auth/token/', obtain_auth_token, name = 'auth-token' ),
	path( 'schema/', SpectacularAPIView.as_view(), name = 'api-schema' ),
	path( 'docs/', SpectacularSwaggerView.as_view( url_name = 'api-schema' ), name = 'api-docs' ),
]
