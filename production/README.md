# Installing 3DPGIS on a server

Scripts that install the whole platform (web app, model uploads and tiling, and optionally 3D reconstruction from photos)
on **one Ubuntu 24.04 server**, behind HTTPS.

| File | What it does |
| --- | --- |
| `setup.sh` | First installation: packages, PostgreSQL 18 + PostGIS, Valkey, Node.js, Obj2Tiles, settings, HTTPS certificate, nginx, services |
| `install_reconstruction_tools.sh` | Builds COLMAP 4.2.1 and OpenMVS 2.4.0 from source (run by `setup.sh --reconstruction`) |
| `update.sh` | Updates to the latest code: packages, front-end build, database, restart |
| `backup.sh` | Nightly database dump (run by `3dpgis-backup.timer`) |
| `nginx.conf` | HTTPS site; serves the front end and 3D Tiles directly, keeps uploads and photos private |
| `systemd/` | Services: `3dpgis-web` (gunicorn), `3dpgis-worker` (tiling), `3dpgis-reconstruction`, the backup timer |

## Resource requirements

Choose the server by what it will do. The platform itself is light. Converting uploads and, above all, reconstructing
models from photos are what need memory, CPU and disk.

| Setup | CPU | Memory | Disk | Good for |
| --- | --- | --- | --- | --- |
| **Viewing only** (models tiled elsewhere) | 1 vCPU | 1 GB | 25 GB | a demo or a read-only catalogue |
| **Viewing + uploads and tiling** | 2 vCPU | 4 GB (8 GB for meshes over ~500 MB) | 50 GB or more | most installations without reconstruction |
| **+ reconstruction on the CPU** | 4–8 vCPU | 8 GB minimum, 16 GB recommended | 100 GB or more | occasional reconstructions of up to a few hundred photos |
| **+ reconstruction on a GPU** | 8 vCPU | 32 GB | 200 GB or more | regular use, `high` preset, large photo sets |

GPU means an NVIDIA GPU with CUDA and at least 8 GB of video memory, with the driver installed (cloud "GPU" images
usually have it). Without a GPU everything still works, only more slowly.

**Memory**
- Each tiling job can use several GB on a large mesh; `CELERY_WORKER_CONCURRENCY` (default 2) sets how many run at once.
- One reconstruction runs at a time. On the development laptop (8 GB, CPU only) 50 photos took about 1.4 GB with the
  `preview` preset and 1.9 GB with `standard`. Memory grows with photo size and count.
- With less than 12 GB, `setup.sh` sets `RECONSTRUCTION_MAX_IMAGE_SIZE=2000`, which caps the photo size. A job that runs
  out of memory is retried with smaller photos, up to twice.
- Building the front end needs about 1.5 GB. Building COLMAP and OpenMVS needs about 8 GB; `setup.sh` adds 2 GB of swap.

**Time.** On that laptop, 50 photos took about 25 minutes (`preview`) and 35 minutes (`standard`). A cloud vCPU is often
slower than a laptop core, so expect similar or longer times on 4 vCPUs. A GPU speeds up feature matching and
densification several times over.

**Disk**
- Keep about 3× the size of each upload free while it is processed (original + unpacked + tiles); uploads are up to 2 GiB,
  and archives may unpack to 20 GiB.
- Reconstructions keep their photos and intermediate files (dense points, meshes) in `media/recon/`. Allow several GB per
  hundred photos.
- Building COLMAP and OpenMVS needs about 20 GB temporarily.
- The disk always keeps `PIPELINE_MIN_FREE_SPACE` (1 GiB) free: a job that would cross it waits and is retried.

**Network.** Visitors download 3D Tiles: tens to hundreds of MB per visit for large models. Check the server's transfer
allowance, or serve the tiles from a bucket with a CDN (see "File storage" in the main README).

**Installation time.** About 15 minutes without reconstruction, plus 1–2 hours to build COLMAP and OpenMVS.

## Before you start

- An Ubuntu 24.04 server matching the table above, with SSH access as root (key log-in).
- A domain name whose DNS A record points at the server. Free names such as DuckDNS work too.
- Ports 80 and 443 free: nothing else, such as a VPN or proxy, listening on them.

## Install

```sh
sudo git clone https://github.com/WinterCodeForEverything/Web3DPGIS.git /srv/3DPGIS/app

# viewing, uploads and tiling
sudo bash /srv/3DPGIS/app/production/setup.sh --domain 3d.example.com --email you@example.com

# ... or with reconstruction (add --gpu on an NVIDIA GPU server)
sudo bash /srv/3DPGIS/app/production/setup.sh --domain 3d.example.com --email you@example.com --reconstruction
```

The email address is only given to Let's Encrypt, for certificate expiry notices. When the script finishes, it prints
the command to create the first administrator account. Then open `https://3d.example.com/`.

To add reconstruction later, run `setup.sh` again with `--reconstruction`. Settings in `/srv/3DPGIS/.env` are kept.

## Where things are

| Path | What |
| --- | --- |
| `/srv/3DPGIS/app` | the code (this repository) |
| `/srv/3DPGIS/.env` | settings: secret key, domain, limits (see `.env.example` for every option) |
| `/srv/3DPGIS/media` | uploads, 3D Tiles, thumbnails, reconstruction photos |
| `/srv/3DPGIS/work` | temporary space for jobs |
| `/srv/3DPGIS/recon-tools` | Obj2Tiles, OpenMVS |
| `/srv/3DPGIS/backups` | nightly database dumps, last 14 kept |

## Day to day

- **Update:** `sudo bash /srv/3DPGIS/app/production/update.sh`
- **Change settings:** edit `/srv/3DPGIS/.env`, then
  `sudo systemctl restart 3dpgis-web 3dpgis-worker 3dpgis-reconstruction`
- **Logs:** `journalctl -u 3dpgis-web -f`, `journalctl -u 3dpgis-worker -f`, `journalctl -u 3dpgis-reconstruction -f`.
  Each job's own log is shown in the app.
- **Backups:** `backup.sh` dumps the database every night. Back up `/srv/3DPGIS/media` with your provider's disk
  snapshots, or use S3 storage.

## Growing beyond one server

Keep files in an S3-compatible bucket (`STORAGE_BACKEND=s3`, see "File storage" in the main README). Then the web server
and a separate reconstruction server can share them:
- On the reconstruction server, install with `--reconstruction` and point `.env` at the same database, broker and bucket.
- Enable only `3dpgis-reconstruction` there.
- Disable `3dpgis-reconstruction` on the web server.

## Security

- **Anyone can sign up**, and every account can upload files and start reconstructions. On a public server, watch disk use
  and the job queue, or keep the site private, for example behind a VPN or with nginx `allow`/`deny` rules.
- The firewall allows only SSH, HTTP and HTTPS. PostgreSQL and Valkey listen on the server itself only, and the database
  uses the local socket with no password.
- Original uploads and reconstruction photos are not served. 3D Tiles are public links: anyone with the URL of a private
  model's tiles can load them.
- **Licence:** 3DPGIS is AGPL-3.0. If you change it and run it for others over a network, offer them your source code.

These scripts follow COLMAP's and OpenMVS's published build instructions. Report any problem on a fresh Ubuntu 24.04
server as an issue.
