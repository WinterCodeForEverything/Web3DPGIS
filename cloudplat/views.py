from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie

MISSING_BUILD = '''<!doctype html><meta charset="utf-8"><title>3DPGIS</title>
<p>The web app has not been built yet. Run <code>npm run build</code> in <code>frontend/</code>,
or use the development server: <code>npm run dev</code> and open <a href="http://localhost:5173/">http://localhost:5173/</a>.</p>
<p>The API is available at <a href="/api/docs/">/api/docs/</a>.</p>'''


@ensure_csrf_cookie
def frontend( request, path = '' ):
	"""Serve the Vue app's index.html for every page URL; the app's router takes it from there."""
	index = settings.FRONTEND_DIST / 'index.html'
	if not index.exists():
		return HttpResponse( MISSING_BUILD, status = 503 )
	response = HttpResponse( index.read_text( encoding = 'utf-8' ) )
	response['Cache-Control'] = 'no-cache'
	return response
