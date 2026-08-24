# Easy TDX 选股台架构

## 目标

这是一个独立的本地公式选股应用：行情来自通达信 `vipdoc` 的已完成日线 `.day` 文件，公式计算是纯数组计算，扫描任务通过 API 异步轮询，Vue 页面负责配置和展示。

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
        ▼
EasyTdxAdapter ── easy_tdx 公共离线 API ── vipdoc/{sh,sz}/lday/*.day
```

## 分层规则

- `adapters/` 是唯一的上游依赖边界，将 `SecurityBar` 转成项目自己的 DataFrame 字段：`date/open/high/low/close/volume/amount`。
- `formulas/` 不发网络请求、不修改传入 DataFrame；每个公式返回 `FormulaResult`，包含中间数组、命名输出、信号数组和最后一根已完成 K 线状态。
- `screening/` 负责 universe、条件合并、单股容错、进度与 JSON/CSV；它不处理 HTTP。
- `web/` 只做请求校验、任务轮询和安全错误响应，不操作上游对象。
- `web-ui/` 只做表单、请求状态和结果表，不计算公式。

页面保留“预置指标”和“自定义公式”两种模式。自定义模式先将公式提交到 `/parse`：解析器只接受白名单 AST 节点和数组函数，不执行用户 Python；`名称:=数值` 被识别为参数，`名称:表达式` 被识别为可选输出。扫描请求携带原始公式、参数覆盖值和选中的 `custom.*` 输出。

## 公式一致性约束

- 除零返回 `NaN`，不让一个坏分母终止全市场任务。
- 公式一保留 `MIN(HIGH-VAR1,0)` 的负分母语义。
- 公式二保留缺失的 `REF(A,19)`，直接使用 `REF(A,20)`；`W3` 的两个相同 IF 分支用动态 REF 等价实现。
- 公式三保留 `SMA(...,3.2,1)`。
- 首段 `REF`/滚动 NaN 不会被伪造为信号；最少历史不足的股票记为 `skipped`。
- 计算只消费 DataFrame 中最后一根已完成日线，不使用未来行，也不在共享 frame 上原地修改。

## 扫描和任务

`ScanConfig` 通过 registry 验证 signal id，再由 `ScreenEngine` 按公式去重计算。`all`、`any` 和 `at_least` 只针对用户已选择的信号做合并。默认 worker 为 1；默认适配器在 `workers > 1` 时使用 `ProcessPoolExecutor`，注入测试适配器则退化为线程池以保持可测试性。每只股票异常只增加失败计数并继续扫描。

`ScreenJobRunner` 是本项目自己的任务生命周期组件：状态保留在内存，重启后任务丢失，结果查询接口返回 409/404/500 等语义状态。它没有引入 Redis/Celery；部署为单机本地工具时足够。未来如果需要跨进程持久化，应替换 runner，而不是把任务状态塞进路由。

## API

- `GET /api/v1/formula-screen/metadata`
- `POST /api/v1/formula-screen/parse`
- `POST /api/v1/formula-screen/jobs`（兼容别名 `/scan`）
- `GET /api/v1/formula-screen/jobs/{job_id}`
- `GET /api/v1/formula-screen/jobs/{job_id}/results`
- `GET /api/v1/formula-screen/jobs/{job_id}/export.json`
- `GET /api/v1/formula-screen/jobs/{job_id}/export.csv`

响应使用 `data`/`meta` 成功 envelope 和 `error.code/message` 错误 envelope；未处理异常写服务端日志但不会向前端发送 traceback。
