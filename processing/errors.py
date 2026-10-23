"""Pipeline errors, split by whether trying again can help.

PipelineError   the upload itself is the problem (bad format, unsafe or oversized archive): fail at once
TransientError  something around the job went wrong (converter killed, disk full, database blip): retry later
"""
from django.db import InterfaceError, OperationalError


class PipelineError( Exception ):
	"""A problem with the upload; the message is shown to the user."""


class TransientError( Exception ):
	"""A temporary problem; the job is retried with back-off."""


def is_transient( exc ):
	if isinstance( exc, PipelineError ):
		return False
	if isinstance( exc, ( TransientError, OperationalError, InterfaceError ) ):
		return True
	# disk full, I/O errors, lost network mounts …; a missing file is a bug or bad input, not a blip
	return isinstance( exc, OSError ) and not isinstance( exc, ( FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError ) )
