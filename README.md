# 3DPGIS

Web platform for uploading, viewing and annotating 3D models (3D Tiles) on a Cesium globe.

Stack: Django 5.2 LTS (Python 3.12) · PostgreSQL 18 + PostGIS · Cesium 1.146 · jQuery/Bootstrap templates.

## Apps

| App | URL prefix | Purpose |
|---|---|---|
| `user_login` | `/accounts/` | register / login |
| `modelshow` | `/show/` | upload archives (zip/tar/rar containing `tileset.json`), list, show/hide, delete, Cesium viewer |
| `addlabel` | `/label/` | label icons and labels placed on a model |
| `viewermode` | `/viewer/` | saved camera flight paths |
| `othertools` | `/other/` | model height adjustment |
| `analyzetool` | `/analyze/` | analysis tools page (sight line, viewshed run in the browser) |

Uploaded archives go to `media/package/` and are extracted to `media/Data/<archive name>/`.

## Local development (macOS)

```sh
brew install postgresql@18 postgis
brew services start postgresql@18
psql -d postgres -c "CREATE ROLE southcloud LOGIN PASSWORD 'southcloud';" -c "CREATE DATABASE southcloud OWNER southcloud;"
psql -d southcloud -c "CREATE EXTENSION postgis;"

python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # edit as needed
set -a; source .env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # optional, for /admin/
.venv/bin/python manage.py runserver
```

RAR uploads need an extraction tool on `PATH` that `rarfile` can use: `unrar`, `unar` (`brew install unar`) or `bsdtar`.

## Production

Run with gunicorn behind nginx (see `deploy/nginx.conf`), with `DJANGO_DEBUG=false`, a real `DJANGO_SECRET_KEY`,
and `DJANGO_ALLOWED_HOSTS` set. Run `python manage.py collectstatic` before starting.
