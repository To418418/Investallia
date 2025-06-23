# technical_analysis_page.py
import streamlit as st
import datetime
import pandas as pd
import logging
import io
import matplotlib.pyplot as plt
import japanize_matplotlib

try:
    # 'stock_chart_app' からのインポートパスを修正
    from stock_chart_app import app as stock_chart_module
    from stock_chart_app import chart_analyzer
    logger = stock_chart_module.logger
    logger.info("technical_analysis_page.py: Successfully imported stock_chart_app components.")
except ImportError as e:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.error(f"technical_analysis_page.py: CRITICAL - Failed to import from stock_chart_app: {e}", exc_info=True)

def get_yfinance_ticker(stock_code: str, all_stocks_data: dict) -> str:
    """
    与えられたstock_codeをyfinanceが認識できる形式に変換します。
    """
    if stock_code is None:
        return None
    if '.' in stock_code:
        return stock_code

    if stock_code.isdigit() and len(stock_code) == 4:
        logger.debug(f"Applying '.T' suffix to Japanese stock code: {stock_code}")
        return f"{stock_code}.T"

    return stock_code

def render_page(sm, fm, akm, active_model_global):
    st.title("高度なテクニカル分析")
    logger.info("technical_analysis_page.py: render_page called.")

    if 'stock_chart_module' not in globals() or 'chart_analyzer' not in globals():
        st.error("テクニカル分析モジュールの読み込みに失敗しました。アプリケーション設定を確認してください。")
        logger.error("render_page: stock_chart_module or chart_analyzer not loaded. Aborting.")
        return

    # --- 元の仕様に基づいた銘柄選択ロジック ---
    selected_stock_code_global = sm.get_value("app.selected_stock_code")
    selected_stock_name_global = sm.get_value("app.selected_stock_name")
    all_stocks_data = sm.get_value("data_display.all_stocks_data_loaded", {})

    if not selected_stock_code_global:
        st.warning("まず、画面上部のヘッダーから分析したい銘柄を選択してください。")
        # 状態をリセット
        sm.set_value("tech_analysis.show_chart_button_clicked", False)
        sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
        sm.set_value("tech_analysis.current_chart_json", None)
        sm.set_value("tech_analysis.ai_analysis_result", None)
        return

    yfinance_ticker = get_yfinance_ticker(selected_stock_code_global, all_stocks_data)
    st.info(f"分析対象: {selected_stock_name_global} ({selected_stock_code_global} -> yfinance: {yfinance_ticker})")
    st.markdown("---")

    # --- 元の仕様に基づいた期間選択ロジックを復元 ---
    st.subheader("分析期間と足種")

    date_selection_mode_key = "tech_analysis.date_selection_mode"
    date_mode_options = ["プリセット", "カスタム"]
    current_date_mode = sm.get_value(date_selection_mode_key, "プリセット")
    if current_date_mode not in date_mode_options:
        current_date_mode = "プリセット"
        sm.set_value(date_selection_mode_key, current_date_mode)

    selected_date_mode = st.radio(
        "期間選択モード:",
        options=date_mode_options,
        index=date_mode_options.index(current_date_mode),
        key="tech_analysis_date_mode_radio_v5", # キーは元のファイルから引用
        horizontal=True,
    )
    if selected_date_mode != current_date_mode:
        sm.set_value(date_selection_mode_key, selected_date_mode)
        sm.set_value("tech_analysis.show_chart_button_clicked", False)
        sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
        st.rerun()

    cols_date_interval_display = st.columns([2, 1])
    today = datetime.date.today()

    if selected_date_mode == "カスタム":
        with cols_date_interval_display[0]:
            # カスタムの日付選択UI
            default_start_custom = sm.get_value("tech_analysis.start_date_custom", today - datetime.timedelta(days=365))
            default_end_custom = sm.get_value("tech_analysis.end_date_custom", today)
            start_date_input = st.date_input("開始日", value=default_start_custom, key="tech_analysis_start_date_custom_input_v4")
            end_date_input = st.date_input("終了日", value=default_end_custom, key="tech_analysis_end_date_custom_input_v4")
            sm.set_value("tech_analysis.start_date_custom", start_date_input)
            sm.set_value("tech_analysis.end_date_custom", end_date_input)
            # グローバルな期間設定も更新
            sm.set_value("tech_analysis.start_date", start_date_input)
            sm.set_value("tech_analysis.end_date", end_date_input)

        with cols_date_interval_display[1]:
            # カスタムの足種選択UI
            interval_options_custom = {"1d": "日足", "1wk": "週足", "1mo": "月足"}
            current_interval_val_custom = sm.get_value("tech_analysis.interval_custom", "1d")
            interval_selected_key_custom = st.selectbox(
                "足種", options=list(interval_options_custom.keys()),
                format_func=lambda k: interval_options_custom[k],
                index=list(interval_options_custom.keys()).index(current_interval_val_custom),
                key="tech_analysis_interval_select_custom_v4"
            )
            sm.set_value("tech_analysis.interval_custom", interval_selected_key_custom)
            sm.set_value("tech_analysis.interval", interval_selected_key_custom)

    elif selected_date_mode == "プリセット":
        # プリセットの期間選択UI
        preset_period_options = {
            "6ヶ月 (日足)": {"days": 180, "interval": "1d"},
            "1年 (日足)": {"days": 365, "interval": "1d"},
            "3年 (週足)": {"days": 3 * 365, "interval": "1wk"},
            "5年 (週足)": {"days": 5 * 365, "interval": "1wk"},
        }
        # UI表示部分
        with cols_date_interval_display[0]:
            st.markdown("###### プリセット期間を選択:")
            preset_cols = st.columns(len(preset_period_options))
            current_preset_label = sm.get_value("tech_analysis.preset_period_label", "6ヶ月 (日足)")

            newly_selected_preset_label = current_preset_label
            for i, (label, config_data) in enumerate(preset_period_options.items()):
                with preset_cols[i]:
                    if st.button(label, key=f"preset_btn_{i}", use_container_width=True, type="primary" if label == current_preset_label else "secondary"):
                        newly_selected_preset_label = label

            if newly_selected_preset_label != current_preset_label:
                sm.set_value("tech_analysis.preset_period_label", newly_selected_preset_label)
                sm.set_value("tech_analysis.show_chart_button_clicked", False)
                sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
                st.rerun()

        # プリセットに基づいて期間と足種を設定
        final_preset_config = preset_period_options[newly_selected_preset_label]
        end_date_preset = today
        start_date_preset = end_date_preset - datetime.timedelta(days=final_preset_config["days"])
        interval_preset = final_preset_config["interval"]

        sm.set_value("tech_analysis.start_date", start_date_preset)
        sm.set_value("tech_analysis.end_date", end_date_preset)
        sm.set_value("tech_analysis.interval", interval_preset)

    final_start_date = sm.get_value("tech_analysis.start_date")
    final_end_date = sm.get_value("tech_analysis.end_date")
    final_interval = sm.get_value("tech_analysis.interval")

    # --- テクニカル指標選択（折りたたみなし） ---
    st.subheader("テクニカル指標")
    try:
        indicators_config = stock_chart_module.INDICATORS_CONFIG
    except AttributeError:
        st.error("指標設定の読み込みに失敗しました。")
        return

    # カテゴリと順番の定義
    indicator_order = {
        "トレンド系指標": ['sma', 'ema', 'bollinger', 'ichimoku', 'psar', 'ma_envelope', 'donchian', 'keltner', 'vwap', 'pivot'],
        "オシレーター系指標": ['macd', 'rsi', 'stochastics', 'rci', 'dmi_adx', 'williams_r', 'aroon', 'ma_dev_rate', 'psy_line', 'coppock', 'force_index', 'mass_index'],
        "出来高系指標": ['volume', 'volume_sma', 'obv', 'mfi', 'cmf', 'eom'],
        "その他（ボラティリティ等）": ['std_dev', 'atr']
    }

    selected_indicator_keys_from_checkboxes = []

    for category, keys in indicator_order.items():
        st.markdown(f"**{category}**")
        cols = st.columns(4)
        col_idx = 0
        for key in keys:
            if key in indicators_config:
                is_checked = cols[col_idx % 4].checkbox(
                    indicators_config[key]['label'],
                    value=(key in sm.get_value("tech_analysis.selected_indicator_keys", ['sma', 'volume'])),
                    key=f"indicator_cb_{key}_v6"
                )
                if is_checked:
                    selected_indicator_keys_from_checkboxes.append(key)
                col_idx += 1
        st.markdown("<hr style='margin-top:0.5rem; margin-bottom:0.5rem;'>", unsafe_allow_html=True)

    # 選択状態が変わったらチャートを非表示にする
    if set(sm.get_value("tech_analysis.selected_indicator_keys", [])) != set(selected_indicator_keys_from_checkboxes):
        sm.set_value("tech_analysis.selected_indicator_keys", selected_indicator_keys_from_checkboxes)
        sm.set_value("tech_analysis.show_chart_button_clicked", False)
        sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)

    # --- パラメータ設定機能は削除 ---
    indicator_params_values = {}
    sm.set_value("tech_analysis.indicator_params_values", indicator_params_values)

    # --- 静的画像モードの追加 ---
    st.markdown("---")
    st.subheader("チャート表示設定")

    def toggle_static_mode_callback_tech():
        sm.set_value("tech_analysis.static_chart_mode", not sm.get_value("tech_analysis.static_chart_mode", False))

    is_static_mode = st.checkbox(
        "静的画像として表示（モバイル向け・HD解像度）",
        value=sm.get_value("tech_analysis.static_chart_mode", False),
        key="tech_analysis_static_mode_checkbox_v1",
        on_change=toggle_static_mode_callback_tech,
        help="チェックを入れると、matplotlibで生成された静的な画像として表示します。AI分析用の元データは保持されます。"
    )

    # --- チャート表示とAI分析（元のボタンロジック） ---
    if st.button("テクニカルチャート表示", type="primary", key="tech_analysis_display_chart_button_v3", use_container_width=True):
        if final_start_date >= final_end_date:
            st.error("エラー: 開始日は終了日より前に設定してください。")
            sm.set_value("tech_analysis.show_chart_button_clicked", False)
            sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
        else:
            sm.set_value("tech_analysis.show_chart_button_clicked", True)
            sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
            sm.set_value("tech_analysis.current_chart_json", None)
            sm.set_value("tech_analysis.ai_analysis_result", None)
            logger.info("Display chart button clicked. Parameters saved.")
            st.rerun()

    if sm.get_value("tech_analysis.show_chart_button_clicked", False):
        logger.info("Attempting to display chart.")
        # yfinanceのendは指定日を含まないので、翌日を渡す
        end_date_for_yfinance = final_end_date + datetime.timedelta(days=1)

        stock_chart_module.render_technical_analysis_content(
            sm_main_app=sm,
            ticker_symbol=yfinance_ticker,
            start_date=final_start_date,
            end_date=end_date_for_yfinance, # 修正
            interval=final_interval,
            selected_indicator_keys=selected_indicator_keys_from_checkboxes,
            indicator_params_values=indicator_params_values, # 常に空
            gemini_api_key=akm.get_api_key("GEMINI_API_KEY"),
            pro_model_password=akm.get_api_key("PRO_MODEL_UNLOCK_PASSWORD"),
            active_gemini_model_name=active_model_global,
            use_static_image=is_static_mode  # ★新しい引数を追加
        )

        current_chart_json = sm.get_value("tech_analysis.current_chart_json")
        if current_chart_json:
            st.markdown("---")
            st.subheader("AIによるチャート分析")
            if not akm.get_api_key("GEMINI_API_KEY"):
                st.warning("AI分析を実行するには、Gemini APIキーが必要です。")
            else:
                if st.button("このチャートのテクニカルデータをAIで分析する", type="primary", key="tech_analysis_run_ai_button_single_v1", use_container_width=True):
                    sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", True)
                    sm.set_value("tech_analysis.ai_analysis_result", None)
                    st.rerun()

    if sm.get_value("tech_analysis.trigger_ai_analysis_button_clicked", False):
        logger.info(f"Executing AI analysis. Model: {active_model_global}")
        with st.spinner(f"AI ({active_model_global.split('/')[-1]}) が分析中です..."):
            try:
                analysis_result_text = chart_analyzer.analyze_chart_with_llm(
                    technical_data_json=sm.get_value("tech_analysis.current_chart_json"),
                    indicator_labels=sm.get_value("tech_analysis.indicator_labels_for_ai", {}),
                    api_key=akm.get_api_key("GEMINI_API_KEY"),
                    model_name=active_model_global
                )
                sm.set_value("tech_analysis.ai_analysis_result", analysis_result_text)
            except Exception as e_analyze:
                logger.error(f"Error during AI analysis call: {e_analyze}", exc_info=True)
                sm.set_value("tech_analysis.ai_analysis_result", f"[ERROR] AI分析中にエラーが発生しました: {e_analyze}")
        sm.set_value("tech_analysis.trigger_ai_analysis_button_clicked", False)
        st.rerun()

    final_ai_result_to_display = sm.get_value("tech_analysis.ai_analysis_result")
    if final_ai_result_to_display:
        st.markdown("#### AIによる分析結果:")
        if isinstance(final_ai_result_to_display, str):
            if final_ai_result_to_display.startswith("[ERROR]"):
                st.error(final_ai_result_to_display)
            else:
                st.markdown(final_ai_result_to_display, unsafe_allow_html=True)
        else:
            st.error(f"AI分析結果の形式が不正です: {type(final_ai_result_to_display)}")

    logger.info("technical_analysis_page.py: render_page finished.")

    st.markdown("---")
    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back_nav, col_next_nav = st.columns(2)
    with col_back_nav:
        if st.button("戻る (ステップ7: 抽出データ表示へ)", key="s8_back_to_s7", use_container_width=True):
            sm.set_value("app.current_step", 7)
            st.rerun()
    with col_next_nav:
        if st.button("次へ (ステップ9: EDINET報告書ビューアへ)", type="primary", key="s8_next_to_s9", use_container_width=True):
            sm.set_value("app.current_step", 9)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
