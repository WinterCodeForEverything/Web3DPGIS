# 3DPGIS

Web platform for uploading 3D models, processing them into georeferenced 3D Tiles, and viewing, measuring and annotating them on a Cesium globe.

Stack: Django 5.2 LTS + Django REST Framework (Python 3.12) · PostgreSQL 18 + PostGIS · Celery + Valkey · local disk or S3-compatible storage · Vue 3 + Vite + CesiumJS 1.146.

```
Browser ── Vue 3 app (frontend/) ──► /api/v1/ (Django REST Framework) ──► PostgreSQL + PostGIS
   │                                        │ upload
   │                                        ▼
   │                                   Celery worker (processing/) ── obj2gltf, gltf-pipeline, assimp,
   │                                        │                          3d-tiles-tools, py3dtiles
   └──── tileset.json + tiles ◄── storage: media/ folder, or an S3 bucket / CDN (tiles/<model id>/)
```

## Layout

| Path | What it holds |
|---|---|
| `config/` | Django settings, URLs, Celery app |
| `api/` | REST API: serializers, viewsets, permissions, spatial filters; OpenAPI docs at `/api/docs/` |
| `catalog/` | `Model3D` (owner, status, PostGIS `location`, tileset path) and file clean-up on delete |
| `labels/` | `LabelIcon`, `Label` (PostGIS point + JSON properties) |
| `viewer_tools/` | `FlightPath`, `FlightPoint` (camera poses), `Measurement` (PostGIS geometry) and the measurement maths |
| `processing/` | `Job` model, Celery task and the upload → 3D Tiles pipeline |
| `accounts/` | `UserProfile` |
| `converters/` | Node command-line converters used by the pipeline |
| `frontend/` | Vue 3 app, laid out below |

The Django apps keep their original labels (`modelshow`, `addlabel`, `viewermode`, `user_login`, see each `apps.py`),
so database tables and migration history did not change when the folders were renamed.

| `frontend/src/` | What it holds |
|---|---|
| `views/` | Pages: model list, upload, login, and `ViewerSwitchPage` which opens a model in `ThreeViewerView` (default) or `MapViewerView` |
| `three/` | The three.js 3D model viewer (`ModelViewer.ts`) and its label and measuring drawing |
| `cesium/` | The Cesium map viewer (`mapViewer.ts`), its GIS tools in `tools/`, tool sessions, line of sight, label and measuring drawing |
| `labels/` | Labels shared by both viewers: store, editor, popup, and the `LabelHost` each viewer provides |
| `measurements/` | Measuring shared by both viewers: panel, shapes, and the `MeasureHost` each viewer provides |
| `geo/` | Measurement maths on Earth-centred points (no Cesium), used by both viewers |
| `api/` | Typed client for the REST API |

## What uploads are accepted

| Upload | How it becomes 3D Tiles |
|---|---|
| zip / tar / rar containing a `tileset.json` | copied as is; wrapped with a transform if it has no georeference |
| GLB, glTF | gltf-pipeline → 3d-tiles-tools `createTilesetJson` |
| OBJ | obj2gltf → 3d-tiles-tools |
| FBX, DAE, 3DS, PLY, STL | assimp → 3d-tiles-tools |
| LAS, LAZ point clouds | py3dtiles (give the CRS, e.g. `EPSG:4547`, if the file does not carry one) |

Meshes without a georeference are placed at the longitude/latitude given at upload, or at `DEFAULT_MODEL_LOCATION`.
Meshes become a single tile; very large meshes would need a level-of-detail tiler.

### Limits and retries

Before an archive is unpacked, its declared contents are checked against `PIPELINE_MAX_EXTRACTED_SIZE`, `PIPELINE_MAX_ARCHIVE_FILES`
and `PIPELINE_MAX_COMPRESSION_RATIO`, and the disk must keep `PIPELINE_MIN_FREE_SPACE` free; what actually lands is measured again.
A job that fails because of the upload (unsupported, damaged, unsafe or oversized) fails at once with a message.
A job that fails for a temporary reason (a converter killed by the system, a full disk, a lost database connection) is retried
up to `PIPELINE_MAX_RETRIES` times, waiting `PIPELINE_RETRY_BACKOFF` seconds and doubling each time; the job shows
"waiting to retry" and its attempt count meanwhile. See `.env.example` for the defaults.

## File storage

`STORAGE_BACKEND=local` (the default) keeps uploads and tiles in `media/`. `STORAGE_BACKEND=s3` keeps them in an S3-compatible
bucket (AWS S3, Aliyun OSS, Tencent COS, Cloudflare R2, SeaweedFS, MinIO …), so several web servers and workers can share them.
Workers download an upload to `PIPELINE_WORK_DIR`, convert it there and publish the tiles to `tiles/<model id>/`.
Browsers read tiles, thumbnails and label icons straight from the bucket (or a CDN set as `S3_PUBLIC_DOMAIN`);
original uploads under `package/` stay private.

```sh
# configure STORAGE_BACKEND=s3 and the S3_* settings (see .env.example), then:
.venv/bin/python manage.py setup_storage           # creates the bucket, public read for tiles/images/icons, CORS; then checks it
.venv/bin/python manage.py copy_media_to_storage   # moving an existing install: uploads media/ under the same names
```

If your provider rejects bucket policies or CORS through the API, `setup_storage` says so; set the same rules in its console.
Tile URLs are public links: anyone with the URL of a private model's tiles can load them, as with `/media/` before.

For a local S3 server, SeaweedFS (Apache-2.0) works: `brew install seaweedfs`, then
`weed server -dir=/tmp/seaweed -s3 -s3.port=8333 -s3.config=s3.json` with an `s3.json` defining an access key for the app and
`"anonymous"` read access on `3dpgis/tiles/`, `3dpgis/image/`, `3dpgis/label/` and `3dpgis/Data/`.

## Permissions

Anyone can see public, visible models. Signed-in users upload models and own them; only the owner (or staff) can change or
delete a model and its labels, flight paths and jobs. Every change uses POST, PATCH or DELETE with a CSRF token or an API token.

## Local development (macOS)

```sh
brew install postgresql@18 postgis valkey assimp
brew services start postgresql@18
brew services start valkey
psql -d postgres -c "CREATE ROLE southcloud LOGIN CREATEDB PASSWORD 'southcloud';" -c "CREATE DATABASE southcloud OWNER southcloud;"
psql -d southcloud -c "CREATE EXTENSION postgis;"
psql -d template1 -c "CREATE EXTENSION IF NOT EXISTS postgis;"   # lets the test runner create PostGIS databases

python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # requirements.txt alone in production
(cd converters && npm install)
(cd frontend && npm install)
cp .env.example .env            # edit as needed
set -a; source .env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # optional, for /admin/
```

Run three processes:

```sh
.venv/bin/python manage.py runserver                 # API on :8000
.venv/bin/celery -A config worker -l info          # processing jobs
cd frontend && npm run dev                            # app on http://localhost:5173 (proxies /api and /media to :8000)
```

Or build the app once (`cd frontend && npm run build`) and open http://localhost:8000/, where Django serves it.

RAR uploads need an extraction tool on `PATH` that `rarfile` can use: `unrar`, `unar` (`brew install unar`) or `bsdtar`.

## Tests

```sh
.venv/bin/python manage.py test                     # 64 tests: API, permissions, spatial search, pipeline with real converters,
                                                    # limits and retries, S3 storage (moto), 2019 data migrations both ways
cd frontend && npm test && npm run typecheck        # measurement maths, tool clean-up, types
scripts/e2e.sh                                      # browser test: sign up, upload, processing, every viewer tool, delete
```

`scripts/e2e.sh` creates its own database (`southcloud_e2e`), media folder and queue, starts a server and a Celery worker,
drives Chrome through the app, and removes everything afterwards; screenshots and logs land in `e2e-artifacts/`.
It needs PostgreSQL + PostGIS, Valkey, the converters and Chrome (`CHROME_PATH` if it is not in the usual place).

GitHub Actions (`.github/workflows/ci.yml`) runs all three on every push and pull request, with PostGIS and Valkey as
services; the end-to-end job keeps its screenshots and logs as a build artifact.

## Production

- `cd frontend && npm ci && npm run build`, then `python manage.py collectstatic --noinput`.
- Run the API with gunicorn behind nginx (`deploy/nginx.conf`) and at least one Celery worker:
  `celery -A config worker -l info` (thread pool by default; set `CELERY_WORKER_CONCURRENCY` to taste).
- With more than one server, use `STORAGE_BACKEND=s3` so all servers and workers share files (see File storage).
- Set `DJANGO_DEBUG=false`, a real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and, behind HTTPS, `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Upgrading a 2019 database: `python manage.py migrate` converts usernames to owners and Earth-centred coordinates to
  PostGIS points; the migrations are reversible.
