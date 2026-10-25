# Third-party software

3DPGIS is licensed under the GNU Affero General Public License v3.0 or later (see `LICENSE`).
It uses the software below. Each keeps its own licence; versions are those pinned or installed when this list was made.

## Reconstruction tools (separate programs, run unmodified as commands)

| Software | Licence | Used for |
| --- | --- | --- |
| [COLMAP](https://colmap.github.io/) 4.2 | BSD-3-Clause | Feature extraction, matching, sparse reconstruction, georeferencing, undistortion |
| [OpenMVS](https://github.com/cdcseacave/openMVS) | AGPL-3.0 | Dense point cloud, mesh and texture |
| [Obj2Tiles](https://github.com/OpenDroneMap/Obj2Tiles) | AGPL-3.0 | Levels of detail and 3D Tiles for textured meshes |

## Tiling converters (separate programs)

| Software | Licence |
| --- | --- |
| [obj2gltf](https://github.com/CesiumGS/obj2gltf) 3.2.0 | Apache-2.0 |
| [gltf-pipeline](https://github.com/CesiumGS/gltf-pipeline) 4.3.1 | Apache-2.0 |
| [3d-tiles-tools](https://github.com/CesiumGS/3d-tiles-tools) 0.5.4 | Apache-2.0 |
| [assimp](https://github.com/assimp/assimp) 6.0 | BSD-3-Clause (with bundled parts under MIT, BSL-1.0, Zlib and others) |
| [py3dtiles](https://gitlab.com/py3dtiles/py3dtiles) 12.1 | Apache-2.0 |

## Back end (Python libraries)

| Software | Licence |
| --- | --- |
| Django 5.2, Django REST Framework, Celery, drf-spectacular, django-filter, django-storages | BSD-3-Clause |
| psycopg 3 | LGPL-3.0-only |
| boto3 | Apache-2.0 |
| whitenoise, gunicorn | MIT |
| Pillow | MIT-CMU |

## Front end (bundled into the web app)

| Software | Licence |
| --- | --- |
| Vue 3.5, Vue Router, Pinia | MIT |
| three.js 0.186 | MIT |
| 3d-tiles-renderer 0.5.3 | Apache-2.0 |
| CesiumJS 1.146 | Apache-2.0 |
