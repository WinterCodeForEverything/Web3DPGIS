#!/usr/bin/env bash
# Update a server installed with setup.sh to the latest code, or (re)build the application after setup:
#
#   sudo bash /srv/3DPGIS/app/production/update.sh [--no-pull] [--no-restart]
#
# Pulls the code, installs Python and Node packages, builds the front end, updates the database, collects static
# files and restarts the services. Jobs that are running when the workers restart are retried.
set -euo pipefail

root=/srv/3DPGIS
app=$root/app
pull=true restart=true
for arg in "$@"; do
	case $arg in
		--no-pull) pull=false ;;
		--no-restart) restart=false ;;
		*) echo "Unknown option $arg" >&2; exit 2 ;;
	esac
done
[ "$( id -u )" = 0 ] || { echo 'Run as root (sudo).' >&2; exit 1; }

as_app() { sudo -u pgis -H bash -c "set -a; source $root/.env; set +a; cd $app; $*"; }

if $pull; then
	echo '== Code'
	sudo -u pgis git -C "$app" pull --ff-only
fi

echo '== Python packages'
[ -d "$root/venv" ] || sudo -u pgis python3 -m venv "$root/venv"
sudo -u pgis "$root/venv/bin/pip" install --quiet --upgrade pip
sudo -u pgis "$root/venv/bin/pip" install --quiet -r "$app/requirements.txt"

echo '== Converters and front end'
as_app 'cd converters && npm ci --no-audit --no-fund'
as_app 'cd frontend && npm ci --no-audit --no-fund && npm run build'

echo '== Database and static files'
as_app "$root/venv/bin/python manage.py migrate --noinput"
as_app "$root/venv/bin/python manage.py collectstatic --noinput --verbosity 0"

if $restart; then
	echo '== Restarting'
	for s in 3dpgis-web 3dpgis-worker 3dpgis-reconstruction; do
		if systemctl is-enabled --quiet "$s" 2>/dev/null; then systemctl restart "$s"; fi
	done
fi
echo 'Updated.'
