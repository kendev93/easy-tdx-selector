#!/bin/sh

set -eu

if [ "$#" -ne 1 ]; then
  echo "用法: sh scripts/import_vipdoc.sh /path/to/vipdoc" >&2
  exit 2
fi

SOURCE_PATH=$1
if [ ! -d "$SOURCE_PATH" ]; then
  echo "vipdoc 目录不存在: $SOURCE_PATH" >&2
  exit 1
fi

VOLUME_NAME=easy_tdx_selector_vipdoc
docker volume create "$VOLUME_NAME" >/dev/null
docker run --rm \
  --mount "type=bind,src=$SOURCE_PATH,dst=/source,readonly" \
  --mount "type=volume,src=$VOLUME_NAME,dst=/data" \
  alpine:3.20 \
  sh -c 'cp -a /source/. /data/'

echo "vipdoc 已导入 Docker volume: $VOLUME_NAME"
