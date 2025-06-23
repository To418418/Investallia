# trade_history_page.py
import streamlit as st
import pandas as pd
import logging
from io import BytesIO # For uploaded file
import os
import time # AI処理時間計測用

# import ui_styles # ui_styles のインポートと使用を安全に行う
import config as app_config
import api_services # AI分析のため追加

logger = logging.getLogger(__name__)

# --- ui_styles の安全なインポートと属性アクセス ---
trade_history_page_custom_style = "<style></style>" # デフォルトの空スタイル
try:
    import ui_styles
    if hasattr(ui_styles, 'trade_history_page_style'):
        trade_history_page_custom_style = ui_styles.trade_history_page_style
    else:
        logger.warning("ui_styles module found, but 'trade_history_page_style' attribute is missing. Using default empty style for trade history page.")
except ImportError:
    logger.warning("ui_styles module could not be imported. Using default empty style for trade history page.")
except Exception as e_ui:
    logger.error(f"An unexpected error occurred while trying to load trade_history_page_style from ui_styles: {e_ui}. Using default empty style.")


# --- StateManagerで使用するキー (このモジュール固有のもの) ---
KEY_RAW_DF = "trade_history.raw_df"
KEY_IS_SHOWING_ALL = "trade_history.is_showing_all"
KEY_CURRENT_PAGE = "trade_history.current_page"
KEY_CURRENT_FILE_NAME = "trade_history.current_file_name"
KEY_SUCCESSFUL_ENCODING = "trade_history.successful_encoding"
KEY_MESSAGE_TEXT = "trade_history.message_text"
KEY_MESSAGE_TYPE = "trade_history.message_type"
KEY_LAST_UPLOADED_FILE_ID = "trade_history.last_uploaded_file_id"
KEY_INITIALIZED = "trade_history.initialized"

# AI分析関連のキー
KEY_AI_ANALYSIS_TRIGGERED_TRADE = "trade_history.ai_analysis_triggered"
KEY_AI_ANALYSIS_ACTIVE_TRADE = "trade_history.ai_analysis_active"
KEY_AI_ANALYSIS_RESULT_TRADE = "trade_history.ai_analysis_result"
KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE = "trade_history.ai_analysis_status_messages"
KEY_AI_PROCESSING_TIME_MESSAGE_TRADE = "trade_history.ai_processing_time_message"
KEY_PAGE_LEVEL_ERROR_TRADE = "trade_history.page_level_error" # AI分析時のエラー用

# --- ヘルパー関数 (取引履歴ページ専用) ---
def generate_initial_sample_trade_data_df() -> pd.DataFrame:
    """初期表示用のサンプル取引履歴データを生成する"""
    num_rows = 200
    sample_headers = ['ID', '約定日', '銘柄', '数量', '単価', '売買']
    data = []
    for i in range(num_rows):
        id_val = i + 1
        day = (i % 28) + 1
        month = (i // 28 % 12) + 1
        year = 2023 + (i // (28 * 12))
        trade_date = f"{year}-{month:02d}-{day:02d}"
        name = f'銘柄{ (i % 30) + 1 }-{chr(65 + (i%26)) }'
        quantity = (i % 15 + 1) * 100
        price = round(100 + (i * 1.7 % 300) + (i % 7 / 10), 2)
        action = "買" if i % 2 == 0 else "売"
        data.append([id_val, trade_date, name, quantity, price, action])
    return pd.DataFrame(data, columns=sample_headers)

def load_default_trade_data(sm, fm):
    """
    デフォルトの取引履歴CSVデータをFileManagerを使って読み込む。
    この関数はエラーメッセージをState Managerに設定する役割も持つ。
    """
    df, encoding, error_msg = fm.load_csv('default_trade_history')

    if error_msg:
        full_error_msg = f"デフォルト取引履歴の読み込みエラー: {error_msg}"
        sm.set_value(KEY_MESSAGE_TEXT, full_error_msg)
        sm.set_value(KEY_MESSAGE_TYPE, "error")
        logger.error(full_error_msg)
        return pd.DataFrame(), None

    if df is not None and encoding:
        success_msg = f"デフォルト取引履歴をエンコーディング [{encoding}] でロードしました。({len(df)}行)"
        sm.set_value(KEY_MESSAGE_TEXT, success_msg)
        sm.set_value(KEY_MESSAGE_TYPE, "success" if not df.empty else "warning")
        logger.info(success_msg)
        return df, encoding

    unknown_error_msg = "デフォルト取引履歴の読み込みに失敗しました (不明なエラー)。"
    sm.set_value(KEY_MESSAGE_TEXT, unknown_error_msg)
    sm.set_value(KEY_MESSAGE_TYPE, "error")
    logger.error(unknown_error_msg)
    return pd.DataFrame(), None


def render_page(sm, fm, akm, active_model):
    st.markdown(trade_history_page_custom_style, unsafe_allow_html=True)
    st.markdown('<h1 class="app-title-trade">インタラクティブCSVビューア & AI分析 (取引履歴)</h1>', unsafe_allow_html=True)
    st.markdown('<p class="app-subtitle-trade">取引履歴のCSVファイルを選択・アップロードすると表示され、AIによる分析も可能です。</p>', unsafe_allow_html=True)

    message_placeholder = st.empty()
    current_msg_text = sm.get_value(KEY_MESSAGE_TEXT)
    current_msg_type = sm.get_value(KEY_MESSAGE_TYPE, "info")
    if current_msg_text:
        if current_msg_type == "success": message_placeholder.success(current_msg_text)
        elif current_msg_type == "error": message_placeholder.error(current_msg_text)
        elif current_msg_type == "warning": message_placeholder.warning(current_msg_text)
        else: message_placeholder.info(current_msg_text)

    st.markdown('<div class="trade-history-content-wrapper">', unsafe_allow_html=True)
    col_controls1, col_controls2 = st.columns([0.6, 0.4])
    with col_controls1:
        uploaded_file = st.file_uploader(
            "CSVファイルを選択 (.csv, .txt)",
            type=['csv', 'txt'],
            key="trade_csv_file_uploader_main_v2_fixed_0603", # キーを微修正
            help="UTF-8, Shift_JIS, EUC-JPなどの一般的なエンコーディングに対応しています。"
        )
    with col_controls2:
        st.write("")
        st.write("")
        default_csv_meta = app_config.FILE_METADATA.get('default_trade_history', {})
        default_csv_display_name = os.path.basename(default_csv_meta.get('path_colab', 'default_trade.csv')) if not app_config.IS_CLOUD_RUN else os.path.basename(default_csv_meta.get('path_gcs_blob', 'default_trade.csv'))

        if st.button(f"デモ取引履歴 ({default_csv_display_name}) で試す", key="load_default_trade_csv_main_v2_fixed_0603"): # キーを微修正
            sm.set_value(KEY_MESSAGE_TEXT, "")
            sm.set_value(KEY_MESSAGE_TYPE, "info")
            message_placeholder.empty()

            with st.spinner(f"{default_csv_display_name} をロード中..."):
                df_from_file, encoding_from_file = load_default_trade_data(sm, fm)

                if df_from_file is not None and not df_from_file.empty:
                    logger.info(f"Loaded default trade history from file: {default_csv_display_name}")
                    sm.set_value(KEY_RAW_DF, df_from_file)
                    sm.set_value(KEY_CURRENT_FILE_NAME, default_csv_display_name)
                    sm.set_value(KEY_SUCCESSFUL_ENCODING, encoding_from_file or "不明(ファイル成功時)")
                else:
                    original_error_msg = sm.get_value(KEY_MESSAGE_TEXT, "デフォルトファイルの読み込みに失敗しました。")
                    logger.warning(f"Failed to load '{default_csv_display_name}' or it was empty. Falling back to generated sample data. Original error: {original_error_msg}")

                    sample_df = generate_initial_sample_trade_data_df()
                    sm.set_value(KEY_RAW_DF, sample_df)
                    sm.set_value(KEY_CURRENT_FILE_NAME, "生成サンプルデータ (取引履歴風)")
                    sm.set_value(KEY_SUCCESSFUL_ENCODING, "UTF-8 (生成サンプル)")

                    fallback_msg = f"警告: '{default_csv_display_name}' の読み込みに失敗したため、代わりにプログラム生成のサンプルデータを表示します。(元エラー: {original_error_msg})"
                    sm.set_value(KEY_MESSAGE_TEXT, fallback_msg)
                    sm.set_value(KEY_MESSAGE_TYPE, "warning")

                sm.set_value(KEY_IS_SHOWING_ALL, False)
                sm.set_value(KEY_CURRENT_PAGE, 1)
                sm.set_value(KEY_AI_ANALYSIS_RESULT_TRADE, None)
                sm.set_value(KEY_AI_ANALYSIS_ACTIVE_TRADE, False)
                sm.set_value(KEY_AI_ANALYSIS_TRIGGERED_TRADE, False)
                sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE, None)
                sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, None)
            st.rerun()

    if uploaded_file is not None:
        current_file_id_tuple = (uploaded_file.name, uploaded_file.size, uploaded_file.type)
        if current_file_id_tuple != sm.get_value(KEY_LAST_UPLOADED_FILE_ID):
            sm.set_value(KEY_LAST_UPLOADED_FILE_ID, current_file_id_tuple)
            sm.set_value(KEY_MESSAGE_TEXT, "")
            message_placeholder.empty()

            with st.spinner(f"ファイル「{uploaded_file.name}」を処理中..."):
                file_bytes = uploaded_file.getvalue()
                df, encoding = fm._try_parse_csv_with_encodings(
                    file_bytes,
                    app_config.FILE_METADATA.get('default_trade_history', {}).get('encoding_options', ['utf-8', 'cp932']),
                    uploaded_file.name
                )

                if df is not None:
                    sm.set_value(KEY_RAW_DF, df)
                    sm.set_value(KEY_CURRENT_FILE_NAME, uploaded_file.name)
                    sm.set_value(KEY_SUCCESSFUL_ENCODING, encoding or "不明")
                    sm.set_value(KEY_IS_SHOWING_ALL, False)
                    sm.set_value(KEY_CURRENT_PAGE, 1)
                    sm.set_value(KEY_AI_ANALYSIS_RESULT_TRADE, None)
                    sm.set_value(KEY_AI_ANALYSIS_ACTIVE_TRADE, False)
                    sm.set_value(KEY_AI_ANALYSIS_TRIGGERED_TRADE, False)
                    sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE, None)
                    sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, None)

                    if not df.empty:
                        sm.set_value(KEY_MESSAGE_TEXT, f"✓ {uploaded_file.name} をエンコーディング [{encoding}] でロードしました。({len(df)}行)")
                        sm.set_value(KEY_MESSAGE_TYPE, "success")
                    else:
                        sm.set_value(KEY_MESSAGE_TEXT, f"⚠️ {uploaded_file.name} (エンコーディング: {encoding}) は読み込めましたが、データ行がありません。")
                        sm.set_value(KEY_MESSAGE_TYPE, "warning")
                else:
                    sm.set_value(KEY_RAW_DF, None)
                    sm.set_value(KEY_MESSAGE_TEXT, f"ファイル「{uploaded_file.name}」のエンコーディング特定・パースに失敗しました。詳細はログを確認してください。")
                    sm.set_value(KEY_MESSAGE_TYPE, "error")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    df_display = sm.get_value(KEY_RAW_DF) # ロードされた全データ
    if df_display is not None:
        st.markdown("---")
        col_header1, col_header2 = st.columns([0.7, 0.3])
        with col_header1:
            encoding_info = f" (エンコーディング: {sm.get_value(KEY_SUCCESSFUL_ENCODING, 'N/A')})"
            st.markdown(f'<h2 class="section-title-trade" style="margin-bottom: 0;">表示中のファイル: {sm.get_value(KEY_CURRENT_FILE_NAME, "N/A")}{encoding_info}</h2>', unsafe_allow_html=True)

        total_data_rows = len(df_display)
        with col_header2:
            if total_data_rows > app_config.INITIAL_ROWS_TO_SHOW_TRADE_HISTORY :
                toggle_button_text = "一部表示に戻す" if sm.get_value(KEY_IS_SHOWING_ALL) else f"全 {total_data_rows} 行表示"
                if st.button(toggle_button_text, key="toggle_view_trade_history_main_v2_fixed_0603"):
                    sm.set_value(KEY_IS_SHOWING_ALL, not sm.get_value(KEY_IS_SHOWING_ALL, False))
                    sm.set_value(KEY_CURRENT_PAGE, 1)
                    sm.set_value(KEY_MESSAGE_TEXT, "")
                    message_placeholder.empty()
                    st.rerun()
            elif total_data_rows > 0:
                st.caption(f"全 {total_data_rows} 行表示中")

        df_to_show_final = pd.DataFrame()
        if total_data_rows > 0:
            if sm.get_value(KEY_IS_SHOWING_ALL):
                start_idx = (sm.get_value(KEY_CURRENT_PAGE, 1) - 1) * app_config.ROWS_PER_PAGE_TRADE_HISTORY
                end_idx = start_idx + app_config.ROWS_PER_PAGE_TRADE_HISTORY
                df_to_show_final = df_display.iloc[start_idx:end_idx]
            else:
                df_to_show_final = df_display.head(app_config.INITIAL_ROWS_TO_SHOW_TRADE_HISTORY)

            num_rows_to_display = len(df_to_show_final)
            estimated_height = min(max(150, num_rows_to_display * 35 + 38), 600 if sm.get_value(KEY_IS_SHOWING_ALL) else 400)
            st.dataframe(df_to_show_final, use_container_width=True, height=estimated_height)
        elif total_data_rows == 0 and len(df_display.columns) > 0:
            st.dataframe(df_display.head(0), use_container_width=True)
            st.info("ファイルにデータ行がありません。ヘッダーのみ表示しています。")
            df_to_show_final = df_display.head(0)

        if sm.get_value(KEY_IS_SHOWING_ALL) and total_data_rows > app_config.ROWS_PER_PAGE_TRADE_HISTORY:
            total_pages = (total_data_rows + app_config.ROWS_PER_PAGE_TRADE_HISTORY - 1) // app_config.ROWS_PER_PAGE_TRADE_HISTORY
            current_page_for_nav = sm.get_value(KEY_CURRENT_PAGE, 1)
            st.markdown('<div class="pagination-controls">', unsafe_allow_html=True)
            nav_cols = st.columns((1, 1, 2, 1, 1))
            with nav_cols[0]:
                if st.button("最初へ", key="page_first_trade_main_v2_fixed_0603", disabled=(current_page_for_nav == 1), use_container_width=True):
                    sm.set_value(KEY_CURRENT_PAGE, 1); st.rerun()
            with nav_cols[1]:
                if st.button("前へ", key="page_prev_trade_main_v2_fixed_0603", disabled=(current_page_for_nav == 1), use_container_width=True):
                    sm.set_value(KEY_CURRENT_PAGE, current_page_for_nav - 1); st.rerun()
            with nav_cols[2]:
                st.markdown(f"<div style='text-align: center; padding-top: 0.5rem;'>ページ: {current_page_for_nav} / {total_pages}</div>", unsafe_allow_html=True)
            with nav_cols[3]:
                if st.button("次へ", key="page_next_trade_main_v2_fixed_0603", disabled=(current_page_for_nav == total_pages), use_container_width=True):
                    sm.set_value(KEY_CURRENT_PAGE, current_page_for_nav + 1); st.rerun()
            with nav_cols[4]:
                if st.button("最後へ", key="page_last_trade_main_v2_fixed_0603", disabled=(current_page_for_nav == total_pages), use_container_width=True):
                    sm.set_value(KEY_CURRENT_PAGE, total_pages); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if total_data_rows > 0 : # AI分析ボタンはデータがある場合のみ表示
            st.markdown("---")
            st.subheader("🤖 取引履歴AI分析")
            ai_status_placeholder_trade = st.empty()
            ai_error_placeholder_trade = st.empty()

            if sm.get_value(KEY_PAGE_LEVEL_ERROR_TRADE):
                 ai_error_placeholder_trade.error(sm.get_value(KEY_PAGE_LEVEL_ERROR_TRADE), icon="🚨")

            if sm.get_value(KEY_AI_ANALYSIS_ACTIVE_TRADE):
                status_msgs_trade = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, [])
                if status_msgs_trade:
                    current_status_text_trade = "AI分析 処理状況:\n" + "\n".join(status_msgs_trade)
                    is_error_trade = any("エラー" in msg.lower() or "失敗" in msg.lower() for msg in status_msgs_trade)
                    is_completed_trade = "分析完了" in (status_msgs_trade[-1] if status_msgs_trade else "")

                    if is_error_trade: ai_status_placeholder_trade.error(current_status_text_trade, icon="🚨")
                    elif is_completed_trade: ai_status_placeholder_trade.success(current_status_text_trade, icon="✅")
                    else: ai_status_placeholder_trade.info(current_status_text_trade, icon="⏳")

            if st.button("取引履歴全体をAIで分析する", key="run_trade_history_ai_analysis_v2_fixed_0603", type="primary"):
                if not api_services.is_gemini_api_configured():
                    sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, "AI分析を実行できません。Gemini APIキーが設定されていません。")
                    st.rerun()
                elif df_display.empty: # df_display (全データ) が空なら分析しない
                    sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, "AI分析を実行できません。分析対象の取引データがありません。")
                    st.rerun()
                else:
                    sm.set_value(KEY_AI_ANALYSIS_TRIGGERED_TRADE, True)
                    sm.set_value(KEY_AI_ANALYSIS_ACTIVE_TRADE, True)
                    sm.set_value(KEY_AI_ANALYSIS_RESULT_TRADE, None)
                    sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE, None)
                    sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, None)
                    sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, ["取引履歴AI分析プロセスを開始します..."])
                    ai_status_placeholder_trade.info("AI分析 処理状況:\n取引履歴AI分析プロセスを開始します...", icon="⏳")
                    st.rerun()

            if sm.get_value(KEY_AI_ANALYSIS_TRIGGERED_TRADE) and df_display is not None and not df_display.empty:
                with st.spinner("取引履歴をAIで分析中です..."):
                    try:
                        current_status_list_trade = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, [])

                        # --- 修正箇所: AIに渡すデータを全データ (df_display) に変更 ---
                        # 注意: df_displayが非常に大きい場合、トークン制限に影響する可能性があります。
                        data_to_analyze_md = df_display.to_markdown(index=False)
                        current_status_list_trade.append(f"分析対象データ (全 {len(df_display)}行) を準備しました。")
                        # --- 修正箇所ここまで ---
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, current_status_list_trade[:])
                        ai_status_placeholder_trade.info("AI分析 処理状況:\n" + "\n".join(current_status_list_trade), icon="⏳")

                        prompt = f"""あなたは経験豊富な金融アナリストです。
以下の株式取引履歴データを分析し、投資家の取引傾向、強み、弱み、改善点、その他注目すべきパターンについて、具体的かつ建設的なフィードバックを提供してください。
結果はMarkdown形式で、箇条書きや小見出しを効果的に使用し、初心者にも分かりやすく記述してください。

## 分析対象の取引履歴データ
{data_to_analyze_md}

## 分析のポイント
- 取引頻度や期間について
- 利益が出ている取引、損失が出ている取引の共通点
- 特定の銘柄やセクターへの集中度
- リスク管理の観点からの評価 (損切り、利益確定のタイミングなど)
- ポートフォリオ全体への影響 (もし推測できれば)
- 今後の取引戦略への具体的なアドバイス

上記以外にも、あなたが専門家として気づいた点があれば自由に指摘してください。
"""
                        current_status_list_trade.append(f"プロンプト生成完了。LLM ({active_model}) にリクエスト中...")
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, current_status_list_trade[:])
                        ai_status_placeholder_trade.info("AI分析 処理状況:\n" + "\n".join(current_status_list_trade), icon="⏳")

                        start_time = time.time()
                        analysis_result = api_services.generate_gemini_response(prompt, active_model)
                        processing_time = time.time() - start_time
                        minutes_ai, seconds_ai = divmod(int(processing_time), 60)
                        time_msg_trade = f"取引履歴のAI分析が完了しました。処理時間: {minutes_ai}分{seconds_ai}秒"

                        if analysis_result.startswith("[LLM エラー]"):
                            raise ValueError(analysis_result)

                        sm.set_value(KEY_AI_ANALYSIS_RESULT_TRADE, analysis_result)
                        sm.set_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE, time_msg_trade)
                        current_status_list_trade.append("分析完了。")
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, current_status_list_trade[:])

                    except Exception as e:
                        logger.error(f"取引履歴AI分析中にエラー: {e}", exc_info=True)
                        error_msg_for_ui_trade = f"取引履歴AI分析中にエラーが発生しました: {e}"
                        sm.set_value(KEY_PAGE_LEVEL_ERROR_TRADE, error_msg_for_ui_trade)
                        sm.set_value(KEY_AI_ANALYSIS_RESULT_TRADE, f"[AI分析エラー]\n{error_msg_for_ui_trade}")
                        current_status_list_trade = sm.get_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, [])
                        current_status_list_trade.append(f"エラー発生: {e}")
                        sm.set_value(KEY_AI_ANALYSIS_STATUS_MESSAGES_TRADE, current_status_list_trade[:])
                    finally:
                        sm.set_value(KEY_AI_ANALYSIS_TRIGGERED_TRADE, False)
                        sm.set_value(KEY_AI_ANALYSIS_ACTIVE_TRADE, False)
                        st.rerun()

            if sm.get_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE):
                st.success(sm.get_value(KEY_AI_PROCESSING_TIME_MESSAGE_TRADE), icon="✅")

            ai_analysis_result_text = sm.get_value(KEY_AI_ANALYSIS_RESULT_TRADE)
            if ai_analysis_result_text:
                st.markdown("---")
                st.subheader("AIによる分析結果")
                if ai_analysis_result_text.startswith("[AI分析エラー]"):
                    st.error(ai_analysis_result_text, icon="🚨")
                else:
                    st.markdown(ai_analysis_result_text)
        elif total_data_rows == 0 and df_display is not None:
             pass

    if not sm.get_value(KEY_INITIALIZED, False) and sm.get_value(KEY_RAW_DF) is None:
        sm.set_value(KEY_MESSAGE_TEXT, "")
        message_placeholder.empty()
        with st.spinner("初期サンプルデータをロード中..."):
            sample_df = generate_initial_sample_trade_data_df()
            if not sample_df.empty:
                sm.set_value(KEY_RAW_DF, sample_df)
                sm.set_value(KEY_CURRENT_FILE_NAME, "初期サンプルデータ (取引履歴風)")
                sm.set_value(KEY_SUCCESSFUL_ENCODING, "UTF-8 (サンプル)")
                sm.set_value(KEY_IS_SHOWING_ALL, False)
                sm.set_value(KEY_CURRENT_PAGE, 1)
                sm.set_value(KEY_MESSAGE_TEXT, "初期サンプルデータをロードしました。ご自身のCSVファイルもアップロードできます。")
                sm.set_value(KEY_MESSAGE_TYPE, "info")
            else:
                sm.set_value(KEY_MESSAGE_TEXT, "初期サンプルデータのロードに失敗しました。")
                sm.set_value(KEY_MESSAGE_TYPE, "error")
        sm.set_value(KEY_INITIALIZED, True)
        st.rerun()

    st.markdown("---")
    st.caption("インタラクティブCSVビューア & AI分析 (Streamlit版)")

    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back_trade, col_next_trade = st.columns(2)
    with col_back_trade:
        if st.button("戻る (ステップ1: ポートフォリオ入力へ)", key="s2_back_to_s1_trade_main_v2_fixed_0603", use_container_width=True):
            sm.set_value("app.current_step", 1); st.rerun()
    with col_next_trade:
        if st.button("次へ進む (ステップ3: 銘柄分析へ)", type="primary", key="s2_next_to_s3_trade_main_v2_fixed_0603", use_container_width=True):
            sm.set_value("app.current_step", 3); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

