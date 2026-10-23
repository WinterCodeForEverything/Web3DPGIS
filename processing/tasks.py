import logging

from celery import shared_task
from django.conf import settings

from .errors import is_transient
from .models import Job
from .pipeline import mark_finished, mark_retrying, mark_started, run_job

logger = logging.getLogger( __name__ )


def retry_delay( attempt ):
	"""Seconds to wait after a failed attempt: base, 2 x base, 4 x base, …"""
	return settings.PIPELINE_RETRY_BACKOFF * 2 ** ( attempt - 1 )


@shared_task( bind = True, acks_late = True, max_retries = None )
def process_job( self, job_id ):
	job = Job.objects.select_related( 'model' ).filter( pk = job_id ).first()
	if job is None:
		logger.warning( 'Job %s no longer exists', job_id )
		return
	mark_started( job )
	try:
		run_job( job )
	except Exception as exc:
		max_attempts = settings.PIPELINE_MAX_RETRIES + 1
		if is_transient( exc ) and job.attempts < max_attempts:
			delay = retry_delay( job.attempts )
			logger.warning( 'Job %s attempt %s failed, retrying in %s s: %s', job_id, job.attempts, delay, exc )
			mark_retrying( job, exc, delay, max_attempts )
			# Retry ends this run and re-queues the task after `delay` (eager mode re-runs it at once)
			raise self.retry( countdown = delay )
		logger.exception( 'Job %s failed', job_id )
		if is_transient( exc ):
			exc = f'{exc} (gave up after {job.attempts} attempts)'
		mark_finished( job, error = exc )
	else:
		mark_finished( job )
