"""Background jobs on a 3D model, whatever they do.

A job kind is registered once, usually from an app's AppConfig.ready():

    register_job_kind( 'tiling', run_tiling, title = 'Build 3D Tiles' )
    register_job_kind( 'reconstruction', run_reconstruction, queue = 'gpu' )   # e.g. a later module

start_job( model, kind ) queues a job; the Celery task (tasks.process_job) runs the kind's `run( job, report )` with
retries for temporary failures. A model has at most one queued or running job; a kind may start a follow-up job when
it is done, e.g. reconstruction → tiling, with start_job( model, 'tiling', follow_up_of = job ).
"""
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.db import connection, transaction
from django.utils import timezone

DEFAULT_QUEUE = 'celery'
# a running job touches Job.heartbeat_at this often; a heartbeat older than STALE_AFTER means its worker is gone
HEARTBEAT_INTERVAL = timedelta( seconds = 60 )
STALE_AFTER = timedelta( minutes = 5 )


class JobConflict( Exception ):
	"""The model already has a queued or running job."""

	def __init__( self, job ):
		super().__init__( f'Model {job.model_id} already has a {job.kind} job in progress (job {job.pk}).' )
		self.job = job


class JobReporter:
	"""Writes progress, stage and log lines to the Job row as a job runs."""

	def __init__( self, job ):
		self.job = job

	def step( self, stage, progress ):
		self.job.stage, self.job.progress = stage, progress
		self.job.save( update_fields = [ 'stage', 'progress' ] )

	def log( self, text ):
		self.job.log = ( self.job.log + text.rstrip() + '\n' )[-100_000:]
		self.job.save( update_fields = [ 'log' ] )


@dataclass( frozen = True )
class JobKind:
	name: str
	run: Callable[ [ 'Job', JobReporter ], None ]    # noqa: F821 — raises on failure; see errors.py for retries
	title: str
	queue: str = DEFAULT_QUEUE                       # Celery queue, so heavy kinds can have their own workers
	done_message: str = 'Done.'                      # shown on the job when it succeeds


_kinds: dict[ str, JobKind ] = {}


def register_job_kind( name, run, *, title = None, queue = DEFAULT_QUEUE, done_message = 'Done.' ):
	if name in _kinds and _kinds[ name ].run is not run:
		raise ValueError( f'Job kind {name!r} is already registered' )
	_kinds[ name ] = JobKind( name, run, title or name.capitalize(), queue, done_message )


def job_kind( name ):
	try:
		return _kinds[ name ]
	except KeyError:
		raise LookupError( f'No job kind {name!r}; registered: {", ".join( sorted( _kinds ) ) or "none"}' ) from None


def job_kinds():
	return list( _kinds.values() )


def start_job( model, kind = 'tiling', *, follow_up_of = None ):
	"""Create a Job of `kind` for model and queue it once the current transaction commits.

	Raises JobConflict while the model has another queued or running job; `follow_up_of` is the running job that
	starts this one as its next step, and does not count.
	"""
	from .models import Job
	from .tasks import process_job

	queue = job_kind( kind ).queue
	with transaction.atomic():
		# lock the model row so two requests cannot both start a job
		type( model ).objects.select_for_update().filter( pk = model.pk ).first()
		active = Job.objects.filter( model = model, status__in = [ Job.Status.QUEUED, Job.Status.RUNNING ] )
		if follow_up_of is not None:
			active = active.exclude( pk = follow_up_of.pk )
		if ( busy := active.first() ) is not None:
			raise JobConflict( busy )
		job = Job.objects.create( model = model, kind = kind, stage = 'queued' )
		model.status = model.Status.PENDING
		model.save( update_fields = [ 'status', 'updated_at' ] )
	transaction.on_commit( lambda: process_job.apply_async( ( job.pk, ), queue = queue ) )
	return job


class Heartbeat:
	"""Touches the job's heartbeat_at every HEARTBEAT_INTERVAL from a thread of its own while the job runs,
	so a long command with no output still shows the job is alive."""

	def __init__( self, job ):
		self.job_id = job.pk
		self._stop = threading.Event()
		self._thread = threading.Thread( target = self._beat, name = f'job-{job.pk}-heartbeat', daemon = True )

	def __enter__( self ):
		self._thread.start()
		return self

	def __exit__( self, *exc ):
		self._stop.set()
		self._thread.join()

	def _beat( self ):
		from .models import Job
		try:
			while not self._stop.wait( HEARTBEAT_INTERVAL.total_seconds() ):
				Job.objects.filter( pk = self.job_id ).update( heartbeat_at = timezone.now() )
		finally:
			connection.close()   # this thread's own database connection


def is_running_elsewhere( job ):
	"""True when job is marked running and its worker showed a sign of life recently."""
	fresh = job.heartbeat_at is not None and timezone.now() - job.heartbeat_at < STALE_AFTER
	return job.status == job.Status.RUNNING and fresh


def run_job( job ):
	"""Do the work of one job attempt; raises on failure (the task records it)."""
	job_kind( job.kind ).run( job, JobReporter( job ) )


def mark_started( job ):
	job.attempts += 1
	job.status, job.started_at, job.heartbeat_at, job.progress = job.Status.RUNNING, timezone.now(), timezone.now(), 0
	job.save( update_fields = [ 'status', 'started_at', 'heartbeat_at', 'progress', 'attempts' ] )
	job.model.status = job.model.Status.PROCESSING
	job.model.save( update_fields = [ 'status', 'updated_at' ] )


def mark_retrying( job, error, delay, max_attempts ):
	"""A temporary failure: put the job back in the queue and say when it runs again."""
	job.status, job.stage = job.Status.QUEUED, 'waiting to retry'
	job.message = f'Temporary problem: {str( error ).rstrip( "." )}. Retrying in {delay} s (attempt {job.attempts + 1} of {max_attempts}).'
	job.log = ( job.log + f'Attempt {job.attempts} failed: {error}\n' )[-100_000:]
	job.save( update_fields = [ 'status', 'stage', 'message', 'log' ] )
	job.model.status = job.model.Status.PENDING
	job.model.save( update_fields = [ 'status', 'updated_at' ] )


def mark_finished( job, error = None ):
	job.finished_at = timezone.now()
	if error is None:
		done = _kinds[ job.kind ].done_message if job.kind in _kinds else 'Done.'
		job.status, job.progress, job.stage, job.message = job.Status.SUCCEEDED, 100, 'done', done
	else:
		job.status, job.message = job.Status.FAILED, str( error )
		job.model.status = job.model.Status.FAILED
		job.model.save( update_fields = [ 'status', 'updated_at' ] )
	job.save()
