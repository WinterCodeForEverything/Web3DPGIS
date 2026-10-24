from django.apps import AppConfig


class LabelsConfig( AppConfig ):
	name = 'labels'
	# the app's original label, so its tables (e.g. addlabel_…) and migration history stay as they are
	label = 'addlabel'
	verbose_name = 'Labels'
