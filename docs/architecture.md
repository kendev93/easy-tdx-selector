# Easy TDX 选股台架构

## 目标

这是一个独立的本地公式选股应用：行情来自通达信 `vipdoc` 的已完成日线 `.day` 文件，公式计算是纯数组计算，扫描和同步任务通过 API 异步轮询，Vue 页面负责配置、行情浏览和结果展示。

```text
Vue/TypeScript 页面
        │ JSON API / 轮询
        ▼
FastAPI 路由与 Pydantic 校验
        │
        ▼
ScreenJobRunner（进程内任务生命周期）
        │
        ▼
ScreenEngine ── FormulaRegistry ── 三组纯公式
        │
        ├── EasyTdxAdapter ── easy_tdx 公共离线 API ── vipdoc/{sh,sz}/lday/*.day
        ├── EasyTdxMarketSync ── easy_tdx 在线 API + .day 写入 API ──┘
        ├── LocalMarketDataService ── 日/月/年聚合 + MA/RSI/MACD ── 本地行情图表
        ├── BacktestService ── easy_tdx BacktestEngine（单股票交易与绩效基础设施）
        ├── PortfolioBacktestService ── 动态排名、槽位补位 ── PerformanceAnalyzer（组合绩效）
        └── StrategyFitnessService ── 时间切分单股回测 ── PortfolioBacktestService（单槽位语义）
```

## 分层规则

- `adapters/` 是行情数据的上游依赖边界，将 `SecurityBar` 转成项目自己的 DataFrame 字段：`date/open/high/low/close/volume/amount`；`backtest/` 只通过 easy-tdx 的公开回测 API 接入交易执行和绩效能力。
- `formulas/` 不发网络请求、不修改传入 DataFrame；每个公式返回 `FormulaResult`，包含中间数组、命名输出、信号数组和最后一根已完成 K 线状态。
- `screening/` 负责 universe、条件合并、单股容错、进度与 JSON/CSV；它不处理 HTTP。
- `web/` 只做请求校验、任务轮询和安全错误响应，不操作上游对象。
- `market_data/` 负责本地行情文件的分页摘要、周期聚合和常用技术指标序列，不修改行情文件。
- `web-ui/` 只做表单、请求状态、K 线图和结果表，不计算通达信公式。

页面保留“预置指标”和“自定义公式”两种模式。自定义模式先将公式提交到 `/parse`：解析器只接受白名单 AST 节点和数组函数，不执行用户 Python；`名称:=数值` 被识别为参数，`名称:表达式` 被识别为可选输出。扫描请求携带原始公式、参数覆盖值和选中的 `custom.*` 输出。

行情同步复用同一个 `ScreenJobRunner` 生命周期：`EasyTdxMarketSync` 通过公开的 `TdxClient.get_security_list_all()`、`get_security_bars()` 获取沪深 A 股日线，再通过 `easy_tdx.offline.find_daily_bar_file()` 和 `sync_daily_bars_from_security_bars()` 写回目标 `vipdoc`。默认目标是容器内 `/data/vipdoc`，因此 named volume 模式和本地 bind 模式都能使用同一套同步逻辑。

`LocalMarketDataService` 通过 `EasyTdxAdapter` 读取本地 `.day` 文件；列表接口只解析当前分页的文件，图表接口对单只股票先计算完整历史的 MA5/10/20/60、RSI14 和 MACD，再按日线、月线或年线聚合并截取日期范围。它只读文件，不参与同步写入，指标也不依赖线上行情。

`BacktestService` 先在完整本地历史上计算预置或自定义公式的信号，再按日期区间截取信号和 K 线，使用 `easy_tdx.backtest.BacktestEngine` 的公开交易策略、订单撮合、持仓追踪和绩效分析能力。页面明确选择一个买入输出和一个卖出输出；持仓时只响应卖出信号，空仓时只响应买入信号，同一根 K 线同时满足时优先处理当前持仓的卖出逻辑。

`PortfolioBacktestService` 在相同的规范化日线和公式输出之上维护一个固定槽位的长仓组合。每个刷新日先筛选选股信号，再按指标值排序；已有持仓保留，卖出信号、止盈止损、指标阈值或指标比较触发后，下一根 K 线执行卖出并释放槽位，排名靠前的未持仓候选随后进入空槽。默认每个槽位使用组合总资产的等额预算并按 100 股整数下单。该动态候选轮换语义不是上游静态 `PortfolioBacktestEngine` 的能力，因此由本项目服务实现；绩效汇总复用 easy-tdx 的公开 `PerformanceAnalyzer`。

组合服务可选启用 `RollingFitnessFilter`。它先用相同单股票交易规则为每个上下文生成一次历史交易轨迹，再在候选刷新日通过二分边界读取严格早于当天的累计已平仓交易和净值前缀，计算成交数、期望收益、盈亏比、总收益和最大回撤五项检查。适配分过滤发生在当前指标排序之前，排名事件会保留被排除候选及原因；未启用时不增加这次历史模拟开销。

`StrategyFitnessService` 先一次性缓存股票池行情，再以组合服务的单股票单槽位入口分别运行训练、验证和测试窗口，避免复制另一套买卖逻辑。三段窗口使用全市场共同的实际交易日期边界，公式仍在完整单股历史上计算后再截取窗口，保证均线和 `REF` 预热数据不丢失；每段独立从初始资金和空仓开始。评估分数只由验证/测试样本数、期望收益、盈亏比、收益和回撤等透明检查项组成；它不自动优化参数，也不把完整历史分数直接注入历史交易。

## 公式一致性约束

- 除零返回 `NaN`，不让一个坏分母终止全市场任务。
- 公式一保留 `MIN(HIGH-VAR1,0)` 的负分母语义。
- 公式二保留缺失的 `REF(A,19)`，直接使用 `REF(A,20)`；`W3` 的两个相同 IF 分支用动态 REF 等价实现。
- 公式三保留 `SMA(...,3.2,1)`。
- 首段 `REF`/滚动 NaN 不会被伪造为信号；最少历史不足的股票记为 `skipped`。
- 上海时间 15:05 前，适配器会过滤 `.day` 中可能存在的今日临时记录；收盘后才允许它成为最后一根信号 K 线。
- 计算只消费 DataFrame 中最后一根已完成日线，不使用未来行，也不在共享 frame 上原地修改。

## 扫描和任务

`ScanConfig` 通过 registry 验证 signal id，再由 `ScreenEngine` 按公式去重计算。`all`、`any` 和 `at_least` 只针对用户已选择的信号做合并。默认 worker 为 1；默认适配器在 `workers > 1` 时使用 `ProcessPoolExecutor`，注入测试适配器则退化为线程池以保持可测试性。每只股票异常只增加失败计数并继续扫描。

`ScreenJobRunner` 是本项目自己的任务生命周期组件：状态保留在内存，重启后任务丢失，结果查询接口返回 409/404/500 等语义状态。它没有引入 Redis/Celery；部署为单机本地工具时足够。未来如果需要跨进程持久化，应替换 runner，而不是把任务状态塞进路由。

同步与选股任务在应用内共用单线程队列，避免本项目自己的读写重叠；通达信桌面端不共享这个 Python 锁，因此共享 bind 模式下仍应避开桌面端正在更新同一 `.day` 文件的时段。

## API

- `GET /api/v1/formula-screen/metadata`
- `POST /api/v1/formula-screen/parse`
- `POST /api/v1/formula-screen/jobs`（兼容别名 `/scan`）
- `GET /api/v1/formula-screen/jobs/{job_id}`
- `GET /api/v1/formula-screen/jobs/{job_id}/results`
- `GET /api/v1/formula-screen/jobs/{job_id}/export.json`
- `GET /api/v1/formula-screen/jobs/{job_id}/export.csv`
- `POST /api/v1/market-data/sync`
- `GET /api/v1/market-data/sync/jobs/{job_id}`
- `GET /api/v1/market-data/local/instruments`
- `GET /api/v1/market-data/local/{market}/{code}/bars`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/{job_id}`
- `GET /api/v1/backtests/{job_id}/results`
- `POST /api/v1/portfolio-backtests`
- `GET /api/v1/portfolio-backtests/{job_id}`
- `GET /api/v1/portfolio-backtests/{job_id}/results`
- `POST /api/v1/strategy-fitness`
- `GET /api/v1/strategy-fitness/{job_id}`
- `GET /api/v1/strategy-fitness/{job_id}/results`

响应使用 `data`/`meta` 成功 envelope 和 `error.code/message` 错误 envelope；未处理异常写服务端日志但不会向前端发送 traceback。
