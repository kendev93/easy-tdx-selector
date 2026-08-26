# Easy TDX 选股台

一个独立的“公式选股”应用，使用 Vue/TypeScript + FastAPI，基于本地通达信 `vipdoc` 日线数据计算三组通达信公式信号。

本项目基于 [`easy-tdx`](https://pypi.org/project/easy-tdx/) 公共 API，但不是 easy-tdx 官方项目；不复制、不修改上游源码。上游版本固定为 `1.20.8`，MIT 相关声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 已实现能力

- 指标一：主力进场、洗盘、主力拉高、出货；
- 指标二：始/终、高饱和、新高突破、短中长成本关系；
- 指标三：准备拉升、压住庄家、建仓区、始/终；
- 页面支持粘贴自定义通达信公式，自动识别 `名称:=数值` 参数，并将命名输出转换为可选信号；
- AND、OR、至少满足 N 个；
- 沪深全部 A 股、仅上海、仅深圳、自定义股票列表；
- 排除 ETF、基金、指数、债券和未支持的北京市场文件；
- 后台任务、进度、失败/跳过摘要、结果 JSON/CSV 导出；
- 一键同步通达信最新日线到共享 `vipdoc`，已存在日期自动跳过；
- 公式层安全除零、数据不足跳过、无未来数据；
- Python 单元/集成测试、Vue 单元测试和 Playwright E2E 流程。

首次进入页面时，预置模式会默认选中“准备拉升”和“建仓区”，Docker 模式自动填入 `/data/vipdoc`；市场范围、条件组合、并发和周期收在“高级设置”中。页面会在浏览器本地记住上次配置，不会上传这些配置。

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

## Docker Compose 启动

如果不想在宿主机安装 Python、easy-tdx 或 Node.js，可以直接使用 Docker：

```bash
cd easy-tdx-selector
docker compose up --build -d
```

这样克隆项目后即可直接启动页面和 API。Docker 会自动创建名为 `easy_tdx_selector_vipdoc` 的命名卷；如果卷还没有行情文件，页面仍然可以打开、解析自定义公式和配置扫描任务，但扫描结果会为空。

如果本机已经安装通达信，推荐直接共享桌面端的 `vipdoc` 目录，而不是复制一份：

```bash
HOST_VIPDOC_PATH=/你的通达信目录/vipdoc \
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local-vipdoc.yml \
  up --build -d
```

这种模式将桌面端目录直接挂载到容器，桌面端更新行情后容器立即可见；页面点击“同步最新行情”时，容器也会把新 `.day` 数据写回这个目录。页面的 vipdoc 输入框填写：

```text
/data/vipdoc
```

无通达信模式使用持久化 named volume；普通 `docker compose down` 或删除容器不会删除数据。共享模式使用宿主机原目录，容器只通过同步服务写入兼容的 `.day` 文件，不会删除宿主机行情文件。不要使用 `docker compose down -v` 或执行 `docker volume rm easy_tdx_selector_vipdoc`，除非确认要删除无通达信模式下的行情数据。查看卷使用 `docker volume inspect easy_tdx_selector_vipdoc`，查看状态使用 `docker compose ps`，停止使用 `docker compose down`。`WEB_PORT` 和 `API_PORT` 仍可通过 `.env` 修改。

如果只想把已有数据复制进 Docker，而不持续共享桌面端目录，仍可使用：

```bash
sh scripts/import_vipdoc.sh /你的通达信目录/vipdoc
```

## 配置 vipdoc

页面中的 `vipdoc 数据目录` 应指向包含下列目录的通达信数据目录：

```text
vipdoc/
├── sh/lday/sh600000.day
└── sz/lday/sz000001.day
```

扫描读取的是已经写入 `.day` 的最新日线；本应用不会把实时未完成 K 线当成收盘信号。自定义列表每行支持 `SH 600000`、`SZ 000001` 或单独六位代码，空行和 `#` 注释会忽略。

页面的“同步最新行情”按钮会通过 easy-tdx 连接通达信行情服务器，先检查每只股票本地文件的最后日期；没有新完成日线时不会重复下载完整历史，有新数据时才补取并追加到 `.day`。全量同步可能需要较长时间，期间可以查看任务进度。

## API 快速说明

```text
GET  /api/v1/formula-screen/metadata
POST /api/v1/formula-screen/parse
POST /api/v1/formula-screen/jobs
GET  /api/v1/formula-screen/jobs/{job_id}
GET  /api/v1/formula-screen/jobs/{job_id}/results
GET  /api/v1/formula-screen/jobs/{job_id}/export.json
GET  /api/v1/formula-screen/jobs/{job_id}/export.csv
POST /api/v1/market-data/sync
GET  /api/v1/market-data/sync/jobs/{job_id}
```

提交任务必须至少选择一个信号；`at_least` 必须给出不超过所选信号数的 `minimum_matches`。自定义公式先调用 `/parse`，解析成功后再提交 `/jobs`；显式常量赋值如 `N:=5` 会生成参数控件，`SIGNAL:...` 会生成输出信号。完整 API 结构见 [docs/architecture.md](docs/architecture.md)。

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
