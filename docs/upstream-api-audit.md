# easy_tdx 上游 API 审计

审计日期：2026-08-24  
审计对象：本机已下载的 `easy_tdx` 源码 checkout  
版本：`1.20.8`

本项目是独立的 Easy TDX 选股台，不是 easy_tdx 官方项目，也不复制或修改上游源码。正式运行依赖 `easy-tdx==1.20.8`；本报告记录的是本版本实际检查过的 API 和兼容边界。

## 1. 版本、依赖和入口

上游 `pyproject.toml` 当前声明：

- 包名：`easy-tdx`；版本：`1.20.8`；Python `>=3.10`；
- 核心依赖：`pandas>=2.0,<3`、`tzdata>=2024.1`、`click>=8.0,<9`；
- `web` 可选依赖提供 FastAPI/Uvicorn；`science` 可选依赖提供 SciPy；
- `easy-tdx` CLI 入口为 `easy_tdx.cli:cli`。

稳定调用的公开入口包括：

```python
from easy_tdx import KlineCategory, Market, TdxClient
from easy_tdx.offline import find_daily_bar_file, read_daily_bars, resolve_vipdoc
from easy_tdx import MyTT
```

同步行情客户端公开提供 `TdxClient.connect()`、`close()`、`get_security_count()`、`get_security_list()`、`get_security_list_all()` 和 `get_security_bars()`；异步版本对应 `AsyncTdxClient`。本项目的行情同步服务使用同步客户端获取日线，公式扫描仍然读取已经落地的本地文件。

## 2. K 线字段和来源

`TdxClient.get_security_bars(market, code, category, start, count=800, *, bar_time="start")` 返回 pandas DataFrame。`SecurityBar` 的字段为：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `open`, `close`, `high`, `low` | `float` | 价格 |
| `vol` | `float` | 成交量，A 股 `.day` 读取后为股 |
| `amount` | `float` | 成交额，元 |
| `year`, `month`, `day`, `hour`, `minute` | `int` | 时间组成字段，日线的时分为 0 |
| `datetime_str` | `str` 属性 | `YYYY-MM-DD HH:MM` |

日线请求最多 800 根/次，`start=0` 表示最新分页。分钟线的 `bar_time` 对齐参数对日线不生效。

## 3. `.day` 离线文件

已确认支持本地通达信日线文件：

```text
vipdoc/{sh,sz}/lday/{exchange}{code}.day
```

公开调用为 `resolve_vipdoc()`、`find_daily_bar_file(market, code, vipdoc=None)` 和 `read_daily_bars(filepath)`；写入侧还提供 `append_daily_bars()` 与 `sync_daily_bars_from_security_bars()`。文件读取/写入使用 32 字节小端记录：`YYYYMMDD`、开盘、最高、最低、收盘、成交额、成交量及保留字段。上游根据文件名区分证券类型并使用价格/数量系数；本项目不重新实现该二进制编解码，而把上游的 `SecurityBar` 转换成项目自己的 DataFrame，写入时使用 A 股系数 `price_coeff=0.01`、`vol_coeff=0.01`。

本应用自己的 universe 过滤器只允许：

- 上海 `60xxxx`、`68xxxx`；
- 深圳 `00xxxx`、`30xxxx`。

因此 ETF、基金、指数、债券和北京市场不会被默默当成 A 股扫描。当前版本页面明确显示只支持 SH/SZ A 股。

## 4. MyTT 技术指标 API

上游 `easy_tdx.MyTT` 提供本项目需要的 `REF`、`SMA`、`EMA`、`LLV`、`HHV`、`BARSLAST`、`COUNT`、`CROSS` 等数组函数。其实现基于 NumPy/pandas，函数返回与输入等长的 NumPy 数组；`REF` 首段产生 `NaN`，滚动窗口函数在预热段产生 `NaN`。

本项目的 `selector_app/formulas/` 只把这些函数作为计算依赖，不把行情请求放进公式层。除零由本项目 `safe_divide()` 统一处理为 `NaN`，负分母保持符号；数据不足则被标记为 `skipped`。

## 5. `SignalScanner`、Web 和 CLI 能力

`from easy_tdx.screen import SignalScanner` 确实可直接调用，但它的契约是：接收 `Strategy` 子类，在本地 `.day` 文件上提取策略买入信号，并输出简化的 `ScanResult(code, market, signal_date, last_close)`。它不支持本需求的公式一/二/三信号注册、AND/OR/至少 N 个条件合并、指标值回传，因此本项目没有强行复用它。

上游已有 FastAPI 路由、`easy-tdx` CLI 和一个用于回测的进程内任务执行器。它们分别属于上游应用层；本项目的公式任务需要另一套结果字段和本地公式 registry，所以只在本项目内部提供轻量任务执行器，并不让业务代码依赖上游 `easy_tdx.web.*` 内部模块。本项目的 `EasyTdxMarketSync` 已使用上游在线 `get_security_list_all()`/`get_security_bars()` 加上 `.day` 写入 API；公式选股仍只消费本地已经完成的日线。

## 6. 本项目适配器和内部实现边界

唯一上游集成边界是 `selector_app/adapters/easy_tdx_adapter.py`，目前调用：

- `easy_tdx.Market`；
- `easy_tdx.offline.resolve_vipdoc`；
- `easy_tdx.offline.find_daily_bar_file`；
- `easy_tdx.offline.read_daily_bars`；
- `easy_tdx.offline.get_last_bar_date`；
- `easy_tdx.offline.sync_daily_bars_from_security_bars`；
- `easy_tdx.TdxClient`、`Market`、`KlineCategory`、`SecurityBar`；
- `easy_tdx.MyTT`（由公式层调用，但仍是上游公开模块）。

没有使用上游的 `_detect_security_type`、协议 command、transport、`easy_tdx.web` 路由或 `easy_tdx.screen.scanner` 私有实现。上游的 `SecurityBar` 只在适配器中被转换和写入，不会进入公式或 Web 路由。

## 7. 升级兼容风险

升级 `easy-tdx` 时重点检查：

1. `SecurityBar` 字段名/单位、`.day` 价格和成交量系数；
2. `read_daily_bars`、`find_daily_bar_file`、`resolve_vipdoc` 是否仍从 `easy_tdx.offline` 导出；
3. `Market.SH/SZ` 与 `KlineCategory.DAY` 的枚举值；
4. MyTT 中移动平均、交叉和滚动函数的 NaN/预热语义；
5. pandas 版本上限与 Python 版本兼容性；
6. 上游 CLI/Web/`SignalScanner` 的行为变化（本项目不把它们当作业务契约）。

升级接受条件：修改 `pyproject.toml` 和 `requirements.lock` 后，重新审计本文件，运行新增 Python 测试、API 测试、前端 typecheck/build 和 E2E；只有全部通过才接受版本变更。

## 8. 安装策略

开发/生产均使用版本依赖，不提交本机绝对路径：

```bash
python -m pip install -r requirements.lock
python -m pip install -e ".[dev]"
```

如果需要用源码 checkout 做 API 验证，应在独立虚拟环境中先构建上游自身的前端产物，再执行 `pip install -e <easy_tdx-checkout>`；不要把 `file:///...` 写进本项目的 `pyproject.toml` 或 lock 文件。CI 使用 PyPI 版本，测试夹具仅在本地存在并列源码时优先导入源码，便于发现上游漂移。
