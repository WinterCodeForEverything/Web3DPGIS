#!/usr/bin/env bash
# Install the full 3DPGIS platform on one Ubuntu 24.04 server: web app, uploads, tiling worker and, optionally,
# 3D reconstruction from photos. See production/README.md for the resources each setup needs.
#
#   git clone https://github.com/WinterCodeForEverything/Web3DPGIS.git /srv/3DPGIS/app
#   sudo bash /srv/3DPGIS/app/production/setup.sh --domain 3d.example.com --email you@example.com [--reconstruction] [--gpu]
#
#   --domain           the site's name; its DNS A record must already point at this server (for the HTTPS certificate)
#   --email            given to Let's Encrypt only, for certificate expiry notices
#   --reconstruction   also build COLMAP and OpenMVS and run a reconstruction worker (adds 1-2 hours)
#   --gpu              build them with CUDA (needs an NVIDIA GPU with its driver installed)
#
# Safe to run again: steps that are done are skipped, settings in /srv/3DPGIS/.env are kept.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

root=/srv/3DPGIS
app=$root/app
here=$( cd "$( dirname "$0" )" && pwd )
domain= email= reconstruction=false gpu=false
while [ $# -gt 0 ]; do
	case $1 in
		--domain) domain=$2; shift 2 ;;
		--email) email=$2; shift 2 ;;
		--reconstruction) reconstruction=true; shift ;;
		--gpu) gpu=true; reconstruction=true; shift ;;
		*) echo "Unknown option $1" >&2; exit 2 ;;
	esac
done
[ -n "$domain" ] && [ -n "$email" ] || { sed -n '2,14p' "$0"; exit 2; }
[ "$( id -u )" = 0 ] || { echo 'Run as root (sudo).' >&2; exit 1; }
[ "$here" = "$app/production" ] || { echo "Clone the repository to $app first (see the top of this script)." >&2; exit 1; }

memory_gb=$(( $( awk '/MemTotal/ { print $2 }' /proc/meminfo ) / 1024 / 1024 ))
cpus=$( nproc )
disk_gb=$( df -BG --output=avail "$root" | tail -1 | tr -dc 0-9 )
echo "This server: $cpus CPUs, ${memory_gb} GB memory, ${disk_gb} GB free disk."
need_memory=3 need_disk=30
if $reconstruction; then need_memory=7 need_disk=80; fi
if [ "$memory_gb" -lt "$need_memory" ] || [ "$disk_gb" -lt "$need_disk" ]; then
	echo "Warning: below the minimum for this setup (about $(( need_memory + 1 )) GB memory, $need_disk GB disk); see production/README.md." >&2
	read -r -p 'Continue anyway? [y/N] ' answer
	[ "$answer" = y ] || exit 1
fi

step() { echo; echo "== $*"; }
as_app() { sudo -u pgis -H bash -c "set -a; source $root/.env; set +a; cd $app; $*"; }

step 'Swap'
if ! swapon --show | grep -q /swapfile; then
	fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
	grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

step 'System packages'
apt-get update
apt-get install -y ca-certificates curl gnupg git unzip nginx certbot ufw \
	python3-venv python3-dev build-essential gdal-bin libgdal-dev libgeos-dev libproj-dev binutils \
	assimp-utils unar libicu74
# Valkey where Ubuntu has it, otherwise Redis (same protocol)
apt-get install -y valkey-server 2>/dev/null || apt-get install -y redis-server

if [ ! -f /etc/apt/sources.list.d/pgdg.list ]; then
	install -d /usr/share/postgresql-common/pgdg
	curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
	echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main" \
		> /etc/apt/sources.list.d/pgdg.list
fi
if [ ! -f /etc/apt/sources.list.d/nodesource.list ]; then
	# Node.js 22 (Ubuntu's own is too old for the front-end build)
	install -d /etc/apt/keyrings
	curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
	echo 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main' > /etc/apt/sources.list.d/nodesource.list
fi
apt-get update
apt-get install -y postgresql-18 postgresql-18-postgis-3 nodejs

step 'Firewall: SSH, HTTP, HTTPS only'
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

step 'User, folders, database'
id pgis >/dev/null 2>&1 || useradd --system --home-dir "$root" --shell /usr/sbin/nologin pgis
install -d -o pgis -g pgis "$root" "$root/media" "$root/work" "$root/recon-tools" "$root/backups"
chown -R pgis:pgis "$app"
# the pgis user reaches its database through the local socket, without a password
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'pgis'" | grep -q 1 || sudo -u postgres createuser pgis
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = 'pgis'" | grep -q 1 || sudo -u postgres createdb -O pgis pgis
sudo -u postgres psql -d pgis -qc 'CREATE EXTENSION IF NOT EXISTS postgis'

step 'Obj2Tiles (levels of detail for large meshes)'
if [ ! -x "$root/recon-tools/obj2tiles/Obj2Tiles" ]; then
	# 1.6.2 is the version the tiling code is written for (see README, "What uploads are accepted")
	arch=$( [ "$( uname -m )" = aarch64 ] && echo LinuxArm64 || echo Linux64 )
	curl -fsSL -o /tmp/obj2tiles.zip "https://github.com/OpenDroneMap/Obj2Tiles/releases/download/v1.6.2/Obj2Tiles-$arch.zip"
	install -d -o pgis -g pgis "$root/recon-tools/obj2tiles"
	unzip -oq /tmp/obj2tiles.zip -d "$root/recon-tools/obj2tiles"
	chmod +x "$root/recon-tools/obj2tiles/Obj2Tiles"
	chown -R pgis:pgis "$root/recon-tools/obj2tiles"
	rm /tmp/obj2tiles.zip
fi

step 'Settings'
if [ ! -f "$root/.env" ]; then
	max_image=0
	[ "$memory_gb" -lt 12 ] && max_image=2000      # what fits in 8 GB; see README, "3D reconstruction from photos"
	cat > "$root/.env" <<-EOF
		DJANGO_DEBUG=false
		DJANGO_SECRET_KEY=$( python3 -c 'import secrets; print( secrets.token_urlsafe( 50 ) )' )
		DJANGO_ALLOWED_HOSTS=$domain
		DJANGO_CSRF_TRUSTED_ORIGINS=https://$domain
		POSTGRES_DB=pgis
		POSTGRES_USER=pgis
		POSTGRES_PASSWORD=
		POSTGRES_HOST=
		CELERY_BROKER_URL=redis://localhost:6379/0
		STORAGE_BACKEND=local
		MEDIA_ROOT=$root/media
		PIPELINE_WORK_DIR=$root/work
		PIPELINE_OBJ2TILES=$root/recon-tools/obj2tiles/Obj2Tiles
		MAX_UPLOAD_SIZE=2147483648
		RECONSTRUCTION_TOOLS_DIR=$root/recon-tools
		RECONSTRUCTION_COLMAP=/usr/local/bin/colmap
		RECONSTRUCTION_USE_GPU=$gpu
		RECONSTRUCTION_MAX_IMAGE_SIZE=$max_image
	EOF
fi
sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=$domain|; s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://$domain|" "$root/.env"
$gpu && sed -i 's|^RECONSTRUCTION_USE_GPU=.*|RECONSTRUCTION_USE_GPU=true|' "$root/.env"
chown root:pgis "$root/.env"
chmod 640 "$root/.env"

if $reconstruction; then
	step 'COLMAP and OpenMVS (1-2 hours)'
	bash "$here/install_reconstruction_tools.sh" $( $gpu && echo --gpu )
fi

step 'Application: Python packages, converters, front end, database'
bash "$here/update.sh" --no-pull --no-restart

step 'HTTPS certificate'
install -d /var/www/certbot
rm -f /etc/nginx/sites-enabled/default
if [ ! -d "/etc/letsencrypt/live/$domain" ]; then
	printf 'server {\n\tlisten 80;\n\tserver_name %s;\n\tlocation /.well-known/acme-challenge/ { root /var/www/certbot; }\n}\n' "$domain" \
		> /etc/nginx/sites-available/3dpgis
	ln -sf /etc/nginx/sites-available/3dpgis /etc/nginx/sites-enabled/3dpgis
	systemctl reload nginx
	certbot certonly --webroot -w /var/www/certbot -d "$domain" -m "$email" --agree-tos -n --deploy-hook 'systemctl reload nginx'
fi

step 'nginx and services'
sed "s/DOMAIN/$domain/g" "$here/nginx.conf" > /etc/nginx/sites-available/3dpgis
ln -sf /etc/nginx/sites-available/3dpgis /etc/nginx/sites-enabled/3dpgis
nginx -t
systemctl reload nginx
services=( 3dpgis-web 3dpgis-worker )
$reconstruction && services+=( 3dpgis-reconstruction )
for s in "${services[@]}"; do install -m 644 "$here/systemd/$s.service" /etc/systemd/system/; done
install -m 644 "$here/systemd/3dpgis-backup.service" "$here/systemd/3dpgis-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "${services[@]}" 3dpgis-backup.timer
systemctl restart "${services[@]}"

echo
echo "Done: https://$domain/"
echo "Create an administrator account:"
echo "  sudo -u pgis -H bash -c 'set -a; source $root/.env; set +a; cd $app; $root/venv/bin/python manage.py createsuperuser'"
