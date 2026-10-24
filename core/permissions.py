"""Permission rules that work for any app: the owner of an object (or of what it belongs to) may change it."""
from rest_framework import permissions


def owner_of( obj ):
	"""The user who controls obj: its own owner, or the owner of what it belongs to (obj.model, obj.path …)."""
	if hasattr( obj, 'owner_id' ):
		return obj.owner
	parent = getattr( obj, 'model', None ) or getattr( obj, 'path', None )
	return owner_of( parent ) if parent is not None else None


def can_edit( user, obj ):
	if not user.is_authenticated:
		return False
	return user.is_staff or owner_of( obj ) == user


class IsOwnerOrReadOnly( permissions.BasePermission ):
	"""Anyone who can see an object may read it; only its owner (or staff) may change it."""

	def has_object_permission( self, request, view, obj ):
		if request.method in permissions.SAFE_METHODS:
			return True
		return can_edit( request.user, obj )


class IsCreatorOrStaff( permissions.BasePermission ):
	"""Only the user who created an object (or staff) may use it, e.g. personal measurements."""

	def has_object_permission( self, request, view, obj ):
		return request.user.is_staff or obj.created_by_id == request.user.id
