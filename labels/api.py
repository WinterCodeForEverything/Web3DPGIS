"""Labels on models and the icon library: /api/v1/labels/, /api/v1/label-icons/"""
from django.db.models import Q
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from catalog.access import EditableModelField, ModelChildSerializerMixin, readable_models
from core.api_fields import GeoPointField
from core.permissions import IsOwnerOrReadOnly

from . import geometry
from .models import Label, LabelIcon


class LabelIconSerializer( serializers.ModelSerializer ):
	owner = serializers.CharField( source = 'owner.username', read_only = True, default = None )
	can_edit = serializers.SerializerMethodField()

	class Meta:
		model = LabelIcon
		fields = [ 'id', 'name', 'image', 'owner', 'can_edit' ]

	def get_can_edit( self, obj ) -> bool:
		user = self.context['request'].user
		return user.is_authenticated and ( user.is_staff or obj.owner_id == user.id )


class LabelSerializer( ModelChildSerializerMixin, serializers.ModelSerializer ):
	"""A label is a point or a shape (see labels.geometry). Its kind and shape are fixed once it is saved;
	the name, icon, colour and properties can change."""
	model = EditableModelField()
	position = GeoPointField( required = False )
	points = serializers.ListField( child = GeoPointField(), required = False,
		help_text = 'Vertices of a polyline, polygon or wall, in order; empty for other kinds.' )
	color = serializers.RegexField( r'^#[0-9a-fA-F]{6}$', required = False, error_messages = { 'invalid': 'Use a colour like #1e90ff.' } )
	icon_url = serializers.ImageField( source = 'icon.image', read_only = True, default = None )

	class Meta:
		model = Label
		fields = [ 'id', 'model', 'kind', 'name', 'icon', 'icon_url', 'position', 'points', 'radius', 'height', 'color', 'properties' ]

	def to_representation( self, instance ):
		data = super().to_representation( instance )
		data['points'] = [ { 'longitude': x, 'latitude': y, 'height': z } for x, y, z in geometry.vertices( instance.geometry ) ]
		return data

	def validate( self, attrs ):
		attrs = super().validate( attrs )
		if self.instance is not None:
			fixed = [ f for f in ( 'kind', 'points', 'radius', 'height' ) if f in attrs ]
			if fixed:
				raise serializers.ValidationError( { f: 'This cannot be changed; delete the label and draw it again.' for f in fixed } )
			return attrs
		kind = attrs.setdefault( 'kind', Label.Kind.POINT )
		points = attrs.pop( 'points', [] )
		errors = {}
		if kind in geometry.VERTEX_COUNTS:
			fewest, most = geometry.VERTEX_COUNTS[ kind ]
			if not fewest <= len( points ) <= most:
				count = str( fewest ) if fewest == most else f'{fewest} to {most}'
				errors['points'] = f'A {kind} label takes {count} points.'
		elif points:
			errors['points'] = f'A {kind} label has no points; its position is its centre.'
		elif 'position' not in attrs:
			errors['position'] = 'This field is required.'
		for field, needed in ( ( 'radius', geometry.NEEDS_RADIUS ), ( 'height', geometry.NEEDS_HEIGHT ) ):
			value = attrs.get( field )
			if kind in needed and not ( value and value > 0 ):
				errors[field] = f'A {kind} label needs a {field} greater than 0 m.'
			elif kind not in needed and value is not None:
				errors[field] = f'A {kind} label has no {field}.'
		if errors:
			raise serializers.ValidationError( errors )
		if kind in geometry.VERTEX_COUNTS:
			coords = [ p.coords for p in points ]
			attrs['geometry'] = geometry.build_geometry( kind, coords )
			attrs.setdefault( 'position', geometry.middle( coords ) )
		return attrs

	def validate_icon( self, icon ):
		user = self.context['request'].user
		if icon is not None and icon.owner_id not in ( None, user.id ) and not user.is_staff:
			raise serializers.ValidationError( 'Unknown icon.' )
		return icon


class LabelIconViewSet( mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
						mixins.DestroyModelMixin, viewsets.GenericViewSet ):
	"""Label icons: shared icons (no owner) plus your own."""
	serializer_class = LabelIconSerializer

	def get_queryset( self ):
		user = self.request.user
		mine = Q( owner = user ) if user.is_authenticated else Q( pk__in = [] )
		return LabelIcon.objects.filter( Q( owner__isnull = True ) | mine ).order_by( 'id' )

	def perform_create( self, serializer ):
		serializer.save( owner = self.request.user )

	def perform_destroy( self, instance ):
		user = self.request.user
		if not ( user.is_staff or instance.owner_id == user.id ):
			raise PermissionDenied( 'Only the owner can delete this icon.' )
		instance.delete()


class LabelViewSet( viewsets.ModelViewSet ):
	"""Labels on models; filter with ?model=<id>."""
	serializer_class = LabelSerializer
	permission_classes = [ permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly ]
	filterset_fields = [ 'model' ]

	def get_queryset( self ):
		return Label.objects.filter( model__in = readable_models( self.request.user ) ).select_related( 'icon' )


routes = [ ( 'labels', LabelViewSet, 'label' ), ( 'label-icons', LabelIconViewSet, 'label-icon' ) ]
