from django.apps import AppConfig


class ViewerToolsConfig( AppConfig ):
	name = 'viewer_tools'
	# the app's original label, so its tables (e.g. viewermode_…) and migration history stay as they are
	label = 'viewermode'
	verbose_name = 'Viewer tools: flight paths and measurements'
