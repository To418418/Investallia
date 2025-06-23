# news_services.py
import requests
import datetime
from dateutil.relativedelta import relativedelta
import json
import logging
from urllib.parse import urlparse
import time
import os
import streamlit as st # キャッシュ用
import re # スニペットからの日付抽出用
from concurrent.futures import ThreadPoolExecutor, as_completed # ★ 並列処理のために追加
from functools import partial # ★ 並列処理のために追加

# config から設定をインポート
import config as app_config

# Google API Client Library (オプション)
try:
    from googleapiclient.discovery import build as google_build_service
    from googleapiclient.errors import HttpError as GoogleHttpError
except ImportError:
    google_build_service = None
    GoogleHttpError = None
    logger_gapi = logging.getLogger(__name__) # logger名変更
    logger_gapi.warning("google-api-python-client がインストールされていないため、Google CSEは利用できません。")


# Tavily APIクライアント (オプション)
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None
    logger_tavily = logging.getLogger(__name__) # logger名変更
    logger_tavily.warning("tavily-python SDK がインストールされていないため、Tavily APIは利用できません。")


logger = logging.getLogger(__name__)

# --- キャッシュ関連ヘルパー関数 ---
def _get_cache_filepath(news_type: str, stock_name_for_company: str = None, is_cloud_run: bool = False) -> str | None:
    base_dir = app_config.NEWS_SERVICE_CONFIG["cache_dir_colab"]
    if is_cloud_run:
        base_dir = "/tmp/news_cache_gcr" # Cloud Runでは一時ディレクトリを使用
    if not os.path.exists(base_dir) and not is_cloud_run: # Cloud Runでは/tmpは常に存在すると仮定
        try: os.makedirs(base_dir)
        except OSError as e: logger.error(f"キャッシュディレクトリの作成に失敗: {base_dir}, エラー: {e}"); return None
    elif not os.path.exists(base_dir) and is_cloud_run: # Cloud Runで/tmp/news_cache_gcrが存在しない場合
        try: os.makedirs(base_dir)
        except OSError as e: logger.error(f"Cloud Run キャッシュディレクトリの作成に失敗: {base_dir}, エラー: {e}"); return None

    filename_part = ""
    if news_type == "market_news": filename_part = "market_news_cache"
    elif news_type == "company_news":
        if not stock_name_for_company: logger.error("企業ニュースのキャッシュファイル名生成には銘柄名が必要です。"); return None
        safe_stock_name = "".join(c if c.isalnum() else "_" for c in stock_name_for_company)
        filename_part = f"{safe_stock_name}_company_news_cache"
    else: logger.error(f"未知のニュースタイプ: {news_type}"); return None
    return os.path.join(base_dir, f"{filename_part}.json")

def _load_from_cache(filepath: str | None, expiry_hours: int) -> tuple[list | None, dict | None]:
    """キャッシュファイルから整形済みデータと生レスポンスを読み込み、有効期限内であれば返す"""
    if filepath is None or not os.path.exists(filepath): return None, None
    try:
        with open(filepath, 'r', encoding='utf-8') as f: cache_data = json.load(f)
        timestamp_str = cache_data.get("timestamp")
        if timestamp_str:
            cached_time_naive = datetime.datetime.fromisoformat(timestamp_str)
            if cached_time_naive.tzinfo is None:
                    cached_time_utc = cached_time_naive.replace(tzinfo=datetime.timezone.utc)
            else:
                    cached_time_utc = cached_time_naive.astimezone(datetime.timezone.utc)

            if datetime.datetime.now(datetime.timezone.utc) - cached_time_utc < datetime.timedelta(hours=expiry_hours):
                logger.info(f"有効なキャッシュが見つかりました: {filepath}")
                formatted_data = cache_data.get("formatted_data", [])
                raw_responses = cache_data.get("raw_api_responses_cache", {})
                return formatted_data, raw_responses
        logger.info(f"キャッシュは古いか、タイムスタンプが無効です: {filepath}")
    except (IOError, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"キャッシュファイルの読み込み/解析に失敗: {filepath}, エラー: {e}")
    return None, None

def _save_to_cache(filepath: str | None, formatted_data: list, raw_responses_to_cache: dict):
    """取得した整形済みデータと生レスポンスをキャッシュファイルに保存する"""
    if filepath is None: logger.error("キャッシュファイルパスがNoneのため、保存できません。"); return
    try:
        cache_content = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "formatted_data": formatted_data,
            "raw_api_responses_cache": raw_responses_to_cache
        }
        cache_dir = os.path.dirname(filepath)
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
                logger.info(f"キャッシュディレクトリを作成しました: {cache_dir}")
            except OSError as e:
                logger.error(f"キャッシュディレクトリの作成に失敗: {cache_dir}, エラー: {e}")
                return

        with open(filepath, 'w', encoding='utf-8') as f: json.dump(cache_content, f, ensure_ascii=False, indent=4)
        logger.info(f"データをキャッシュに保存しました: {filepath}")
    except IOError as e: logger.error(f"キャッシュファイルへの保存に失敗: {filepath}, エラー: {e}")

# --- 共通ヘルパー関数 (APIリクエスト、日付パース) ---
def _make_api_request(url, params=None, headers=None, api_name="API", method="GET", data=None, timeout=15, return_raw_text=False):
    logger.debug(f"{api_name} - リクエスト開始: {method} {url}, Params: {params}, Headers: {headers is not None}, Data: {data is not None}")
    # 初期値をエラーを示すJSON文字列にすることも検討 (ただし、成功時は上書きされる)
    raw_text_response_for_debug = json.dumps({"status": "initiated", "api": api_name, "url": url})
    try:
        if method.upper() == "POST": response = requests.post(url, params=params, headers=headers, json=data, timeout=timeout)
        else: response = requests.get(url, params=params, headers=headers, timeout=timeout)
        raw_text_response_for_debug = response.text
        response.raise_for_status() # HTTPエラーがあればここで例外発生
        logger.debug(f"{api_name} - リクエスト成功: Status {response.status_code}")
        if return_raw_text:
            return raw_text_response_for_debug # 成功時は生のテキスト
        return response.json() # 成功時はパースされたJSON
    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code if http_err.response is not None else "N/A"
        # エラー時も raw_text_response_for_debug にはレスポンスボディが入っている可能性があるので利用
        response_body_preview = raw_text_response_for_debug[:200].replace('"', '\\"') + "..." if raw_text_response_for_debug else "No response body."
        logger.error(f"{api_name} - HTTPエラー: {http_err} (URL: {url}), Status: {status_code}, Response Preview: {response_body_preview}")
        error_payload = {"status": "error", "api": api_name, "error_type": "HTTPError",
                         "status_code": str(status_code), "message": str(http_err),
                         "response_preview": response_body_preview}
        if return_raw_text: return json.dumps(error_payload)
    except requests.exceptions.Timeout:
        logger.error(f"{api_name} - リクエストタイムアウト (URL: {url})")
        error_payload = {"status": "error", "api": api_name, "error_type": "Timeout", "message": f"Request timed out for {url}"}
        if return_raw_text: return json.dumps(error_payload)
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"{api_name} - 接続エラー (URL: {url}): {conn_err}")
        error_payload = {"status": "error", "api": api_name, "error_type": "ConnectionError", "message": f"Connection error for {url}: {conn_err}"}
        if return_raw_text: return json.dumps(error_payload)
    except json.JSONDecodeError as e: # raise_for_status()を通った後のJSONパースエラー
        logger.error(f"{api_name} - JSONデコードエラー: {e} (URL: {url}). Raw text: {raw_text_response_for_debug[:200]}...")
        error_payload = {"status": "error", "api": api_name, "error_type": "JSONDecodeError",
                         "message": str(e), "raw_response_preview": raw_text_response_for_debug[:200].replace('"', '\\"') + "..."}
        if return_raw_text: return json.dumps(error_payload)
    except Exception as e:
        logger.error(f"{api_name} - 予期せぬリクエストエラー: {e} (URL: {url})", exc_info=True)
        error_payload = {"status": "error", "api": api_name, "error_type": "UnexpectedError", "message": str(e)}
        if return_raw_text: return json.dumps(error_payload)

    # return_raw_text=False でエラーが発生した場合 (response.json()を期待していたがエラーになったケース)
    return None


def _parse_relative_date(relative_date_str: str, base_datetime_utc: datetime.datetime) -> datetime.datetime | None:
    relative_date_str = relative_date_str.strip().lower()
    patterns_en = {
        "year": (r"(\d+)\s*(?:year|years|yr|yrs)\s+ago", relativedelta(years=1)),
        "month": (r"(\d+)\s*(?:month|months|mo)\s+ago", relativedelta(months=1)),
        "week": (r"(\d+)\s*(?:week|weeks|wk|wks)\s+ago", relativedelta(weeks=1)),
        "day": (r"(\d+)\s*(?:day|days|d)\s+ago", relativedelta(days=1)),
        "hour": (r"(\d+)\s*(?:hour|hours|hr|hrs)\s+ago", relativedelta(hours=1)),
        "minute": (r"(\d+)\s*(?:minute|minutes|min|mins)\s+ago", relativedelta(minutes=1)),
    }
    for unit, (pattern, delta_unit) in patterns_en.items():
        match = re.search(pattern, relative_date_str)
        if match:
            value = int(match.group(1))
            logger.debug(f"Relative date matched (EN): '{relative_date_str}' -> {value} {unit} ago")
            return base_datetime_utc - (delta_unit * value)

    patterns_jp_or_general = {
        "year": (r"(\d+)\s*(?:年前)", relativedelta(years=1)),
        "month": (r"(\d+)\s*(?:ヶ月前|ヵ月前|カ月前|か月前)", relativedelta(months=1)),
        "week": (r"(\d+)\s*(?:週間前)", relativedelta(weeks=1)),
        "day": (r"(\d+)\s*(?:日前)", relativedelta(days=1)),
        "hour": (r"(\d+)\s*(?:時間前)", relativedelta(hours=1)),
        "minute": (r"(\d+)\s*(?:分前)", relativedelta(minutes=1)),
    }
    for unit, (pattern, delta_unit) in patterns_jp_or_general.items():
        match = re.search(pattern, relative_date_str)
        if match:
            value = int(match.group(1))
            logger.debug(f"Relative date matched (JP/General): '{relative_date_str}' -> {value} {unit}前")
            return base_datetime_utc - (delta_unit * value)

    if "yesterday" in relative_date_str or "昨日" in relative_date_str: return base_datetime_utc - relativedelta(days=1)
    if "today" in relative_date_str or "今日" in relative_date_str or "just now" in relative_date_str or "たった今" in relative_date_str: return base_datetime_utc
    return None


def _parse_datetime_str(date_str, formats_details, api_name_for_log=""):
    if not date_str or not isinstance(date_str, str): return "N/A"
    date_str = date_str.strip()
    logger.debug(f"{api_name_for_log} - 日付パース試行開始: '{date_str}'")
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    jst = datetime.timezone(datetime.timedelta(hours=9), name="JST")

    absolute_dt_from_relative = _parse_relative_date(date_str, now_utc)
    if absolute_dt_from_relative:
        dt_object_utc = absolute_dt_from_relative
        dt_object_jst_display = dt_object_utc.astimezone(jst)
        logger.info(f"{api_name_for_log} - 相対日付 '{date_str}' を '{dt_object_jst_display.strftime('%Y/%m/%d %H:%M')}' (JST) に変換成功。")
        return dt_object_jst_display.strftime('%Y/%m/%d %H:%M')

    common_web_formats = [
        {"format": "iso"},
        {"format": "%Y年%m月%d日 %H時%M分", "tz": "JST"}, {"format": "%Y年%m月%d日%H時%M分", "tz": "JST"},
        {"format": "%Y年%m月%d日", "tz": "JST"},
        {"format": "%Y/%m/%d %H:%M", "tz": "JST"}, {"format": "%Y/%m/%d %H:%M:%S", "tz": "JST"},
        {"format": "%Y/%m/%d", "tz": "JST"},
        {"format": "%Y-%m-%d %H:%M", "tz": "JST"}, {"format": "%Y-%m-%d %H:%M:%S", "tz": "JST"},
        {"format": "%Y-%m-%d", "tz": "JST"},
        {"format": "%Y.%m.%d %H:%M", "tz": "JST"}, {"format": "%Y.%m.%d", "tz": "JST"},
        {"format": "%m月%d日 %H時%M分", "tz": "JST", "year_missing": True},
        {"format": "%m月%d日", "tz": "JST", "year_missing": True},
        {"format": "%Y-%m-%dT%H:%M:%S%z"}, {"format": "%a, %d %b %Y %H:%M:%S %z"},
        {"format": "%a %b %d %H:%M:%S %Y %z"},
        {"format": "%Y%m%d%H%M%S", "tz": "JST"}, {"format": "%Y%m%d", "tz": "JST"},
        {"format": "%H:%M", "tz": "JST", "date_missing": True},
        {"format": "%b %d, %Y", "tz": "UTC"}, {"format": "%B %d, %Y", "tz": "UTC"},
        {"format": "%b %d %Y", "tz": "UTC"},  {"format": "%B %d %Y", "tz": "UTC"},
        {"format": "%d %b %Y", "tz": "UTC"}, {"format": "%d %B %Y", "tz": "UTC"},
    ]
    if not isinstance(formats_details, list): formats_details = []
    valid_formats_details = [fd for fd in formats_details if isinstance(fd, dict) and "format" in fd]
    final_formats_to_try = valid_formats_details + [cwf for cwf in common_web_formats if cwf["format"] not in {fd["format"] for fd in valid_formats_details}]


    for fmt_detail in final_formats_to_try:
        fmt_string = fmt_detail["format"]
        assumed_tz_str = fmt_detail.get("tz")
        year_missing = fmt_detail.get("year_missing", False)
        date_missing = fmt_detail.get("date_missing", False)
        temp_date_str_loop = date_str
        try:
            dt_object_naive_or_aware = None
            if fmt_string == "iso":
                temp_date_str_loop_iso = temp_date_str_loop.replace('Z', '+00:00')
                if '.' in temp_date_str_loop_iso:
                    parts = temp_date_str_loop_iso.split('.', 1)
                    main_part = parts[0]; frac_part_full = parts[1]
                    tz_suffix_iso = ""; non_digit_idx_frac = -1
                    for char_idx, char_val in enumerate(frac_part_full):
                        if not char_val.isdigit(): non_digit_idx_frac = char_idx; break
                    frac_digits = frac_part_full[:non_digit_idx_frac] if non_digit_idx_frac != -1 else frac_part_full
                    if non_digit_idx_frac != -1: tz_suffix_iso = frac_part_full[non_digit_idx_frac:]
                    if len(frac_digits) > 6: frac_digits = frac_digits[:6]
                    temp_date_str_loop_iso = f"{main_part}.{frac_digits}{tz_suffix_iso}"
                dt_object_naive_or_aware = datetime.datetime.fromisoformat(temp_date_str_loop_iso)
            else:
                dt_object_naive_or_aware = datetime.datetime.strptime(temp_date_str_loop, fmt_string)
                if year_missing: dt_object_naive_or_aware = dt_object_naive_or_aware.replace(year=now_utc.year)
                if date_missing: dt_object_naive_or_aware = dt_object_naive_or_aware.replace(year=now_utc.year, month=now_utc.month, day=now_utc.day)

            if dt_object_naive_or_aware.tzinfo is None or dt_object_naive_or_aware.tzinfo.utcoffset(dt_object_naive_or_aware) is None:
                assumed_tz_obj = None
                if assumed_tz_str == "JST": assumed_tz_obj = jst
                elif assumed_tz_str == "UTC": assumed_tz_obj = datetime.timezone.utc
                else: assumed_tz_obj = jst
                dt_object_aware = dt_object_naive_or_aware.replace(tzinfo=assumed_tz_obj)
            else:
                dt_object_aware = dt_object_naive_or_aware

            dt_object_utc = dt_object_aware.astimezone(datetime.timezone.utc)
            dt_object_jst_display = dt_object_utc.astimezone(jst)
            logger.info(f"{api_name_for_log} - 日付 '{date_str}' をフォーマット '{fmt_string}' で '{dt_object_jst_display.strftime('%Y/%m/%d %H:%M')}' (JST) にパース成功。")
            return dt_object_jst_display.strftime('%Y/%m/%d %H:%M')
        except ValueError:
            logger.debug(f"{api_name_for_log} - ValueError with format '{fmt_string}' for date '{temp_date_str_loop}'")
            continue
        except Exception as e:
            logger.debug(f"{api_name_for_log} - 日付パース中エラー (入力: '{date_str}', 試行フォーマット: '{fmt_string}'): {e}")
            continue
    logger.warning(f"{api_name_for_log} - 全ての日付フォーマット試行失敗: '{date_str}'。Tried: {[f['format'] for f in final_formats_to_try]}")
    return "N/A"

# --- 各APIのニュース取得・フォーマット関数 ---
def _generate_error_response_text(api_name, error_message, status_code="N/A", details=""):
    """エラー情報をJSON文字列として生成するヘルパー関数"""
    return json.dumps({
        "status": "error",
        "api": api_name,
        "status_code": str(status_code),
        "message": error_message,
        "details": details
    })

# NewsAPI
def _format_newsapi_articles(articles_response, news_type_for_log=""):
    news_list = []
    if not articles_response or "articles" not in articles_response: return news_list
    date_formats = [{"format": "iso"}]
    for article in articles_response.get("articles", []):
        news_list.append({
            '日付': _parse_datetime_str(article.get('publishedAt'), date_formats, f"NewsAPI ({news_type_for_log})"),
            'タイトル': article.get('title', 'N/A'), '概要': article.get('description', 'N/A'),
            'ソース': article.get('source', {}).get('name', 'N/A'), 'URL': article.get('url', '#'), 'api_source': 'NewsAPI'
        })
    return news_list

def fetch_newsapi_company_news(stock_name, api_key):
    err_msg_key = "NewsAPIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("NewsAPI (Company)", err_msg_key, "401")
    BASE_URL = "https://newsapi.org/v2/everything"
    dt_now_utc = datetime.datetime.now(datetime.timezone.utc)
    params = {"q": f'"{stock_name}" AND (業績 OR 決算 OR 株価 OR 見通し OR 新製品 OR 提携)', "from": (dt_now_utc - relativedelta(months=1)).isoformat(),
              "to": dt_now_utc.isoformat(), "language": "jp", "sortBy": "relevancy", "pageSize": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "apiKey": api_key}
    raw_resp_text = _make_api_request(BASE_URL, params, api_name="NewsAPI (Company) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"NewsAPI (Company) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and resp_json.get("status") == "ok": # NewsAPI success status is "ok"
        formatted_news = _format_newsapi_articles(resp_json, "Company")
        return formatted_news, None, raw_resp_text

    err_msg_api = "企業ニュース取得失敗 (NewsAPI)"
    # If resp_json exists and contains an error message from NewsAPI, use it
    if resp_json and resp_json.get("status") == "error":
        err_msg_api = f"企業ニュース取得失敗 (NewsAPI): {resp_json.get('message', 'Unknown error')}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("NewsAPI (Company)", err_msg_api, details="Response was None or not valid success JSON.")


def fetch_newsapi_market_news(api_key):
    err_msg_key = "NewsAPIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("NewsAPI (Market)", err_msg_key, "401")
    BASE_URL = "https://newsapi.org/v2/everything"
    dt_now_utc = datetime.datetime.now(datetime.timezone.utc)
    params = {"q": "日本株 OR 株式市場 OR 日経平均 OR TOPIX OR 相場見通し", "from": (dt_now_utc - relativedelta(weeks=1)).isoformat(),
              "to": dt_now_utc.isoformat(), "language": "jp", "sortBy": "publishedAt", "pageSize": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "apiKey": api_key}
    raw_resp_text = _make_api_request(BASE_URL, params, api_name="NewsAPI (Market) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"NewsAPI (Market) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and resp_json.get("status") == "ok":
        formatted_news = _format_newsapi_articles(resp_json, "Market")
        return formatted_news, None, raw_resp_text

    err_msg_api = "市場ニュース取得失敗 (NewsAPI)"
    if resp_json and resp_json.get("status") == "error":
        err_msg_api = f"市場ニュース取得失敗 (NewsAPI): {resp_json.get('message', 'Unknown error')}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("NewsAPI (Market)", err_msg_api, details="Response was None or not valid success JSON.")

# GNews API
def _format_gnews_articles(articles_response, news_type_for_log=""):
    news_list = []
    if not articles_response or "articles" not in articles_response: return news_list
    date_formats = [{"format": '%Y-%m-%d %H:%M:%S', "tz": "UTC"}]
    for article in articles_response.get("articles", []):
        news_list.append({
            '日付': _parse_datetime_str(article.get('publishedAt'), date_formats, f"GNews ({news_type_for_log})"),
            'タイトル': article.get('title', 'N/A'), '概要': article.get('description', 'N/A'),
            'ソース': article.get('source', {}).get('name', 'N/A'), 'URL': article.get('url', '#'), 'api_source': 'GNews'
        })
    return news_list

def fetch_gnews_company_news(stock_name, api_key):
    err_msg_key = "GNews APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("GNews (Company)", err_msg_key, "401")
    BASE_URL = "https://gnews.io/api/v4/search"
    dt_now_utc = datetime.datetime.now(datetime.timezone.utc)
    params = {"q": f'"{stock_name}" (業績 OR 決算 OR 株価 OR 見通し OR 新製品 OR 提携)', "lang": "ja", "country": "jp",
              "from": (dt_now_utc - relativedelta(months=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), "to": dt_now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
              "max": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "sortby": "relevance", "in": "title,description", "token": api_key}
    raw_resp_text = _make_api_request(BASE_URL, params, api_name="GNews (Company) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"GNews (Company) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and "articles" in resp_json :
        formatted_news = _format_gnews_articles(resp_json, "Company")
        return formatted_news, None, raw_resp_text

    err_msg_api = "企業ニュース取得失敗 (GNews)"
    if resp_json and "errors" in resp_json: # GNews error format
        err_msg_api = f"企業ニュース取得失敗 (GNews): {resp_json['errors']}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("GNews (Company)", err_msg_api, details="Response was None or not valid success JSON.")

def fetch_gnews_market_news(api_key):
    err_msg_key = "GNews APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("GNews (Market)", err_msg_key, "401")
    BASE_URL = "https://gnews.io/api/v4/search"
    dt_now_utc = datetime.datetime.now(datetime.timezone.utc)
    params = {"q": "日本株 OR 株式市場 OR 日経平均 OR TOPIX OR 相場見通し", "lang": "ja", "country": "jp",
              "from": (dt_now_utc - relativedelta(weeks=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), "to": dt_now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
              "max": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "sortby": "publishedAt", "token": api_key}
    raw_resp_text = _make_api_request(BASE_URL, params, api_name="GNews (Market) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"GNews (Market) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and "articles" in resp_json:
        formatted_news = _format_gnews_articles(resp_json, "Market")
        return formatted_news, None, raw_resp_text

    err_msg_api = "市場ニュース取得失敗 (GNews)"
    if resp_json and "errors" in resp_json:
        err_msg_api = f"市場ニュース取得失敗 (GNews): {resp_json['errors']}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("GNews (Market)", err_msg_api, details="Response was None or not valid success JSON.")

# Brave Search API
def _format_brave_articles(articles_response, news_type_for_log=""):
    news_list = []
    articles_data = []
    if articles_response and "results" in articles_response.get("news", {}): # Brave specific structure
        articles_data = articles_response.get("news", {}).get("results", [])
    elif articles_response and "web" in articles_response and "results" in articles_response.get("web", {}): # Fallback if news specific isn't there
        articles_data = articles_response.get("web", {}).get("results", [])
    elif articles_response and "results" in articles_response: # General results
        articles_data = articles_response.get("results", [])


    if not articles_data: return news_list
    date_formats = [{"format": "iso"}]
    for article in articles_data:
        source_name = article.get('profile',{}).get('name', article.get('meta_url', {}).get('hostname', 'N/A'))
        published_date_str = article.get('page_age') # Brave uses page_age (relative) or sometimes absolute in meta
        if not published_date_str and 'meta_url' in article and 'published_time' in article['meta_url']: # Hypothetical absolute date
            published_date_str = article['meta_url']['published_time']

        news_list.append({
            '日付': _parse_datetime_str(published_date_str, date_formats, f"Brave ({news_type_for_log})"),
            'タイトル': article.get('title', 'N/A'), '概要': article.get('description', article.get('snippet', 'N/A')),
            'ソース': source_name, 'URL': article.get('url', '#'), 'api_source': 'Brave'
        })
    return news_list

def fetch_brave_company_news(stock_name, api_key):
    err_msg_key = "Brave Search APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("Brave (Company)", err_msg_key, "401")
    BASE_URL = "https://api.search.brave.com/res/v1/news/search" # Using news endpoint
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": f'"{stock_name}" (業績 OR 決算 OR 株価 OR 見通し OR 新製品 OR 提携)', "country": "JP", "search_lang": "jp",
              "freshness": "pm:1", "count": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "spellcheck": "1"}
    raw_resp_text = _make_api_request(BASE_URL, params, headers=headers, api_name="Brave (Company) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"Brave (Company) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    # Brave API success can be checked by presence of 'news' or 'web' or 'results' keys
    if resp_json and (resp_json.get("news") or resp_json.get("web") or resp_json.get("results")):
        formatted_news = _format_brave_articles(resp_json, "Company")
        return formatted_news, None, raw_resp_text

    err_msg_api = "企業ニュース取得失敗 (Brave)"
    if resp_json and resp_json.get("message"): # Brave error often has a "message"
        err_msg_api = f"企業ニュース取得失敗 (Brave): {resp_json.get('message')}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("Brave (Company)", err_msg_api, details="Response was None or not valid success JSON.")

def fetch_brave_market_news(api_key):
    err_msg_key = "Brave Search APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("Brave (Market)", err_msg_key, "401")
    BASE_URL = "https://api.search.brave.com/res/v1/news/search"
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": "日本株 OR 株式市場 OR 日経平均 OR TOPIX OR 相場見通し", "country": "JP", "search_lang": "jp",
              "freshness": "pw:1", "count": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "spellcheck": "1"}
    raw_resp_text = _make_api_request(BASE_URL, params, headers=headers, api_name="Brave (Market) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"Brave (Market) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and (resp_json.get("news") or resp_json.get("web") or resp_json.get("results")):
        formatted_news = _format_brave_articles(resp_json, "Market")
        return formatted_news, None, raw_resp_text

    err_msg_api = "市場ニュース取得失敗 (Brave)"
    if resp_json and resp_json.get("message"):
        err_msg_api = f"市場ニュース取得失敗 (Brave): {resp_json.get('message')}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("Brave (Market)", err_msg_api, details="Response was None or not valid success JSON.")

# Tavily API
def _format_tavily_articles(articles_response, news_type_for_log=""):
    news_list = []
    if not articles_response or "results" not in articles_response: return news_list
    date_formats = [{"format": "iso"}, {"format": '%Y-%m-%d'}]
    for article in articles_response.get("results", []):
        source_name = urlparse(article.get('url', '#')).hostname if article.get('url') else 'N/A'
        published_date_str = article.get('published_date', article.get('publish_date'))
        news_list.append({
            '日付': _parse_datetime_str(published_date_str, date_formats, f"Tavily ({news_type_for_log})"),
            'タイトル': article.get('title', 'N/A'), '概要': article.get('content', 'N/A'),
            'ソース': source_name, 'URL': article.get('url', '#'), 'api_source': 'Tavily'
        })
    return news_list

def fetch_tavily_company_news(stock_name, api_key):
    err_msg_sdk = "Tavily SDK未インストール"
    if TavilyClient is None: return [], err_msg_sdk, _generate_error_response_text("Tavily (Company)", err_msg_sdk, details="SDK not found.")
    err_msg_key = "Tavily APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("Tavily (Company)", err_msg_key, "401")
    raw_resp_text = _generate_error_response_text("Tavily (Company)", "API call initiated, no response yet.") # Default error
    try:
        client = TavilyClient(api_key=api_key)
        query = f'"{stock_name}"の業績、決算、株価、経営見通し、新製品、または提携に関する日本の最新ニュース'
        resp_json = client.search(query=query, search_depth="basic", topic="news",
                                  max_results=app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], include_domains=["*.jp"], days=30)
        raw_resp_text = json.dumps(resp_json, ensure_ascii=False, indent=2) if resp_json else _generate_error_response_text("Tavily (Company)", "API returned None or empty response.")
        if resp_json and "results" in resp_json: # Check for successful response structure
            formatted_news = _format_tavily_articles(resp_json, "Company")
            return formatted_news, None, raw_resp_text
        else: # Handle cases where resp_json might be an error structure from Tavily or empty
            err_msg_api = f"企業ニュース取得失敗 (Tavily): {resp_json.get('error', 'No results or error in response') if isinstance(resp_json, dict) else 'Invalid response'}"
            return [], err_msg_api, raw_resp_text
    except Exception as e:
        logger.error(f"Tavily企業ニュースAPIエラー ({stock_name}): {e}", exc_info=True)
        err_msg_api = f"企業ニュース取得失敗 (Tavily): {e}"
        return [], err_msg_api, raw_resp_text # raw_resp_text might still be the initial error or updated if API call was made
def fetch_tavily_market_news(api_key):
    err_msg_sdk = "Tavily SDK未インストール"
    if TavilyClient is None: return [], err_msg_sdk, _generate_error_response_text("Tavily (Market)", err_msg_sdk, details="SDK not found.")
    err_msg_key = "Tavily APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("Tavily (Market)", err_msg_key, "401")
    raw_resp_text = _generate_error_response_text("Tavily (Market)", "API call initiated, no response yet.")
    try:
        client = TavilyClient(api_key=api_key)
        query = "日本の株式市場の動向、日経平均、TOPIX、または一般的な相場見通しに関する最新ニュース"
        resp_json = client.search(query=query, search_depth="basic", topic="news",
                                  max_results=app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], include_domains=["*.jp"], days=7)
        raw_resp_text = json.dumps(resp_json, ensure_ascii=False, indent=2) if resp_json else _generate_error_response_text("Tavily (Market)", "API returned None or empty response.")
        if resp_json and "results" in resp_json:
            formatted_news = _format_tavily_articles(resp_json, "Market")
            return formatted_news, None, raw_resp_text
        else:
            err_msg_api = f"市場ニュース取得失敗 (Tavily): {resp_json.get('error', 'No results or error in response') if isinstance(resp_json, dict) else 'Invalid response'}"
            return [], err_msg_api, raw_resp_text
    except Exception as e:
        logger.error(f"Tavily市場ニュースAPIエラー: {e}", exc_info=True)
        err_msg_api = f"市場ニュース取得失敗 (Tavily): {e}"
        return [], err_msg_api, raw_resp_text

# Google Custom Search JSON API
def _format_google_cse_articles(articles_response, news_type_for_log=""):
    news_list = []
    if not articles_response or "items" not in articles_response:
        logger.debug(f"GoogleCSE ({news_type_for_log}): レスポンスに 'items' が見つかりません。レスポンス: {str(articles_response)[:200]}")
        return news_list

    date_metatag_keys = ['article:published_time', 'og:article:published_time', 'pubdate', 'publishdate', 'dc.date', 'dcterms.created',
                         'timestamp', 'date', 'sailthru.date', 'article.published', 'article.created', 'article_date_original',
                         'cXenseParse:recs:publishtime', 'parsely-pub-date', 'datepublished', 'datecreated', 'newsarticle:datepublished',
                         'article:modified_time', 'og:updated_time', 'lastmod', 'dateModified', 'moddate', 'updated_time', 'revised',
                         'datePublished', 'uploadDate']
    snippet_date_patterns = [
        r"(\d{4}年\s*\d{1,2}月\s*\d{1,2}日(?:[ 　]*\d{1,2}時\d{1,2}分(?:秒)?(?:頃)?)?)",
        r"(\d{4}/\d{1,2}/\d{1,2}(?:[ 　]+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)",
        r"(\d{4}-\d{1,2}-\d{1,2}(?:[T 　]\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)Z?)?)", # Simpler ISO Z
        r"(\d{4}-\d{1,2}-\d{1,2}(?:[T 　]\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)?[+-]\d{2}:?\d{2})?)", # ISO with offset
        r"(\d{4}\.\d{1,2}\.\d{1,2}(?:[ 　]+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[uarychilestmbrovg\.]{0,7}\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4})",
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[uarychilestmbrovg\.]{0,7}(?:th|st|nd|rd)?,\s+\d{4})", # Day Mon, Year
        r"(\d{1,2}月\d{1,2}日(?:[ 　]*\d{1,2}時\d{1,2}分(?:秒)?(?:頃)?)?)",
        r"(\d+\s+hours?\s+ago)", r"(\d+\s+days?\s+ago)", r"(\d+\s+weeks?\s+ago)", r"(\d+\s+months?\s+ago)", r"(\d+\s+years?\s+ago)",
        r"(\d+\s*時間前)", r"(\d+\s*日前)", r"(\d+\s*週間前)", r"(\d+\s*ヶ月前)", r"(\d+\s*年前)",
        r"(昨日|今日|yesterday|today)", r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?)",
    ]

    for item_idx, item in enumerate(articles_response.get("items", [])):
        pagemap = item.get('pagemap', {})
        metatags_list = pagemap.get('metatags', [])
        metatags = metatags_list[0] if metatags_list and isinstance(metatags_list[0], dict) else {}
        newsarticle_list = pagemap.get('newsarticle', [])
        newsarticle_meta = newsarticle_list[0] if newsarticle_list and isinstance(newsarticle_list[0], dict) else {}
        article_pagemap_list = pagemap.get('article', [])
        article_pagemap_meta = article_pagemap_list[0] if article_pagemap_list and isinstance(article_pagemap_list[0], dict) else {}

        published_at_str = None
        date_sources_ordered = [newsarticle_meta, article_pagemap_meta, metatags]

        for source_idx, source_dict in enumerate(date_sources_ordered):
            for key_idx, key in enumerate(date_metatag_keys):
                if key in source_dict and source_dict[key]:
                    published_at_str = str(source_dict[key])
                    logger.debug(f"GoogleCSE ({news_type_for_log}) - Item {item_idx+1}/{len(articles_response.get('items',[]))}: Date found in source {source_idx+1} (key '{key}'): '{published_at_str}' for '{item.get('title')}'")
                    break
            if published_at_str: break

        if not published_at_str:
            snippet = item.get('snippet', '').replace('...', ' ')
            for pattern_idx, pattern in enumerate(snippet_date_patterns):
                match = re.search(pattern, snippet)
                if match:
                    extracted_date_str = match.group(1)
                    published_at_str = extracted_date_str.strip()
                    logger.debug(f"GoogleCSE ({news_type_for_log}) - Item {item_idx+1}: Date found in snippet (pattern {pattern_idx+1}): '{published_at_str}' for '{item.get('title')}'")
                    break

        if not published_at_str and item.get('date'):
                 published_at_str = str(item.get('date'))
                 logger.debug(f"GoogleCSE ({news_type_for_log}) - Item {item_idx+1}: Date found in item.date: '{published_at_str}' for '{item.get('title')}'")

        if not published_at_str:
            logger.warning(f"GoogleCSE ({news_type_for_log}) - Item {item_idx+1}: FAILED to extract date for '{item.get('title', 'N/A')[:50]}...'. Snippet: '{item.get('snippet', '')[:70]}...'")

        parsed_date = _parse_datetime_str(published_at_str, [], f"GoogleCSE ({news_type_for_log}, item: {item.get('title', 'N/A')[:30]})")

        source_name = metatags.get('og:site_name', newsarticle_meta.get('publisher', {}).get('name', article_pagemap_meta.get('publisher',{}).get('name','')))
        if not source_name and 'provider' in newsarticle_meta and isinstance(newsarticle_meta['provider'], dict):
                 source_name = newsarticle_meta['provider'].get('name')
        if not source_name:
            try:
                parsed_url = urlparse(item.get('link', '#'))
                if parsed_url.hostname: source_name = parsed_url.hostname.replace("www.", "")
                else: source_name = item.get('displayLink', 'N/A')
            except: source_name = item.get('displayLink', 'N/A')

        news_list.append({
            '日付': parsed_date, 'タイトル': item.get('title', 'N/A'), '概要': item.get('snippet', 'N/A').replace('\n', ' ').strip(),
            'ソース': source_name if source_name else 'N/A', 'URL': item.get('link', '#'), 'api_source': 'GoogleCSE'
        })
    return news_list

def fetch_google_cse_company_news(stock_name, api_key, cse_id):
    err_msg_sdk = "google-api-python-client未インストール"
    if google_build_service is None: return [], err_msg_sdk, _generate_error_response_text("GoogleCSE (Company)", err_msg_sdk, details="SDK not found.")
    err_msg_key = "Google CSE APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("GoogleCSE (Company)", err_msg_key, "401")
    err_msg_id = "Google CSE ID未設定"
    if not cse_id: return [], err_msg_id, _generate_error_response_text("GoogleCSE (Company)", err_msg_id, "400")
    dt_now = datetime.datetime.now(datetime.timezone.utc)
    one_month_ago = dt_now - relativedelta(months=1)
    query = f'"{stock_name}" (業績 OR 決算 OR 株価 OR 見通し OR 新製品 OR 提携) site:.jp after:{one_month_ago.strftime("%Y-%m-%d")}'
    raw_resp_text = _generate_error_response_text("GoogleCSE (Company)", "API call initiated, no response yet.")
    try:
        service = google_build_service("customsearch", "v1", developerKey=api_key)
        resp_json = service.cse().list(q=query, cx=cse_id, lr='lang_ja', num=app_config.NEWS_SERVICE_CONFIG["max_news_per_api"]).execute()
        raw_resp_text = json.dumps(resp_json, ensure_ascii=False, indent=2) if resp_json else _generate_error_response_text("GoogleCSE (Company)", "API returned None or empty response.")
        if resp_json and "items" in resp_json: # Check for successful response structure
            formatted_news = _format_google_cse_articles(resp_json, "Company")
            return formatted_news, None, raw_resp_text
        else: # Handle error structure or no items
            err_msg_api = f"企業ニュース取得失敗 (GoogleCSE): {resp_json.get('error', {}).get('message', 'No items or error in response') if isinstance(resp_json, dict) else 'Invalid response'}"
            return [], err_msg_api, raw_resp_text
    except GoogleHttpError as e:
        reason = e._get_reason() if hasattr(e, '_get_reason') else str(e)
        logger.error(f"GoogleCSE (Company) HTTPエラー: {reason}", exc_info=True)
        err_msg_api = f"企業ニュース取得失敗 (GoogleCSE HTTPError): {reason}"
        # Try to get error details from the exception content if possible
        details = str(e.content) if hasattr(e, 'content') else str(e)
        raw_resp_text = _generate_error_response_text("GoogleCSE (Company)", err_msg_api, status_code=e.resp.status if hasattr(e, 'resp') else "N/A", details=details)
        return [], err_msg_api, raw_resp_text
    except Exception as e:
        logger.error(f"GoogleCSE (Company) APIコール中エラー: {e}", exc_info=True)
        err_msg_api = f"企業ニュース取得失敗 (GoogleCSE): {e}"
        return [], err_msg_api, _generate_error_response_text("GoogleCSE (Company)", err_msg_api, details=str(e))


def fetch_google_cse_market_news(api_key, cse_id):
    err_msg_sdk = "google-api-python-client未インストール"
    if google_build_service is None: return [], err_msg_sdk, _generate_error_response_text("GoogleCSE (Market)", err_msg_sdk, details="SDK not found.")
    err_msg_key = "Google CSE APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("GoogleCSE (Market)", err_msg_key, "401")
    err_msg_id = "Google CSE ID未設定"
    if not cse_id: return [], err_msg_id, _generate_error_response_text("GoogleCSE (Market)", err_msg_id, "400")
    dt_now = datetime.datetime.now(datetime.timezone.utc)
    one_week_ago = dt_now - relativedelta(weeks=1)
    query = f"(日本株 OR 株式市場 OR 日経平均 OR TOPIX OR 相場見通し) site:.jp after:{one_week_ago.strftime('%Y-%m-%d')}"
    raw_resp_text = _generate_error_response_text("GoogleCSE (Market)", "API call initiated, no response yet.")
    try:
        service = google_build_service("customsearch", "v1", developerKey=api_key)
        resp_json = service.cse().list(q=query, cx=cse_id, lr='lang_ja', num=app_config.NEWS_SERVICE_CONFIG["max_news_per_api"]).execute()
        raw_resp_text = json.dumps(resp_json, ensure_ascii=False, indent=2) if resp_json else _generate_error_response_text("GoogleCSE (Market)", "API returned None or empty response.")
        if resp_json and "items" in resp_json:
            formatted_news = _format_google_cse_articles(resp_json, "Market")
            return formatted_news, None, raw_resp_text
        else:
            err_msg_api = f"市場ニュース取得失敗 (GoogleCSE): {resp_json.get('error', {}).get('message', 'No items or error in response') if isinstance(resp_json, dict) else 'Invalid response'}"
            return [], err_msg_api, raw_resp_text
    except GoogleHttpError as e:
        reason = e._get_reason() if hasattr(e, '_get_reason') else str(e)
        logger.error(f"GoogleCSE (Market) HTTPエラー: {reason}", exc_info=True)
        err_msg_api = f"市場ニュース取得失敗 (GoogleCSE HTTPError): {reason}"
        details = str(e.content) if hasattr(e, 'content') else str(e)
        raw_resp_text = _generate_error_response_text("GoogleCSE (Market)", err_msg_api, status_code=e.resp.status if hasattr(e, 'resp') else "N/A", details=details)
        return [], err_msg_api, raw_resp_text
    except Exception as e:
        logger.error(f"GoogleCSE (Market) APIコール中エラー: {e}", exc_info=True)
        err_msg_api = f"市場ニュース取得失敗 (GoogleCSE): {e}"
        return [], err_msg_api, _generate_error_response_text("GoogleCSE (Market)", err_msg_api, details=str(e))

# Bing Web Search API
def _format_bing_articles(articles_response, news_type_for_log=""):
    news_list = []
    if not articles_response or "value" not in articles_response: return news_list
    date_formats = [{"format": "iso"}]
    for article in articles_response.get("value", []):
        source_name = article.get('provider', [{}])[0].get('name', 'N/A') if article.get('provider') else 'N/A'
        news_list.append({
            '日付': _parse_datetime_str(article.get('datePublished'), date_formats, f"BingNews ({news_type_for_log})"),
            'タイトル': article.get('name', 'N/A'), '概要': article.get('description', 'N/A'),
            'ソース': source_name, 'URL': article.get('url', '#'), 'api_source': 'BingNews'
        })
    return news_list

def fetch_bing_company_news(stock_name, api_key):
    err_msg_key = "Bing News APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("BingNews (Company)", err_msg_key, "401")
    BASE_URL = "https://api.bing.microsoft.com/v7.0/news/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": f'"{stock_name}" (業績 OR 決算 OR 株価 OR 見通し OR 新製品 OR 提携)', "mkt": "ja-JP",
              "count": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "sortBy": "Relevance", "freshness": "Month"}
    raw_resp_text = _make_api_request(BASE_URL, params, headers=headers, api_name="BingNews (Company) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"Bing (Company) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and resp_json.get("_type") == "News":
        formatted_news = _format_bing_articles(resp_json, "Company")
        return formatted_news, None, raw_resp_text

    err_msg_api = "企業ニュース取得失敗 (BingNews)"
    if resp_json and resp_json.get("errors"): # Bing error format
        err_details = resp_json["errors"][0].get("message", "Unknown Bing error")
        err_msg_api = f"企業ニュース取得失敗 (BingNews): {err_details}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("BingNews (Company)", err_msg_api, details="Response was None or not valid success JSON.")

def fetch_bing_market_news(api_key):
    err_msg_key = "Bing News APIキー未設定"
    if not api_key: return [], err_msg_key, _generate_error_response_text("BingNews (Market)", err_msg_key, "401")
    BASE_URL = "https://api.bing.microsoft.com/v7.0/news/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": f"(日本株 OR 株式市場 OR 日経平均 OR TOPIX OR 相場見通し)", "mkt": "ja-JP",
              "count": app_config.NEWS_SERVICE_CONFIG["max_news_per_api"], "sortBy": "Date", "freshness": "Week"}
    raw_resp_text = _make_api_request(BASE_URL, params, headers=headers, api_name="BingNews (Market) Raw", return_raw_text=True)
    resp_json = None
    if raw_resp_text:
        try: resp_json = json.loads(raw_resp_text)
        except json.JSONDecodeError: logger.error(f"Bing (Market) Raw JSONデコード失敗: {raw_resp_text[:200]}...")

    if resp_json and resp_json.get("_type") == "News":
        formatted_news = _format_bing_articles(resp_json, "Market")
        return formatted_news, None, raw_resp_text

    err_msg_api = "市場ニュース取得失敗 (BingNews)"
    if resp_json and resp_json.get("errors"):
        err_details = resp_json["errors"][0].get("message", "Unknown Bing error")
        err_msg_api = f"市場ニュース取得失敗 (BingNews): {err_details}"
    return [], err_msg_api, raw_resp_text if raw_resp_text else _generate_error_response_text("BingNews (Market)", err_msg_api, details="Response was None or not valid success JSON.")


# --- 重複削除処理 ---
def _deduplicate_news_list(articles_list: list, prefix_length: int) -> list:
    seen_identifiers = set()
    deduplicated_list = []
    for article in articles_list:
        title = article.get('タイトル', 'N/A')
        url = article.get('URL', '#')
        parsed_url = urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}" if parsed_url.scheme and parsed_url.netloc else url
        check_key_title_part = title[:prefix_length].strip().lower() if title != 'N/A' and prefix_length > 0 else title.lower()
        identifier = (check_key_title_part, normalized_url.lower())
        if title == 'N/A' and url == '#':
            deduplicated_list.append(article); continue
        if identifier not in seen_identifiers:
            seen_identifiers.add(identifier)
            deduplicated_list.append(article)
        else: logger.debug(f"重複項目（キー: '{identifier}'）を検出、削除: {title} (URL: {url})")
    return deduplicated_list

# --- ▼▼▼ ここから修正 ▼▼▼ ---
def fetch_all_stock_news(
        stock_name: str,
        active_apis_config: dict,
        api_key_manager
    ) -> dict:
    all_fetched_company_news = []
    all_fetched_market_news = []
    api_errors = {api_name: {"company": None, "market": None} for api_name in active_apis_config.keys()}
    default_unprocessed_company = _generate_error_response_text("N/A", "Company news processing not initiated for this API.")
    default_unprocessed_market = _generate_error_response_text("N/A", "Market news processing not initiated for this API.")
    raw_api_responses = {
        api_name: {
            "company": default_unprocessed_company.replace('"api": "N/A"', f'"api": "{api_name} (Company)"'),
            "market": default_unprocessed_market.replace('"api": "N/A"', f'"api": "{api_name} (Market)"')
        } for api_name in active_apis_config.keys()
    }

    api_fetchers = {
        "newsapi": (fetch_newsapi_company_news, fetch_newsapi_market_news), "gnews": (fetch_gnews_company_news, fetch_gnews_market_news),
        "brave": (fetch_brave_company_news, fetch_brave_market_news), "tavily": (fetch_tavily_company_news, fetch_tavily_market_news),
        "google_cse": (fetch_google_cse_company_news, fetch_google_cse_market_news), "bing": (fetch_bing_company_news, fetch_bing_market_news),
    }
    api_key_names_map = {
        "newsapi": "NEWS_API_KEY", "gnews": "GNEWS_API_KEY", "brave": "BRAVE_API_KEY", "tavily": "TAVILY_API_KEY",
        "google_cse": "GOOGLE_CSE_API_KEY", "bing": "BING_API_KEY",
    }
    google_cse_id_key_name = "GOOGLE_CSE_ID"

    # --- 企業ニュース取得 ---
    logger.info(f"--- 企業ニュース取得フェーズ開始 ({stock_name}) [並列処理] ---")
    company_cache_filepath = _get_cache_filepath("company_news", stock_name, app_config.IS_CLOUD_RUN)
    cached_company_news, cached_company_raw_responses = _load_from_cache(company_cache_filepath, app_config.NEWS_SERVICE_CONFIG["cache_expiry_hours"])

    if cached_company_news is not None and cached_company_raw_responses is not None:
        all_fetched_company_news = cached_company_news
        for api_name_key, responses_for_api in cached_company_raw_responses.items():
            if api_name_key not in raw_api_responses: raw_api_responses[api_name_key] = {}
            raw_api_responses[api_name_key]["company"] = responses_for_api.get("company", raw_api_responses[api_name_key]["company"])
            if responses_for_api.get("market"):
                raw_api_responses[api_name_key]["market"] = responses_for_api.get("market", raw_api_responses[api_name_key]["market"])
        logger.info(f"企業ニュースと生レスポンスをキャッシュからロード: {len(all_fetched_company_news)}件 ({company_cache_filepath})")
    else:
        with ThreadPoolExecutor(max_workers=len(active_apis_config)) as executor:
            future_to_api = {}
            active_apis = {k: v for k, v in active_apis_config.items() if v and k in api_fetchers}

            for api_name in active_apis:
                api_key_actual_name = api_key_names_map.get(api_name)
                api_key_value = api_key_manager.get_api_key(api_key_actual_name) if api_key_actual_name else None
                fetch_comp_func = api_fetchers[api_name][0]

                if api_name == "google_cse":
                    cse_id_value = api_key_manager.get_api_key(google_cse_id_key_name)
                    task = partial(fetch_comp_func, stock_name, api_key_value, cse_id_value)
                else:
                    task = partial(fetch_comp_func, stock_name, api_key_value)

                logger.info(f"  Submitting company news task for {api_name.upper()}...")
                future_to_api[executor.submit(task)] = api_name

            for future in as_completed(future_to_api):
                api_name = future_to_api[future]
                try:
                    comp_news, err_comp, raw_comp_resp_text = future.result()
                    all_fetched_company_news.extend(comp_news)
                    api_errors[api_name]["company"] = err_comp
                    raw_api_responses[api_name]["company"] = raw_comp_resp_text if raw_comp_resp_text else _generate_error_response_text(api_name, "No response text from fetch function (Company).")
                    logger.info(f"  {api_name.upper()} 企業ニュース取得完了 (件数: {len(comp_news)}, エラー: {err_comp})")
                except Exception as exc:
                    err_msg = f"企業ニュースの並列取得中に例外発生 ({api_name}): {exc}"
                    logger.error(err_msg, exc_info=True)
                    api_errors[api_name]["company"] = err_msg
                    raw_api_responses[api_name]["company"] = _generate_error_response_text(api_name, "Exception during parallel fetch (Company)", details=str(exc))

        if company_cache_filepath:
            _save_to_cache(company_cache_filepath, all_fetched_company_news, raw_api_responses)
    logger.info(f"--- 企業ニュース取得フェーズ終了 ({stock_name}) ---")

    # --- 市場ニュース取得 ---
    logger.info("--- 市場ニュース取得フェーズ開始 [並列処理] ---")
    market_cache_filepath = _get_cache_filepath("market_news", is_cloud_run=app_config.IS_CLOUD_RUN)
    cached_market_news_data, cached_market_raw_responses_only_market = _load_from_cache(market_cache_filepath, app_config.NEWS_SERVICE_CONFIG["cache_expiry_hours"])

    if cached_market_news_data is not None and cached_market_raw_responses_only_market is not None:
        all_fetched_market_news = cached_market_news_data
        for api_name_key, responses_for_api in cached_market_raw_responses_only_market.items():
            if api_name_key not in raw_api_responses: raw_api_responses[api_name_key] = {}
            if responses_for_api.get("market"):
                raw_api_responses[api_name_key]["market"] = responses_for_api.get("market", raw_api_responses[api_name_key]["market"])
        logger.info(f"市場ニュースと生レスポンスをキャッシュからロード: {len(all_fetched_market_news)}件 ({market_cache_filepath})")
    else:
        market_specific_raw_responses_for_cache = {api_name: {"market": _generate_error_response_text(api_name, "Not processed", details="Market news for cache not initiated.")} for api_name in active_apis_config.keys()}
        with ThreadPoolExecutor(max_workers=len(active_apis_config)) as executor:
            future_to_api_market = {}
            active_apis = {k: v for k, v in active_apis_config.items() if v and k in api_fetchers}

            for api_name in active_apis:
                api_key_actual_name = api_key_names_map.get(api_name)
                api_key_value = api_key_manager.get_api_key(api_key_actual_name) if api_key_actual_name else None
                fetch_mkt_func = api_fetchers[api_name][1]

                if api_name == "google_cse":
                    cse_id_value = api_key_manager.get_api_key(google_cse_id_key_name)
                    task = partial(fetch_mkt_func, api_key_value, cse_id_value)
                else:
                    task = partial(fetch_mkt_func, api_key_value)

                logger.info(f"  Submitting market news task for {api_name.upper()}...")
                future_to_api_market[executor.submit(task)] = api_name

            for future in as_completed(future_to_api_market):
                api_name = future_to_api_market[future]
                try:
                    mkt_news, err_mkt, raw_mkt_resp_text = future.result()
                    all_fetched_market_news.extend(mkt_news)
                    api_errors[api_name]["market"] = err_mkt
                    raw_api_responses[api_name]["market"] = raw_mkt_resp_text if raw_mkt_resp_text else _generate_error_response_text(api_name, "No response text from fetch function (Market).")
                    if api_name in market_specific_raw_responses_for_cache:
                        market_specific_raw_responses_for_cache[api_name]["market"] = raw_api_responses[api_name]["market"]
                    logger.info(f"  {api_name.upper()} 市場ニュース取得完了 (件数: {len(mkt_news)}, エラー: {err_mkt})")
                except Exception as exc:
                    err_msg = f"市場ニュースの並列取得中に例外発生 ({api_name}): {exc}"
                    logger.error(err_msg, exc_info=True)
                    api_errors[api_name]["market"] = err_msg
                    raw_api_responses[api_name]["market"] = _generate_error_response_text(api_name, "Exception during parallel fetch (Market)", details=str(exc))

        if market_cache_filepath:
            _save_to_cache(market_cache_filepath, all_fetched_market_news, market_specific_raw_responses_for_cache)
    logger.info("--- 市場ニュース取得フェーズ終了 ---")

    deduplicated_company_news = _deduplicate_news_list(all_fetched_company_news, app_config.NEWS_SERVICE_CONFIG["duplicate_title_prefix_length"])
    deduplicated_market_news = _deduplicate_news_list(all_fetched_market_news, app_config.NEWS_SERVICE_CONFIG["duplicate_title_prefix_length"])

    return {
        "stock_name": stock_name,
        "retrieved_from_cache": {"company_news": cached_company_news is not None, "market_news": cached_market_news_data is not None},
        "all_company_news_deduplicated": deduplicated_company_news, "all_market_news_deduplicated": deduplicated_market_news,
        "api_errors": api_errors, "raw_api_responses": raw_api_responses
    }
# --- ▲▲▲ ここまで修正 ▲▲▲ ---
