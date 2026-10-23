#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Date: 2025/1/14 17:00
Desc: 新浪财经-美股实时行情数据和历史行情数据
https://finance.sina.com.cn/stock/usstock/sector.shtml
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import py_mini_racer
from tqdm import tqdm

from akshare.stock.cons import (
    js_hash_text,
    zh_js_decode,
    us_sina_stock_list_url,
    us_sina_stock_dict_payload,
    us_sina_stock_hist_qfq_url,
)


@lru_cache()
def __get_us_page_count() -> int:
    """
    新浪财经-美股-总页数
    https://finance.sina.com.cn/stock/usstock/sector.shtml
    :return: 美股总页数
    :rtype: int
    """
    page = "1"
    us_js_decode = (
        f"US_CategoryService.getList?page={page}&num=20&sort=&asc=0&market=&id="
    )
    js_code = py_mini_racer.MiniRacer()
    js_code.eval(js_hash_text)
    dict_list = js_code.call("d", us_js_decode)  # 执行js解密代码
    us_sina_stock_dict_payload.update({"page": "{}".format(page)})
    res = requests.get(
        us_sina_stock_list_url.format(dict_list),
        params=us_sina_stock_dict_payload,
    )
    data_json = json.loads(res.text[res.text.find("({") + 1 : res.text.rfind(");")])
    if not isinstance(int(data_json["count"]) / 20, int):
        page_count = int(int(data_json["count"]) / 20) + 1
    else:
        page_count = int(int(data_json["count"]) / 20)
    return page_count


@lru_cache()
def get_us_stock_name() -> pd.DataFrame:
    """
    u.s. stock's english name, chinese name and symbol
    you should use symbol to get apply into the next function
    https://finance.sina.com.cn/stock/usstock/sector.shtml
    :return: stock's english name, chinese name and symbol
    :rtype: pandas.DataFrame
    """
    big_df = pd.DataFrame()
    page_count = __get_us_page_count()
    for page in tqdm(range(1, page_count + 1), leave=False):
        us_js_decode = (
            "US_CategoryService.getList?page={}&num=20&sort=&asc=0&market=&id=".format(
                page
            )
        )
        js_code = py_mini_racer.MiniRacer()
        js_code.eval(js_hash_text)
        dict_list = js_code.call("d", us_js_decode)  # 执行js解密代码
        us_sina_stock_dict_payload.update({"page": "{}".format(page)})
        res = requests.get(
            us_sina_stock_list_url.format(dict_list),
            params=us_sina_stock_dict_payload,
        )
        data_json = json.loads(res.text[res.text.find("({") + 1 : res.text.rfind(");")])
        big_df = pd.concat(
            objs=[big_df, pd.DataFrame(data_json["data"])], ignore_index=True
        )
    return big_df[["name", "cname", "symbol"]]


def _us_quote_time(value, now):
    """Parse Sina's yearless Eastern timestamp, including the year boundary."""
    offsets = {"EDT": -4, "EST": -5}
    try:
        text, suffix = value.rsplit(" ", 1)
        parsed = datetime.strptime(text, "%b %d %I:%M%p")
        candidates = [
            parsed.replace(year=year, tzinfo=timezone(timedelta(hours=offsets[suffix])))
            for year in (now.year - 1, now.year, now.year + 1)
        ]
        return min(
            candidates, key=lambda stamp: abs((now - stamp).total_seconds())
        ).astimezone(ZoneInfo("America/New_York"))
    except (ValueError, KeyError):
        return None


def _us_quote_session(stamp):
    if stamp.weekday() >= 5:
        return "closed"
    minute = stamp.hour * 60 + stamp.minute
    if 240 <= minute < 570:
        return "premarket"
    if 570 <= minute < 960:
        return "regular"
    if 960 <= minute < 1200:
        return "after_hours"
    return "overnight_unavailable"


def _parse_us_single_quote(raw, symbol, now):
    """Field mapping follows Sina's official ushttps/js/tool.js parser."""
    feed_symbol = symbol.lower().replace(".", "$")
    match = re.fullmatch(
        r"\s*var\s+hq_str_gb_" + re.escape(feed_symbol) + r'="([^"]*)";?\s*', raw
    )
    if not match:
        raise ValueError(f"Unexpected Sina response for {symbol}")
    fields = match.group(1).split(",")
    if len(fields) < 28:
        raise ValueError(f"Sina quote unavailable for {symbol}")

    def number(index, positive=False):
        try:
            value = float(fields[index])
            return (
                value if math.isfinite(value) and (not positive or value > 0) else None
            )
        except (ValueError, TypeError):
            return None

    now = now.astimezone(ZoneInfo("America/New_York"))
    regular_time = _us_quote_time(fields[25], now)
    extended_time = _us_quote_time(fields[24], now)
    regular_price = number(1, positive=True)
    extended_price = number(21, positive=True)
    session = _us_quote_session(now)
    if session == "regular":
        stamp, price, change, change_percent = (
            regular_time,
            regular_price,
            number(4),
            number(2),
        )
    elif session in ("premarket", "after_hours"):
        stamp, price, change, change_percent = (
            extended_time,
            extended_price,
            number(23),
            number(22),
        )
    else:
        stamp, price, change, change_percent = None, None, None, None
    age = (now - stamp).total_seconds() if stamp else None
    error = None
    if session in ("closed", "overnight_unavailable"):
        error = "Sina does not provide a verified current quote for this session"
    elif price is None or stamp is None:
        error = f"{session} quote unavailable"
    elif stamp.date() != now.date() or _us_quote_session(stamp) != session:
        error = f"Source timestamp does not belong to the current {session} session"
    elif age < -60 or age > 1200:
        error = "Source timestamp is stale or in the future"
    if error:
        price, change, change_percent = None, None, None

    def iso(stamp):
        return stamp.isoformat() if stamp else None

    return {
        "symbol": symbol,
        "cname": fields[0],
        "price": price,
        "diff": change,
        "chg": change_percent,
        "session": session,
        "quote_time": iso(stamp),
        "quote_age_seconds": age,
        "regular_price": regular_price,
        "regular_quote_time": iso(regular_time),
        "extended_price": extended_price,
        "extended_quote_time": iso(extended_time),
        "currency": "USD",
        "source": "sina-gb",
        "error": error,
        "fetched_at": now.isoformat(),
    }


def _stock_us_spot_single(symbol, timeout):
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a single US stock ticker")
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.$][A-Z0-9]+)*", symbol):
        raise ValueError("symbol must be a single US stock ticker")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    response = requests.get(
        "https://hq.sinajs.cn/",
        params={"list": "gb_" + symbol.lower().replace(".", "$")},
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://stock.finance.sina.com.cn/",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = "gb18030"
    row = _parse_us_single_quote(
        response.text, symbol, datetime.now(ZoneInfo("America/New_York"))
    )
    return pd.DataFrame([row])


def stock_us_spot(symbol: str | None = None, timeout: float = 10) -> pd.DataFrame:
    """
    新浪财经-美股行情。本地扩展：传 symbol 时只请求一只股票。
    不传 symbol 保持全市场查询；全市场列表有 15 分钟延迟。
    单股查询分别解析常规、盘前和盘后报价，延迟以供应商为准。
    当前时段缺失、夜盘或时间超过 20 分钟时 price 为空，原因见 error。
    https://stock.finance.sina.com.cn/usstock/quotes/MU.html
    :param symbol: 单只美股代码，如 MU；None 返回全市场
    :param timeout: 单股请求超时，单位秒
    :return: 全市场列表，或含 price/session/quote_time 的单股 DataFrame
    :rtype: pandas.DataFrame
    """
    if symbol is not None:
        return _stock_us_spot_single(symbol, timeout)
    big_df = pd.DataFrame()
    page_count = __get_us_page_count()
    for page in tqdm(range(1, page_count + 1), leave=False):
        # page = "1"
        us_js_decode = (
            "US_CategoryService.getList?page={}&num=20&sort=&asc=0&market=&id=".format(
                page
            )
        )
        js_code = py_mini_racer.MiniRacer()
        js_code.eval(js_hash_text)
        dict_list = js_code.call("d", us_js_decode)  # 执行js解密代码
        us_sina_stock_dict_payload.update({"page": "{}".format(page)})
        res = requests.get(
            us_sina_stock_list_url.format(dict_list),
            params=us_sina_stock_dict_payload,
        )
        data_json = json.loads(res.text[res.text.find("({") + 1 : res.text.rfind(");")])
        big_df = pd.concat(
            objs=[big_df, pd.DataFrame(data_json["data"])], ignore_index=True
        )
    return big_df


def stock_us_daily(symbol: str = "FB", adjust: str = "") -> pd.DataFrame:
    """
    新浪财经-美股
    https://finance.sina.com.cn/stock/usstock/sector.shtml
    备注：
    1. CIEN 新浪复权因子错误
    2. AI 新浪复权因子错误，该股票刚上市未发生复权，但是返回复权因子
    :param symbol: 可以使用 get_us_stock_name 获取
    :type symbol: str
    :param adjust: "": 返回未复权的数据 ; qfq: 返回前复权后的数据；qfq-factor: 返回前复权因子和调整；
    :type adjust: str
    :return: 指定 adjust 的数据
    :rtype: pandas.DataFrame
    """
    url = f"https://finance.sina.com.cn/staticdata/us/{symbol}"
    res = requests.get(url)
    js_code = py_mini_racer.MiniRacer()
    js_code.eval(zh_js_decode)
    dict_list = js_code.call("d", res.text.split("=")[1].split(";")[0].replace('"', ""))
    data_df = pd.DataFrame(dict_list)
    data_df["date"] = pd.to_datetime(data_df["date"]).dt.date
    data_df.index = pd.to_datetime(data_df["date"])
    del data_df["amount"]
    del data_df["date"]
    data_df = data_df.astype("float")
    url = us_sina_stock_hist_qfq_url.format(symbol)
    res = requests.get(url)
    qfq_factor_df = pd.DataFrame(eval(res.text.split("=")[1].split("\n")[0])["data"])
    qfq_factor_df.rename(
        columns={
            "c": "adjust",
            "d": "date",
            "f": "qfq_factor",
        },
        inplace=True,
    )
    qfq_factor_df.index = pd.to_datetime(qfq_factor_df["date"])
    del qfq_factor_df["date"]

    # 处理复权因子
    temp_date_range = pd.date_range("1900-01-01", qfq_factor_df.index[0].isoformat())
    temp_df = pd.DataFrame(range(len(temp_date_range)), temp_date_range)
    new_range = pd.merge(
        temp_df, qfq_factor_df, left_index=True, right_index=True, how="left"
    )
    new_range = new_range.ffill()
    new_range = new_range.iloc[:, [1, 2]]

    if adjust == "qfq":
        if len(new_range) == 1:
            new_range.index = [pd.to_datetime(str(data_df.index.date[0]))]
        temp_df = pd.merge(
            data_df, new_range, left_index=True, right_index=True, how="left"
        )
        try:
            # try for pandas >= 2.1.0
            temp_df.ffill(inplace=True)
        except Exception:
            try:
                # try for pandas < 2.1.0
                temp_df.fillna(method="ffill", inplace=True)
            except Exception as e:
                print("Error:", e)
        try:
            # try for pandas >= 2.1.0
            temp_df.bfill(inplace=True)
        except Exception:
            try:
                # try for pandas < 2.1.0
                temp_df.fillna(method="bfill", inplace=True)
            except Exception as e:
                print("Error:", e)

        temp_df = temp_df.astype(float)
        temp_df["open"] = temp_df["open"] * temp_df["qfq_factor"] + temp_df["adjust"]
        temp_df["high"] = temp_df["high"] * temp_df["qfq_factor"] + temp_df["adjust"]
        temp_df["close"] = temp_df["close"] * temp_df["qfq_factor"] + temp_df["adjust"]
        temp_df["low"] = temp_df["low"] * temp_df["qfq_factor"] + temp_df["adjust"]
        temp_df = temp_df.apply(lambda x: round(x, 4))
        temp_df = temp_df.astype("float")
        # 处理复权因子错误的情况-开始
        check_df = temp_df[["open", "high", "low", "close"]].copy()
        check_df.dropna(inplace=True)
        if check_df.empty:
            data_df.reset_index(inplace=True)
            return data_df
        # 处理复权因子错误的情况-结束
        result_data = temp_df.iloc[:, :-2]
        result_data.reset_index(inplace=True)
        return result_data

    if adjust == "qfq-factor":
        qfq_factor_df.reset_index(inplace=True)
        return qfq_factor_df

    if adjust == "":
        data_df.reset_index(inplace=True)
        return data_df


if __name__ == "__main__":
    stock_us_stock_name_df = get_us_stock_name()
    print(stock_us_stock_name_df)

    stock_us_spot_df = stock_us_spot()
    print(stock_us_spot_df)

    stock_us_daily_df = stock_us_daily(symbol=".DJI", adjust="")
    print(stock_us_daily_df)

    stock_us_daily_qfq_df = stock_us_daily(symbol="WOLF", adjust="qfq")
    print(stock_us_daily_qfq_df)

    stock_us_daily_qfq_factor_df = stock_us_daily(symbol="AAPL", adjust="qfq-factor")
    print(stock_us_daily_qfq_factor_df)
