# 其他系统如何使用长桥数据接入

这套接入是我们 AKShare fork 内的 Python 数据适配层，底层使用长桥官方 SDK。已经实现 Python 函数和 JSON 命令行入口；没有独立 HTTP 服务、共享缓存或消息队列。需要多系统共享时，可在此基础上建设集中采集服务，不应把尚未建设的服务当成现有能力。

## 本机绝对路径

| 内容 | 路径 |
| --- | --- |
| 日常使用的源码目录 | `C:\Users\admin\Documents\Codex\akshare` |
| 当前 PR 的隔离工作目录 | `C:\Users\admin\Documents\ChatGPT\投资\akshare-longbridge` |
| 行情 Python/CLI 入口 | `C:\Users\admin\Documents\Codex\akshare\stock_alert\us_quotes.py` |
| 完整四时段快照 | `C:\Users\admin\Documents\Codex\akshare\stock_alert\market_quotes.py` |
| SDK、基本面与配置入口 | `C:\Users\admin\Documents\Codex\akshare\stock_alert\longbridge_sdk.py` |
| 配置示例 | `C:\Users\admin\Documents\Codex\akshare\.env.example` |
| 完整用法 | `C:\Users\admin\Documents\Codex\akshare\docs\longbridge.md` |
| 本文 | `C:\Users\admin\Documents\Codex\akshare\docs\integrating-other-systems.md` |
| 本机现有真实凭据（只在本机） | `C:\githubProject\.env-lark` |
| 下载的官方 SDK 源码 | `C:\Users\admin\Documents\ChatGPT\投资\longbridge-openapi` |

代码仓库：<https://github.com/Aaronyu29/akshare>。这些本机 Windows 路径不是云端部署路径；云端通过安装包导入模块，通过 Secret 配置凭据，无需复用开发机目录结构。

## Python 业务系统

在业务系统自己的虚拟环境安装我们的 fork，并固定已合并、已通过检查的提交；直接安装 PyPI 的普通 AKShare 版本不会包含本 fork 扩展。下面的 `MERGED_COMMIT_SHA` 必须替换为实际合并提交：

```text
akshare[quotes] @ git+https://github.com/Aaronyu29/akshare.git@MERGED_COMMIT_SHA
```

部署平台向业务进程注入长桥三项 Secret 后即可调用，不需要复制凭据到源码中，也不需要修改系统全局 Python。

```python
from stock_alert.us_quotes import fetch_us_quote
from stock_alert.market_quotes import fetch_market_snapshots
from stock_alert.longbridge_sdk import LongbridgeClient, LongbridgeError, to_jsonable

# 指定官方来源，便于业务系统明确监控长桥连接与权限。
quote = fetch_us_quote("TSM", source="longbridge-api", timeout=6, max_age=60)
if quote.status == "current" and quote.price is not None:
    current_price = quote.price
else:
    # 向业务层保留缺失、过期或休市状态；不要把空值转换成 0。
    current_price = None

snapshots = fetch_market_snapshots(["TSM", "MU", "NVDA"],
                                    source="longbridge-api", include_sessions=True)

client = LongbridgeClient(timeout=10)
try:
    report = client.query("fundamental", "financial_report", "TSM.US",
                           kind="All", period="Annual")
    report_json = to_jsonable(report)
except LongbridgeError as exc:
    # 保存数据缺口和可安全展示的错误标签，按业务需要重试。
    report_json = None
```

统一报价入口接受 `TSM`；直接 SDK/基本面入口使用 `TSM.US`。原生返回类型、方法和枚举也可通过 `client.quotes`、`client.fundamentals`、`client.markets`、`client.calendars` 调用。`query` 包含超时和错误脱敏；直接调用原生上下文时由调用方管理生命周期和错误。实时推送要使用 `streaming_quotes()` 保持 WebSocket 上下文存活。

## 非 Python 系统

现有命令行入口支持标准输出 JSON。Node.js、Java、Go 等系统可以启动受控 Python 子进程并解析输出。以 PowerShell 在本机验证：

```powershell
Set-Location 'C:\Users\admin\Documents\Codex\akshare'
$env:AKSHARE_QUOTE_ENV_FILE = 'C:\githubProject\.env-lark'
python -m stock_alert.us_quotes TSM,MU --source longbridge-api --format json
python -m stock_alert.longbridge_sdk fundamental company_profile --args '["TSM.US"]'
```

实际业务使用参数数组启动子进程，避免拼接 shell 命令；只传股票代码和方法参数，不把 Token 放在命令行。设置进程超时，检查执行结果，并检查每条报价的 `status`/`error`；成功退出不等于每一只股票都有有效当前价格。SDK 基本面 CLI 遇到 `LongbridgeError` 返回非零退出码。

## 返回数据约定

| 字段 | 业务含义 |
| --- | --- |
| `symbol` / `currency` | 股票代码和报价币种；统一美股报价是 USD |
| `price` | 源成交价格；简短当前价入口抑制过期/不可用价格 |
| `session` | `premarket` / `regular` / `after_hours` / `overnight`，或休市状态 |
| `status` | `current` 当前有效、`historical` 历史时段记录、`stale` 过期、`unavailable` 不可用、`closed` 休市 |
| `quote_time` / `timestamp_ms` | 源行情发生时间，不能替换成请求完成时间 |
| `quote_time_shanghai` | 完整快照中的北京时间；简短入口保留带时区的 `quote_time` |
| `fetched_at` | 本次结果取得时间 |
| `source` | `longbridge-openapi` 为官方 SDK；公开备用源另有独立名称 |
| `error` / `attempts` | 当前记录错误/完整快照中的数据源尝试记录 |

四时段快照的 `quotes` 保存四个时段各自的最后记录；`selected` 是本次选定时段。当前在盘前时，上一个夜盘通常是 `historical`，不能作为“当前夜盘价”。默认报价新鲜度 1200 秒，业务可以收紧；最后成交较少的股票可能自然较旧。当前时段基于交易日历估计，不等于已验证所有供应商临时市场安排。

基本面接口结构随方法不同；保留原始报告期、单位和币种。`to_jsonable` 把 Decimal 转为字符串以保留精度。接口报错不能当成空持仓、零利润或没有事件；有效空列表与失败要区分。

## 多系统共用的建议部署方式

只有一个 Python 系统时直接调用即可。多个系统持续消费相同股票时，建议由一个采集进程统一管理长桥连接、批量查询与限频，行情结果写入带源时间和状态的共享缓存，再由内部 HTTP API 或消息队列提供给其他系统。基本面按需或较低频刷新，避免每次读取都重新请求财报。HTTP 服务需另行实现鉴权、超时、健康检查和流量控制。

当前官方批量报价最多 500 个代码一批，默认 30 只只发一次请求；其他接口可能逐个请求，应用端应限制并发并按供应商限制使用。单代码 5 秒进程内缓存不是跨系统缓存，批量报价每次获取新批次。正式持续推送可以使用原生 SDK 订阅接口；本次验证的四时段覆盖主要来自 HTTP 快照，未在正在交易的夜盘中持续验收推送。

## 凭据与部署边界

推荐由云端 Secret 管理功能注入三项 `LONGBRIDGE_*` 环境变量，或通过同名 `_FILE` 变量指定 `/run/secrets/...` 挂载文件。单机服务器可显式指定 `/etc/akshare/longbridge.env`；真实凭据不放在项目目录、镜像层、GitHub 或测试日志中。[配置示例](../.env.example) 可提交，真实文件不可提交。

AP 区账户已验证能够获取 TSM 四时段行情与通用财报、估值等。部分 `us_*` 专用基本面接口有地区限制，基金持仓测试返回服务器错误；业务系统必须容忍这些缺口。接入层不创建订单或查询交易账户。本次工作交付数据适配层与部署说明，不表示已在某台云服务器部署运行。
