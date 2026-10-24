"""Labels on models and the icon library: /api/v1/labels/, /api/v1/label-icons/"""
from django.db.models import Q
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from catalog.access import EditableModelField, ModelChildSerializerMixin, readable_models
from core.api_fields import GeoPointField
from core.permissions import IsOwnerOrReadOnly

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
	model = EditableModelField()
	position = GeoPointField()
	icon_url = serializers.ImageField( source = 'icon.image', read_only = True, default = None )

	class Meta:
		model = Label
		fields = [ 'id', 'model', 'name', 'icon', 'icon_url', 'position', 'properties' ]

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
