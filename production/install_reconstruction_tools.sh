#!/usr/bin/env bash
# Build COLMAP and OpenMVS for 3D reconstruction from photos, on Ubuntu 24.04. setup.sh runs it with --reconstruction;
# it can also be run by itself, e.g. on a separate reconstruction server:
#
#   sudo bash install_reconstruction_tools.sh [--gpu]
#
# COLMAP 4.x is required (the pipeline uses its 4.x option names; Ubuntu's own package is 3.9), so both are built from
# source, following their build instructions (colmap.github.io/install.html, github.com/cdcseacave/openMVS/wiki/Building).
#   COLMAP  -> /usr/local/bin/colmap
#   OpenMVS -> /srv/3DPGIS/recon-tools/openmvs/   (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, RefineMesh, TextureMesh)
# Takes 1-2 hours on 4 CPUs, needs about 8 GB of memory and 20 GB of free disk while building (removed afterwards).
# --gpu builds with CUDA; the NVIDIA driver must already be installed (nvidia-smi works).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

COLMAP_VERSION=4.2.1
OPENMVS_VERSION=v2.4.0
tools=/srv/3DPGIS/recon-tools
build=/var/tmp/3dpgis-build
gpu=false
[ "${1:-}" = --gpu ] && gpu=true
[ "$( id -u )" = 0 ] || { echo 'Run as root (sudo).' >&2; exit 1; }

# parallel compile jobs: one per CPU, but no more than one per 2 GB of memory
memory_gb=$(( $( awk '/MemTotal/ { print $2 }' /proc/meminfo ) / 1024 / 1024 ))
jobs=$( nproc )
[ $(( memory_gb / 2 )) -lt "$jobs" ] && jobs=$(( memory_gb / 2 ))
[ "$jobs" -lt 1 ] && jobs=1

cuda_args=()
if $gpu; then
	nvidia-smi >/dev/null || { echo 'nvidia-smi does not work: install the NVIDIA driver first.' >&2; exit 1; }
	command -v nvcc >/dev/null || apt-get install -y nvidia-cuda-toolkit nvidia-cuda-toolkit-gcc
	# Ubuntu's CUDA needs an older host compiler than the system's; this package provides it
	[ -x /usr/bin/cuda-g++ ] && export CUDAHOSTCXX=/usr/bin/cuda-g++
	cuda_args=( -DCMAKE_CUDA_ARCHITECTURES=native )
fi

mkdir -p "$build"

if ! /usr/local/bin/colmap help 2>/dev/null | grep -q "COLMAP $COLMAP_VERSION"; then
	echo "== COLMAP $COLMAP_VERSION"
	apt-get install -y git cmake ninja-build build-essential \
		libboost-program-options-dev libboost-graph-dev libboost-system-dev libeigen3-dev \
		libopenimageio-dev openimageio-tools libmetis-dev libgoogle-glog-dev libgtest-dev libgmock-dev \
		libsqlite3-dev libglew-dev libcgal-dev libceres-dev libsuitesparse-dev libcurl4-openssl-dev libssl-dev libmkl-full-dev
	# Ubuntu's OpenImageIO CMake files expect this folder (COLMAP's install notes)
	mkdir -p /usr/include/opencv4
	rm -rf "$build/colmap"
	git clone --depth 1 --branch "$COLMAP_VERSION" https://github.com/colmap/colmap.git "$build/colmap"
	cmake -S "$build/colmap" -B "$build/colmap/build" -GNinja -DCMAKE_BUILD_TYPE=Release \
		-DBLA_VENDOR=Intel10_64lp -DGUI_ENABLED=OFF -DCUDA_ENABLED=$( $gpu && echo ON || echo OFF ) "${cuda_args[@]}"
	ninja -C "$build/colmap/build" -j "$jobs"
	ninja -C "$build/colmap/build" install
	rm -rf "$build/colmap"
fi
/usr/local/bin/colmap help | head -1

if [ ! -x "$tools/openmvs/TextureMesh" ]; then
	echo "== OpenMVS $OPENMVS_VERSION"
	apt-get install -y git cmake ninja-build build-essential curl zip unzip tar \
		autoconf autoconf-archive automake libtool bison gfortran pkg-config nasm \
		libxi-dev libx11-dev libxft-dev libxtst-dev libxext-dev libxrandr-dev libxinerama-dev libxcursor-dev xorg-dev \
		libgl-dev libglu1-mesa-dev libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev
	rm -rf "$build/openmvs"
	git clone --depth 1 --branch "$OPENMVS_VERSION" --recurse-submodules --shallow-submodules \
		https://github.com/cdcseacave/openMVS.git "$build/openmvs"
	# its dependencies (OpenCV, Boost, CGAL …) are built by the bundled vcpkg: most of the time is spent here
	cmake -S "$build/openmvs" -B "$build/openmvs/make" -DCMAKE_BUILD_TYPE=Release \
		-DOpenMVS_USE_CUDA=$( $gpu && echo ON || echo OFF ) "${cuda_args[@]}"
	cmake --build "$build/openmvs/make" -j "$jobs"
	install -d "$tools/openmvs"
	for tool in InterfaceCOLMAP DensifyPointCloud ReconstructMesh RefineMesh TextureMesh; do
		found=$( find "$build/openmvs/make" -type f -name "$tool" -perm -u+x | head -1 )
		[ -n "$found" ] || { echo "OpenMVS build did not produce $tool" >&2; exit 1; }
		install -m 755 "$found" "$tools/openmvs/$tool"
	done
	chown -R pgis:pgis "$tools" 2>/dev/null || true
	rm -rf "$build/openmvs"
fi
ls "$tools/openmvs"
echo 'Reconstruction tools ready.'
