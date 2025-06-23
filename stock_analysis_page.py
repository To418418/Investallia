# stock_analysis_page.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import logging
import re
import datetime
import yfinance as yf

import ui_styles # HTML生成関数がここにある
import config as app_config # リファクタリング後の設定ファイル
import api_services as api_services # リファクタリングされたAPIサービス
import news_services as news_services # リファクタリングされたニュースサービス
import stock_utils # stock_utils.py は前回提供したものを使用

logger = logging.getLogger(__name__)

# --- StateManagerで使用するキー (このモジュール固有のもの) ---
KEY_PREFIX = "stock_analysis_v6." # プレフィックスでキーをグループ化 (バージョンアップ)
KEY_REPORT_BUTTON_CLICKED = f"{KEY_PREFIX}report_button_clicked"
KEY_HTML_CONTENT = f"{KEY_PREFIX}html_content"
KEY_AI_ANALYSIS_TRIGGERED = f"{KEY_PREFIX}ai_analysis_triggered_flag"
KEY_AI_ANALYSIS_ACTIVE = f"{KEY_PREFIX}ai_analysis_active"
KEY_AI_ANALYSIS_TEXT = f"{KEY_PREFIX}ai_analysis_text"
KEY_AI_ANALYSIS_STATUS_MESSAGES = f"{KEY_PREFIX}ai_analysis_status_messages"
KEY_AI_PROCESSING_TIME_MESSAGE = f"{KEY_PREFIX}ai_processing_time_message"
KEY_PAGE_LEVEL_ERROR = f"{KEY_PREFIX}page_level_error"
KEY_DEBUG_STOCK_DATA_SUMMARY = f"{KEY_PREFIX}debug_stock_data_summary"
KEY_DEBUG_JS_DATA_STRING_PREVIEW = f"{KEY_PREFIX}debug_js_data_string_preview"
KEY_TARGET_STOCKS_JSON_INPUT = f"{KEY_PREFIX}target_stocks_json_input"
KEY_RAW_NEWS_API_RESPONSES = f"{KEY_PREFIX}raw_news_api_responses"
KEY_COLLECT_RELATED_STOCKS = f"{KEY_PREFIX}collect_related_stocks"
KEY_ALL_STOCK_DATA_FOR_REPORT = f"{KEY_PREFIX}all_stock_data_for_report"
KEY_EXTENDED_TARGET_STOCKS_OPTIONS = f"{KEY_PREFIX}extended_target_stocks_options"
KEY_AI_USER_QUESTION = f"{KEY_PREFIX}ai_user_question"
KEY_CURRENT_REPORT_TARGET_STOCK_DISPLAY = f"{KEY_PREFIX}current_report_target_stock_display" # AI分析用に追加
KEY_AI_SELECTED_STOCK_DISPLAY_NAME = f"{KEY_PREFIX}ai_selected_stock_display_name" # AI分析用に追加
KEY_FULL_DATA_FOR_RELATED = f"{KEY_PREFIX}full_data_for_related" # ★関連銘柄検索用の全データキーを追加

# --- Helper Functions ---
def format_japanese_yen(value, unit_oku=False, decimals=0):
    if pd.isna(value) or (isinstance(value, float) and np.isnan(value)) or not isinstance(value, (int, float)):
        return 'N/A'
    if unit_oku:
        val_oku = value / 100_000_000
        return f"{val_oku:,.{decimals}f}億円"
    return f"{value:,.{decimals}f}円"

def format_percentage(value, decimals=2):
    if pd.isna(value) or (isinstance(value, float) and np.isnan(value)) or not isinstance(value, (int, float)):
        return 'N/A'
    return f"{value * 100:.{decimals}f}%"

def create_html_table_from_df_for_report(
    df, table_id="",
    th_classes="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
    td_classes="px-4 py-2 whitespace-nowrap text-sm text-gray-900",
    custom_headers=None, is_transposed_recommendations=False
    ):
    if df is None or df.empty: return "<p class='text-sm text-gray-500'>データがありません。</p>"
    html = f"<div class='overflow-x-auto'><table id='{table_id}' class='min-w-full divide-y divide-gray-200'>"
    html += "<thead class='bg-gray-50'><tr>"
    headers_to_use = custom_headers if custom_headers and len(custom_headers) == len(df.columns) else df.columns
    for i, col_header in enumerate(headers_to_use):
        current_th_classes = th_classes
        if is_transposed_recommendations and i > 0:
            current_th_classes += " text-center"
        html += f"<th class='{current_th_classes}'>{col_header}</th>"
    html += "</tr></thead>"
    html += "<tbody class='bg-white divide-y divide-gray-200'>"
    df_columns_original = list(df.columns)
    for _, row in df.iterrows():
        html += "<tr>"
        for i, col_header_display in enumerate(headers_to_use):
            original_col_name = df_columns_original[i] if custom_headers and i < len(df_columns_original) else col_header_display
            cell_value = row.get(original_col_name, 'N/A')
            if pd.isna(cell_value): cell_value = 'N/A'
            current_td_classes = td_classes
            if is_transposed_recommendations:
                if i == 0: current_td_classes += ' font-semibold text-left'
                else: current_td_classes += ' text-center'
            html += f"<td class='{current_td_classes}'>{cell_value}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html

def find_column_name_for_report(df_columns, potential_names):
    df_columns_list = list(df_columns)
    df_columns_lower = [str(col).lower() for col in df_columns_list]
    for name in potential_names:
        if str(name).lower() in df_columns_lower:
            return df_columns_list[df_columns_lower.index(str(name).lower())]
    return None

def process_financial_summary_for_report(financial_data_df, period_type_jp):
    if financial_data_df is None or financial_data_df.empty:
        return f"<p class='text-sm text-gray-500'>業績データ({period_type_jp})が取得できませんでした。</p>", None
    summary_df_latest = financial_data_df.iloc[:, :4].copy()
    if isinstance(summary_df_latest.columns, pd.DatetimeIndex):
        if period_type_jp == "四半期":
            summary_df_latest.columns = [col.strftime('%Y年%m月') for col in summary_df_latest.columns]
        else:
            summary_df_latest.columns = [col.strftime('%Y年') for col in summary_df_latest.columns]
    else:
        summary_df_latest.columns = [str(col) for col in summary_df_latest.columns]

    map_financial_items_english_to_jp = {
        'Total Revenue': '売上高', 'Operating Income': '営業利益',
        'Pretax Income': '税引前利益', 'Net Income': '純利益',
        'Basic EPS': 'EPS (実績)', 'EBIT': 'EBIT', 'EBITDA': 'EBITDA'
    }
    available_english_items = [item for item in map_financial_items_english_to_jp.keys() if item in summary_df_latest.index]
    if not available_english_items:
        return f"<p class='text-sm text-gray-500'>主要な業績項目({period_type_jp})が見つかりません。</p>", None
    selected_summary = summary_df_latest.loc[available_english_items].copy()
    selected_summary.rename(index=map_financial_items_english_to_jp, inplace=True)

    desired_jp_order = ['売上高', '営業利益', '税引前利益', '純利益', 'EPS (実績)', 'EBIT', 'EBITDA']
    ordered_summary_index = [item for item in desired_jp_order if item in selected_summary.index]
    if not ordered_summary_index:
        return f"<p class='text-sm text-gray-500'>指定された業績項目({period_type_jp})がデータにありません。</p>", None
    selected_summary = selected_summary.loc[ordered_summary_index]

    for col in selected_summary.columns:
        for idx_label in selected_summary.index:
            current_val = selected_summary.loc[idx_label, col]
            if pd.isna(current_val) or (isinstance(current_val, float) and np.isnan(current_val)):
                selected_summary.loc[idx_label, col] = None
                continue
            if idx_label not in ['EPS (実績)']:
                if isinstance(current_val, (int, float)):
                    selected_summary.loc[idx_label, col] = current_val / 100_000_000
            else:
                if isinstance(current_val, (int, float)):
                    selected_summary.loc[idx_label, col] = f"{current_val:.2f}"
    df_for_table = selected_summary.copy()
    for col_idx in df_for_table.columns:
        for row_idx in df_for_table.index:
            if df_for_table.loc[row_idx, col_idx] is None :
                df_for_table.loc[row_idx, col_idx] = 'N/A'
    df_for_table = df_for_table.reset_index().rename(columns={'index':'科目'})
    custom_headers_summary = ['科目'] + list(selected_summary.columns)
    table_html = create_html_table_from_df_for_report(df_for_table[custom_headers_summary],
                                                    table_id=f"financial-summary-{period_type_jp.replace(' ', '')}-table",
                                                    custom_headers=custom_headers_summary)
    chart_data = None
    if period_type_jp == "通期":
        chart_data = {"labels": [], "datasets": []}
        chart_data['labels'] = list(selected_summary.columns)[::-1]

        revenue_data_raw = selected_summary.loc['売上高'].tolist()[::-1] if '売上高' in selected_summary.index else []
        net_income_data_raw = selected_summary.loc['純利益'].tolist()[::-1] if '純利益' in selected_summary.index else []

        revenue_data_chart = [round(x,1) if isinstance(x, (int,float)) and pd.notnull(x) else None for x in revenue_data_raw]
        net_income_data_chart = [round(x,1) if isinstance(x, (int,float)) and pd.notnull(x) else None for x in net_income_data_raw]

        if '売上高' in selected_summary.index and any(d is not None for d in revenue_data_chart):
            chart_data['datasets'].append({
                "label": '売上高 (億円)', "data": revenue_data_chart,
                "backgroundColor": 'rgba(75, 192, 192, 0.6)', "borderColor": 'rgba(75, 192, 192, 1)', "borderWidth": 1})
        if '純利益' in selected_summary.index and any(d is not None for d in net_income_data_chart):
            chart_data['datasets'].append({
                "label": '純利益 (億円)', "data": net_income_data_chart,
                "backgroundColor": 'rgba(255, 159, 64, 0.6)', "borderColor": 'rgba(255, 159, 64, 1)', "borderWidth": 1})
    return table_html, chart_data

def get_stock_data_for_html_report(ticker_code_input: str, company_name_jp: str, akm, sm) -> dict:
    logger.info(f"レポート用データ取得開始: {company_name_jp} ({ticker_code_input})")
    data_payload = {
        "companyName": company_name_jp, "ticker": ticker_code_input.split('.')[0], "currentPrice": None,
        "logo_url": f"https://placehold.co/120x60/e0e7ff/3730a3?text={ticker_code_input.split('.')[0]}_Init",
        "priceChange": "N/A", "priceChangeColor": "text-gray-500", "historicalPrices": {"labels": [], "data": []},
        "financials": [], "financialSummaryAnnual": {"table_html": ""}, "financialSummaryQuarterly": {"table_html": ""},
        "financialSummaryChart": {"labels": [], "datasets": []}, "earningsDatesHtml": "", "recommendationsHtml": "", "news": []
    }
    try:
        ticker_data = yf.Ticker(ticker_code_input)
        info = ticker_data.info
        if not info or not info.get('symbol'):
            logger.warning(f"ティッカー {ticker_code_input} の基本情報(info)を取得できませんでした。")
            data_payload["financials"] = [{"label": "エラー", "value": "基本情報取得失敗"}]
            data_payload["financialSummaryAnnual"]["table_html"] = f"<p class='text-sm text-red-500'>基本情報なしのため通期業績データ取得失敗</p>"
            data_payload["financialSummaryQuarterly"]["table_html"] = f"<p class='text-sm text-red-500'>基本情報なしのため四半期業績データ取得失敗</p>"
            data_payload["earningsDatesHtml"] = "<p class='text-sm text-red-500'>基本情報なしのため決算日データ取得失敗</p>"
            data_payload["recommendationsHtml"] = "<p class='text-sm text-red-500'>基本情報なしのためアナリスト推奨データ取得失敗</p>"
            data_payload["news"] = [{"date": "N/A", "title": "ニュース取得失敗(基本情報なし)", "source":"システム", "url":"#"}]
            return data_payload

        data_payload.update({
            "companyName": info.get('longName', company_name_jp),
            "currentPrice": info.get('currentPrice', info.get('regularMarketPrice')),
            "logo_url": info.get('logo_url', f"https://placehold.co/120x60/e0e7ff/3730a3?text={data_payload['ticker']}")
        })

        price_change_val = info.get('regularMarketChange', 0.0) if info.get('regularMarketChange') is not None else 0.0
        price_change_percent_val = info.get('regularMarketChangePercent', 0.0)/100 if info.get('regularMarketChangePercent') is not None else 0.0
        data_payload["priceChange"] = f"{price_change_val:+.2f} ({format_percentage(price_change_percent_val, 2)})"
        data_payload["priceChangeColor"] = "text-green-600" if price_change_val >= 0 else "text-red-600"

        hist = ticker_data.history(period="1y", interval="1mo")
        if not hist.empty:
            data_payload["historicalPrices"] = {
                "labels": [f"{idx.year}-{idx.month:02d}月" for idx in hist.index],
                "data": [round(val, 2) if pd.notnull(val) else None for val in hist['Close'].tolist()]
            }

        data_payload["financials"] = [
            {"label": "時価総額", "value": format_japanese_yen(info.get('marketCap'), unit_oku=True, decimals=1)},
            {"label": "配当利回り", "value": format_percentage(info.get('dividendYield'))},
            {"label": "1株配当", "value": format_japanese_yen(info.get('dividendRate', info.get('trailingAnnualDividendRate')))},
            {"label": "PER", "value": f"{info.get('trailingPE'):.2f}倍" if isinstance(info.get('trailingPE'), (int, float)) and pd.notnull(info.get('trailingPE')) else 'N/A'},
            {"label": "PBR", "value": f"{info.get('priceToBook'):.2f}倍" if isinstance(info.get('priceToBook'), (int, float)) and pd.notnull(info.get('priceToBook')) else 'N/A'},
            {"label": "EPS (実績)", "value": f"{info.get('trailingEps'):.2f}" if isinstance(info.get('trailingEps'), (int, float)) and pd.notnull(info.get('trailingEps')) else 'N/A'},
            {"label": "BPS (実績)", "value": f"{info.get('bookValue'):.2f}" if isinstance(info.get('bookValue'), (int, float)) and pd.notnull(info.get('bookValue')) else 'N/A'},
            {"label": "ROE (実績)", "value": format_percentage(info.get('returnOnEquity'))},
            {"label": "52週高値", "value": format_japanese_yen(info.get('fiftyTwoWeekHigh'))},
            {"label": "52週安値", "value": format_japanese_yen(info.get('fiftyTwoWeekLow'))},
        ]

        try:
            financials_annual_df = ticker_data.financials
            table_html_annual, chart_data_annual = process_financial_summary_for_report(financials_annual_df, "通期")
            data_payload["financialSummaryAnnual"]["table_html"] = table_html_annual
            if chart_data_annual: data_payload["financialSummaryChart"] = chart_data_annual
        except Exception as e_fin_an:
            logger.warning(f"通期業績サマリーエラー ({ticker_code_input}): {e_fin_an}")
            data_payload["financialSummaryAnnual"]["table_html"] = f"<p class='text-sm text-red-500'>通期業績エラー: {e_fin_an}</p>"

        try:
            financials_quarterly_df = ticker_data.quarterly_financials
            table_html_quarterly, _ = process_financial_summary_for_report(financials_quarterly_df, "四半期")
            data_payload["financialSummaryQuarterly"]["table_html"] = table_html_quarterly
        except Exception as e_fin_q:
            logger.warning(f"四半期業績サマリーエラー ({ticker_code_input}): {e_fin_q}")
            data_payload["financialSummaryQuarterly"]["table_html"] = f"<p class='text-sm text-red-500'>四半期業績エラー: {e_fin_q}</p>"

        try:
            earnings_df_raw = ticker_data.earnings_dates
            if earnings_df_raw is not None and not earnings_df_raw.empty:
                earnings_df_processed = earnings_df_raw.copy().reset_index()
                earnings_df_processed.columns = [col.replace(' ', '_') for col in earnings_df_processed.columns]

                cols_to_check_for_na = ['EPS_Estimate', 'Reported_EPS', 'Surprise(%)']
                existing_cols_to_check = [col for col in cols_to_check_for_na if col in earnings_df_processed.columns]
                if existing_cols_to_check:
                    earnings_df_processed.dropna(subset=existing_cols_to_check, how='all', inplace=True)

                if 'Earnings_Date' in earnings_df_processed.columns:
                    earnings_df_processed['Earnings_Date'] = pd.to_datetime(earnings_df_processed['Earnings_Date']).dt.strftime('%Y-%m-%d')

                cols_to_display_earnings = [col for col in ['Earnings_Date', 'EPS_Estimate', 'Reported_EPS', 'Surprise(%)'] if col in earnings_df_processed.columns]
                custom_headers_earnings = {'Earnings_Date': '決算発表日', 'EPS_Estimate': 'EPS予想', 'Reported_EPS': '実績EPS', 'Surprise(%)': 'サプライズ(%)'}
                display_headers_earnings = [custom_headers_earnings.get(col, col) for col in cols_to_display_earnings]

                if not earnings_df_processed.empty and cols_to_display_earnings:
                    data_payload["earningsDatesHtml"] = create_html_table_from_df_for_report(
                        earnings_df_processed[cols_to_display_earnings].head(8),
                        table_id="earnings-dates-table",
                        custom_headers=display_headers_earnings
                    )
                else:
                    data_payload["earningsDatesHtml"] = "<p class='text-sm text-gray-500'>表示可能な決算発表データがありません。</p>"
            else:
                data_payload["earningsDatesHtml"] = "<p class='text-sm text-gray-500'>決算発表データがありません。</p>"
        except Exception as e_earn:
            logger.warning(f"決算発表日データ処理エラー ({ticker_code_input}): {e_earn}")
            data_payload["earningsDatesHtml"] = f"<p class='text-sm text-red-500'>決算発表日エラー: {e_earn}</p>"

        try:
            reco_df_raw = ticker_data.recommendations_summary
            if reco_df_raw is None or reco_df_raw.empty:
                reco_df_raw = ticker_data.recommendations

            if reco_df_raw is not None and not reco_df_raw.empty:
                reco_df_processed = reco_df_raw.copy()
                if not isinstance(reco_df_processed.index, pd.MultiIndex) and 'Period' not in reco_df_processed.columns:
                    reco_df_processed = reco_df_processed.reset_index()

                period_col_name = find_column_name_for_report(reco_df_processed.columns, ['Period', 'period'])
                if not period_col_name and isinstance(reco_df_processed.index.name, str) and reco_df_processed.index.name.lower() == 'period':
                    reco_df_processed.reset_index(inplace=True)
                    period_col_name = find_column_name_for_report(reco_df_processed.columns, ['Period', 'period'])

                if period_col_name:
                    reco_df_pivot = reco_df_processed.set_index(period_col_name)
                    transposed_reco_df = reco_df_pivot.head(4).T.reset_index()
                    transposed_reco_df.rename(columns={'index': '評価'}, inplace=True)
                    table_headers_reco = list(transposed_reco_df.columns)
                    data_payload["recommendationsHtml"] = create_html_table_from_df_for_report(
                        transposed_reco_df,
                        table_id="recommendations-table-transposed",
                        custom_headers=table_headers_reco,
                        is_transposed_recommendations=True
                    )
                else:
                    data_payload["recommendationsHtml"] = "<p class='text-sm text-gray-500'>アナリスト推奨Period列不明</p>"
            else:
                data_payload["recommendationsHtml"] = "<p class='text-sm text-gray-500'>アナリスト推奨データなし</p>"
        except Exception as e_reco:
            logger.warning(f"アナリスト推奨データ処理エラー ({ticker_code_input}): {e_reco}")
            data_payload["recommendationsHtml"] = f"<p class='text-sm text-red-500'>アナリスト推奨エラー: {e_reco}</p>"

        news_data_result = news_services.fetch_all_stock_news(company_name_jp, app_config.NEWS_SERVICE_CONFIG["active_apis"], akm)
        company_news_items = news_data_result.get("all_company_news_deduplicated", [])
        data_payload["news"] = [{"date": item.get('日付', 'N/A'), "title": item.get('タイトル', 'N/A'), "source": item.get('ソース', 'N/A'), "url": item.get('URL', '#')} for item in company_news_items[:5]]
        if not data_payload["news"]:
            news_api_message = news_data_result.get("api_errors", {}).get("message", "関連ニュースは取得できませんでした。")
            if isinstance(news_api_message, dict) and "company" in news_api_message:
                combined_msg = "; ".join([f"{k.upper()}: {v}" for k,v in news_api_message.items() if v])
                news_api_message = combined_msg if combined_msg else "関連ニュースは取得できませんでした。"

            data_payload["news"] = [{"date": "N/A", "title": news_api_message, "source": "システムメッセージ", "url": "#"}]

        if sm:
            raw_responses_all = sm.get_value(KEY_RAW_NEWS_API_RESPONSES, {})
            raw_responses_all[data_payload['ticker']] = news_data_result.get("raw_api_responses", {})
            sm.set_value(KEY_RAW_NEWS_API_RESPONSES, raw_responses_all)

        logger.info(f"レポート用データ取得完了: {company_name_jp} ({ticker_code_input})")
    except Exception as e:
        logger.error(f"get_stock_data_for_html_report で予期せぬエラー ({ticker_code_input}): {e}", exc_info=True)
        if sm: sm.set_value(KEY_PAGE_LEVEL_ERROR, f"銘柄「{company_name_jp}」のデータ取得中に予期せぬエラー: {e}")
        data_payload["financials"] = [{"label": "エラー", "value": f"データ取得全体エラー: {e}"}]
        data_payload["financialSummaryAnnual"]["table_html"] = f"<p class='text-sm text-red-500'>通期業績データ取得エラー: {e}</p>"
        data_payload["financialSummaryQuarterly"]["table_html"] = f"<p class='text-sm text-red-500'>四半期業績データ取得エラー: {e}</p>"
        data_payload["earningsDatesHtml"] = f"<p class='text-sm text-red-500'>決算日データ取得エラー: {e}</p>"
        data_payload["recommendationsHtml"] = f"<p class='text-sm text-red-500'>アナリスト推奨データ取得エラー: {e}</p>"
        data_payload["news"] = [{"date": "N/A", "title": f"ニュースデータ取得エラー: {e}", "source": "システム", "url":"#"}]
    return data_payload

# --- ▼▼▼ ここから修正 ▼▼▼ ---
# @st.cache_dataデコレータを削除し、通常の関数に変更
# 引数にsmとakmを明示的に受け取るように変更
def load_all_stock_data_for_report(stocks_dict, akm, sm):
    """
    指定された銘柄辞書のすべての銘柄について、レポート用のデータを取得する。
    この関数はセッションステートにアクセス・更新するため、キャッシュしない。
    """
    all_data = {}
    total_stocks = len(stocks_dict)
    logger.info(f"全{total_stocks}銘柄のレポート用データ取得処理開始...")

    # StateManagerが渡されていることを確認
    if not sm:
        logger.error("load_all_stock_data_for_report: StateManagerが提供されていません。")
        return {}

    # ニュースの生レスポンスを保存する領域を初期化
    sm.set_value(KEY_RAW_NEWS_API_RESPONSES, {})

    for i, (ticker_code, name) in enumerate(stocks_dict.items()):
        logger.info(f"データ取得中 ({i+1}/{total_stocks}): {name} ({ticker_code})")
        try:
            # get_stock_data_for_html_reportにakmとsmを渡す
            stock_data = get_stock_data_for_html_report(ticker_code, name, akm, sm)
            all_data[str(ticker_code).split('.')[0]] = stock_data
        except Exception as e:
            logger.error(f"load_all_stock_data_for_report内でエラー: {name} ({ticker_code}) - {e}", exc_info=True)
            all_data[str(ticker_code).split('.')[0]] = {"companyName": name, "ticker": str(ticker_code).split('.')[0], "error": str(e)}
        # APIへの連続リクエストを避けるための短い待機
        time.sleep(0.2)

    logger.info(f"全{total_stocks}銘柄のレポート用データ取得処理完了。")
    return all_data
# --- ▲▲▲ ここまで修正 ▲▲▲ ---

# --- メインページ描画関数 ---
def render_page(sm, fm, akm, active_model):
    st.header("ステップ3: 株式情報レポート & AI分析")
    st.markdown("画面上部で選択された銘柄、またはサイドバーで指定した複数銘柄の情報を表示し、AI分析を行います。")

    if sm.get_value("app.global_stock_just_changed_flag", False):
        logger.info(f"Global stock change detected in stock_analysis_page. Resetting {KEY_TARGET_STOCKS_JSON_INPUT} and related report states.")
        sm.set_value(KEY_TARGET_STOCKS_JSON_INPUT, None)
        sm.set_value(KEY_HTML_CONTENT, None)
        sm.set_value(KEY_AI_ANALYSIS_TEXT, None)
        sm.set_value(KEY_EXTENDED_TARGET_STOCKS_OPTIONS, None)
        sm.set_value(KEY_ALL_STOCK_DATA_FOR_REPORT, None)
        sm.set_value(KEY_PAGE_LEVEL_ERROR, None)
        sm.set_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME, None)
        sm.set_value("app.global_stock_just_changed_flag", False)
        st.rerun()

    globally_selected_code = sm.get_value("app.selected_stock_code")
    globally_selected_name = sm.get_value("app.selected_stock_name")

    if sm.get_value(KEY_PAGE_LEVEL_ERROR):
        st.error(sm.get_value(KEY_PAGE_LEVEL_ERROR), icon="🚨")

    st.sidebar.header("レポート対象銘柄リスト")
    default_target_stocks_for_report_dict = {}
    if globally_selected_code and globally_selected_name:
        ticker_for_json = globally_selected_code
        # yfinance用の.Tサフィックスを確認・追加
        if re.fullmatch(r"^\d{4}$", globally_selected_code) or \
           re.fullmatch(r"^[1-9][0-9]{2}[ACDFGHJKLMNPRSTUWXY]$", globally_selected_code) or \
           re.fullmatch(r"^[1-9][ACDFGHJKLMNPRSTUWXY][0-9]{2}$", globally_selected_code) or \
           re.fullmatch(r"^[1-9][ACDFGHJKLMNPRSTUWXY][0-9][ACDFGHJKLMNPRSTUWXY]$", globally_selected_code):
            ticker_for_json = f"{globally_selected_code}.T"
        default_target_stocks_for_report_dict = {ticker_for_json: globally_selected_name}

    default_json_text_for_sidebar = json.dumps(default_target_stocks_for_report_dict, ensure_ascii=False, indent=2) if default_target_stocks_for_report_dict else "{}"

    current_json_input_val = sm.get_value(KEY_TARGET_STOCKS_JSON_INPUT)
    if current_json_input_val is None:
        current_json_input_val = default_json_text_for_sidebar
        sm.set_value(KEY_TARGET_STOCKS_JSON_INPUT, current_json_input_val)

    new_stocks_json_input_from_sidebar = st.sidebar.text_area(
        "銘柄リスト (JSON形式: {\"ティッカー.T\": \"企業名\", ...})",
        value=current_json_input_val,
        height=150, key=f"{KEY_PREFIX}report_stocks_json_input_sidebar_widget"
    )
    if new_stocks_json_input_from_sidebar != current_json_input_val:
        sm.set_value(KEY_TARGET_STOCKS_JSON_INPUT, new_stocks_json_input_from_sidebar)
        sm.set_value(KEY_HTML_CONTENT, None)
        sm.set_value(KEY_ALL_STOCK_DATA_FOR_REPORT, None)
        sm.set_value(KEY_EXTENDED_TARGET_STOCKS_OPTIONS, None)
        sm.set_value(KEY_AI_ANALYSIS_TEXT, None)
        sm.set_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME, None)
        logger.info("User manually changed report target JSON. Dependent data cleared.")
        st.rerun()

    target_stocks_for_processing = {}
    json_str_for_processing = sm.get_value(KEY_TARGET_STOCKS_JSON_INPUT, default_json_text_for_sidebar)
    try:
        parsed_json = json.loads(json_str_for_processing)
        if isinstance(parsed_json, dict) and parsed_json:
            target_stocks_for_processing = parsed_json
        elif default_target_stocks_for_report_dict:
            target_stocks_for_processing = default_target_stocks_for_report_dict
    except json.JSONDecodeError:
        if default_target_stocks_for_report_dict:
            target_stocks_for_processing = default_target_stocks_for_report_dict

    collect_related = st.checkbox(
        "関連銘柄も同時に収集する",
        value=sm.get_value(KEY_COLLECT_RELATED_STOCKS, False),
        key=f"{KEY_PREFIX}collect_related_stocks_checkbox_widget"
    )
    if collect_related != sm.get_value(KEY_COLLECT_RELATED_STOCKS):
        sm.set_value(KEY_COLLECT_RELATED_STOCKS, collect_related)
        sm.set_value(KEY_HTML_CONTENT, None)
        sm.set_value(KEY_ALL_STOCK_DATA_FOR_REPORT, None)
        sm.set_value(KEY_EXTENDED_TARGET_STOCKS_OPTIONS, None)
        sm.set_value(KEY_AI_ANALYSIS_TEXT, None)
        sm.set_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME, None)
        logger.info(f"{KEY_COLLECT_RELATED_STOCKS} changed. Dependent data cleared.")
        st.rerun()

    if st.button("株式情報レポート生成・表示", type="primary", key=f"{KEY_PREFIX}generate_report_button_widget"):
        logger.info(f"'{KEY_PREFIX}generate_report_button_widget' clicked. Targets: {target_stocks_for_processing}")
        if not target_stocks_for_processing:
            st.warning("レポート対象の銘柄が指定されていません。")
        else:
            sm.set_value(KEY_TARGET_STOCKS_JSON_INPUT, json.dumps(target_stocks_for_processing, ensure_ascii=False, indent=2))
            sm.set_value(KEY_REPORT_BUTTON_CLICKED, True)
            sm.set_value(KEY_HTML_CONTENT, None)
            sm.set_value(KEY_AI_ANALYSIS_TEXT, "")
            sm.set_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME, None)
            sm.set_value(KEY_AI_ANALYSIS_TRIGGERED, False)
            sm.set_value(KEY_AI_ANALYSIS_ACTIVE, False)
            sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, [])
            sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE, None)
            sm.set_value(KEY_PAGE_LEVEL_ERROR, None)
            sm.set_value(KEY_ALL_STOCK_DATA_FOR_REPORT, None)
            sm.set_value(KEY_EXTENDED_TARGET_STOCKS_OPTIONS, None)
            st.rerun()

    if sm.get_value(KEY_REPORT_BUTTON_CLICKED):
        logger.info(f"Processing report generation as {KEY_REPORT_BUTTON_CLICKED} is True.")

        final_target_stocks_json = sm.get_value(KEY_TARGET_STOCKS_JSON_INPUT, "{}")
        try:
            actual_target_stocks = json.loads(final_target_stocks_json)
            if not (isinstance(actual_target_stocks, dict) and actual_target_stocks):
                logger.warning(f"レポート生成時、最終的な対象銘柄リストが空または不正です: {actual_target_stocks}")
                st.warning("レポート対象銘柄が設定されていません。")
                sm.set_value(KEY_REPORT_BUTTON_CLICKED, False); st.rerun(); return
        except Exception as e:
            logger.error(f"レポート対象JSONの最終パース失敗: {e}")
            st.error(f"レポート対象銘柄のJSON形式が不正です: {e}")
            sm.set_value(KEY_REPORT_BUTTON_CLICKED, False); st.rerun(); return

        logger.info(f"レポート生成対象 (確定): {actual_target_stocks}")
        status_placeholder_report = st.empty()
        try:
            status_placeholder_report.info("レポート生成処理を開始します...", icon="⏳")
            effective_target_stocks = actual_target_stocks.copy()

            if sm.get_value(KEY_COLLECT_RELATED_STOCKS, False):
                status_placeholder_report.info("関連銘柄を検索中...", icon="🔍")
                all_stocks_master_data = sm.get_value(KEY_FULL_DATA_FOR_RELATED)
                if all_stocks_master_data is None:
                    status_placeholder_report.info("関連銘柄検索のため、全銘柄データを読み込みます...(初回のみ)", icon="⏳")
                    try:
                        json_bytes = fm.get_file_bytes("stock_data_all")
                        if json_bytes:
                            all_stocks_master_data = json.loads(json_bytes.decode('utf-8'))
                            sm.set_value(KEY_FULL_DATA_FOR_RELATED, all_stocks_master_data)
                            logger.info(f"Loaded 'stock_data_all.json' for related stocks feature ({len(all_stocks_master_data)} items).")
                        else:
                            all_stocks_master_data = {}
                            logger.error("'stock_data_all.json' is empty or could not be retrieved.")
                            st.warning("'stock_data_all.json'が空のため、関連銘柄を検索できません。")
                    except Exception as e:
                        all_stocks_master_data = {}
                        logger.error(f"Failed to load 'stock_data_all.json': {e}", exc_info=True)
                        st.error(f"全銘柄データ(stock_data_all.json)の読み込みに失敗しました: {e}")

                if not all_stocks_master_data:
                    logger.warning("関連銘柄検索: 全銘柄データ(stock_data_all)が見つかりません。")
                else:
                    market_cap_df = stock_utils.create_market_cap_df_from_json_dict(all_stocks_master_data)
                    if not market_cap_df.empty and 'コード' in market_cap_df.columns:
                        market_cap_df['コード'] = market_cap_df['コード'].astype(str)
                        logger.info("関連銘柄検索のため、market_cap_dfの'コード'列を文字列型に変換しました。")

                    if market_cap_df.empty:
                        logger.warning("関連銘柄検索: 時価総額DataFrameが空です。")
                    else:
                        logger.info(f"関連銘柄検索: 時価総額DF作成完了 ({len(market_cap_df)}件)")
                        if actual_target_stocks:
                            base_ticker_with_t = next(iter(actual_target_stocks))
                            base_ticker_no_t = base_ticker_with_t.split('.')[0]
                            logger.info(f"関連銘柄検索の基準銘柄: {base_ticker_no_t} (元: {base_ticker_with_t})")
                            similar_companies_df = stock_utils.get_similar_companies(market_cap_df, base_ticker_no_t, num_neighbors_per_side=2)
                            logger.info(f"基準銘柄 {base_ticker_no_t} の類似企業として {len(similar_companies_df)} 件見つかりました（自身含む）。")
                            if not similar_companies_df.empty:
                                for _, row in similar_companies_df.iterrows():
                                    related_ticker_no_t_val = str(row['コード'])
                                    related_name_val = str(row['銘柄名'])
                                    related_ticker_with_t_val = f"{related_ticker_no_t_val}.T"
                                    if related_ticker_with_t_val not in effective_target_stocks:
                                        effective_target_stocks[related_ticker_with_t_val] = related_name_val
                                        logger.info(f"関連銘柄追加: {related_name_val} ({related_ticker_with_t_val})")
                        else: logger.warning("関連銘柄検索: 基準となる銘柄リストが空です。")

            logger.info(f"最終的なレポート生成対象銘柄 (関連銘柄処理後): {effective_target_stocks}")

            if not effective_target_stocks:
                st.warning("処理対象の銘柄がありません。")
                sm.set_value(KEY_REPORT_BUTTON_CLICKED, False); st.rerun(); return

            status_placeholder_report.info(f"全{len(effective_target_stocks)}銘柄のデータ取得開始...", icon="⏳")

            # --- ▼▼▼ ここから修正 ▼▼▼ ---
            # 修正したload_all_stock_data_for_report関数を呼び出す
            all_stock_data = load_all_stock_data_for_report(effective_target_stocks, akm, sm)
            # --- ▲▲▲ ここまで修正 ▲▲▲ ---

            if not all_stock_data:
                logger.error("load_all_stock_data_for_reportから空のデータが返されました。")
                sm.set_value(KEY_PAGE_LEVEL_ERROR, "銘柄データの取得に失敗しました。詳細はログを確認してください。")
                sm.set_value(KEY_HTML_CONTENT, "<p class='text-red-500'>銘柄データの取得に失敗しました。</p>")
            else:
                logger.info(f"データ取得完了。HTMLレポート生成へ。取得銘柄数: {len(all_stock_data)}")
                sm.set_value(KEY_ALL_STOCK_DATA_FOR_REPORT, all_stock_data)
                sm.set_value(KEY_EXTENDED_TARGET_STOCKS_OPTIONS, effective_target_stocks)
                options_html = "".join([f'<option value="{str(c).split(".")[0]}">{n} ({str(c).split(".")[0]})</option>' for c, n in effective_target_stocks.items()])
                js_data = json.dumps(all_stock_data, ensure_ascii=False, allow_nan=True).replace('NaN', 'null')

                logger.debug(f"HTML生成用JSデータ (最初の500文字): {js_data[:500]}")
                html_generated = ui_styles.generate_stock_report_html(options_html, js_data)
                sm.set_value(KEY_HTML_CONTENT, html_generated)
                logger.info(f"HTMLコンテンツ設定完了。長さ: {len(html_generated) if html_generated else 0}")
                status_placeholder_report.success("HTMLレポート生成完了！", icon="🎉")
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"レポート生成処理中に予期せぬエラー: {e}", exc_info=True)
            sm.set_value(KEY_PAGE_LEVEL_ERROR, f"レポート生成エラー: {e}")
            if hasattr(status_placeholder_report, 'error'): status_placeholder_report.error(f"レポート生成エラー: {e}", icon="🚨")
        finally:
            if hasattr(status_placeholder_report, 'empty'): status_placeholder_report.empty()
            sm.set_value(KEY_REPORT_BUTTON_CLICKED, False)
            st.rerun()

    html_content_val = sm.get_value(KEY_HTML_CONTENT)
    if html_content_val:
        logger.info(f"HTMLコンテンツを表示します。最初の100文字: {html_content_val[:100]}")
        if "<p class='text-red-500'>" not in html_content_val and "レポート生成済み (仮)" not in html_content_val :
            st.components.v1.html(html_content_val, height=1800, scrolling=True)
        elif "レポート生成済み (仮)" in html_content_val:
            st.info("レポートデータの取得処理は完了しましたが、HTMLテンプレートの適用に問題がある可能性があります（仮表示）。")
            st.markdown(html_content_val, unsafe_allow_html=True)
        else:
            st.markdown(html_content_val, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("AIによる財務・関連ニュース分析")
        ai_status_placeholder = st.empty()

        if sm.get_value(KEY_AI_ANALYSIS_ACTIVE):
            status_msgs_ai = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, [])
            if status_msgs_ai:
                current_status_text_ai = "AI分析 処理状況:\n" + "\n".join(status_msgs_ai)
                is_error_ai = any("エラー" in msg.lower() or "失敗" in msg.lower() for msg in status_msgs_ai)
                is_completed_ai = "分析完了" in (status_msgs_ai[-1] if status_msgs_ai else "")
                if is_error_ai: ai_status_placeholder.error(current_status_text_ai, icon="🚨")
                elif is_completed_ai: ai_status_placeholder.success(current_status_text_ai, icon="✅")
                else: ai_status_placeholder.info(current_status_text_ai, icon="⏳")
        elif not sm.get_value(KEY_AI_ANALYSIS_ACTIVE) and (sm.get_value(KEY_AI_PROCESSING_TIME_MESSAGE) or sm.get_value(f"{KEY_PREFIX}page_level_error_ai_section")):
            ai_status_placeholder.empty()

        default_ai_question = "この銘柄の財務状況と最近のニュースを分析し、投資判断のポイントを教えてください。"
        if sm.get_value(KEY_AI_USER_QUESTION) is None: sm.set_value(KEY_AI_USER_QUESTION, default_ai_question)

        ai_question_input = st.text_area(
            "AIへの質問（適宜編集してください）:",
            value=sm.get_value(KEY_AI_USER_QUESTION),
            height=100, key=f"{KEY_PREFIX}ai_question_input_widget_v2"
        )
        if ai_question_input != sm.get_value(KEY_AI_USER_QUESTION):
            sm.set_value(KEY_AI_USER_QUESTION, ai_question_input)

        analysis_target_options_dict_ai = {}
        try:
            current_target_stocks_for_dropdown_ai = sm.get_value(
                KEY_EXTENDED_TARGET_STOCKS_OPTIONS,
                json.loads(sm.get_value(KEY_TARGET_STOCKS_JSON_INPUT, '{}'))
            )
            if isinstance(current_target_stocks_for_dropdown_ai, dict):
                analysis_target_options_dict_ai = {
                    f"{name} ({str(ticker).split('.')[0]})": ticker
                    for ticker, name in current_target_stocks_for_dropdown_ai.items()
                }
        except json.JSONDecodeError: analysis_target_options_dict_ai = {}

        selected_display_name_for_ai_analysis = None
        if not analysis_target_options_dict_ai:
            st.info("AI分析対象の銘柄がレポートリストにありません。サイドバーで銘柄を追加し、「株式情報レポート生成・表示」ボタンを押してください。", icon="ℹ️")
        else:
            options_list_for_ai_select = list(analysis_target_options_dict_ai.keys())

            default_selected_display_ai = sm.get_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME)
            current_idx_for_ai_select = 0
            if default_selected_display_ai and default_selected_display_ai in options_list_for_ai_select:
                current_idx_for_ai_select = options_list_for_ai_select.index(default_selected_display_ai)
            elif globally_selected_code and globally_selected_name:
                potential_default_display = f"{globally_selected_name} ({globally_selected_code})"
                if potential_default_display in options_list_for_ai_select:
                    current_idx_for_ai_select = options_list_for_ai_select.index(potential_default_display)
                elif options_list_for_ai_select:
                    current_idx_for_ai_select = 0
            elif options_list_for_ai_select:
                current_idx_for_ai_select = 0

            selected_display_name_for_ai_analysis = st.selectbox(
                "AI分析する銘柄を選択してください:",
                options=options_list_for_ai_select,
                index=current_idx_for_ai_select,
                key=f"{KEY_PREFIX}ai_analysis_stock_select_widget"
            )
            if selected_display_name_for_ai_analysis != sm.get_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME):
                sm.set_value(KEY_AI_SELECTED_STOCK_DISPLAY_NAME, selected_display_name_for_ai_analysis)

            if selected_display_name_for_ai_analysis:
                if st.button("選択した銘柄のAI分析を実行", type='primary', key=f"{KEY_PREFIX}run_ai_analysis_button_widget"):
                    sm.set_value(KEY_AI_ANALYSIS_TRIGGERED, True)
                    sm.set_value(KEY_AI_ANALYSIS_ACTIVE, True)
                    sm.set_value(KEY_AI_ANALYSIS_TEXT, "")
                    sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE, None)
                    sm.set_value(f"{KEY_PREFIX}page_level_error_ai_section", None)
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ["AI分析プロセスを開始します..."])
                    ai_status_placeholder.info("AI分析 処理状況:\n" + "\n".join(sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES)), icon="⏳")
                    st.rerun()

        if sm.get_value(KEY_AI_ANALYSIS_TRIGGERED) and selected_display_name_for_ai_analysis:
            with st.spinner(f"{selected_display_name_for_ai_analysis} のAI分析を実行中です..."):
                try:
                    if not api_services.is_gemini_api_configured():
                        raise ValueError("[AI分析エラー] Gemini APIキーが不足または正しく設定されていません。")

                    selected_ticker_ai_with_suffix = analysis_target_options_dict_ai[selected_display_name_for_ai_analysis]
                    selected_name_ai = selected_display_name_for_ai_analysis.split(' (')[0]
                    selected_code_no_t_ai = selected_ticker_ai_with_suffix.split('.')[0]

                    ai_status_messages_list_update = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, [])
                    ai_status_messages_list_update.append(f"{selected_name_ai} ({selected_code_no_t_ai}) のAI分析用データ準備中...")
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_update[:])

                    start_time_ai = time.time()

                    try:
                        logger.info(f"AI分析用データ取得開始 (yfinance): {selected_name_ai} ({selected_ticker_ai_with_suffix})")
                        ticker_obj_for_ai = yf.Ticker(selected_ticker_ai_with_suffix)
                        info_for_ai = ticker_obj_for_ai.info
                        if not info_for_ai or not info_for_ai.get('symbol'):
                            raise ValueError(f"{selected_name_ai} の基本情報(info)をAI分析用に取得できませんでした。")

                        fin_df_ai = ticker_obj_for_ai.financials
                        q_fin_df_ai = ticker_obj_for_ai.quarterly_financials
                        div_df_ai_raw = ticker_obj_for_ai.dividends
                        div_df_ai = div_df_ai_raw.reset_index() if div_df_ai_raw is not None and not div_df_ai_raw.empty else pd.DataFrame()
                        earn_df_ai_raw = ticker_obj_for_ai.earnings_dates
                        earn_df_ai = earn_df_ai_raw.reset_index() if earn_df_ai_raw is not None and not earn_df_ai_raw.empty else pd.DataFrame()
                        reco_df_ai_raw = ticker_obj_for_ai.recommendations
                        reco_df_ai = reco_df_ai_raw.reset_index() if reco_df_ai_raw is not None and not reco_df_ai_raw.empty else pd.DataFrame()
                        logger.info(f"AI分析用 yfinanceデータ取得完了: {selected_name_ai}")
                    except Exception as e_yf_ai:
                        logger.error(f"AI分析用 yfinanceデータ取得エラー ({selected_name_ai}): {e_yf_ai}")
                        raise ValueError(f"{selected_name_ai} の財務データ取得中にエラーが発生しました (AI分析用): {e_yf_ai}")

                    all_stock_data_for_ai_prompt = sm.get_value(KEY_ALL_STOCK_DATA_FOR_REPORT, {})
                    current_stock_data_for_ai_prompt = all_stock_data_for_ai_prompt.get(selected_code_no_t_ai, {})
                    comp_news_for_ai_prompt = current_stock_data_for_ai_prompt.get("news", [])
                    user_question_for_ai = sm.get_value(KEY_AI_USER_QUESTION, default_ai_question)

                    ai_task_prompt_parts = [
                        f"あなたは世界的に著名な金融アナリストです。",
                        f"以下の {selected_name_ai} ({selected_code_no_t_ai}) に関する財務データと最新ニュースを詳細に分析してください。",
                        "証券マンらしく、投資判断に役立つ注目すべき点を具体的に指摘してください。",
                        "分析の根拠となったデータ（財務諸表の項目名やニュースのタイトルなど）を適宜引用し、プロフェッショナルかつ客観的な視点で記述してください。",
                        "マークダウン形式で、見出しや箇条書きを効果的に使用して、読みやすいレポートを作成してください。",
                        "特に若年層の投資家が興味を持つような、分かりやすい言葉遣いを心がけてください。",
                        f"ユーザーからの主な相談内容は「{user_question_for_ai}」です。これも考慮に入れたアドバイスをお願いします。"
                    ]

                    financials_md_ai = f"\n\n## {selected_name_ai} 財務諸表 (通期)\n"
                    financials_md_ai += (fin_df_ai.head().to_markdown(index=True) if fin_df_ai is not None and not fin_df_ai.empty else 'データなし')
                    quarterly_md_ai = f"\n\n## {selected_name_ai} 財務諸表 (四半期)\n"
                    quarterly_md_ai += (q_fin_df_ai.head().to_markdown(index=True) if q_fin_df_ai is not None and not q_fin_df_ai.empty else 'データなし')
                    dividends_md_ai = f"\n\n## 配当情報\n"
                    dividends_md_ai += (div_df_ai.tail().to_markdown(index=False) if not div_df_ai.empty else 'データなし')
                    earnings_md_ai = f"\n\n## EPS情報\n"
                    earnings_md_ai += (earn_df_ai.tail().to_markdown(index=False) if not earn_df_ai.empty else 'データなし')
                    ratings_md_ai = f"\n\n## アナリスト評価\n"
                    ratings_md_ai += (reco_df_ai.tail().to_markdown(index=False) if not reco_df_ai.empty else 'データなし')
                    company_news_md_ai = f"\n\n## {selected_name_ai} 関連ニュース (上位5件)\n"
                    if comp_news_for_ai_prompt:
                        for item_news in comp_news_for_ai_prompt[:5]: company_news_md_ai += f"- {item_news.get('date','N/A')} {item_news.get('title','N/A')} ({item_news.get('source','N/A')})\n"
                    else: company_news_md_ai += "関連ニュースなし\n"

                    full_prompt_for_ai_analysis = "\n".join(ai_task_prompt_parts) + financials_md_ai + quarterly_md_ai + dividends_md_ai + earnings_md_ai + ratings_md_ai + company_news_md_ai

                    related_stocks_comparison_prompt_part_ai = ""
                    if sm.get_value(KEY_COLLECT_RELATED_STOCKS, False):
                        ai_status_messages_list_update.append("関連銘柄情報を収集中（AI分析用）...")
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_update[:])

                        all_stocks_master_data_for_related_ai = sm.get_value(KEY_FULL_DATA_FOR_RELATED) # ★修正: 全データを使用

                        if all_stocks_master_data_for_related_ai and all_stock_data_for_ai_prompt:
                            market_cap_df_for_related_ai = stock_utils.create_market_cap_df_from_json_dict(all_stocks_master_data_for_related_ai)
                            if not market_cap_df_for_related_ai.empty:
                                similar_companies_df_for_ai = stock_utils.get_similar_companies(market_cap_df_for_related_ai, selected_code_no_t_ai, num_neighbors_per_side=2)
                                related_stocks_info_md_parts_ai = ["\n\n## 比較参考: 関連銘柄の財務・ニュース概要\n"]
                                added_related_count_ai = 0
                                for _, row_related in similar_companies_df_for_ai.iterrows():
                                    related_ticker_no_t_val_ai = str(row_related['コード'])
                                    if related_ticker_no_t_val_ai == selected_code_no_t_ai: continue
                                    if related_ticker_no_t_val_ai in all_stock_data_for_ai_prompt:
                                        related_data_ai = all_stock_data_for_ai_prompt[related_ticker_no_t_val_ai]
                                        related_stocks_info_md_parts_ai.append(f"### {related_data_ai.get('companyName', row_related['銘柄名'])} ({related_ticker_no_t_val_ai})\n")
                                        financials_list_related_ai = related_data_ai.get('financials', [])
                                        key_metrics_to_extract_ai = ["時価総額", "PER", "PBR", "配当利回り", "ROE (実績)"]
                                        for metric_label_ai in key_metrics_to_extract_ai:
                                            metric_value_found_ai = next((f_item['value'] for f_item in financials_list_related_ai if f_item['label'] == metric_label_ai), 'N/A')
                                            related_stocks_info_md_parts_ai.append(f"- {metric_label_ai}: {metric_value_found_ai}\n")
                                        news_items_list_related_ai = related_data_ai.get('news', [])[:2]
                                        if news_items_list_related_ai:
                                            related_stocks_info_md_parts_ai.append("- 直近ニュース:\n")
                                            for news_item_related_ai in news_items_list_related_ai:
                                                related_stocks_info_md_parts_ai.append(f"  - {news_item_related_ai.get('title', 'N/A')}\n")
                                        else: related_stocks_info_md_parts_ai.append("- 直近ニュース: N/A\n")
                                        added_related_count_ai +=1
                                        if added_related_count_ai >= 3: break
                                if added_related_count_ai > 0:
                                    full_prompt_for_ai_analysis += "".join(related_stocks_info_md_parts_ai)
                                    related_stocks_comparison_prompt_part_ai = f"""
## 関連銘柄との比較分析
上記の関連銘柄の情報も踏まえ、主分析銘柄である **{selected_name_ai}** がこれらの企業と比較して、
**どのような点で優れているか、また、どのような点で見劣りする可能性があるか**を具体的に分析してください。
特に以下の観点から、詳細な比較と評価をお願いします。
1.  **財務健全性・収益性**: PER、PBR、ROE、配当利回りなどの指標を比較し、割安感や収益力の違いを指摘してください。
2.  **成長性**: 過去の業績トレンドや将来の成長見通し（もし情報があれば）を比較し、成長ポテンシャルの違いを考察してください。
3.  **市場での競争力・ポジショニング**: 提供されているニュース情報や事業概要から、各社の強みや弱み、市場での立ち位置の違いを推察し、{selected_name_ai} の競争優位性または課題を明らかにしてください。
4.  **投資妙味**: 上記の比較分析に基づき、現時点での {selected_name_ai} の投資対象としての魅力について、関連銘柄と比較しながら総合的に評価してください。
客観的なデータと論理的な推論に基づき、具体的かつ説得力のある比較分析を行ってください。
"""
                                    full_prompt_for_ai_analysis += related_stocks_comparison_prompt_part_ai
                                    ai_status_messages_list_update.append(f"{added_related_count_ai}件の関連銘柄情報をプロンプトに追加。比較分析を指示。")
                                else: ai_status_messages_list_update.append("比較対象となる関連銘柄情報なし (プロンプトに追加せず)。")
                            else: ai_status_messages_list_update.append("関連銘柄検索用データ(時価総額DF)作成失敗（AI分析）。")
                        else: ai_status_messages_list_update.append("関連銘柄検索用データ(全銘柄情報/レポートデータ)ロード失敗（AI分析）。")
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_update[:])

                    logger.info(f"AI分析プロンプト生成完了。対象: {selected_name_ai}, 文字数: {len(full_prompt_for_ai_analysis)}")
                    logger.debug(f"--- AI Prompt for {selected_name_ai} ---\n{full_prompt_for_ai_analysis}\n--- End of AI Prompt ---")

                    ai_status_messages_list_update.append(f"LLM ({active_model}) にリクエスト送信中...")
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_update[:])

                    ai_result_text_val = api_services.generate_gemini_response(full_prompt_for_ai_analysis, active_model, temperature=0.5)
                    sm.set_value(KEY_AI_ANALYSIS_TEXT, ai_result_text_val)
                    if ai_result_text_val.startswith("[LLM エラー]"):
                        raise ValueError(ai_result_text_val)

                    processing_time_ai = time.time() - start_time_ai
                    minutes_ai_proc, seconds_ai_proc = divmod(int(processing_time_ai), 60)
                    time_msg_ai = f"{selected_name_ai} のAI分析が完了しました。処理時間: {minutes_ai_proc}分{seconds_ai_proc}秒"
                    sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE, time_msg_ai)
                    ai_status_messages_list_update.append("分析完了。")
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_update[:])

                except Exception as e_ai_analysis_exec:
                    logger.error(f"AI分析処理中にエラー ({selected_name_ai}): {e_ai_analysis_exec}", exc_info=True)
                    err_msg_for_ui_ai = f"AI分析中にエラーが発生しました ({selected_name_ai}): {e_ai_analysis_exec}"
                    sm.set_value(f"{KEY_PREFIX}page_level_error_ai_section", err_msg_for_ui_ai)
                    sm.set_value(KEY_AI_ANALYSIS_TEXT, f"[AI分析エラー] {e_ai_analysis_exec}")
                    ai_status_messages_list_err = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, [])
                    ai_status_messages_list_err.append(f"エラー発生: {e_ai_analysis_exec}")
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES, ai_status_messages_list_err[:])
                finally:
                    sm.set_value(KEY_AI_ANALYSIS_TRIGGERED, False)
                    sm.set_value(KEY_AI_ANALYSIS_ACTIVE, False)
                    st.rerun()

        if sm.get_value(KEY_AI_PROCESSING_TIME_MESSAGE):
            st.success(sm.get_value(KEY_AI_PROCESSING_TIME_MESSAGE), icon="✅")
            if not sm.get_value(KEY_AI_ANALYSIS_TEXT,"").startswith("[AI分析エラー]") and \
               not sm.get_value(KEY_AI_ANALYSIS_TEXT,"").startswith("[LLM エラー]"):
                sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE, None)

        ai_text_to_display = sm.get_value(KEY_AI_ANALYSIS_TEXT, "")
        if ai_text_to_display:
            st.markdown("---"); st.subheader("AIによる分析結果:")
            if ai_text_to_display.startswith("[AI分析エラー]") or ai_text_to_display.startswith("[LLM エラー]"):
                st.error(ai_text_to_display, icon="🚨")
            else:
                st.markdown(ai_text_to_display)

        ai_section_error = sm.get_value(f"{KEY_PREFIX}page_level_error_ai_section")
        if ai_section_error and not (ai_text_to_display and (ai_text_to_display.startswith("[AI分析エラー]") or ai_text_to_display.startswith("[LLM エラー]"))):
            st.error(ai_section_error, icon="🚨")

    elif not sm.get_value(KEY_REPORT_BUTTON_CLICKED) and not sm.get_value(KEY_AI_ANALYSIS_TRIGGERED):
        st.info("上の「株式情報レポート生成・表示」ボタンを押して、レポートとAI分析機能を利用してください。", icon="ℹ️")

    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back_nav, col_next_nav = st.columns(2)
    with col_back_nav:
        if st.button("戻る (ステップ2: 取引履歴へ)", key="s3_back_to_s2", use_container_width=True): sm.set_value("app.current_step", 2); st.rerun()
    with col_next_nav:
        if st.button("次へ進む (ステップ4: LLMチャットへ)", type="primary", key="s3_next_to_s4", use_container_width=True): sm.set_value("app.current_step", 4); st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

