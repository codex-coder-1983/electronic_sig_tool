# build.sh
#!/usr/bin/env bash

apt-get update && apt-get install -y \
  libglib2.0-0 \
  libxext6 \
  libsm6 \
  libxrender1 \
  libpoppler-cpp-dev
