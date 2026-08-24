# Easy TDX 选股台

一个独立的“公式选股”应用，使用 Vue/TypeScript + FastAPI，基于本地通达信 `vipdoc` 日线数据计算三组通达信公式信号。

本项目基于 [`easy-tdx`](https://pypi.org/project/easy-tdx/) 公共 API，但不是 easy-tdx 官方项目；不复制、不修改上游源码。上游版本固定为 `1.20.8`，MIT 相关声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 已实现能力

- 指标一：主力进场、洗盘、主力拉高、出货；
- 指标二：始/终、高饱和、新高突破、短中长成本关系；
- 指标三：准备拉升、压住庄家、建仓区、始/终；
- AND、OR、至少满足 N 个；
- 沪深全部 A 股、仅上海、仅深圳、自定义股票列表；
- 排除 ETF、基金、指数、债券和未支持的北京市场文件；
- 后台任务、进度、失败/跳过摘要、结果 JSON/CSV 导出；
- 公式层安全除零、数据不足跳过、无未来数据；
- Python 单元/集成测试、Vue 单元测试和 Playwright E2E 流程。

## 启动

要求 Python 3.10–3.13、Node.js 20+。推荐创建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.lock
python -m pip install -e ".[dev]"
```

启动后端：

```bash
uvicorn selector_app.web.app:app --reload --host 127.0.0.1 --port 8000
# 或：easy-tdx-selector --reload
```

启动前端开发服务器：

```bash
cd web-ui
npm install
npm run dev
```

浏览器打开 <http://127.0.0.1:5173/formula-screen>。Vite 会把 `/api` 请求代理到 `127.0.0.1:8000`。

## 配置 vipdoc

页面中的 `vipdoc 数据目录` 应指向包含下列目录的通达信数据目录：

```text
vipdoc/
├── sh/lday/sh600000.day
└── sz/lday/sz000001.day
```

扫描读取的是已经写入 `.day` 的最新日线；本应用不会把实时未完成 K 线当成收盘信号。自定义列表每行支持 `SH 600000`、`SZ 000001` 或单独六位代码，空行和 `#` 注释会忽略。

## API 快速说明

```text
GET  /api/v1/formula-screen/metadata
POST /api/v1/formula-screen/jobs
GET  /api/v1/formula-screen/jobs/{job_id}
GET  /api/v1/formula-screen/jobs/{job_id}/results
GET  /api/v1/formula-screen/jobs/{job_id}/export.json
GET  /api/v1/formula-screen/jobs/{job_id}/export.csv
```

提交任务必须至少选择一个信号；`at_least` 必须给出不超过所选信号数的 `minimum_matches`。完整 API 结构见 [docs/architecture.md](docs/architecture.md)。

## 测试和质量检查

后端：

```bash
PYTHONPATH=. pytest --cov=selector_app --cov-report=term-missing
ruff check selector_app tests
mypy selector_app
```

前端：

```bash
cd web-ui
npm test
npm run test:coverage
npm run typecheck
npm run build
npm run e2e
```

E2E 测试通过 Playwright 路由模拟 API，不需要真实 vipdoc；真实页面运行需要同时启动后端和前端。

## easy-tdx 升级流程

1. 修改 `pyproject.toml` 和 `requirements.lock` 中的 `easy-tdx` 版本；
2. 阅读并更新 [docs/upstream-api-audit.md](docs/upstream-api-audit.md)；
3. 安装新版本，运行公式单元测试和 API 集成测试；
4. 运行前端 typecheck/build 及 E2E；
5. 检查 `git diff`，确认没有绝对路径依赖、密钥、临时文件，也没有修改上游 checkout。

## 许可证边界

上游 `easy-tdx` 继续按其 MIT 许可证作为独立依赖分发；本项目自己的业务代码与上游分开，具体授权可由项目维护者另行确定。请随本项目分发 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
