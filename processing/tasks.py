import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction

from .errors import is_transient
from .jobs import Heartbeat, is_running_elsewhere, job_kind, mark_finished, mark_retrying, mark_started, run_job
from .models import Job

logger = logging.getLogger( __name__ )


def retry_delay( attempt ):
	"""Seconds to wait after a failed attempt: base, 2 x base, 4 x base, …"""
	return settings.PIPELINE_RETRY_BACKOFF * 2 ** ( attempt - 1 )


def claim( job_id ):
	"""The job, marked as started by this worker; None when there is nothing to do: the job is gone, already finished,
	or still running on another worker (the broker re-delivers unacknowledged tasks after its visibility timeout)."""
	with transaction.atomic():
		job = Job.objects.select_for_update().select_related( 'model' ).filter( pk = job_id ).first()
		if job is None:
			logger.warning( 'Job %s no longer exists', job_id )
			return None
		if job.status in ( Job.Status.SUCCEEDED, Job.Status.FAILED ):
			logger.warning( 'Job %s already %s; ignoring a repeated delivery', job_id, job.status )
			return None
		if is_running_elsewhere( job ):
			logger.warning( 'Job %s is still running on another worker; ignoring a repeated delivery', job_id )
			return None
		mark_started( job )
	return job


@shared_task( bind = True, acks_late = True, max_retries = None )
def process_job( self, job_id ):
	job = claim( job_id )
	if job is None:
		return
	try:
		with Heartbeat( job ):
			run_job( job )
	except Exception as exc:
		max_attempts = settings.PIPELINE_MAX_RETRIES + 1
		if is_transient( exc ) and job.attempts < max_attempts:
			delay = retry_delay( job.attempts )
			logger.warning( 'Job %s attempt %s failed, retrying in %s s: %s', job_id, job.attempts, delay, exc )
			mark_retrying( job, exc, delay, max_attempts )
			# Retry ends this run and re-queues the task after `delay` (eager mode re-runs it at once)
			raise self.retry( countdown = delay, queue = job_kind( job.kind ).queue )
		logger.exception( 'Job %s failed', job_id )
		if is_transient( exc ):
			exc = f'{exc} (gave up after {job.attempts} attempts)'
		mark_finished( job, error = exc )
	else:
		mark_finished( job )
