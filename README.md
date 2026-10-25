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
| `core/` | Shared building blocks that import no app: geodesy, file storage, API fields, generic permissions, test helpers |
| `accounts/` | `UserProfile`; sign-up, login and logout API |
| `catalog/` | `Model3D` (owner, status, PostGIS `location`, tileset path), who may see a model, the models API with spatial search, file clean-up on delete |
| `processing/` | Background job engine (`Job`, job kinds, Celery task, retries) and the tiling job: upload → 3D Tiles |
| `labels/` | `LabelIcon`, `Label` (PostGIS point + JSON properties) and their API |
| `viewer_tools/` | `FlightPath`, `FlightPoint` (camera poses), `Measurement` (PostGIS geometry), the measurement maths and their API |
| `api/` | Puts the apps' own `api.py` modules together under `/api/v1/`; OpenAPI docs at `/api/docs/` |
| `converters/` | Node command-line converters used by the tiling job |
| `frontend/` | Vue 3 app, laid out below |

The Django apps keep their original labels (`modelshow`, `addlabel`, `viewermode`, `user_login`, see each `apps.py`),
so database tables and migration history did not change when the folders were renamed.

| `frontend/src/` | What it holds |
|---|---|
| `views/` | Pages: model list, upload, login, and `ViewerSwitchPage` which opens a model in `ThreeViewerView` (default) or `MapViewerView` |
| `three/` | The three.js 3D model viewer (`ModelViewer.ts`), its tool list (`tools/`) and its label and measuring drawing |
| `cesium/` | The Cesium map viewer (`mapViewer.ts`), its GIS tools and tool list (`tools/`), tool sessions, line of sight, label and measuring drawing, flight paths API |
| `labels/` | Labels shared by both viewers: store, editor, popup, API, and the `LabelHost` each viewer provides |
| `measurements/` | Measuring shared by both viewers: panel, shapes, API, and the `MeasureHost` each viewer provides |
| `geo/` | Measurement maths on Earth-centred points (no Cesium), used by both viewers |
| `components/` | `ToolDock`: the toolbar and tool panel every viewer uses |
| `api/` | HTTP client (`http.ts`), shared types, and the auth and models/jobs API |

## Architecture

**Back end: who may import whom.** `core/test_architecture.py` fails the test run when an import breaks these rules.

```
core            ← imports no app
processing      → core              (knows models only through Job.model, a foreign key by label)
catalog         → core, processing  (starts jobs)
labels, viewer_tools → core, catalog (things attached to a model)
accounts        → core
api             → core              (finds each app's api.py; no app imports api)
```

**Extension points**

| To add … | Do this |
|---|---|
| API endpoints | Give the app an `api.py` with `routes = [ ( prefix, viewset, basename ) ]` and/or `urlpatterns`; `api/urls.py` picks it up from `INSTALLED_APPS` |
| A kind of background job | `processing.jobs.register_job_kind( name, run, queue = … )` in the app's `AppConfig.ready()`; start it with `start_job( model, name )` (one queued or running job per model; a job's own next step passes `follow_up_of = job`). `run( job, report )` raises on failure; temporary errors (`processing.errors.TransientError`) are retried. A job can start a follow-up job, e.g. `tiling` |
| An upload format for tiling | `processing.tiling.register_input_handler( InputHandler( … ), before = 'mesh' )`; its extensions are then accepted by the upload API |
| A viewer tool | A panel component plus one entry in `frontend/src/cesium/tools/index.ts` or `frontend/src/three/tools/index.ts` |
| A feature in both viewers | Shared logic in its own folder talking to a small host interface, plus a host per viewer (see `labels/` and `measurements/`) |
| A page | A view in `frontend/src/views/` and a route in `router.ts` |

**Adding a module such as 3D reconstruction**, where photos become a model:

1. A Django app `reconstruction/` in `INSTALLED_APPS`, with a rule in `core/test_architecture.py` (e.g. `{ 'core', 'catalog', 'processing' }`).
2. Its own models, e.g. a photo set and settings linked one-to-one to the `Model3D` it produces.
3. `api.py` with its endpoints, e.g. create a reconstruction and upload photos. Creating one makes a `Model3D` and calls `start_job( model, 'reconstruction' )`.
4. In `AppConfig.ready()`: `register_job_kind( 'reconstruction', run, queue = 'reconstruction' )`. `run` builds a mesh or point cloud, saves it as `model.source_file`, and calls `start_job( model, 'tiling', follow_up_of = job )`. From then on the model is tiled, listed, viewed, labelled and measured like any upload.
5. Workers for the heavy part: `celery -A config worker -Q reconstruction` on machines with the reconstruction software (and GPU); the usual workers keep serving the default `celery` queue.
6. Front end: `frontend/src/reconstruction/` with its API file and pages, routes in `router.ts`, and a nav link in `App.vue`.

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
.venv/bin/python manage.py test                     # API, permissions, spatial search, pipeline with real converters, dependency rules,
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

## License

3DPGIS is free software under the [GNU Affero General Public License v3.0 or later](LICENSE): you may use, change and
share it, and a modified version offered to users over a network must make its source available to them.
Third-party software it uses keeps its own licence; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
