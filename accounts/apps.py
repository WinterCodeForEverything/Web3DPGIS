from django.apps import AppConfig


class AccountsConfig( AppConfig ):
	name = 'accounts'
	# the app's original label, so its tables (e.g. user_login_…) and migration history stay as they are
	label = 'user_login'
	verbose_name = 'Accounts'
