#!/usr/bin/env bash
# Nightly database backup, run by 3dpgis-backup.timer as the pgis user. Keeps the last 14 dumps in /srv/3DPGIS/backups.
# Uploaded files and tiles (/srv/3DPGIS/media) are not copied here: back them up with your provider's disk snapshots,
# or keep them in an S3 bucket (STORAGE_BACKEND=s3).
# Restore: pg_restore --clean --if-exists -d pgis /srv/3DPGIS/backups/pgis-YYYYMMDD.dump
set -euo pipefail
dir=/srv/3DPGIS/backups
pg_dump --format custom --file "$dir/pgis-$( date +%Y%m%d ).dump" pgis
ls -1t "$dir"/pgis-*.dump | tail -n +15 | xargs -r rm --
