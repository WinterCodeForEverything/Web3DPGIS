"""Processing jobs: /api/v1/jobs/"""
from rest_framework import permissions, serializers, viewsets

from .models import Job


class JobSerializer( serializers.ModelSerializer ):
	class Meta:
		model = Job
		fields = [ 'id', 'model', 'kind', 'status', 'progress', 'attempts', 'stage', 'message', 'created_at', 'started_at', 'finished_at' ]
		read_only_fields = fields


class JobDetailSerializer( JobSerializer ):
	class Meta( JobSerializer.Meta ):
		fields = JobSerializer.Meta.fields + [ 'log' ]
		read_only_fields = fields


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


routes = [ ( 'jobs', JobViewSet, 'job' ) ]
