from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

# 本地开发时优先使用与本项目并列的上游源码；正式安装仍由 pyproject.toml
# 中的 easy-tdx PyPI 依赖负责。这里不把开发机绝对路径写入正式配置。
_workspace_parent = Path(__file__).resolve().parents[2]
_local_upstream_src = _workspace_parent / "easy_tdx" / "src"
if _local_upstream_src.is_dir():
    sys.path.insert(0, str(_local_upstream_src))

# easy_tdx's source package resolves __version__ through distribution metadata.
# The upstream repository cannot be installed editable until its optional
# frontend dist is built, so provide the audited source version only inside the
# test process. Production installs use normal package metadata.
try:
    importlib.metadata.version("easy-tdx")
except importlib.metadata.PackageNotFoundError:
    _real_version = importlib.metadata.version

    def _local_version(name: str) -> str:
        if name == "easy-tdx":
            return "1.20.8"
        return _real_version(name)

    importlib.metadata.version = _local_version  # type: ignore[assignment]
