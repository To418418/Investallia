# data_display_page.py
import streamlit as st
import google.generativeai as genai
import os
import json
import re
import pandas as pd
import numpy as np
from collections import defaultdict
import copy # For deep copying dictionaries


# --- 定数・設定 ---
key_dict = {
    "Reference date": "基準日",
    "Code": "コード",
    "Company Name ja": "銘柄名",
    "Market_Product Category ja": "市場・商品区分",
    "33 Sector Code ja": "33業種コード",
    "33 Sector Classification ja": "33業種区分",
    "17 Sector Code ja": "17業種コード",
    "17 Sector Classification ja": "17業種区分",
    "Size Code ja": "規模コード",
    "Size Classification ja": "規模区分",
    "yf_ticker": "yfinanceティッカー",
    "fetch_timestamp_tokyo": "データ取得タイムスタンプ（東京時間）",
    "address1": "住所1",
    "city": "市",
    "zip": "郵便番号",
    "country": "国",
    "phone": "電話番号",
    "website": "ウェブサイト",
    "industry": "産業",
    "industryKey": "産業キー",
    "industryDisp": "産業（表示名）",
    "sector": "セクター",
    "sectorKey": "セクターキー",
    "sectorDisp": "セクター（表示名）",
    "longBusinessSummary": "長期事業概要",
    "fullTimeEmployees": "正社員数",
    "companyOfficers": "役員情報",
    "auditRisk": "監査リスク",
    "boardRisk": "取締役会リスク",
    "compensationRisk": "報酬リスク",
    "shareHolderRightsRisk": "株主権リスク",
    "overallRisk": "全体リスク",
    "governanceEpochDate": "ガバナンスエポック日付",
    "compensationAsOfEpochDate": "報酬基準エポック日付",
    "irWebsite": "IRウェブサイト",
    "executiveTeam": "経営陣情報",
    "maxAge": "最大経過時間",
    "priceHint": "価格ヒント",
    "previousClose": "前日終値",
    "open": "始値",
    "dayLow": "日中安値",
    "dayHigh": "日中高値",
    "regularMarketPreviousClose": "通常市場前日終値",
    "regularMarketOpen": "通常市場始値",
    "regularMarketDayLow": "通常市場日中安値",
    "regularMarketDayHigh": "通常市場日中高値",
    "dividendRate": "配当率",
    "dividendYield": "配当利回り",
    "exDividendDate": "配当落ち日",
    "payoutRatio": "配当性向",
    "fiveYearAvgDividendYield": "5年平均配当利回り",
    "beta": "ベータ値",
    "trailingPE": "実績PER",
    "forwardPE": "予想PER",
    "volume": "出来高",
    "regularMarketVolume": "通常市場出来高",
    "averageVolume": "平均出来高",
    "averageVolume10days": "10日間平均出来高",
    "averageDailyVolume10Day": "10日平均出来高",
    "bid": "買気配値",
    "ask": "売気配値",
    "bidSize": "買気配数量",
    "askSize": "売気配数量",
    "marketCap": "時価総額",
    "fiftyTwoWeekLow": "52週安値",
    "fiftyTwoWeekHigh": "52週高値",
    "priceToSalesTrailing12Months": "株価売上高倍率（実績）",
    "fiftyDayAverage": "50日移動平均株価",
    "twoHundredDayAverage": "200日移動平均株価",
    "trailingAnnualDividendRate": "年間配当率（実績）",
    "trailingAnnualDividendYield": "年間配当利回り（実績）",
    "currency": "通貨",
    "tradeable": "取引可否",
    "enterpriseValue": "企業価値（EV）",
    "profitMargins": "純利益率",
    "floatShares": "浮動株数",
    "sharesOutstanding": "発行済株式総数",
    "heldPercentInsiders": "内部者保有率",
    "heldPercentInstitutions": "機関投資家保有率",
    "impliedSharesOutstanding": "潜在株式数",
    "bookValue": "1株当たり純資産（BPS）",
    "priceToBook": "株価純資産倍率（PBR）",
    "lastFiscalYearEnd": "直近会計年度末日",
    "nextFiscalYearEnd": "次期会計年度末日",
    "mostRecentQuarter": "直近四半期末日",
    "earningsQuarterlyGrowth": "四半期利益成長率",
    "netIncomeToCommon": "普通株主帰属純利益",
    "trailingEps": "1株当たり利益（EPS実績）",
    "forwardEps": "1株当たり利益（EPS予想）",
    "lastSplitFactor": "直近株式分割比率",
    "lastSplitDate": "直近株式分割日",
    "enterpriseToRevenue": "EV/売上高倍率",
    "enterpriseToEbitda": "EV/EBITDA倍率",
    "52WeekChange": "52週株価変動率",
    "SandP52WeekChange": "S&P500指数 52週変動率",
    "lastDividendValue": "直近1株当たり配当金",
    "lastDividendDate": "直近配当基準日",
    "quoteType": "銘柄種別",
    "currentPrice": "現在株価",
    "targetHighPrice": "目標株価（高値）",
    "targetLowPrice": "目標株価（安値）",
    "targetMeanPrice": "目標株価（平均）",
    "targetMedianPrice": "目標株価（中央値）",
    "recommendationMean": "アナリスト評価（平均）",
    "recommendationKey": "アナリスト評価（キー）",
    "numberOfAnalystOpinions": "アナリスト評価数",
    "totalCash": "現預金合計",
    "totalCashPerShare": "1株当たり現預金",
    "ebitda": "EBITDA（単体）",
    "totalDebt": "有利子負債合計",
    "quickRatio": "当座比率",
    "currentRatio": "流動比率",
    "totalRevenue": "総収益（単体）",
    "debtToEquity": "D/Eレシオ（負債資本倍率）",
    "revenuePerShare": "1株当たり売上高",
    "returnOnAssets": "総資産利益率（ROA）",
    "returnOnEquity": "自己資本利益率（ROE）",
    "grossProfits": "売上総利益（単体）",
    "freeCashflow": "フリーキャッシュフロー",
    "operatingCashflow": "営業キャッシュフロー",
    "earningsGrowth": "利益成長率（単体）",
    "revenueGrowth": "収益成長率",
    "grossMargins": "売上総利益率",
    "ebitdaMargins": "EBITDAマージン",
    "operatingMargins": "営業利益率",
    "financialCurrency": "財務報告通貨",
    "language": "言語",
    "region": "地域",
    "typeDisp": "種類（表示用）",
    "quoteSourceName": "株価情報源",
    "triggerable": "トリガー可能",
    "customPriceAlertConfidence": "カスタム価格アラート信頼度",
    "shortName": "略称", # DataFrameからは除外
    "longName": "正式名称", # DataFrameからは除外
    "regularMarketChange": "通常取引：株価変動額",
    "regularMarketDayRange": "通常取引：日中値幅",
    "fullExchangeName": "取引所正式名称",
    "averageDailyVolume3Month": "3ヶ月平均出来高",
    "fiftyTwoWeekLowChange": "52週安値からの変動額",
    "fiftyTwoWeekLowChangePercent": "52週安値からの変動率",
    "fiftyTwoWeekRange": "52週値幅",
    "fiftyTwoWeekHighChange": "52週高値からの変動額",
    "fiftyTwoWeekHighChangePercent": "52週高値からの変動率",
    "fiftyTwoWeekChangePercent": "52週変動率（%）",
    "earningsTimestamp": "決算発表タイムスタンプ",
    "earningsTimestampStart": "決算期間開始タイムスタンプ",
    "earningsTimestampEnd": "決算期間終了タイムスタンプ",
    "earningsCallTimestampStart": "決算説明会開始タイムスタンプ",
    "earningsCallTimestampEnd": "決算説明会終了タイムスタンプ",
    "isEarningsDateEstimate": "決算発表日（予想フラグ）",
    "epsTrailingTwelveMonths": "EPS（過去12ヶ月）",
    "epsForward": "EPS（予想）",
    "fiftyDayAverageChange": "50日平均からの変動額",
    "fiftyDayAverageChangePercent": "50日平均からの変動率",
    "twoHundredDayAverageChange": "200日平均からの変動額",
    "twoHundredDayAverageChangePercent": "200日平均からの変動率",
    "sourceInterval": "情報源更新間隔",
    "exchangeDataDelayedBy": "取引所データ遅延（分）",
    "averageAnalystRating": "アナリスト評価（平均テキスト）",
    "corporateActions": "コーポレートアクション",
    "regularMarketTime": "通常取引時刻",
    "exchange": "取引所コード",
    "messageBoardId": "掲示板ID",
    "exchangeTimezoneName": "取引所タイムゾーン名",
    "exchangeTimezoneShortName": "取引所タイムゾーン略称",
    "gmtOffSetMilliseconds": "GMTオフセット（ミリ秒）",
    "market": "市場コード",
    "esgPopulated": "ESGデータ有無",
    "regularMarketChangePercent": "通常取引：株価変動率",
    "regularMarketPrice": "通常取引：現在株価",
    "cryptoTradeable": "暗号資産取引可否",
    "hasPrePostMarketData": "時間外取引データ有無",
    "firstTradeDateMilliseconds": "上場日（ミリ秒）",
    "marketState": "市場状態",
    "trailingPegRatio": "PEGレシオ（実績）",
    "Tax Effect Of Unusual Items": "特別損益税効果額",
    "Tax Rate For Calcs": "計算用税率",
    "Normalized EBITDA": "EBITDA（正規化）",
    "Total Unusual Items": "特別損益合計",
    "Total Unusual Items Excluding Goodwill": "のれん償却前特別損益合計",
    "Net Income From Continuing Operation Net Minority Interest": "継続事業純利益（非支配持分控除後）",
    "Reconciled Depreciation": "減価償却費（調整後）",
    "Reconciled Cost Of Revenue": "売上原価（調整後）",
    "EBITDA": "EBITDA",
    "EBIT": "EBIT（金利・税引前利益）",
    "Net Interest Income": "純金利収益",
    "Interest Expense": "支払利息",
    "Interest Income": "受取利息",
    "Normalized Income": "純利益（正規化）",
    "Net Income From Continuing And Discontinued Operation": "継続・非継続事業純利益",
    "Total Expenses": "総費用",
    "Total Operating Income As Reported": "営業利益（報告ベース）",
    "Diluted Average Shares": "希薄化後平均株式数",
    "Basic Average Shares": "発行済平均株式数",
    "Diluted EPS": "希薄化後EPS",
    "Basic EPS": "基本的EPS",
    "Diluted NI Availto Com Stockholders": "普通株主帰属希薄化後純利益",
    "Average Dilution Earnings": "希薄化調整額",
    "Net Income Common Stockholders": "普通株主帰属純利益",
    "Otherunder Preferred Stock Dividend": "優先株配当関連調整",
    "Net Income": "純利益",
    "Minority Interests": "少数株主持分利益",
    "Net Income Including Noncontrolling Interests": "少数株主持分含む純利益",
    "Net Income Continuous Operations": "継続事業純利益",
    "Tax Provision": "法人税等",
    "Pretax Income": "税引前利益",
    "Other Income Expense": "その他営業外損益",
    "Other Non Operating Income Expenses": "その他営業外収益費用（純額）",
    "Earnings From Equity Interest": "持分法投資利益",
    "Gain On Sale Of Security": "有価証券売却益",
    "Net Non Operating Interest Income Expense": "純営業外受取支払利息",
    "Total Other Finance Cost": "その他財務費用合計",
    "Interest Expense Non Operating": "支払利息（営業外）",
    "Interest Income Non Operating": "受取利息（営業外）",
    "Operating Income": "営業利益",
    "Operating Expense": "営業費用",
    "Selling General And Administration": "販売費及び一般管理費",
    "Gross Profit": "売上総利益",
    "Cost Of Revenue": "売上原価",
    "Total Revenue": "総収益",
    "Operating Revenue": "営業収益",
    "dividends_history": "配当履歴",
    "EPS Estimate": "EPS予想（アナリスト）",
    "Reported EPS": "EPS実績（報告ベース）",
    "EPS Surprise(%)": "EPSサプライズ（%）",
    "recommendations": "アナリスト推奨（詳細）",
    "amount": "金額",
    "date": "日付",
    "revenue": "売上高",
    "earnings": "利益",
    "dividends": "配当金",
    "yearly": "年間",
    "quarterly": "四半期",
    "financialsChart": "財務チャート",
    "profile": "企業概要"
}
KEYS_DESCRIPTIONS_FULL = "\n".join([f"{key}: {value}" for key, value in key_dict.items()])

# --- ヘルパー関数 ---
def is_year_key(key: str) -> bool:
    if not isinstance(key, str): return False
    return bool(re.match(r"^\d{4}$", key))

def is_full_date_key(key: str) -> bool:
    if not isinstance(key, str): return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", key))

def get_fiscal_year(date_str: str) -> int | None:
    try:
        if is_year_key(date_str):
            return int(date_str)
        elif is_full_date_key(date_str):
            year = int(date_str[:4])
            month = int(date_str[5:7])
            return year - 1 if month <= 3 else year # 3月決算を想定
        else:
            if len(date_str) >= 4 and date_str[:4].isdigit():
                year_candidate = int(date_str[:4])
                if len(date_str) >= 6 and date_str[4:6].isdigit() and 1 <= int(date_str[4:6]) <= 12:
                    month_candidate = int(date_str[4:6])
                    return year_candidate - 1 if month_candidate <= 3 else year_candidate
                return year_candidate
            return None
    except ValueError:
        return None

def determine_numeric_scale_and_format(series: pd.Series, col_name: str = ""):
    """数値列のスケールと書式を判定し、単位換算係数、接尾辞、書式テンプレート、パーセントフラグを返す。"""
    if series.empty:
        return 1, "", "{:.0f}", False

    numeric_series = pd.to_numeric(series, errors='coerce').dropna()
    if numeric_series.empty:
        return 1, "", "{:.0f}", False

    is_percentage = False
    if col_name:
        normalized_col_name = col_name.lower()
        percent_keywords = ['率', '利回り', 'ratio', 'percent', 'yield', 'changepercent', 'growth']
        if any(kw in normalized_col_name for kw in percent_keywords):
            if not numeric_series.empty:
                if numeric_series.abs().max() <= 1.01 :
                    is_percentage = True
    if is_percentage:
        return 1, "%", "{:.2%}", True

    min_val_orig = numeric_series.min()
    max_val_orig = numeric_series.max()
    abs_max = max(abs(min_val_orig), abs(max_val_orig))

    if abs_max == 0: return 1, "", "{:,.0f}", False
    if abs_max >= 1_000_000_000_000: return 1_000_000_000_000, "兆円", "{:,.2f}", False
    elif abs_max >= 1_000_000_000: return 100_000_000, "億円", "{:,.1f}", False
    elif abs_max >= 1_000_000: return 1_000_000, "百万円", "{:,.1f}", False
    elif abs_max >= 10_000: return 10_000, "万円", "{:,.0f}", False
    elif abs_max >= 1_000: return 1_000, "千円", "{:,.0f}", False

    if abs_max < 0.01 and abs_max != 0: return 1, "", "{:.4f}", False
    elif abs_max < 0.1: return 1, "", "{:.3f}", False
    elif abs_max < 1: return 1, "", "{:.2f}", False
    elif abs_max < 100: return 1, "", "{:,.1f}", False

    return 1, "", "{:,.0f}", False


def preprocess_and_aggregate_data(item_data, key_dict_local):
    processed_data = copy.deepcopy(item_data)
    keys_to_delete_after_aggregation = set()

    if 'dividends_history' in processed_data and isinstance(processed_data['dividends_history'], dict):
        annual_dividends = defaultdict(float)
        has_aggregatable_dividends = False
        for date_key, div_info in processed_data['dividends_history'].items():
            fiscal_year = get_fiscal_year(str(date_key))
            amount_val = None
            if isinstance(div_info, dict) and 'amount' in div_info:
                amount_val = div_info['amount']
            elif isinstance(div_info, (int, float, np.number)):
                amount_val = div_info
            if fiscal_year and isinstance(amount_val, (int, float, np.number)):
                try:
                    annual_dividends[fiscal_year] += float(amount_val)
                    has_aggregatable_dividends = True
                except (ValueError, TypeError): pass
        if has_aggregatable_dividends:
            summary_key = f"{key_dict_local.get('dividends_history','配当履歴')}_年間合計"
            processed_data[summary_key] = { f"{year}年度": total_amount for year, total_amount in annual_dividends.items() }
            keys_to_delete_after_aggregation.add('dividends_history')

    if 'financialsChart' in processed_data and isinstance(processed_data['financialsChart'], dict):
        fc_annual_summary = defaultdict(lambda: defaultdict(float))
        has_fc_aggregated_data = False
        original_fc_data = processed_data['financialsChart']
        for period_type in ['yearly', 'quarterly']:
            if period_type in original_fc_data and isinstance(original_fc_data[period_type], list):
                for entry in original_fc_data[period_type]:
                    if isinstance(entry, dict) and 'date' in entry:
                        date_val = str(entry.get('date'))
                        fiscal_year = get_fiscal_year(date_val)
                        if fiscal_year:
                            for metric_en in ['revenue', 'earnings', 'dividends']:
                                if metric_en in entry and isinstance(entry[metric_en], (int, float, np.number)):
                                    try:
                                        metric_ja = key_dict_local.get(metric_en, metric_en)
                                        period_ja = key_dict_local.get(period_type, period_type)
                                        fc_metric_base_name = f"{period_ja}_{metric_ja}"
                                        fc_annual_summary[fiscal_year][fc_metric_base_name] += float(entry[metric_en])
                                        has_fc_aggregated_data = True
                                    except (ValueError, TypeError): pass
        if has_fc_aggregated_data:
            summary_key = f"{key_dict_local.get('financialsChart','財務チャート')}_年間集計"
            processed_data[summary_key] = { f"{year}年度": metrics_dict for year, metrics_dict in fc_annual_summary.items() }
            keys_to_delete_after_aggregation.add('financialsChart')

    other_date_keyed_metrics = []
    for key, value in processed_data.items():
        if key in keys_to_delete_after_aggregation: continue
        if isinstance(value, dict) and value:
            all_sub_keys_are_dates = True
            has_numeric_values = False
            for sub_key_str, sub_value in value.items():
                if not (is_full_date_key(str(sub_key_str)) or is_year_key(str(sub_key_str))):
                    all_sub_keys_are_dates = False; break
                if isinstance(sub_value, (int, float, np.number)): has_numeric_values = True
            if all_sub_keys_are_dates and has_numeric_values:
                other_date_keyed_metrics.append(key)
    for top_key in other_date_keyed_metrics:
        current_dict_to_check = processed_data[top_key]
        annual_values = defaultdict(float)
        has_any_aggregatable_data_in_block = False
        for date_key_str, value_item in current_dict_to_check.items():
            fiscal_year = get_fiscal_year(str(date_key_str))
            if fiscal_year and isinstance(value_item, (int, float, np.number)):
                try:
                    annual_values[fiscal_year] += float(value_item)
                    has_any_aggregatable_data_in_block = True
                except (ValueError, TypeError): pass
        if has_any_aggregatable_data_in_block:
            summary_key = f"{key_dict_local.get(top_key,top_key)}_年間合計"
            processed_data[summary_key] = { f"{year}年度": total_value for year, total_value in annual_values.items() }
            keys_to_delete_after_aggregation.add(top_key)

    for key_to_del in keys_to_delete_after_aggregation:
        if key_to_del in processed_data:
            del processed_data[key_to_del]
    return processed_data

def flatten_data_recursive(data, current_path_parts):
    flat_map = {}
    if isinstance(data, dict):
        for key, value in data.items():
            new_path_parts = current_path_parts + [str(key)]
            if isinstance(value, (dict, list)):
                flat_map.update(flatten_data_recursive(value, new_path_parts))
            else:
                flat_map[tuple(new_path_parts)] = value
    elif isinstance(data, list):
        if current_path_parts:
            flat_map[tuple(current_path_parts)] = json.dumps(data, ensure_ascii=False)
    return flat_map

def transform_flattened_to_df_row(flat_data_one_stock, key_dict_local):
    output_row = {}
    for path_tuple, value in flat_data_one_stock.items():
        if not path_tuple: continue
        if any(part in ["longName", "shortName"] for part in path_tuple if part not in key_dict_local.values()):
            continue
        is_already_formatted_for_column = False
        final_col_name = ""
        if len(path_tuple) >= 1:
            first_part = str(path_tuple[0])
            if first_part.endswith(("_年間合計", "_年間集計")) and len(path_tuple) >= 2 and str(path_tuple[1]).endswith("年度"):
                base_name_key = first_part
                year_part = str(path_tuple[1])
                if len(path_tuple) == 2:
                    final_col_name = f"{base_name_key}_{year_part}"
                    is_already_formatted_for_column = True
                elif len(path_tuple) > 2 and base_name_key.endswith("_年間集計"):
                    metric_name_parts = [str(p) for p in path_tuple[2:]]
                    final_col_name = f"{base_name_key}_{year_part}_{'_'.join(metric_name_parts)}"
                    is_already_formatted_for_column = True
        if not is_already_formatted_for_column:
            temp_parts = []
            for part_str_original in path_tuple:
                part_str = str(part_str_original)
                if part_str.isdigit() and len(path_tuple) > 1 and path_tuple[-1] != part_str_original :
                    pass
                else:
                    temp_parts.append(key_dict_local.get(part_str, part_str))
            if not temp_parts: continue
            final_col_name = "_".join(filter(None, temp_parts))
        if not final_col_name: continue
        original_col_name = final_col_name
        counter = 1
        while final_col_name in output_row:
            final_col_name = f"{original_col_name}_{counter}"
            counter += 1
        if not isinstance(value, (dict, list)):
            output_row[final_col_name] = value
        elif isinstance(value, list):
            try: output_row[final_col_name] = value
            except TypeError: output_row[final_col_name] = str(value)
    return output_row

def get_stock_name(stock_code, all_stocks_data_local):
    stock_data_item = all_stocks_data_local.get(str(stock_code), {})
    name_val = stock_data_item.get("Company Name ja")
    if name_val is not None: return name_val
    profile_data = stock_data_item.get("profile", {})
    if isinstance(profile_data, dict):
        name_val = profile_data.get("longName", profile_data.get("shortName"))
        if name_val: return name_val
    return f"銘柄 {stock_code}"

def configure_gemini_for_page(api_key_manager):
    session_key = "gemini_configured_for_data_display_page"
    if st.session_state.get(session_key, False): return True
    api_key = api_key_manager.get_api_key("GEMINI_API_KEY")
    if not api_key:
        st.error("`GEMINI_API_KEY` がApiKeyManager経由で取得できませんでした。LLM機能は利用できません。")
        st.session_state[session_key] = False
        return False
    try:
        genai.configure(api_key=api_key)
        st.session_state[session_key] = True
        return True
    except Exception as e:
        st.error(f"Data Display Page: Gemini APIキーの設定中にエラーが発生しました: {e}")
        st.session_state[session_key] = False
        return False

def get_relevant_conceptual_keys_from_gemini(user_question: str, model_name: str, all_keys_descriptions: str) -> list[str]:
    if not st.session_state.get("gemini_configured_for_data_display_page", False):
        st.warning("Gemini APIがこのページ用に設定されていません。キー抽出をスキップします。")
        return []
    valid_english_keys = set(key_dict.keys())
    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        あなたはAIアシスタントで、金融データを専門としています。
        ユーザーの株式に関する日本語の質問から、主要な関心事である財務項目やデータカテゴリに対応する「英語のキー名」を、提供されたリストの中から抽出してください。
        例えば、「2022年の売上と配当は？」という質問で、リストに "totalRevenue: 総収益（単体）" と "dividends_history: 配当履歴" があれば、「totalRevenue」と「dividends_history」を抽出してください。
        「PERが高い企業は？」でリストに "trailingPE: 実績PER" があれば「trailingPE」を抽出してください。
        「各社の利益の推移」であれば、「netIncomeToCommon」や「Net Income」などを抽出してください。

        ユーザーの質問（日本語）: "{user_question}"

        利用可能な金融データキーとその説明のリスト（形式: EnglishKey: 日本語での説明）:
        {all_keys_descriptions}

        応答の指示:
        1. ユーザーの質問を注意深く分析し、彼らが求めている主要な財務概念やデータ項目を特定してください。
        2. 上記の「利用可能な金融データキーとその説明のリスト」から、特定した概念に最も合致する「英語のキー名（コロン':'の前の英語の部分）」**のみ**を選択してください。
        3. 選択した英語のキー名のみを、各項目を新しい行に記述して返してください。
        4. 応答には、日本語の説明、導入/結びのテキスト、その他の説明的な注釈を含めないでください。
        5. **提供されたリストに存在する英語のキー名以外は絶対に出力しないでください。** ユーザーの質問に合致するキーがリストにない場合は、何も返さないでください。
        6. 「売上」に関連するキーは "totalRevenue", "operatingRevenue", "revenue"、「利益」に関連するキーは "netIncomeToCommon", "Net Income", "earnings"、「配当」に関連するキーは "dividends_history", "dividendRate", "dividends" を優先的に検討してください。
        7. "yearly" や "quarterly" といった期間を示す言葉が質問に含まれていても、それ自体をキーとして抽出するのではなく、関連する財務データキー（例: "Net Income"）の抽出に役立ててください。

        ユーザーの質問「{user_question}」に基づいて、上記の指示に厳密に従い、関連する英語のキー名を提示してください。
        """
        generation_config = genai.types.GenerationConfig(temperature=0.0)
        response = model.generate_content(prompt, generation_config=generation_config)
        if response.parts:
            extracted_concepts_text = response.text.strip()
            if not extracted_concepts_text: return []
            raw_concepts = [concept.strip() for concept in extracted_concepts_text.split('\n') if concept.strip()]
            final_concepts = [cs for cs in raw_concepts if cs in valid_english_keys]
            return list(set(final_concepts))
        else:
            st.warning("Gemini APIが応答にパーツを返しませんでした（関連概念キー抽出）。")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback: st.caption(f"プロンプトフィードバック: {response.prompt_feedback}")
            return []
    except Exception as e:
        st.error(f"Gemini APIの呼び出しまたは応答処理中にエラーが発生しました（関連概念キー抽出）: {e}")
        return []

def calculate_dataframe_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameの数値列の統計情報を計算し、DataFrameとして返す。"""
    if df is None or df.empty:
        return pd.DataFrame()

    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()

    if 'コード' in numeric_cols:
        numeric_cols.remove('コード')

    if not numeric_cols:
        return pd.DataFrame()

    stats_df = pd.concat(
        [pd.to_numeric(df[col], errors='coerce').describe(percentiles=[0.1, 0.9]) for col in numeric_cols],
        axis=1
    )
    stats_df.columns = numeric_cols

    return stats_df

def render_statistics_display(stats_df: pd.DataFrame):
    """計算された統計情報DataFrameをStreamlit UIに描画する。"""
    if stats_df.empty:
        return

    st.markdown("---")
    st.subheader("生成されたDataFrameの統計情報")
    st.caption("各項目の分布を把握し、フィルタリングやソートの参考にしてください。")

    with st.expander("各項目の統計データを表示/非表示", expanded=True):
        index_mapping = {
            'count': '件数', 'mean': '平均', 'std': '標準偏差',
            'min': '最小値', '10%': '下位10%', '50%': '中央値',
            '90%': '上位10%', 'max': '最大値'
        }
        ordered_indices = ['count', 'mean', 'std', 'min', '10%', '50%', '90%', 'max']
        display_df = stats_df.rename(index=index_mapping).reindex([index_mapping[i] for i in ordered_indices if i in stats_df.index])
        st.dataframe(display_df.style.format("{:,.2f}", na_rep="N/A"))


# --- Streamlit アプリケーション ---
def render_page(sm, fm, akm, active_model_for_pages):
    st.title("LLMによる財務関連キー抽出とDataFrame表示")
    st.markdown("""
    ユーザーの質問に基づいてLLMが関連キーを抽出し、ユーザーが選択したキーに基づいてJSONデータから情報を取得・加工してDataFrameで表示します。
    生成されたDataFrameの各列に対して、動的なフィルタUIが表示され、条件に応じた絞り込みが可能です。
    数値列は「数値範囲指定」または「パーセンタイル範囲指定」でフィルタリングできます。文字列列はユニーク数に応じてチェックボックスまたは検索ボックスでフィルタリングできます。
    DataFrameの数値は、列の特性に応じて適切な単位（例：億円、百万円、%）で表示されます。
    """)

    if not configure_gemini_for_page(akm):
        st.warning("Gemini APIの初期設定に失敗しました。LLMによるキー抽出機能は利用できませんが、データの表示・フィルタリングは可能です。")

    # --- このページ専用のデータ読み込み処理 ---
    full_data_key = "data_display.full_stock_data"
    all_stocks_data = sm.get_value(full_data_key)

    if all_stocks_data is None:
        st.info("このページで利用する全銘柄データ（stock_data_all.json）を読み込みます。")
        with st.spinner("全銘柄データを読み込み中..."):
            try:
                if fm:
                    json_bytes = fm.get_file_bytes("stock_data_all")
                    if json_bytes:
                        all_stocks_data = json.loads(json_bytes.decode('utf-8'))
                        sm.set_value(full_data_key, all_stocks_data)
                        st.success(f"全銘柄情報のJSONファイル（stock_data_all.json）を読み込みました。({len(all_stocks_data):,}件)")
                        st.rerun()
                    else:
                        st.error("全銘柄情報のJSONファイルの内容が空です。")
                        all_stocks_data = {}
                else:
                    st.error("FileManagerが初期化されていません。")
                    all_stocks_data = {}
            except FileNotFoundError:
                st.error("全銘柄情報のJSONファイル (stock_data_all.json) が見つかりません。")
                all_stocks_data = {}
            except json.JSONDecodeError:
                st.error("全銘柄情報のJSONファイルの解析に失敗しました。")
                all_stocks_data = {}
            except Exception as e:
                st.error(f"全銘柄情報のJSONファイルの読み込み中に予期せぬエラー: {e}")
                all_stocks_data = {}
    else:
        st.success(f"全銘柄データ（stock_data_all.json）は既にロード済みです。({len(all_stocks_data):,}件)")

    if not all_stocks_data:
        st.warning("全銘柄データがロードできなかったため、これ以上の処理は実行できません。")
        return

    default_question = "時価総額が大きくて、配当利回りのいい企業を調べたい。"
    if sm.get_value("data_display.user_question") is None: sm.set_value("data_display.user_question", default_question)
    if sm.get_value('llm_extracted_keys_for_selection') is None: sm.set_value('llm_extracted_keys_for_selection', [])
    if sm.get_value('user_selected_english_keys_for_df') is None: sm.set_value('user_selected_english_keys_for_df', [])
    if sm.get_value('data_display.show_all_df_rows') is None: sm.set_value('data_display.show_all_df_rows', False)
    if sm.get_value("data_display.dataframe_results") is None: sm.set_value("data_display.dataframe_results", pd.DataFrame())
    if sm.get_value("data_display.active_filtered_df") is None: sm.set_value("data_display.active_filtered_df", None)
    if not isinstance(sm.get_value("data_display.calculated_stats"), pd.DataFrame):
        sm.set_value("data_display.calculated_stats", pd.DataFrame())


    user_question = st.text_area(
        "分析したい質問を入力してください:",
        value=sm.get_value("data_display.user_question", default_question),
        height=100,
        key="user_question_input_data_display_main_dynfilter_scaled_v4"
    )
    sm.set_value("data_display.user_question", user_question)

    if st.button("1. LLMに関連キーを抽出させる", key="run_llm_key_extraction_main_dynfilter_scaled_v4"):
        if not user_question.strip():
            st.warning("質問を入力してください。")
        elif not st.session_state.get("gemini_configured_for_data_display_page", False):
            st.error("Gemini APIが設定されていないため、キー抽出を実行できません。")
        else:
            with st.spinner("LLMによるキー抽出を実行中..."):
                conceptual_keys_from_llm = get_relevant_conceptual_keys_from_gemini(user_question, active_model_for_pages, KEYS_DESCRIPTIONS_FULL)
                if conceptual_keys_from_llm:
                    sm.set_value('llm_extracted_keys_for_selection', conceptual_keys_from_llm)
                    st.success(f"LLMが抽出したキー候補: {len(conceptual_keys_from_llm)}件")
                    sm.set_value('user_selected_english_keys_for_df', [])
                    for en_key in conceptual_keys_from_llm: sm.set_value(f"data_display.checkbox_selected_{en_key}", False)
                    sm.set_value("data_display.dataframe_results", pd.DataFrame())
                    sm.set_value("data_display.active_filtered_df", None)
                    sm.set_value("data_display.calculated_stats", pd.DataFrame())
                else:
                    st.info("LLMは関連するキーを抽出できませんでした。質問を変えて試してみてください。")
                    sm.set_value('llm_extracted_keys_for_selection', [])
                    sm.set_value('user_selected_english_keys_for_df', [])
                    sm.set_value("data_display.dataframe_results", pd.DataFrame())
                    sm.set_value("data_display.active_filtered_df", None)
                    sm.set_value("data_display.calculated_stats", pd.DataFrame())

    llm_english_keys_options = sm.get_value('llm_extracted_keys_for_selection', [])
    current_user_selected_english_keys = []
    if llm_english_keys_options:
        st.markdown("---")
        st.subheader("2. DataFrameに含める項目を選択してください")
        previously_selected_en_keys = sm.get_value('user_selected_english_keys_for_df', [])
        cols = st.columns(3)
        col_idx = 0
        for en_key in llm_english_keys_options:
            ja_name = key_dict.get(en_key, en_key)
            checkbox_key_sm_persist = f"data_display.checkbox_selected_{en_key}"
            checkbox_key_st_widget = f"st_checkbox_widget_dynfilter_scaled_v4_{en_key}"
            is_checked_default = sm.get_value(checkbox_key_sm_persist, (en_key in previously_selected_en_keys))
            with cols[col_idx % 3]:
                is_checked = st.checkbox(ja_name, value=is_checked_default, key=checkbox_key_st_widget)
            sm.set_value(checkbox_key_sm_persist, is_checked)
            if is_checked: current_user_selected_english_keys.append(en_key)
            col_idx += 1
        sm.set_value('user_selected_english_keys_for_df', current_user_selected_english_keys)

    if st.button("3. DataFrameを生成・表示", key="run_df_generation_from_selection_main_dynfilter_scaled_v4", disabled=not sm.get_value('user_selected_english_keys_for_df', [])):
        user_selected_keys = sm.get_value('user_selected_english_keys_for_df', [])
        if not user_selected_keys:
            st.warning("表示する項目を1つ以上選択してください。")
        elif not all_stocks_data:
            st.error("全銘柄データがロードされていないため、DataFrameを生成できません。")
        else:
            with st.spinner("DataFrameを生成中..."):
                filtered_initial_data = {}
                essential_keys_for_df = ["Code", "Company Name ja"]
                for stock_code, stock_data_item in all_stocks_data.items():
                    if not isinstance(stock_data_item, dict): continue
                    temp_filtered_stock_data = {}
                    for selected_key_en in user_selected_keys:
                        if selected_key_en in stock_data_item: temp_filtered_stock_data[selected_key_en] = stock_data_item[selected_key_en]
                    for ess_key_en in essential_keys_for_df:
                        if ess_key_en in stock_data_item and ess_key_en not in temp_filtered_stock_data: temp_filtered_stock_data[ess_key_en] = stock_data_item[ess_key_en]
                    if temp_filtered_stock_data: filtered_initial_data[stock_code] = temp_filtered_stock_data
                if not filtered_initial_data:
                    st.info("ユーザーが選択したキーに合致するデータが、どの銘柄にも見つかりませんでした。")
                    sm.set_value("data_display.dataframe_results", pd.DataFrame())
                    sm.set_value("data_display.active_filtered_df", None)
                    sm.set_value("data_display.show_all_df_rows", False)
                    sm.set_value("data_display.calculated_stats", pd.DataFrame())
                else:
                    processed_rows = []
                    all_df_columns = set(['コード', '銘柄名'])
                    for stock_code, item_data_to_process in filtered_initial_data.items():
                        aggregated_data = preprocess_and_aggregate_data(item_data_to_process, key_dict)
                        flat_data = flatten_data_recursive(aggregated_data, [])
                        df_row_data = transform_flattened_to_df_row(flat_data, key_dict)
                        if df_row_data:
                            df_row_data["コード"] = item_data_to_process.get("Code", stock_code)
                            df_row_data["銘柄名"] = item_data_to_process.get("Company Name ja", get_stock_name(stock_code, all_stocks_data))
                            processed_rows.append(df_row_data)
                            all_df_columns.update(df_row_data.keys())
                    if processed_rows:
                        results_df = pd.DataFrame(processed_rows)
                        year_pattern = re.compile(r"_(\d{4})年度(?:_|$)")
                        def get_year_from_col_name(col_name):
                            if not isinstance(col_name, str): return -1
                            match = year_pattern.search(col_name)
                            return int(match.group(1)) if match else -1
                        year_cols = sorted([col for col in all_df_columns if get_year_from_col_name(col) != -1 and col not in ['コード', '銘柄名']], key=lambda x: (-get_year_from_col_name(x), x))
                        other_cols = sorted([col for col in all_df_columns if get_year_from_col_name(col) == -1 and col not in ['コード', '銘柄名']])
                        final_ordered_columns = ['コード', '銘柄名'] + year_cols + other_cols
                        for col in final_ordered_columns:
                            if col not in results_df.columns: results_df[col] = pd.NA
                        cols_to_drop_final = [col for col in results_df.columns if ("longName" in col.lower() or "shortName" in col.lower() or "正式名称" in col or "略称" in col) and col != '銘柄名']
                        results_df = results_df.drop(columns=cols_to_drop_final, errors='ignore')
                        final_ordered_columns = [col for col in final_ordered_columns if col not in cols_to_drop_final]
                        results_df = results_df.reindex(columns=final_ordered_columns, fill_value=pd.NA)
                        sm.set_value("data_display.dataframe_results", results_df)
                        calculated_stats_df = calculate_dataframe_statistics(results_df)
                        sm.set_value("data_display.calculated_stats", calculated_stats_df)
                        sm.set_value("data_display.active_filtered_df", None)
                        sm.set_value("data_display.show_all_df_rows", False)
                        for col_name_clear in results_df.columns:
                            sm.delete_value(f"data_display.filter_tab_selection_{col_name_clear}")
                            sm.delete_value(f"data_display.filter_slider_val_display_{col_name_clear}")
                            sm.delete_value(f"data_display.percentile_range_value_{col_name_clear}")
                            sm.delete_value(f"data_display.filter_multiselect_val_{col_name_clear}")
                            sm.delete_value(f"data_display.filter_textinput_val_{col_name_clear}")
                        st.info(f"{len(results_df)}銘柄のデータでDataFrameを生成しました。")
                    else:
                        st.info("フィルタリング・集計・平坦化後、DataFrameに表示できるデータがありませんでした。")
                        sm.set_value("data_display.dataframe_results", pd.DataFrame())
                        sm.set_value("data_display.active_filtered_df", None)
                        sm.set_value("data_display.show_all_df_rows", False)
                        sm.set_value("data_display.calculated_stats", pd.DataFrame())

    df_original_for_filter_ui = sm.get_value("data_display.dataframe_results")

    if df_original_for_filter_ui is not None and not df_original_for_filter_ui.empty:
        calculated_stats_to_render = sm.get_value("data_display.calculated_stats")
        if isinstance(calculated_stats_to_render, pd.DataFrame) and not calculated_stats_to_render.empty:
            render_statistics_display(calculated_stats_to_render)

        st.markdown("---")
        st.subheader("DataFrameの動的フィルタリング")
        filter_container = st.container()
        current_filter_conditions = {}

        with filter_container:
            st.markdown("##### 各列のフィルタを設定してください:")
            filter_ui_cols_list = st.columns(3)
            col_idx_filter_ui = 0
            for col_name in df_original_for_filter_ui.columns:
                if col_name in ['コード', '銘柄名']: continue
                with filter_ui_cols_list[col_idx_filter_ui % 3]:
                    st.markdown(f"**{col_name}**")
                    col_data_series_original = df_original_for_filter_ui[col_name].dropna()
                    if pd.api.types.is_numeric_dtype(df_original_for_filter_ui[col_name].dtype) and not col_data_series_original.empty:
                        min_val_orig_for_slider = float(col_data_series_original.min())
                        max_val_orig_for_slider = float(col_data_series_original.max())
                        tab1_title = "数値範囲"
                        tab2_title = "パーセンタイル範囲"
                        tab1, tab2 = st.tabs([tab1_title, tab2_title])

                        with tab1:
                            slider_session_key = f"data_display.filter_slider_val_display_{col_name}"
                            current_slider_val_tuple = sm.get_value(slider_session_key, (min_val_orig_for_slider, max_val_orig_for_slider))
                            clamped_default_slider_val_0 = max(min_val_orig_for_slider, min(current_slider_val_tuple[0], max_val_orig_for_slider))
                            clamped_default_slider_val_1 = max(min_val_orig_for_slider, min(current_slider_val_tuple[1], max_val_orig_for_slider))
                            clamped_default_slider_val = tuple(sorted((clamped_default_slider_val_0, clamped_default_slider_val_1)))
                            if min_val_orig_for_slider < max_val_orig_for_slider:
                                slider_format_str = "%.2f"
                                abs_max_slider_val = max(abs(min_val_orig_for_slider), abs(max_val_orig_for_slider))
                                if abs_max_slider_val == 0: slider_format_str = "%.0f"
                                elif abs_max_slider_val >= 1000 : slider_format_str = "%.0f"
                                elif abs_max_slider_val < 1 and abs_max_slider_val != 0:
                                    if abs_max_slider_val < 0.0001: slider_format_str = "%.6f"
                                    elif abs_max_slider_val < 0.001: slider_format_str = "%.5f"
                                    elif abs_max_slider_val < 0.01: slider_format_str = "%.4f"
                                    elif abs_max_slider_val < 0.1: slider_format_str = "%.3f"
                                    else: slider_format_str = "%.2f"
                                elif abs_max_slider_val < 10: slider_format_str = "%.2f"
                                elif abs_max_slider_val < 100: slider_format_str = "%.1f"
                                else: slider_format_str = "%.0f"
                                selected_range_val = st.slider(f"{col_name}", min_value=min_val_orig_for_slider, max_value=max_val_orig_for_slider, value=clamped_default_slider_val, key=f"slider_filter_widget_scaled_v4_{col_name}", format=slider_format_str)
                                sm.set_value(slider_session_key, selected_range_val)
                                is_default_range = np.isclose(selected_range_val[0], min_val_orig_for_slider) and np.isclose(selected_range_val[1], max_val_orig_for_slider)
                                if not is_default_range:
                                    current_filter_conditions[col_name] = {"type": "numeric_range", "value_original_scale": selected_range_val, "filter_source_tab": tab1_title}
                            elif min_val_orig_for_slider == max_val_orig_for_slider:
                                st.caption(f"固定値: {min_val_orig_for_slider:g}")
                                if slider_session_key in st.session_state: sm.delete_value(slider_session_key)
                            else:
                                st.caption("データなし/範囲不定")
                                if slider_session_key in st.session_state: sm.delete_value(slider_session_key)

                        with tab2:
                            percentile_range_session_key = f"data_display.percentile_range_value_{col_name}"
                            current_percentile_range_tuple = sm.get_value(percentile_range_session_key, (0, 100))
                            selected_percentile_range = st.slider("パーセンタイル範囲 (%):", min_value=0, max_value=100, value=(int(current_percentile_range_tuple[0]), int(current_percentile_range_tuple[1])), step=1, key=f"percentile_range_slider_widget_v4_{col_name}", format="%d%%")
                            sm.set_value(percentile_range_session_key, selected_percentile_range)
                            is_default_percentile_range = selected_percentile_range[0] == 0 and selected_percentile_range[1] == 100
                            if not is_default_percentile_range:
                                current_filter_conditions[col_name] = {"type": "percentile_range", "value_percent_range": selected_percentile_range, "filter_source_tab": tab2_title}

                    elif (pd.api.types.is_string_dtype(df_original_for_filter_ui[col_name].dtype) or df_original_for_filter_ui[col_name].dtype == 'object') and not col_data_series_original.empty:
                        unique_values = sorted(col_data_series_original.unique().astype(str))
                        if len(unique_values) <= 40:
                            multiselect_session_key = f"data_display.filter_multiselect_val_{col_name}"
                            current_multiselect_val = sm.get_value(multiselect_session_key, [])
                            valid_current_selection = [val for val in current_multiselect_val if val in unique_values]
                            selected_options = st.multiselect(f"選択 (OR条件)", options=unique_values, default=valid_current_selection, key=f"multiselect_filter_widget_scaled_v4_{col_name}")
                            if selected_options:
                                current_filter_conditions[col_name] = {"type": "string_multiselect", "value": selected_options}
                            sm.set_value(multiselect_session_key, selected_options)
                        else:
                            text_input_session_key = f"data_display.filter_textinput_val_{col_name}"
                            current_text_val = sm.get_value(text_input_session_key, "")
                            search_text = st.text_input(f"含む文字で検索", value=current_text_val, key=f"textinput_filter_widget_scaled_v4_{col_name}")
                            if search_text:
                                current_filter_conditions[col_name] = {"type": "string_contains", "value": search_text}
                            sm.set_value(text_input_session_key, search_text)
                col_idx_filter_ui += 1

            btn_cols = st.columns(2)
            with btn_cols[0]:
                if st.button("フィルタ適用", key="apply_dynamic_filters_button_scaled_v4"):
                    if not current_filter_conditions:
                        st.info("適用するフィルタ条件が設定されていません。全件表示します。")
                        sm.set_value("data_display.active_filtered_df", df_original_for_filter_ui)
                    else:
                        df_to_filter_apply = df_original_for_filter_ui.copy()
                        active_filter_descriptions = []
                        for col, condition in current_filter_conditions.items():
                            series_for_display_format = df_original_for_filter_ui[col].dropna()
                            unit_factor_disp, suffix_disp, num_format_template_disp, is_percent_disp = determine_numeric_scale_and_format(series_for_display_format, col)
                            if condition["type"] == "numeric_range":
                                filter_val_min, filter_val_max = condition["value_original_scale"]
                                numeric_col = pd.to_numeric(df_to_filter_apply[col], errors='coerce')
                                df_to_filter_apply = df_to_filter_apply[(numeric_col >= filter_val_min) & (numeric_col <= filter_val_max)]
                                min_desc = (num_format_template_disp.format(filter_val_min / unit_factor_disp) + suffix_disp) if unit_factor_disp !=1 and not is_percent_disp else num_format_template_disp.format(filter_val_min)
                                if is_percent_disp : min_desc = num_format_template_disp.format(filter_val_min)
                                max_desc = (num_format_template_disp.format(filter_val_max / unit_factor_disp) + suffix_disp) if unit_factor_disp !=1 and not is_percent_disp else num_format_template_disp.format(filter_val_max)
                                if is_percent_disp : max_desc = num_format_template_disp.format(filter_val_max)
                                active_filter_descriptions.append(f"{col} ({condition['filter_source_tab']}): {min_desc} ～ {max_desc}")
                            elif condition["type"] == "percentile_range":
                                min_percent, max_percent = condition["value_percent_range"]
                                numeric_col_for_quantile = pd.to_numeric(df_original_for_filter_ui[col], errors='coerce').dropna()
                                if not numeric_col_for_quantile.empty and min_percent <= max_percent :
                                    lower_bound_value = numeric_col_for_quantile.quantile(min_percent / 100.0)
                                    upper_bound_value = numeric_col_for_quantile.quantile(max_percent / 100.0)
                                    numeric_col_to_filter = pd.to_numeric(df_to_filter_apply[col], errors='coerce')
                                    df_to_filter_apply = df_to_filter_apply[(numeric_col_to_filter >= lower_bound_value) & (numeric_col_to_filter <= upper_bound_value)]
                                    lower_desc = (num_format_template_disp.format(lower_bound_value / unit_factor_disp) + suffix_disp) if unit_factor_disp !=1 and not is_percent_disp else num_format_template_disp.format(lower_bound_value)
                                    if is_percent_disp: lower_desc = num_format_template_disp.format(lower_bound_value)
                                    upper_desc = (num_format_template_disp.format(upper_bound_value / unit_factor_disp) + suffix_disp) if unit_factor_disp !=1 and not is_percent_disp else num_format_template_disp.format(upper_bound_value)
                                    if is_percent_disp: upper_desc = num_format_template_disp.format(upper_bound_value)
                                    active_filter_descriptions.append(f"{col} ({condition['filter_source_tab']}): {min_percent}% ({lower_desc}) ～ {max_percent}% ({upper_desc})")
                                else:
                                    active_filter_descriptions.append(f"{col} ({condition['filter_source_tab']}): パーセンタイル範囲フィルタスキップ (データなしまたは範囲不正)")
                            elif condition["type"] == "string_multiselect":
                                val = condition["value"]
                                df_to_filter_apply = df_to_filter_apply[df_to_filter_apply[col].isin(val)]
                                active_filter_descriptions.append(f"{col}: {', '.join(val)}")
                            elif condition["type"] == "string_contains":
                                val = condition["value"]
                                df_to_filter_apply = df_to_filter_apply[df_to_filter_apply[col].astype(str).str.contains(val, case=False, na=False)]
                                active_filter_descriptions.append(f"{col} (検索): '{val}'")
                        sm.set_value("data_display.active_filtered_df", df_to_filter_apply)
                        if active_filter_descriptions:
                            st.success(f"フィルタ適用完了 ({len(df_to_filter_apply)}件)。適用中のフィルタ: {'; '.join(active_filter_descriptions)}")
                        else:
                            st.info("有効なフィルタ条件が指定されませんでした。全件表示します。")
                            sm.set_value("data_display.active_filtered_df", df_original_for_filter_ui)
                    st.rerun()

            with btn_cols[1]:
                if st.button("フィルタ解除", key="reset_dynamic_filters_button_scaled_v4"):
                    for col_name_reset in df_original_for_filter_ui.columns:
                        if col_name_reset in ['コード', '銘柄名']: continue
                        sm.delete_value(f"data_display.filter_tab_selection_{col_name_reset}")
                        sm.delete_value(f"data_display.filter_slider_val_display_{col_name_reset}")
                        sm.delete_value(f"data_display.percentile_range_value_{col_name_reset}")
                        sm.delete_value(f"data_display.filter_multiselect_val_{col_name_reset}")
                        sm.delete_value(f"data_display.filter_textinput_val_{col_name_reset}")
                    sm.set_value("data_display.active_filtered_df", df_original_for_filter_ui)
                    st.info("すべてのフィルタを解除しました。")
                    st.rerun()

        df_for_final_display_actual = sm.get_value("data_display.active_filtered_df", df_original_for_filter_ui)
        if df_for_final_display_actual is None: df_for_final_display_actual = df_original_for_filter_ui

        st.markdown("---")
        st.subheader("表示結果 DataFrame")
        if df_for_final_display_actual.empty:
            st.caption("表示するデータがありません（フィルタ結果が空の可能性があります）。")
        else:
            global_formatters = {}
            for col_name_fmt in df_for_final_display_actual.columns:
                if pd.api.types.is_numeric_dtype(df_for_final_display_actual[col_name_fmt].dtype):
                    series_data = df_for_final_display_actual[col_name_fmt]
                    if not series_data.dropna().empty:
                        unit_factor, suffix, base_format_template, is_percent = determine_numeric_scale_and_format(series_data, col_name_fmt)
                        if is_percent:
                            global_formatters[col_name_fmt] = base_format_template
                        elif suffix and unit_factor != 1:
                            global_formatters[col_name_fmt] = lambda x, factor=unit_factor, sfx=suffix, fmt=base_format_template: (fmt.format(x / factor) + sfx) if pd.notnull(x) else ""
                        else:
                            global_formatters[col_name_fmt] = lambda x, fmt=base_format_template: fmt.format(x) if pd.notnull(x) else ""
            show_all_rows_flag_key = "data_display.show_all_df_rows"
            show_all = sm.get_value(show_all_rows_flag_key, False)
            if len(df_for_final_display_actual) > 10:
                button_text = "上位10行のみ表示に戻す" if show_all else f"全 {len(df_for_final_display_actual)} 行表示する"
                if st.button(button_text, key="toggle_show_all_df_button_main_dynfilter_scaled_v4"):
                    sm.set_value(show_all_rows_flag_key, not show_all)
                    st.rerun()
            df_to_show = df_for_final_display_actual if show_all else df_for_final_display_actual.head(10)
            if not df_to_show.empty:
                active_formatters = {k: v for k, v in global_formatters.items() if k in df_to_show.columns}
                st.dataframe(df_to_show.style.format(active_formatters))
            else:
                st.caption("表示するデータがありません（フィルタ結果が空の可能性があります）。")
            if not show_all and len(df_for_final_display_actual) > 10:
                st.caption(f"全 {len(df_for_final_display_actual)} 行中、上位10行を表示しています。")

    elif df_original_for_filter_ui is not None and df_original_for_filter_ui.empty:
        st.markdown("---")
        st.subheader("生成されたDataFrame")
        st.caption("表示するデータがありません。")

    st.markdown("---")
    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back_nav, col_next_nav = st.columns(2)
    with col_back_nav:
        if st.button("戻る (ステップ6: AIテキスト読み上げへ)", key="s7_back_to_s6", use_container_width=True):
            sm.set_value("app.current_step", 6)
            st.rerun()
    with col_next_nav:
        if st.button("次へ (ステップ8: テクニカル分析へ)", type="primary", key="s7_next_to_s8", use_container_width=True):
            sm.set_value("app.current_step", 8)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
