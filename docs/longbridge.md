# 长桥官方 SDK：行情与基本面

本分支基于 AKShare 1.19.1，通过官方 Python 包 `longbridge` 接入行情、基本面、市场数据和财经日历。SDK 底层是官方 Rust 实现；不需要自行实现签名、协议或下载 Rust 编译器。官方源码与 SDK 不复制到 AKShare 包内，由可选依赖安装。

- 官方源码：<https://github.com/longbridge/openapi>，Python 位于 `python/`，Rust 位于 `rust/`。
- Python 参考：<https://longbridge.github.io/openapi/python/reference_all/>
- 行情概览：<https://open.longbridge.com/zh-CN/docs/quote/overview>
- 基本面概览：<https://open.longbridge.com/zh-CN/docs/fundamental/overview>
- Terminal：<https://github.com/longbridge/longbridge-terminal> 是另一个可交互的命令行客户端，适合人工查询；本项目直接调用 SDK，保留 Python 返回类型与批量查询能力。

## 安装与凭据

在本仓库目录执行：

```powershell
python -m pip install -e ".[quotes]"
```

默认读取 `C:\githubProject\.env-lark` 中的三个长桥字段。不会修改该文件，也不会把飞书凭据加载到进程环境。

| 文件内已有字段 | 对应长桥标准字段 |
| --- | --- |
| `APPKEY` | `LONGBRIDGE_APP_KEY` |
| `AppSecretLong` | `LONGBRIDGE_APP_SECRET` |
| `AccessToken` | `LONGBRIDGE_ACCESS_TOKEN` |

`APPSecret` 是其他服务的字段，不用于长桥。支持标准 `LONGBRIDGE_*` 和旧的 `LONGPORT_*` 三项环境变量，环境变量优先于文件。通用别名仅在选定文件内识别。文件内容不做 `${...}` 替换，支持 UTF-8 BOM。

其他机器可通过环境变量指定文件：

```powershell
$env:AKSHARE_QUOTE_ENV_FILE = 'D:\private\longbridge.env'
```

Python 可指定 `LongbridgeClient(env_file=...)`。不要把真实凭据写入代码、命令行参数、报告或 Git；`.env`、`.env.*` 已忽略。

## 四时段报价

```powershell
# 当前时段；默认使用已配置的长桥 OpenAPI
python -m stock_alert.us_quotes TSM,MU,NVDA

# 四个时段分别展示最后可用的记录
python -m stock_alert.us_quotes TSM --all-sessions

# 明确只使用官方接口；缺权限或连接失败时不替换成公开源
python -m stock_alert.us_quotes TSM --source longbridge-api --all-sessions

# 上一个夜盘的最后记录，非夜盘期间会标记 historical
python -m stock_alert.us_quotes TSM --session overnight

# 不传代码，批量获取内置 30 只股票和 ETF
python -m stock_alert.us_quotes --source longbridge-api

# JSON 和完整时段快照
python -m stock_alert.us_quotes TSM --format json
python -m stock_alert.us_quotes --all-sessions --output stock-alert/reports/quotes.json
```

Windows 可以双击 `stock-alert/query-us-stocks.cmd`，优先使用仓库 `.venv`，不存在时使用当前 Python。

```python
from stock_alert.us_quotes import fetch_us_quote, fetch_us_quotes
from stock_alert.market_quotes import fetch_market_snapshot, fetch_market_snapshots

current = fetch_us_quote("TSM")
print(current.payload())
quotes = fetch_us_quotes(["TSM", "MU", "NVDA"])
snapshot = fetch_market_snapshot("TSM", source="longbridge-api", include_sessions=True)
print(snapshot["quotes"]["overnight"])
batch = fetch_market_snapshots(source="longbridge-api", include_sessions=True)
```

一次官方报价请求支持最多 500 个代码；默认 30 只合并成一次请求，超过 500 自动分批。不会为了查询一只股票扫描整个市场。批量顺序去重并保留输入顺序；官方返回缺项时，只对缺项使用公开备用源。拉取使用 SDK HTTP 传输，自动开启 `enable_overnight=True`。

| `source` 参数 | 行为 |
| --- | --- |
| `auto` | 配置凭据时优先官方 SDK，错误/缺项/过期时尝试公开源；无凭据使用公开源 |
| `longbridge-api` | 只调用官方 SDK，结果来源标记 `longbridge-openapi` |
| `longbridge` | 长桥公开网页，来源 `longbridge-public` |
| `akshare` | AKShare 新浪单代码接口，来源 `akshare-sina` |
| `nasdaq` | Nasdaq 公开接口，来源 `nasdaq-public` |

备用源不保证四个时段完整覆盖。官方错误会保留在 `attempts`，不同来源有明确标签。

`premarket`、`regular`、`after_hours`、`overnight` 分别来自官方响应的 `pre_market_quote`、常规字段、`post_market_quote`、`overnight_quote`。每条记录包含价格、源时间、成交量、前收盘、可用的开高低与成交额。盘前盘后 SDK 本身没有 open 时，返回空值。不会用收盘价填补缺失夜盘。

`quote_time` 为美东时间，`quote_time_shanghai` 为北京时间，`fetched_at` 为请求结果取得时间。SDK 的无时区 datetime 按机器本地时间转换，不能直接当成 UTC。交易时段使用 XNYS 日历估计并区分假日、提前收盘和周末；证券非正常交易状态标记停牌，公开源提供的状态优先于估计。供应商非标准的临时交易安排仍可能需要核实。

状态包括 `current`、`historical`、`stale`、`unavailable`、`closed`。默认新鲜度阈值 1200 秒，可用 `--max-age` 调整；它表示最后成交时间是否足够近，不代表已验证完整实时推送。简短 Python/JSON 当前价入口会抑制过期价格；完整快照保留价格及其状态。单代码当前查询有 5 秒进程内缓存，`--no-cache` 可跳过。批量官方查询每次获取新批次。

## 行情 SDK 的其余能力

`LongbridgeClient` 共用凭据创建四类原生数据上下文：`quotes`、`fundamentals`、`markets`、`calendars`。保留安装版本的全部方法、参数、枚举和原生返回值。

```python
from longbridge.openapi import AdjustType, Period
from stock_alert.longbridge_sdk import LongbridgeClient, to_jsonable

client = LongbridgeClient(timeout=10)
info = client.query("quote", "static_info", ["TSM.US"])
depth = client.query("quote", "depth", "TSM.US")
trades = client.query("quote", "trades", "TSM.US", count=10)
lines = client.query("quote", "intraday", "TSM.US")
bars = client.query("quote", "candlesticks", "TSM.US",
                    period=Period.Day, count=10, adjust_type=AdjustType.NoAdjust)
print(to_jsonable(bars))
# 原生上下文（直接 SDK 调用，不经过 query 的超时/错误包装）
dates = client.quotes.option_chain_expiry_date_list("TSM.US")
```

| 行情概览能力 | 对应原生 `QuoteContext` 方法 |
| --- | --- |
| 基础信息、报价 | `static_info`、`quote` |
| 期权、轮证报价 | `option_quote`、`warrant_quote` |
| 盘口、经纪队列、席位 | `depth`、`brokers`、`participants` |
| 逐笔、分时、K 线 | `trades`、`intraday`、`candlesticks` |
| 历史 K 线 | `history_candlesticks_by_date`、`history_candlesticks_by_offset` |
| 期权链 | `option_chain_expiry_date_list`、`option_chain_info_by_date` |
| 轮证发行商、筛选 | `warrant_issuers`、`warrant_list` |
| 交易时段、交易日 | `trading_session`、`trading_days` |
| 资金流向、分布、指标 | `capital_flow`、`capital_distribution`、`calc_indexes` |
| 标的列表、自选列表 | `security_list`、`watchlist` |
| 订阅、取消、当前订阅 | `subscribe`、`unsubscribe`、`subscriptions` |
| 推送回调 | `set_on_quote`、`set_on_depth`、`set_on_brokers`、`set_on_trades` |
| 自选分组管理 | 原生 `create_watchlist_group`、`delete_watchlist_group`、`update_watchlist_group`；仅供显式调用 |

HTTP `query` 使用异步 SDK 并限制超时。推送/实时缓存必须在持久的 WebSocket 上下文中使用：

```python
import time
from longbridge.openapi import SubType
from stock_alert.longbridge_sdk import LongbridgeClient

stream = LongbridgeClient().streaming_quotes()
stream.set_on_quote(lambda symbol, event: print(symbol, event))
stream.subscribe(["TSM.US"], [SubType.Quote])
try:
    time.sleep(30)
finally:
    stream.unsubscribe(["TSM.US"], [SubType.Quote])
```

推送依赖网络 WSS 连通性与对应行情权限。期权、港股深度、经纪队列等可能需要额外权限；接入入口可调用不等于本账户全部接口均已获权。自选分组变更不是自动执行的接入步骤。测试未调用交易 API。

## 基本面、市场和财经日历

网页概览的部分方法名不同于 SDK 5.2.2 的实际名字。`query` 接受下表的概览名，也接受 SDK 原名；直接使用原生上下文时按 SDK 原名调用。

| 分组 | 概览名 | SDK 方法/分类 |
| --- | --- | --- |
| fundamental | `company_profile` | `company` |
| fundamental | `financial_report` | `financial_report` |
| fundamental | `valuations` | `valuation` |
| fundamental | `dividends` | `dividend` |
| fundamental | `fund_holdings` | `fund_holder` |
| fundamental | `shareholders` | `shareholder` |
| fundamental | `executives` | `executive` |
| fundamental | `corp_action` | `corp_action` |
| market | `market_status` | `market_status` |
| market | `trading_stats` | `trade_stats` |
| market | `index_components` | `constituent` |
| market | `ah_premium` | `ah_premium` |
| market | `broker_positions` | `broker_holding` |
| market | `unusual_items` | `anomaly` |
| calendar | `earnings_calendar` | `finance_calendar(CalendarCategory.Report, ...)` |
| calendar | `dividend_calendar` | 分类 `Dividend` |
| calendar | `ipo_calendar` | 分类 `Ipo` |
| calendar | `split_calendar` | 分类 `Split` |
| calendar | `macro_calendar` | 分类 `MacroData` |

```python
from stock_alert.longbridge_sdk import LongbridgeClient, to_jsonable

client = LongbridgeClient()
company = client.query("fundamental", "company_profile", "TSM.US")
reports = client.query("fundamental", "financial_report", "TSM.US",
                       kind="All", period="Annual")
valuation = client.query("fundamental", "valuations", "TSM.US")
dividends = client.query("fundamental", "dividends", "TSM.US")
holders = client.query("fundamental", "shareholders", "TSM.US")
state = client.query("market", "market_status")
stats = client.query("market", "trading_stats", "TSM.US")
events = client.query("calendar", "earnings_calendar",
                      "2026-10-23", "2026-10-30", market="US", count=20)
print(to_jsonable(reports))
print(to_jsonable(events))
```

日历按市场/日期查询，不是单股过滤；返回记录和分页字段不丢弃，不会为了单次请求自动抓完整市场。根据原始结果的游标继续分页；缺事件和查询失败分别处理。A/H 溢价和港股经纪商持仓适用于对应港股，不适用于 TSM 美股 ADR。金额币种、报告期、单位以供应商字段为准，不能把基本面里的本币财务数字直接当成 USD。

PowerShell CLI 支持 JSON 位置参数和关键字参数：

```powershell
python -m stock_alert.longbridge_sdk fundamental company_profile --args '["TSM.US"]'
python -m stock_alert.longbridge_sdk fundamental financial_report --args '["TSM.US"]' --params '{"kind":"All","period":"Annual"}'
python -m stock_alert.longbridge_sdk fundamental valuations --args '["TSM.US"]'
python -m stock_alert.longbridge_sdk market market_status
python -m stock_alert.longbridge_sdk calendar earnings_calendar --args '["2026-10-23","2026-10-30"]' --params '{"market":"US","count":20}'
```

CLI 输出 JSON，Decimal 保持字符串精度，日期保留时区。SDK 错误转为固定诊断标签，避免响应体意外携带认证信息。需要精确参数类型时查看安装包签名或官方 SDK 文档。

## 实测记录与限制（2026-10-23，北京时间）

先直接用官方 SDK 和已有凭据测试 TSM，再通过接入代码复测。

| 实测范围 | 结果 |
| --- | --- |
| 报价、基础信息、盘口、逐笔、分时、K 线，共 6 项 | 全部成功 |
| 公司资料、通用财报、估值、分红、股东、管理层、公司行动，共 7 项 | 全部成功；分红返回 46 条、股东返回 61 条 |
| 市场状态、交易统计、指数成分、异动，共 4 项 | 请求成功；异动列表为空 |
| 财报/分红/IPO/拆股/宏观日历，共 5 项 | 请求成功；测试窗口内 IPO 列表为空 |
| `fund_holder("TSM.US")` | 服务器错误 `2101400`；保留失败，不视为空持仓 |
| `us_company_overview`、`us_financial_statement` | SDK 提示仅 US 数据中心支持；当前账户为 AP 区 |

合计 25 项调用，22 项成功，3 项失败。成功响应不保证所有字段都有数据，也不能据此确认所有 SDK 接口的权限。

19:42 左右，接入入口返回 TSM：盘前 414.500（19:42:21）、上一常规盘 412.350（04:00:00）、盘后 410.075（07:59:59）、夜盘 416.530（16:00:00），单位 USD，均为北京时间。它们是测试时的记录，不是文档阅读时的实时报价。

19:45 左右，30 只主要股票/ETF 的一批报价全部返回四时段记录；当时处于盘前，其他时段为历史记录。本次没有在夜盘正在交易时持续验收推送。股票少成交时，最后成交时间可能自然较早。

AP 区限制不影响已验证的四时段行情和上述通用基本面。未来如需 US 专用接口独有字段，需要另行确认账户地区资格；代码不绕过区域限制、不伪造缺失字段。机构基金持仓的服务器错误是独立问题。

离线测试覆盖凭据映射、TSM 时区、缺失字段、过期/停牌/周末、官方批量一次请求、备用源、错误脱敏、基本面 19 项概览映射、超时和日历分页保留。CI 安装 `quotes` extra，并沿用仓库的跨平台 Python 测试矩阵。
