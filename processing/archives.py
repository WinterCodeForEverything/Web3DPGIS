"""Safe extraction of uploaded archives.

Every archive is inspected before anything is written: entries must stay inside the destination ("zip slip"),
and the total unpacked size, file count and compression ratio must stay within the PIPELINE_* limits,
so a small upload cannot expand into a disk-filling "zip bomb".
"""
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass

import rarfile
from django.conf import settings

from .errors import PipelineError, TransientError

ARCHIVE_EXTENSIONS = ( '.zip', '.tar', '.tar.gz', '.tgz', '.rar' )

# compression ratios are only judged above this unpacked size; small archives cannot do harm
RATIO_CHECK_FROM = 64 * 1024 ** 2


class ArchiveError( PipelineError ):
	pass


@dataclass
class Limits:
	max_size: int
	max_files: int
	max_ratio: float
	min_free_space: int

	@classmethod
	def from_settings( cls ):
		return cls( settings.PIPELINE_MAX_EXTRACTED_SIZE, settings.PIPELINE_MAX_ARCHIVE_FILES,
			settings.PIPELINE_MAX_COMPRESSION_RATIO, settings.PIPELINE_MIN_FREE_SPACE )


def is_archive( filename ):
	return filename.lower().endswith( ARCHIVE_EXTENSIONS )


def human_size( n ):
	for unit in ( 'B', 'KB', 'MB', 'GB' ):
		if n < 1024:
			return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
		n /= 1024
	return f'{n:.1f} TB'


def _reject_unsafe_paths( names, destination ):
	# reject entries that would be written outside destination ("zip slip")
	root = os.path.realpath( destination )
	for member in names:
		target = os.path.realpath( os.path.join( root, member ) )
		if target != root and not target.startswith( root + os.sep ):
			raise ArchiveError( f'Unsafe path in archive: {member}' )


def ensure_free_space( directory, needed, limits ):
	"""Raise TransientError when the disk holding directory lacks room for needed bytes plus the safety margin."""
	os.makedirs( directory, exist_ok = True )
	free = shutil.disk_usage( directory ).free
	if free < needed + limits.min_free_space:
		raise TransientError( f'Not enough disk space: need {human_size( needed )} plus {human_size( limits.min_free_space )} spare, '
			f'{human_size( free )} free.' )


def check_declared_sizes( archive_path, sizes, limits ):
	"""Validate the declared sizes of an archive's files against the limits before extracting."""
	total, count = sum( sizes ), len( sizes )
	if count > limits.max_files:
		raise ArchiveError( f'The archive holds {count} files; the limit is {limits.max_files}.' )
	if total > limits.max_size:
		raise ArchiveError( f'The archive unpacks to {human_size( total )}; the limit is {human_size( limits.max_size )}.' )
	packed = max( os.path.getsize( archive_path ), 1 )
	if total >= RATIO_CHECK_FROM and total / packed > limits.max_ratio:
		raise ArchiveError( f'The archive expands {total / packed:.0f} times ({human_size( packed )} to {human_size( total )}), '
			f'more than the allowed {limits.max_ratio:.0f}; it looks like a "zip bomb".' )
	return total


def _directory_size( path ):
	return sum( os.path.getsize( os.path.join( root, f ) ) for root, _, files in os.walk( path ) for f in files )


def extract( path, destination, limits = None ):
	"""Extract a zip, tar(.gz) or rar archive into destination, within limits."""
	limits = limits or Limits.from_settings()
	os.makedirs( destination, exist_ok = True )
	name = path.lower()
	try:
		if name.endswith( '.zip' ):
			with zipfile.ZipFile( path ) as archive:
				infos = [ i for i in archive.infolist() if not i.is_dir() ]
				_reject_unsafe_paths( archive.namelist(), destination )
				total = check_declared_sizes( path, [ i.file_size for i in infos ], limits )
				ensure_free_space( destination, total, limits )
				# zipfile refuses to inflate an entry past its declared size, so the check above holds
				archive.extractall( destination )
		elif name.endswith( ( '.tar', '.tar.gz', '.tgz' ) ):
			with tarfile.open( path ) as archive:
				members = archive.getmembers()
				total = check_declared_sizes( path, [ m.size for m in members if m.isfile() ], limits )
				ensure_free_space( destination, total, limits )
				archive.extractall( destination, filter = 'data' )
		elif name.endswith( '.rar' ):
			# needs an `unrar`, `unar` or `bsdtar` command on PATH
			with rarfile.RarFile( path ) as archive:
				infos = [ i for i in archive.infolist() if not i.is_dir() ]
				_reject_unsafe_paths( archive.namelist(), destination )
				total = check_declared_sizes( path, [ i.file_size for i in infos ], limits )
				ensure_free_space( destination, total, limits )
				archive.extractall( destination )
		else:
			raise ArchiveError( f'Not an archive: {os.path.basename( path )}' )
	except ( zipfile.BadZipFile, tarfile.TarError, rarfile.Error, EOFError ) as exc:
		raise ArchiveError( f'The archive is damaged or not a supported format ({exc}).' ) from exc
	# headers can lie (rar is unpacked by an external tool); measure what actually landed
	if _directory_size( destination ) > limits.max_size:
		shutil.rmtree( destination, ignore_errors = True )
		raise ArchiveError( f'The archive unpacked to more than {human_size( limits.max_size )}.' )
