from django.db import models


class Job( models.Model ):
	"""One background job on a model; `kind` says what it does (see jobs.register_job_kind), e.g. tiling."""

	class Status( models.TextChoices ):
		QUEUED = 'queued', 'Queued'
		RUNNING = 'running', 'Running'
		SUCCEEDED = 'succeeded', 'Succeeded'
		FAILED = 'failed', 'Failed'

	# by label, so this app does not import the catalog app
	model = models.ForeignKey( 'modelshow.Model3D', related_name = 'jobs', on_delete = models.CASCADE )
	kind = models.CharField( max_length = 32, default = 'tiling', help_text = 'What the job does, e.g. tiling' )
	status = models.CharField( max_length = 16, choices = Status.choices, default = Status.QUEUED )
	progress = models.PositiveSmallIntegerField( default = 0 )
	attempts = models.PositiveSmallIntegerField( default = 0, help_text = 'How many times the pipeline has started for this job' )
	stage = models.CharField( max_length = 64, blank = True )
	message = models.TextField( blank = True )
	log = models.TextField( blank = True )
	created_at = models.DateTimeField( auto_now_add = True )
	started_at = models.DateTimeField( null = True, blank = True )
	finished_at = models.DateTimeField( null = True, blank = True )

	class Meta:
		ordering = [ '-id' ]

	def __str__( self ):
		return f'Job {self.pk} for {self.model_id} ({self.status})'
