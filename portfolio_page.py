# portfolio_page.py
import streamlit as st
import pandas as pd
import json
import re
import logging
import time
from datetime import datetime, timezone, timedelta
import io
import os

# --- 可視化ライブラリ ---
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
# ★安定化対応: japanize-matplotlibをインポートして日本語設定を自動化
import japanize_matplotlib

# --- 内部モジュール ---
import ui_styles
import config as app_config
import api_services
import news_services

logger = logging.getLogger(__name__)


# --- StateManagerで使用するキー ---
KEY_BALANCE_DF = "portfolio.balance_df"
KEY_STOCK_DF = "portfolio.stock_df"
KEY_PAGE_INITIALIZED = "portfolio.page_initialized_v3"
KEY_ANALYSIS_BUTTON_CLICKED = "portfolio.analysis_button_clicked"
KEY_ANALYSIS_DATA = "portfolio.analysis_data"
KEY_ANALYSIS_ERROR = "portfolio.analysis.error"
KEY_STATIC_CHART_MODE = "portfolio.static_chart_mode"
KEY_AI_ANALYSIS_CLICKED = "portfolio.ai_analysis_clicked"
KEY_AI_QUESTION = "portfolio.ai_question"
KEY_AI_RESULT = "portfolio.ai_result"
KEY_AI_ERROR = "portfolio.ai_error"
KEY_LAST_AI_PROMPT = "portfolio.last_ai_prompt"

# --- データ取得・加工ヘルパー関数 ---
def _fetch_and_process_data(stock_df, akm):
    error_messages = []
    performance_data = {}
    all_news_articles = []
    tickers_to_fetch = {}

    if stock_df is not None and not stock_df.empty:
        for _, row in stock_df.iterrows():
            code = str(row.get("証券コード", "")).strip()
            name = str(row.get("銘柄", "")).strip()
            if code and name:
                ticker = f"{code}.T" if re.match(r"^\d{4}$", code) else code
                tickers_to_fetch[ticker] = {"name": name, "amount_jpy": row.get("金額(万円)", 0) * 10000}

    if not tickers_to_fetch:
        error_messages.append("分析対象となる証券コードがポートフォリオにありません。")
        return None, error_messages

    tickers_to_fetch["^N225"] = {"name": "日経平均株価", "amount_jpy": 0}

    with st.spinner("各銘柄および日経平均の過去1年間の株価データを取得中..."):
        for ticker, info in tickers_to_fetch.items():
            df, err = api_services.get_stock_price_history(ticker, period="1y", interval="1d")
            if err or df is None or df.empty:
                error_messages.append(f"'{info['name']}' ({ticker}) の株価取得に失敗しました: {err}")
                continue
            performance_data[ticker] = { "name": info["name"], "df": df, "amount_jpy": info["amount_jpy"] }
        logger.info(f"株価取得完了。取得成功: {len(performance_data)}件")

    with st.spinner("関連ニュースを取得中..."):
        for ticker, info in tickers_to_fetch.items():
            if ticker == "^N225": continue
            name = info['name']
            news_result = news_services.fetch_all_stock_news(name, app_config.NEWS_SERVICE_CONFIG["active_apis"], akm)
            company_news = news_result.get("all_company_news_deduplicated", [])
            if company_news: all_news_articles.extend(company_news)
            if news_result.get("api_errors"):
                for api, errors in news_result.get("api_errors", {}).items():
                    if errors.get('company'): logger.warning(f"ニュース取得エラー ({name}, {api}): {errors['company']}")

    all_news_articles.sort(key=lambda x: x.get('日付', '1970/01/01 00:00'), reverse=True)

    if not performance_data:
        error_messages.append("分析可能な株価データを1件も取得できませんでした。")
        return None, error_messages

    return { "performance_data": performance_data, "all_news_articles": all_news_articles }, error_messages

# --- UI描画ヘルパー関数 ---

def _calculate_portfolio_timeseries(analysis_data):
    """
    ポートフォリオ評価額の時系列データを計算し、analysis_dataに追加して返す。
    この関数は描画を行わず、データ処理に専念する。
    """
    performance_data = analysis_data.get("performance_data", {})
    if not performance_data:
        return analysis_data

    portfolio_value_total = None
    for ticker, data in performance_data.items():
        df = data.get("df")
        if df is None or df.empty or 'Close' not in df.columns:
            continue

        if data.get("amount_jpy", 0) > 0 and ticker != "^N225":
            latest_price = df['Close'].dropna().iloc[-1] if not df['Close'].dropna().empty else 0
            if latest_price > 0:
                shares = data["amount_jpy"] / latest_price
                portfolio_value = (df['Close'] * shares) / 10000
                if portfolio_value_total is None:
                    portfolio_value_total = portfolio_value.copy()
                else:
                    portfolio_value_total = portfolio_value_total.add(portfolio_value, fill_value=0)

    if portfolio_value_total is not None:
        analysis_data['portfolio_value_timeseries'] = portfolio_value_total

    return analysis_data

def _create_plotly_chart(analysis_data):
    performance_data = analysis_data.get("performance_data", {})
    portfolio_value_total = analysis_data.get("portfolio_value_timeseries") # 計算済みのデータを取得

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for ticker, data in performance_data.items():
        df = data.get("df")
        if df is None or df.empty: continue
        performance_normalized = (df['Close'] / df['Close'].iloc[0]) * 100
        fig.add_trace(go.Scatter(x=df.index, y=performance_normalized, name=data["name"], mode='lines'), secondary_y=False)

    if portfolio_value_total is not None:
        fig.add_trace(go.Scatter(x=portfolio_value_total.index, y=portfolio_value_total, name="株式合計評価額(万円)", mode='lines+markers', line=dict(color='orangered', width=2.5, dash='solid'), marker=dict(size=4)), secondary_y=True)

    fig.update_layout(title_text="株価パフォーマンスと株式合計評価額の推移", xaxis_title="日付", yaxis_title="パフォーマンス (1年前=100)", yaxis2_title="株式合計評価額 (万円)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), height=600, margin=dict(l=20, r=20, t=80, b=20))
    return fig

def _create_matplotlib_chart_image(analysis_data):
    """matplotlibを使用してチャート画像を生成する"""
    performance_data = analysis_data.get("performance_data", {})
    portfolio_value_total = analysis_data.get("portfolio_value_timeseries") # 計算済みのデータを取得

    fig, ax1 = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    ax2 = ax1.twinx()

    for ticker, data in performance_data.items():
        df = data.get("df")
        if df is None or df.empty: continue
        performance_normalized = (df['Close'] / df['Close'].iloc[0]) * 100
        ax1.plot(df.index, performance_normalized, label=data["name"])

    if portfolio_value_total is not None:
        ax2.plot(portfolio_value_total.index, portfolio_value_total, label="株式合計評価額(万円)", color='orangered', linestyle='--', marker='o', markersize=4)

    ax1.set_xlabel('日付')
    ax1.set_ylabel('パフォーマンス (1年前=100)')
    ax2.set_ylabel('株式合計評価額 (万円)', color='orangered')
    ax2.tick_params(axis='y', labelcolor='orangered')
    fig.suptitle('株価パフォーマンスと株式合計評価額の推移', fontsize=16)

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3)

    ax1.grid(True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()

def _display_news(analysis_data):
    st.subheader("関連ニュース")
    news_articles = analysis_data.get("all_news_articles", [])
    if not news_articles:
        st.info("関連するニュースは見つかりませんでした。")
        return
    for article in news_articles[:20]:
        date, title, source, url, desc = article.get('日付', 'N/A'), article.get('タイトル', 'N/A'), article.get('ソース', 'N/A'), article.get('URL', '#'), article.get('概要', '')
        with st.expander(f"{date} - **{title}** ({source})"):
            st.markdown(f"**ソース:** {source}")
            if desc and desc != 'N/A': st.markdown(f"**概要:** {desc}")
            st.markdown(f"**[記事を読む]({url})**", unsafe_allow_html=True)

def _create_prompt_for_fp_analysis(sm, analysis_data, user_question):
    try:
        balance_df, stock_df = sm.get_value(KEY_BALANCE_DF), sm.get_value(KEY_STOCK_DF)
        asset_json = json.dumps({"資産状況": balance_df.to_dict('records'), "株式保有状況": stock_df.to_dict('records')}, ensure_ascii=False, indent=2)

        summary_texts = ["\n## パフォーマンスサマリー (過去1年)"]
        performance_data = analysis_data.get("performance_data", {})
        for ticker, data in performance_data.items():
            df = data['df']
            if not df.empty and not df['Close'].dropna().empty:
                latest_performance = (df['Close'].dropna().iloc[-1] / df['Close'].dropna().iloc[0]) * 100
                summary_texts.append(f"・{data['name']}: 100 → {latest_performance:.1f}")

        portfolio_value_ts = analysis_data.get('portfolio_value_timeseries')
        if portfolio_value_ts is not None and not portfolio_value_ts.empty:
            start_val, end_val = portfolio_value_ts.dropna().iloc[0], portfolio_value_ts.dropna().iloc[-1]
            summary_texts.append(f"・株式合計評価額: {start_val:,.0f}万円 → {end_val:,.0f}万円")
        summary_text = "\n".join(summary_texts)

        # ★エラー修正: `reset_index()`が正しく動作するように、事前にindexの名前を設定する
        all_series = [pd.Series(d['df']['Close'], name=d['name']) for d in performance_data.values()]
        if portfolio_value_ts is not None: all_series.append(pd.Series(portfolio_value_ts, name="株式合計評価額(万円)"))

        consolidated_df = pd.concat(all_series, axis=1).ffill()
        consolidated_df.index.name = "日付" # これでreset_index()が'日付'列を作成する
        df_for_markdown = consolidated_df.reset_index()

        df_for_markdown['日付'] = pd.to_datetime(df_for_markdown['日付']).dt.strftime('%Y-%m-%d')
        for col in df_for_markdown.columns:
            if col != '日付': df_for_markdown[col] = df_for_markdown[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "N/A")
        chart_markdown = "\n## パフォーマンス時系列データ (日次)\n" + df_for_markdown.to_markdown(index=False)

        news_json = json.dumps(analysis_data.get("all_news_articles", []), ensure_ascii=False, indent=2)
        current_time_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y年%m月%d日 %H:%M')

        prompt = f"""あなたは優秀なFPです。現在の分析時刻は **{current_time_str} (日本時間)** です。
# ユーザーからの質問: {user_question}
---
# クライアントデータ
{asset_json}
---
# パフォーマンスデータ
{summary_text}
{chart_markdown}
---
# 関連ニュース
```json
{news_json}
```
---
# 分析と回答
上記情報を踏まえ、専門的観点から質問に回答してください。ポートフォリオの良い点、懸念点、改善案を根拠と共に具体的に記述してください。"""
        return prompt, None
    except Exception as e:
        logger.error(f"プロンプト生成中にエラー: {e}", exc_info=True)
        return None, f"プロンプトの生成中にエラー: {e}"

# --- メインページ描画関数 ---
def render_page(sm, fm, akm, active_model):
    st.markdown(ui_styles.portfolio_custom_css, unsafe_allow_html=True)
    st.markdown("<div class='main-title'>ポートフォリオ入力フォーム</div>", unsafe_allow_html=True)
    st.info("資産状況と株式状況を入力後、「パフォーマンス分析」ボタンを押すと、ポートフォリオの推移や関連ニュース、AIによる分析が確認できます。")

    def toggle_static_mode_callback():
        sm.set_value(KEY_STATIC_CHART_MODE, not sm.get_value(KEY_STATIC_CHART_MODE, False))

    if not sm.get_value(KEY_PAGE_INITIALIZED, False):
        sm.ensure_df_state(KEY_BALANCE_DF, default_data=app_config.INITIAL_PORTFOLIO_DATA["balance_df"])
        sm.ensure_df_state(KEY_STOCK_DF, default_data=app_config.INITIAL_PORTFOLIO_DATA["stock_df"])
        sm.set_value(KEY_PAGE_INITIALIZED, True)
        st.rerun()

    st.markdown("<div class='section-title'>資産状況</div>", unsafe_allow_html=True)
    edited_balance_df = st.data_editor(sm.get_value(KEY_BALANCE_DF), num_rows="dynamic", key="balance_editor_v3", use_container_width=True, height=150)
    if not edited_balance_df.equals(sm.get_value(KEY_BALANCE_DF)): sm.set_value(KEY_BALANCE_DF, edited_balance_df)

    st.markdown("<div class='section-title'>株式状況</div>", unsafe_allow_html=True)
    edited_stock_df = st.data_editor(sm.get_value(KEY_STOCK_DF), num_rows="dynamic", key="stock_editor_v3", use_container_width=True, height=150)
    if not edited_stock_df.equals(sm.get_value(KEY_STOCK_DF)): sm.set_value(KEY_STOCK_DF, edited_stock_df)

    st.markdown("---")
    st.header("ポートフォリオ分析")

    if st.button("ポートフォリオのパフォーマンスと関連ニュースを分析", type="primary", use_container_width=True):
        sm.update_values({KEY_ANALYSIS_BUTTON_CLICKED: True, KEY_ANALYSIS_DATA: None, KEY_ANALYSIS_ERROR: None, KEY_AI_RESULT: None, KEY_AI_ERROR: None, KEY_LAST_AI_PROMPT: None})
        st.rerun()

    if sm.get_value(KEY_ANALYSIS_BUTTON_CLICKED):
        analysis_data, errors = _fetch_and_process_data(sm.get_value(KEY_STOCK_DF), akm)
        if errors: sm.set_value(KEY_ANALYSIS_ERROR, errors)
        if analysis_data: sm.set_value(KEY_ANALYSIS_DATA, analysis_data)
        sm.set_value(KEY_ANALYSIS_BUTTON_CLICKED, False)
        st.rerun()

    analysis_errors = sm.get_value(KEY_ANALYSIS_ERROR)
    if analysis_errors:
        for error in analysis_errors: st.error(error)

    analysis_results = sm.get_value(KEY_ANALYSIS_DATA)
    if analysis_results:
        enriched_analysis_data = _calculate_portfolio_timeseries(analysis_results)
        if 'portfolio_value_timeseries' in enriched_analysis_data:
             sm.set_value(KEY_ANALYSIS_DATA, enriched_analysis_data)

        st.subheader("パフォーマンス分析")
        st.caption("左軸は各銘柄の株価パフォーマンス（1年前を100として指数化）、右軸は株式合計評価額（万円）の推移です。")

        st.checkbox("静的画像として表示（モバイル向け・HD解像度）", value=sm.get_value(KEY_STATIC_CHART_MODE, False), key="static_mode_checkbox", on_change=toggle_static_mode_callback, help="チェックを入れると、matplotlibで生成された1280x720の静的な画像として表示します。")

        is_static_mode = sm.get_value(KEY_STATIC_CHART_MODE, False)

        if is_static_mode:
            try:
                with st.spinner("matplotlibで静的画像(1280x720)を生成中です..."):
                    img_bytes = _create_matplotlib_chart_image(enriched_analysis_data)
                if img_bytes:
                    # ★警告修正: use_column_width を use_container_width に変更
                    st.image(img_bytes, caption="チャートの静的画像 (1280x720)", use_container_width=True)
                else:
                    st.error("matplotlibでの画像生成に失敗しました。")
            except Exception as e:
                st.error(f"画像生成中にエラーが発生しました: {e}")
                logger.error(f"Matplotlib画像生成エラー: {e}", exc_info=True)

        else:
            fig = _create_plotly_chart(enriched_analysis_data)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("グラフ描画用のデータがありません。")

        st.markdown("---")
        _display_news(enriched_analysis_data)
        st.markdown("---")

        st.subheader("ポートフォリオAI分析")
        default_q = "この一カ月で私の株式合計額は日経平均の動きに対してどうだったか？、また相場状況を含めて見直ししたほうがいい銘柄はあるか？ポートフォリオ全体を見てアドバイスして。"
        ai_question = st.text_area("AIへの質問:", value=sm.get_value(KEY_AI_QUESTION, default_q), height=100)
        sm.set_value(KEY_AI_QUESTION, ai_question)
        show_debug = st.checkbox("デバッグ: AIへのプロンプトを表示する")

        if st.button("AIによる分析を実行", key="run_portfolio_ai_analysis"):
            sm.update_values({KEY_AI_ANALYSIS_CLICKED: True, KEY_AI_RESULT: None, KEY_AI_ERROR: None, KEY_LAST_AI_PROMPT: None})
            st.rerun()

    if sm.get_value(KEY_AI_ANALYSIS_CLICKED):
        with st.spinner("AIがポートフォリオを分析中です..."):
            prompt, err = _create_prompt_for_fp_analysis(sm, sm.get_value(KEY_ANALYSIS_DATA), sm.get_value(KEY_AI_QUESTION))
            sm.set_value(KEY_LAST_AI_PROMPT, prompt)
            if err: sm.set_value(KEY_AI_ERROR, err)
            else:
                if not api_services.is_gemini_api_configured(): sm.set_value(KEY_AI_ERROR, "Gemini APIキーが設定されていません。")
                else:
                    try:
                        response = api_services.generate_gemini_response(prompt, active_model)
                        sm.set_value(KEY_AI_RESULT, response)
                    except Exception as e:
                        sm.set_value(KEY_AI_ERROR, f"AIの応答生成中にエラーが発生しました: {e}")
        sm.set_value(KEY_AI_ANALYSIS_CLICKED, False)
        st.rerun()

    ai_error = sm.get_value(KEY_AI_ERROR)
    if ai_error: st.error(ai_error)

    ai_result = sm.get_value(KEY_AI_RESULT)
    if ai_result:
        st.markdown("### AIからのアドバイス")
        st.markdown(ai_result)

    if 'show_debug' in locals() and show_debug:
        last_prompt = sm.get_value(KEY_LAST_AI_PROMPT)
        if last_prompt:
            with st.expander("AIに送信された最新のプロンプト（デバッグ用）", expanded=False): st.code(last_prompt, language='markdown')

    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("ステップ0: ダッシュボードへ戻る", key="s1_back_to_s0_v3", use_container_width=True):
            sm.set_value("app.current_step", 0)
            st.rerun()
    with col_next:
        if st.button("次へ進む (ステップ2: 取引履歴へ)", type="primary", key="s1_next_to_s2_v3", use_container_width=True):
            sm.set_value("app.current_step", 2)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
