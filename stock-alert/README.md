# 股票行情与长桥基本面

完整安装、凭据、四时段行情、官方 SDK、基本面和财经日历用法见 [接入文档](../docs/longbridge.md)。

```powershell
python -m pip install -e ".[quotes]"
python -m stock_alert.us_quotes TSM --all-sessions
python -m stock_alert.longbridge_sdk fundamental company_profile --args '["TSM.US"]'
```

可双击本目录的 `query-us-stocks.cmd` 查询默认 30 只主要股票与 ETF。
