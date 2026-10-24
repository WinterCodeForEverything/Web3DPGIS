"""Who may see a 3D model, and API helpers for things that belong to a model (labels, flight paths, measurements …)."""
from django.db.models import Q
from rest_framework import serializers

from core.permissions import can_edit

from .models import Model3D


def readable_models( user ):
	"""Models the user may see: public and visible ones, plus their own (staff see everything)."""
	qs = Model3D.objects.all()
	if user.is_authenticated and user.is_staff:
		return qs
	visible = Q( is_public = True, is_visible = True )
	if user.is_authenticated:
		visible |= Q( owner = user )
	return qs.filter( visible )


class EditableModelField( serializers.PrimaryKeyRelatedField ):
	"""A model the requesting user may see; writing to it is checked in validate_model."""

	def get_queryset( self ):
		return readable_models( self.context['request'].user )


class ModelChildSerializerMixin:
	"""Only the owner of a model may attach things to it."""

	def validate_model( self, model ):
		if not can_edit( self.context['request'].user, model ):
			raise serializers.ValidationError( 'You can only change models you own.' )
		return model
