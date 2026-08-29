#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

git -C "$REPO_ROOT" config core.hooksPath .githooks
printf '%s\n' '已启用项目 Git Hooks：提交前检查（跳过 Docker），推送前完整检查。'
