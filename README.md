# Easy TDX 选股台

一个独立的“公式选股”应用，使用 Vue/TypeScript + FastAPI，基于本地通达信 `vipdoc` 日线数据计算三组通达信公式信号。

本项目基于 [`easy-tdx`](https://pypi.org/project/easy-tdx/) 公共 API，但不是 easy-tdx 官方项目；不复制、不修改上游源码。上游版本固定为 `1.20.8`，MIT 相关声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 已实现能力

- 指标一：主力进场、洗盘、主力拉高、出货；
- 指标二：始/终、高饱和、新高突破、短中长成本关系；
- 指标三：准备拉升、压住庄家、建仓区、始/终；
- 页面支持粘贴自定义通达信公式，自动识别 `名称:=数值` 参数；命名布尔输出可作为信号，命名数值输出可用于排序和卖出规则；
- AND、OR、至少满足 N 个；
- 沪深全部 A 股、仅上海、仅深圳、自定义股票列表；
- 排除 ETF、基金、指数、债券和未支持的北京市场文件；
- 后台任务、进度、失败/跳过摘要、结果 JSON/CSV 导出；
- 单股票公式回测：历史区间、买卖信号、全仓/固定股数、佣金/印花税/滑点、成交记录、净值曲线和绩效指标；
- 动态组合回测：从公式选股池按指标排序，按固定槽位等额买入，卖出后自动用排名靠前的候选补位；支持每日/每周/每月刷新、止盈止损、指标阈值和指标比较卖出；
- 策略适配性评估：批量对股票池进行时间顺序的训练/验证/测试回测，按成交样本、期望收益、盈亏比、收益、回撤和稳定性生成透明适配分；
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

浏览器打开 <http://127.0.0.1:5173/formula-screen>。单股回测页面是 <http://127.0.0.1:5173/backtest>，动态组合回测页面是 <http://127.0.0.1:5173/portfolio-backtest>，策略适配性页面是 <http://127.0.0.1:5173/strategy-fitness>；Vite 会把 `/api` 请求代理到 `127.0.0.1:8000`。

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

扫描读取的是已经写入 `.day` 的最新日线；如果桌面端在收盘前已写入今日临时记录，本应用也会在 15:05 前忽略它，不把实时未完成 K 线当成收盘信号。自定义列表每行支持 `SH 600000`、`SZ 000001` 或单独六位代码，空行和 `#` 注释会忽略。

页面的“同步最新行情”按钮会通过 easy-tdx 连接通达信行情服务器，先检查每只股票本地文件的最后日期；没有新完成日线时不会重复下载完整历史，有新数据时才补取并追加到 `.day`。全量同步可能需要较长时间，期间可以查看任务进度。默认不会随容器启动自动全量同步，避免重启时产生不必要的服务器请求。

共享模式下不要让通达信桌面端和容器同时写同一只股票的同一个 `.day` 文件；应用内部已串行化同步与选股任务，跨应用的写入时序仍应由使用者错开。

## 公式回测

页面的“公式回测”针对一只沪深 A 股运行历史日线回测。预置模式可以直接选择买入和卖出输出；自定义模式先粘贴公式并解析，再分别选择两个输出。例如：

```text
N:=5;
买入:CROSS(C,REF(C,N));
卖出:CROSS(REF(C,N),C);
```

日期留空表示使用该股票全部本地历史；公式会先在完整历史上计算，再截取所选区间，因此区间起点不会丢失 `REF`、均线等指标的预热数据。默认信号在下一根 K 线开盘成交，也可以切换到下一根收盘；佣金、最低佣金、印花税和每股滑点均可调整。回测结果包含总收益、年化收益、最大回撤、夏普、胜率、成交记录、资金曲线和最近净值表。

回测使用 easy-tdx 的公开 `BacktestEngine`，结果只保存在当前服务进程内存，服务重启后不会保留。历史回测不代表未来收益，交易成本、涨跌停、流动性和幸存者偏差仍可能使实际结果不同，请勿将回测结果直接视为投资建议。

## 动态组合回测

页面的“组合回测”先对股票池计算公式，在每个刷新日筛选满足选股条件的股票，再按一个指标值排序并填充固定数量的持仓槽位。默认是每个槽位等额、100 股整数下单；持仓不会因为排名变化被强制换仓，只有卖出规则触发后才释放槽位，下一次排名会优先补入空位。默认信号在收盘确认，并在下一根 K 线开盘执行，也可以选择下一根收盘执行。

组合配置还可以开启“适配性过滤”。开启后，系统先为每只股票生成自己的历史交易轨迹，在每个历史调仓日只使用早于当天的已平仓交易和净值，计算滚动适配分；只有达到最低适配分、最少成交数和最大回撤要求的标的才进入当前指标排名。这样不会把完整回测结束后的成绩泄漏到过去的组合决策，最近候选排名中也会显示被过滤的原因。

卖出规则可以组合使用：卖出信号、止损/止盈比例、某个指标达到阈值，或两个指标之间的大小关系。自定义公式解析后，命名条件可用于选股/卖出，命名数值可用于排名和指标卖出。例如：

```text
N:=20;
买入:CROSS(C,MA(C,N));
卖出:CROSS(MA(C,N),C);
强度:C/MA(C,N);
```

该版本是长仓、单一组合、固定槽位的历史模拟，不包含实盘下单、融资融券、涨跌停撮合、分红复权校准或多策略资金隔离。结果同样只保存在当前服务进程内存，服务重启后不会保留。

## 策略适配性评估

页面的“策略适配性”用于回答“哪些标的更适合这套买卖规则”，而不是直接替代组合排序。它会批量读取股票池，每只股票使用单股票单槽位和与组合回测相同的公式、买卖、费用、滑点与下一根 K 线执行语义，然后按共同的历史日期切分为训练、验证和测试三段；三段评估彼此独立从初始资金开始，避免把前一段的持仓状态带入后一段。默认比例为 60% / 20% / 20%，可设置验证/测试期最少成交笔数和测试期最大回撤阈值。

适配分由 8 个可解释检查项组成：验证期和测试期成交数达标、两段期望收益为正、测试期盈亏比大于 1、测试期回撤在阈值内、验证期收益为正、测试期收益为正。只有验证期和测试期样本数达标且至少通过 75% 检查项时标记为“高适配”。建议先用该页面筛出适配性达标的标的，再在“组合回测”中按当前指标值排序和补位。适配性评估是研究报告；不应把使用完整历史计算出的分数直接当作过去交易时点可见的信息。

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
POST /api/v1/backtests
GET  /api/v1/backtests/{job_id}
GET  /api/v1/backtests/{job_id}/results
POST /api/v1/portfolio-backtests
GET  /api/v1/portfolio-backtests/{job_id}
GET  /api/v1/portfolio-backtests/{job_id}/results
POST /api/v1/strategy-fitness
GET  /api/v1/strategy-fitness/{job_id}
GET  /api/v1/strategy-fitness/{job_id}/results
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
