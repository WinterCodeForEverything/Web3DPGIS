from django.db.models import Q
from rest_framework import permissions

from catalog.models import Model3D


def readable_models( user ):
	"""Models the user may see: public and visible ones, plus their own (staff see everything)."""
	qs = Model3D.objects.all()
	if user.is_authenticated and user.is_staff:
		return qs
	visible = Q( is_public = True, is_visible = True )
	if user.is_authenticated:
		visible |= Q( owner = user )
	return qs.filter( visible )


def owner_of( obj ):
	"""The user who controls obj: a model's owner, or the owner of the model it belongs to."""
	if isinstance( obj, Model3D ):
		return obj.owner
	model = getattr( obj, 'model', None ) or getattr( getattr( obj, 'path', None ), 'model', None )
	if model is not None:
		return model.owner
	return getattr( obj, 'owner', None )


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
