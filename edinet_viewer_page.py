# edinet_viewer_page.py
import streamlit as st
import pandas as pd
import zipfile
import os
from io import BytesIO
import numpy as np
import json
import logging
import time
import re # For code validation

import config as app_config
import api_services # LLM分析のため

# GCSライブラリをインポート
if app_config.IS_CLOUD_RUN:
    try:
        from google.cloud import storage
    except ImportError:
        storage = None
        logging.getLogger(__name__).critical("GCS環境でgoogle-cloud-storageライブラリのインポートに失敗しました。")
else:
    storage = None

logger = logging.getLogger(__name__)

# --- StateManagerで使用するキー (このモジュール固有のもの) ---
KEY_EV_SELECTED_CODE = "edinet_viewer.selected_code"
KEY_EV_SELECTED_DOC_ID = "edinet_viewer.selected_doc_id"
KEY_EV_DOC_DESCRIPTION_OPTIONS = "edinet_viewer.doc_description_options"
KEY_EV_LOADED_DATA = "edinet_viewer.loaded_data"
KEY_EV_DISPLAY_ROWS_CONFIG = "edinet_viewer.display_rows_config"
KEY_EV_SELECTED_DFS_TO_SHOW = "edinet_viewer.selected_dfs_to_show"
KEY_EV_AI_ANALYSIS_RESULT = "edinet_viewer.ai_analysis_result"
KEY_EV_AI_ANALYSIS_ACTIVE = "edinet_viewer.ai_analysis_active" # ★修正: LLM分析処理中の状態を示すフラグ
KEY_EV_AI_PROCESSING_TIME = "edinet_viewer.ai_processing_time"
KEY_EV_PAGE_MESSAGE = "edinet_viewer.page_message"
KEY_LAST_AI_PROMPT = "edinet_viewer.last_ai_prompt" # ★追加: デバッグ用に最後に生成したプロンプトを保存

# --- データ処理関数のためのグローバル設定 ---
pivot_column_order_global = ['四期前', '三期前', '前々期', '前期', '当期']
replace_dict_context_part1_global = {
    'FilingDateInstant': '当期',
    'Prior4YearDuration': '四期前',
    'Prior3YearDuration': '三期前',
    'Prior2YearDuration': '前々期',
    'Prior1YearDuration': '前期',
    'CurrentYearDuration': '当期',
    'Prior4YearInstant': '四期前',
    'Prior3YearInstant': '三期前',
    'Prior2YearInstant': '前々期',
    'Prior1YearInstant': '前期',
    'CurrentYearInstant': '当期',
}

# --- 単位調整と数値処理関数 (この関数自体は変更なし) ---
def scale_value_and_get_unit(value_base_unit, unit_base):
    if pd.isna(value_base_unit):
        return pd.NA, (unit_base if pd.notna(unit_base) else "")
    try:
        val_num = float(value_base_unit)
    except (ValueError, TypeError):
        return value_base_unit, unit_base

    can_scale_monetary = (unit_base == '円') or (pd.isna(unit_base)) or (unit_base == "")

    if not can_scale_monetary:
        rounded_value = round(val_num, 2)
        if rounded_value == int(rounded_value): return int(rounded_value), unit_base
        return rounded_value, unit_base

    scaled_cho = val_num / 1_000_000_000_000
    if abs(scaled_cho) >= 0.01:
        if abs(int(scaled_cho)) >= 1 and abs(int(scaled_cho)) < 10000:
            return round(scaled_cho, 2), "兆"
    scaled_oku = val_num / 100_000_000
    if abs(scaled_oku) >= 0.01:
        if abs(int(scaled_oku)) >= 1 and abs(int(scaled_oku)) < 10000:
            return round(scaled_oku, 2), "億"
    scaled_man = val_num / 10_000
    if abs(scaled_man) >= 0.1:
        if abs(int(scaled_man)) >= 1 and abs(int(scaled_man)) < 10000:
            return round(scaled_man, 2), "万"

    final_val = round(val_num, 0)
    if final_val == int(final_val): final_val = int(final_val)
    return final_val, unit_base if pd.notna(unit_base) else ""

# --- メイン処理関数 (この関数自体は変更なし) ---
def process_edinet_document(doc_id_main, save_dir_main):
    df_main_indicators_pivot_res = None
    df_pl_consolidated_pivot_res = None
    df_pl_non_consolidated_pivot_res = None
    df_bs_consolidated_pivot_res = None
    df_bs_non_consolidated_pivot_res = None
    df_other_final_res = None

    zip_filename = f"{doc_id_main}.zip"
    zip_file_bytes = None

    # グローバル設定を関数内で使用
    current_pivot_column_order = pivot_column_order_global
    current_replace_dict_context_part1 = replace_dict_context_part1_global

    def process_dataframe_and_create_pivot_inner(df_input, df_name_for_log=""):
        if df_input.empty:
            logger.warning(f"警告 ({df_name_for_log}): 入力DataFrameが空のため処理をスキップします。")
            return None

        df = df_input.copy()

        if '単位' in df.columns and '値' in df.columns:
            df.loc[:, '値_ベースユニット'] = df['値'].copy()
            df.loc[:, '単位_ベース'] = df['単位'].astype(str).fillna("")
            scale_factors = {'千円': 1000, '百万円': 1000000}
            base_unit_map = {'千円': '円', '百万円': '円'}
            for unit_str, factor in scale_factors.items():
                mask = df['単位_ベース'] == unit_str
                if mask.any():
                    df.loc[mask, '値_ベースユニット'] = pd.to_numeric(df.loc[mask, '値_ベースユニット'], errors='coerce') * factor
                    df.loc[mask, '単位_ベース'] = base_unit_map.get(unit_str, df.loc[mask, '単位_ベース'])
            specific_units = ['株', '%', '倍', '人', '名', '社', '日', '年', '件', '純資産額比', '取締役監査役']
            for unit_val in specific_units:
                mask = df['単位_ベース'] == unit_val
                if mask.any(): df.loc[mask, '単位_ベース'] = unit_val
        else:
            df.loc[:, '値_ベースユニット'] = df['値'] if '値' in df.columns else pd.NA
            df.loc[:, '単位_ベース'] = df['単位'].astype(str).fillna("") if '単位' in df.columns else ""

        if '値_ベースユニット' in df.columns and '単位_ベース' in df.columns:
            df.loc[:, '表示値'] = df['値_ベースユニット']
            df.loc[:, '表示単位'] = df['単位_ベース']
        else:
            df.loc[:, '表示値'] = df['値_ベースユニット'] if '値_ベースユニット' in df.columns else (df['値'] if '値' in df.columns else pd.NA)
            df.loc[:, '表示単位'] = df['単位_ベース'] if '単位_ベース' in df.columns else (df['単位'].astype(str).fillna("") if '単位' in df.columns else "")

        if 'ContextID_Part2' in df.columns:
            df.rename(columns={'ContextID_Part2': '連結･個別'}, inplace=True)

        final_pivot_df = None
        pivot_index_cols = ['項目名', '連結･個別', '単位', '表示単位']
        pivot_columns_col = '期間'
        pivot_values_col = '表示値'

        for col in pivot_index_cols:
            if col not in df.columns:
                df[col] = "N/A_INDEX_DEFAULT"
                logger.warning(f"警告 ({df_name_for_log}): ピボットのインデックス列 '{col}' がありません。デフォルト値 'N/A_INDEX_DEFAULT' を使用します。")

        required_cols_for_pivot = pivot_index_cols + [pivot_columns_col, pivot_values_col]

        if pivot_columns_col in df.columns:
            df.loc[:, pivot_columns_col] = pd.Categorical(df[pivot_columns_col], categories=current_pivot_column_order, ordered=True)
            df.dropna(subset=[pivot_columns_col], inplace=True)
        else:
            logger.warning(f"警告 ({df_name_for_log}): ピボットの列となる「{pivot_columns_col}」列がありません。")
            return None

        all_pivot_cols_present = all(col in df.columns for col in required_cols_for_pivot)
        if all_pivot_cols_present and not df.empty and pivot_values_col in df.columns and df[pivot_values_col].notna().any():
            try:
                df_for_pivot = df.copy()
                for col in pivot_index_cols:
                    if df_for_pivot[col].isnull().any():
                        df_for_pivot[col] = df_for_pivot[col].astype(str).fillna("N/A_INDEX")

                unique_rows_for_index = df_for_pivot.drop_duplicates(subset=pivot_index_cols)
                desired_row_index = pd.MultiIndex.from_frame(unique_rows_for_index[pivot_index_cols], names=pivot_index_cols)

                pivot_temp = df_for_pivot.pivot_table(
                    index=pivot_index_cols, columns=pivot_columns_col, values=pivot_values_col,
                    observed=True, aggfunc='first'
                )
                ordered_cols_in_pivot = [col for col in current_pivot_column_order if col in pivot_temp.columns]
                if ordered_cols_in_pivot : pivot_temp = pivot_temp[ordered_cols_in_pivot]

                if not pivot_temp.empty:
                    try:
                        common_indices = desired_row_index.intersection(pivot_temp.index)
                        if not common_indices.empty:
                            final_pivot_df = pivot_temp.reindex(index=common_indices)
                        else:
                            final_pivot_df = pivot_temp
                            logger.warning(f"警告 ({df_name_for_log}): 行の並び替えのための共通インデックスなし。ピボットのデフォルト順序を使用。")
                    except TypeError as e_reindex_type:
                        logger.error(f"エラー ({df_name_for_log}): ピボットテーブルのインデックス再構築中に型エラー: {e_reindex_type}。デフォルト順序を使用。")
                        final_pivot_df = pivot_temp

                if final_pivot_df is None or final_pivot_df.empty: final_pivot_df = None

            except Exception as e_pivot:
                logger.error(f"エラー ({df_name_for_log}): ピボットテーブル作成中にエラー: {e_pivot}", exc_info=True)
                final_pivot_df = None
        else:
            missing_cols_log = [col for col in required_cols_for_pivot if col not in df.columns]
            logger.warning(f"警告 ({df_name_for_log}): ピボット作成に必要な列が存在しないか、「表示値」が全てNaN、またはDataFrameが空です。不足列: {missing_cols_log}")
        return final_pivot_df

    try:
        if app_config.IS_CLOUD_RUN:
            if storage is None:
                logger.critical("GCS環境ですが、Storageライブラリがロードされていません。")
                return (None, None, None, None, None, None)
            if not app_config.GCS_BUCKET_NAME:
                logger.error("GCSバケット名がconfig.pyで設定されていません。")
                return (None, None, None, None, None, None)
            storage_client = storage.Client()
            bucket = storage_client.bucket(app_config.GCS_BUCKET_NAME)
            blob_name = os.path.join(save_dir_main, zip_filename).replace("\\", "/")
            logger.info(f"GCSからファイルを取得しようとしています: gs://{app_config.GCS_BUCKET_NAME}/{blob_name}")
            blob = bucket.blob(blob_name)
            if not blob.exists():
                logger.error(f"エラー: GCS上にZIPファイルが見つかりません gs://{app_config.GCS_BUCKET_NAME}/{blob_name}")
                return (None, None, None, None, None, None)
            zip_file_bytes = blob.download_as_bytes()
            logger.info(f"GCSからファイル {blob_name} を正常にダウンロードしました。")
        else:
            local_zip_filepath = os.path.join(save_dir_main, zip_filename)
            if not os.path.exists(local_zip_filepath):
                logger.error(f"エラー: ローカルにZIPファイルが見つかりません {local_zip_filepath}")
                return (None, None, None, None, None, None)
            with open(local_zip_filepath, 'rb') as f:
                zip_file_bytes = f.read()
            logger.info(f"ローカルからファイル {local_zip_filepath} を正常に読み込みました。")

        with zipfile.ZipFile(BytesIO(zip_file_bytes), 'r') as zf:
            jpcrp_csv_paths = [name for name in zf.namelist() if name.startswith('XBRL_TO_CSV/jpcrp')]
            if not jpcrp_csv_paths:
                logger.error(f"エラー: ZIP '{zip_filename}' 内に 'XBRL_TO_CSV/jpcrp' で始まるCSVがありません。")
                return (None, None, None, None, None, None)
            df_initial = pd.read_csv(BytesIO(zf.read(jpcrp_csv_paths[0])), encoding="utf-16", sep="\t")
            df_initial.insert(0, 'docID', doc_id_main)
            df_initial['値_数値_temp'] = pd.to_numeric(df_initial['値'], errors='coerce')
            numeric_mask = df_initial['値_数値_temp'].notna()
            df_numeric_cleaned = df_initial[numeric_mask].copy()
            df_other_final_res = df_initial[~numeric_mask].copy()
            if not df_numeric_cleaned.empty:
                df_numeric_cleaned.loc[:, '値'] = df_numeric_cleaned['値_数値_temp']
            df_numeric_cleaned = df_numeric_cleaned.drop(columns=['値_数値_temp'], errors='ignore')
            df_other_final_res = df_other_final_res.drop(columns=['値_数値_temp'], errors='ignore')
            if not df_numeric_cleaned.empty:
                df_numeric_cleaned.drop_duplicates(inplace=True)
                if '項目名' in df_numeric_cleaned.columns:
                    df_numeric_cleaned = df_numeric_cleaned[df_numeric_cleaned['項目名'] != 'なし'].copy()
                    df_numeric_cleaned.dropna(subset=['項目名'], inplace=True)
                if 'コンテキストID' in df_numeric_cleaned.columns:
                    df_numeric_cleaned.loc[:, 'コンテキストID'] = df_numeric_cleaned['コンテキストID'].astype(str)
                    df_numeric_cleaned = df_numeric_cleaned[df_numeric_cleaned['コンテキストID'].str.count('_') < 2].copy()
                    split_contexts = df_numeric_cleaned['コンテキストID'].str.split('_', n=1, expand=True)
                    df_numeric_cleaned['ContextID_Part1'] = split_contexts[0]
                    df_numeric_cleaned['ContextID_Part2'] = split_contexts[1] if split_contexts.shape[1] > 1 else "N/A_Context"
                if 'ContextID_Part1' in df_numeric_cleaned.columns:
                    df_numeric_cleaned.loc[:, 'ContextID_Part1'] = df_numeric_cleaned['ContextID_Part1'].astype(str).replace(current_replace_dict_context_part1)
                    df_numeric_cleaned.rename(columns={'ContextID_Part1': '期間'}, inplace=True)
                else:
                    logger.warning("警告: 「ContextID_Part1」列がdf_numeric_cleanedにないため、「期間」列を作成できませんでした。")
                    df_numeric_cleaned.loc[:, '期間'] = pd.NA
                if 'ContextID_Part2' in df_numeric_cleaned.columns:
                    condition_blank = df_numeric_cleaned['ContextID_Part2'].isnull() | (df_numeric_cleaned['ContextID_Part2'] == '') | (df_numeric_cleaned['ContextID_Part2'] == 'N/A_Context')
                    df_numeric_cleaned.loc[condition_blank, 'ContextID_Part2'] = '連結優先'
                    condition_nonconsolidated = df_numeric_cleaned['ContextID_Part2'] == 'NonConsolidatedMember'
                    df_numeric_cleaned.loc[condition_nonconsolidated, 'ContextID_Part2'] = '個別'
                    condition_filter_context_part2 = ((df_numeric_cleaned['ContextID_Part2'] == '連結優先') | (df_numeric_cleaned['ContextID_Part2'] == '個別'))
                    df_numeric_cleaned = df_numeric_cleaned[condition_filter_context_part2].copy()

            df_main_indicators = pd.DataFrame()
            df_pl_consolidated = pd.DataFrame(); df_pl_non_consolidated = pd.DataFrame()
            df_bs_consolidated = pd.DataFrame(); df_bs_non_consolidated = pd.DataFrame()

            if not df_numeric_cleaned.empty:
                main_indicator_mask = df_numeric_cleaned['項目名'].str.endswith('、経営指標等', na=False)
                df_main_indicators = df_numeric_cleaned[main_indicator_mask].copy()
                if not df_main_indicators.empty and '項目名' in df_main_indicators.columns:
                    df_main_indicators.loc[:, '項目名'] = df_main_indicators['項目名'].str.replace('、経営指標等', '', regex=False)
                df_remaining_for_pl_bs = df_numeric_cleaned[~main_indicator_mask].copy()
                pl_keywords = ['期間', 'Duration', '連結会計年度', '事業年度', '報告期間']
                bs_keywords = ['時点', '末', '期末', 'Instant', 'BalanceSheet']
                df_pl_temp, df_bs_temp = pd.DataFrame(), pd.DataFrame()
                if '期間・時点' in df_remaining_for_pl_bs.columns:
                    df_remaining_for_pl_bs.loc[:, '期間・時点'] = df_remaining_for_pl_bs['期間・時点'].astype(str)
                    df_pl_temp = df_remaining_for_pl_bs[df_remaining_for_pl_bs['期間・時点'].str.contains('|'.join(pl_keywords), case=False, na=False)].copy()
                    df_bs_temp = df_remaining_for_pl_bs[df_remaining_for_pl_bs['期間・時点'].str.contains('|'.join(bs_keywords), case=False, na=False)].copy()
                else:
                    logger.warning("警告: 「期間・時点」列が df_remaining_for_pl_bs にないため、P/L, B/S Temp DataFrame は空です。")
                if 'ContextID_Part2' in df_pl_temp.columns:
                    df_pl_consolidated = df_pl_temp[df_pl_temp['ContextID_Part2'] == '連結優先'].copy()
                    df_pl_non_consolidated = df_pl_temp[df_pl_temp['ContextID_Part2'] == '個別'].copy()
                if 'ContextID_Part2' in df_bs_temp.columns:
                    df_bs_consolidated = df_bs_temp[df_bs_temp['ContextID_Part2'] == '連結優先'].copy()
                    df_bs_non_consolidated = df_bs_temp[df_bs_temp['ContextID_Part2'] == '個別'].copy()
            else:
                logger.warning("警告: 数値データ(df_numeric_cleaned)が共通前処理後に空になったため、後続の分割・ピボット処理をスキップします。")

            df_main_indicators_pivot_res = process_dataframe_and_create_pivot_inner(df_main_indicators, "主要経営指標等DF")
            df_pl_consolidated_pivot_res = process_dataframe_and_create_pivot_inner(df_pl_consolidated, "P/L連結優先DF")
            df_pl_non_consolidated_pivot_res = process_dataframe_and_create_pivot_inner(df_pl_non_consolidated, "P/L個別DF")
            df_bs_consolidated_pivot_res = process_dataframe_and_create_pivot_inner(df_bs_consolidated, "B/S連結優先DF")
            df_bs_non_consolidated_pivot_res = process_dataframe_and_create_pivot_inner(df_bs_non_consolidated, "B/S個別DF")

            if df_other_final_res is not None and not df_other_final_res.empty:
                if '値' in df_other_final_res.columns:
                    df_other_final_res = df_other_final_res[df_other_final_res['値'].astype(str) != '－'].copy()
                keep_cols = ['項目名', '値']
                actual_keep_cols = [col for col in keep_cols if col in df_other_final_res.columns]
                if actual_keep_cols:
                    df_other_final_res = df_other_final_res[actual_keep_cols]
                elif not df_other_final_res.empty:
                    logger.warning(f"警告: df_other_final に保持すべき列（{', '.join(keep_cols)}）が一つも見つかりませんでした。")

    except Exception as e_outer:
        logger.error(f"メイン処理ブロックで予期せぬエラー: {e_outer}", exc_info=True)

    return (df_main_indicators_pivot_res,
            df_pl_consolidated_pivot_res, df_pl_non_consolidated_pivot_res,
            df_bs_consolidated_pivot_res, df_bs_non_consolidated_pivot_res,
            df_other_final_res)

# --- ページレンダリング関数 (render_page 以下) ---
def render_page(sm, fm, akm, active_model):
    st.title("ステップ9: EDINET有価証券報告書ビューア")
    st.markdown("EDINETから取得した有価証券報告書のデータを表示・分析します。ページ上部のグローバル検索で選択された銘柄が自動的に反映されます。")

    # --- グローバル銘柄情報の取得とページ状態の同期 ---
    global_stock_code = sm.get_value("app.selected_stock_code")
    global_stock_name = sm.get_value("app.selected_stock_name", "未選択")

    if not global_stock_code:
        st.warning("ページ上部の検索バーから、分析したい銘柄を検索・選択してください。")
        if sm.get_value(KEY_EV_SELECTED_CODE) is not None:
            sm.set_value(KEY_EV_SELECTED_CODE, None)
            sm.set_value(KEY_EV_LOADED_DATA, None)
            sm.set_value(KEY_EV_DOC_DESCRIPTION_OPTIONS, None)
        return

    st.markdown(f"#### 現在の対象銘柄: **{global_stock_name} ({global_stock_code})**")

    page_processed_code = sm.get_value(KEY_EV_SELECTED_CODE)

    if global_stock_code != page_processed_code:
        logger.info(f"EDINET Viewer: Global stock changed from '{page_processed_code}' to '{global_stock_code}'. Resetting page state.")
        sm.set_value(KEY_EV_SELECTED_CODE, global_stock_code)
        sm.set_value(KEY_EV_DOC_DESCRIPTION_OPTIONS, None)
        sm.set_value(KEY_EV_SELECTED_DOC_ID, None)
        sm.set_value(KEY_EV_LOADED_DATA, None)
        sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)
        sm.set_value(KEY_EV_AI_ANALYSIS_ACTIVE, False)
        sm.set_value(KEY_EV_PAGE_MESSAGE, {"text": f"銘柄が「{global_stock_name}」に更新されました。報告書リストを読み込みます。", "type": "info"})
        st.rerun()

    page_message = sm.get_value(KEY_EV_PAGE_MESSAGE)
    if page_message:
        msg_type = page_message.get("type", "info")
        if msg_type == "error": st.error(page_message["text"])
        elif msg_type == "success": st.success(page_message["text"])
        else: st.info(page_message["text"])
        sm.set_value(KEY_EV_PAGE_MESSAGE, None)

    if sm.get_value(KEY_EV_AI_ANALYSIS_ACTIVE, False):
        with st.spinner("LLMによる分析を実行中...しばらくお待ちください。"):
            try:
                start_time = time.time()
                loaded_data_for_ai = sm.get_value(KEY_EV_LOADED_DATA)
                selected_dfs_for_ai = sm.get_value(KEY_EV_SELECTED_DFS_TO_SHOW)
                filer_name_for_prompt = sm.get_value('app.selected_stock_name', '不明な発行者')

                if not loaded_data_for_ai or not selected_dfs_for_ai:
                    raise ValueError("AI分析の対象となるデータがロードされていないか、選択されていません。")

                df_names_map_for_ai = {
                    "main_pivot": "主要経営指標", "pl_con_pivot": "損益計算書 (連結)",
                    "pl_noncon_pivot": "損益計算書 (個別)", "bs_con_pivot": "貸借対照表 (連結)",
                    "bs_noncon_pivot": "貸借対照表 (個別)", "other_df": "その他テキスト情報"
                }

                data_for_llm = {}
                key_list = list(df_names_map_for_ai.keys())
                for df_key in selected_dfs_for_ai:
                    if df_key in key_list:
                        df_index = key_list.index(df_key)
                        df_to_convert_original = loaded_data_for_ai[df_index]

                        if df_to_convert_original is not None and not df_to_convert_original.empty:
                            if isinstance(df_to_convert_original.index, pd.MultiIndex):
                                df_to_convert_original_reset = df_to_convert_original.reset_index()
                            else:
                                df_to_convert_original_reset = df_to_convert_original.copy()

                            df_to_convert_original_reset.columns = [str(col) for col in df_to_convert_original_reset.columns]
                            data_for_llm[df_names_map_for_ai[df_key]] = json.loads(df_to_convert_original_reset.head(20).to_json(orient='split', force_ascii=False))

                if not data_for_llm:
                    raise ValueError("LLMに渡すためのデータが空です。")

                prompt_parts = [
                    f"あなたは優秀な証券アナリストです。以下のEDINET有価証券報告書のデータ（JSON形式）を分析し、企業の財務状況、経営成績、および今後の見通しについて、専門的かつ分かりやすく解説してください。",
                    f"分析対象企業: {filer_name_for_prompt}",
                    f"提供データ:\n{json.dumps(data_for_llm, ensure_ascii=False, indent=2)}",
                    "\n# あなたのタスク:",
                    "1. **全体サマリー**: まず、提供されたデータ全体から読み取れる企業の最も重要なポイントを3点、箇条書きで要約してください。",
                    "2. **詳細分析**: 次に、以下の各項目について、具体的な数値を引用しながら、企業の強み・弱み、注目すべき変化などを詳細に分析してください。",
                    "   - **収益性**: 売上高や利益のトレンド、利益率の変化など。",
                    "   - **財務健全性**: 自己資本比率、有利子負債、資産構成など。",
                    "   - **経営効率**: ROE、ROAなどの指標から企業の資本効率を評価してください。",
                    "   - **その他特記事項**: 経営指標やテキスト情報から読み取れる特筆すべき点があれば言及してください。",
                    "3. **総合評価と今後の見通し**: 最後に、これらの分析を総合して、企業の現状を評価し、考えられる今後のリスクや成長機会について、あなたの専門的な見解を述べてください。",
                    "\n# 出力形式:",
                    "- マークダウン形式で、見出しや箇条書きを適切に使用して、構造化された読みやすいレポートを作成してください。",
                    "- 専門用語には簡単な注釈を付けるなど、投資初心者にも理解しやすいように配慮してください。"
                ]
                prompt = "\n\n".join(prompt_parts)
                sm.set_value(KEY_LAST_AI_PROMPT, prompt)

                analysis_result = api_services.generate_gemini_response(prompt, active_model)
                end_time = time.time()

                if analysis_result.startswith("[LLM エラー]"):
                    sm.set_value(KEY_EV_PAGE_MESSAGE, {"text": f"LLM分析エラー: {analysis_result}", "type": "error"})
                    sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)
                else:
                    sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, analysis_result)
                    sm.set_value(KEY_EV_AI_PROCESSING_TIME, end_time - start_time)

            except Exception as e:
                logger.error(f"EDINET AI分析中にエラーが発生: {e}", exc_info=True)
                sm.set_value(KEY_EV_PAGE_MESSAGE, {"text": f"AI分析の準備中に予期せぬエラーが発生しました: {e}", "type": "error"})
                sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)

            finally:
                sm.set_value(KEY_EV_AI_ANALYSIS_ACTIVE, False)
                st.rerun()

    try:
        if sm.get_value("edinet_viewer.listed_companies_df") is None:
            with st.spinner("企業一覧データを読み込み中..."):
                df_listed_company_summary, encoding, error_msg = fm.load_csv('listed_company_summary')
                if error_msg:
                    st.error(f"企業一覧ファイルの読み込みに失敗: {error_msg}")
                    return
                if df_listed_company_summary is None or df_listed_company_summary.empty:
                    st.error("企業一覧データが空です。")
                    return

                df_listed_company_summary['submitDateTime'] = pd.to_datetime(df_listed_company_summary['submitDateTime'], errors='coerce')
                # 5桁のコードから先頭4桁を取得する
                df_listed_company_summary['secCode'] = df_listed_company_summary['secCode'].astype(str).str[:4]
                sm.set_value("edinet_viewer.listed_companies_df", df_listed_company_summary)
                st.rerun()

        df_listed_companies = sm.get_value("edinet_viewer.listed_companies_df")
        if df_listed_companies is None:
            st.error("企業一覧データが読み込まれていません。リロードしてください。")
            return

        if global_stock_code not in df_listed_companies['secCode'].unique():
            st.error(f"選択された銘柄コード ({global_stock_code}) は、EDINET提出企業一覧に見つかりませんでした。")
            return

        selected_code_for_reports = sm.get_value(KEY_EV_SELECTED_CODE)
        doc_options_dict = sm.get_value(KEY_EV_DOC_DESCRIPTION_OPTIONS)

        if selected_code_for_reports and doc_options_dict is None:
            with st.spinner(f"{selected_code_for_reports} の報告書リストを取得中..."):
                reports_for_code = df_listed_companies[df_listed_companies['secCode'] == selected_code_for_reports].copy()
                reports_for_code.sort_values('submitDateTime', ascending=False, inplace=True)

                temp_doc_options_dict = {}
                for _, row in reports_for_code.iterrows():
                    if pd.notna(row['submitDateTime']) and pd.notna(row['docDescription']) and pd.notna(row['docID']):
                        date_str = row['submitDateTime'].strftime('%Y-%m-%d') if isinstance(row['submitDateTime'], pd.Timestamp) else "日付不明"
                        temp_doc_options_dict[row['docID']] = f"{date_str} - {row['docDescription']} ({row['docID']})"

                doc_options_dict = temp_doc_options_dict
                sm.set_value(KEY_EV_DOC_DESCRIPTION_OPTIONS, doc_options_dict)
                st.rerun()

        if doc_options_dict:
            st.markdown("---")
            st.subheader("1. 閲覧する報告書を選択してください:")
            doc_display_options = list(doc_options_dict.values())
            current_selected_doc_id = sm.get_value(KEY_EV_SELECTED_DOC_ID)
            current_display_value = None
            if current_selected_doc_id and current_selected_doc_id in doc_options_dict:
                current_display_value = doc_options_dict[current_selected_doc_id]

            selected_doc_idx = doc_display_options.index(current_display_value) if current_display_value in doc_display_options else 0

            selected_doc_description_display = st.selectbox(
                "報告書:",
                options=doc_display_options,
                index=selected_doc_idx,
                key="edinet_doc_description_select",
                label_visibility="collapsed"
            )

            new_selected_doc_id = None
            for doc_id_val, desc_val in doc_options_dict.items():
                if desc_val == selected_doc_description_display:
                    new_selected_doc_id = doc_id_val
                    break

            if new_selected_doc_id and new_selected_doc_id != sm.get_value(KEY_EV_SELECTED_DOC_ID):
                sm.set_value(KEY_EV_SELECTED_DOC_ID, new_selected_doc_id)
                sm.set_value(KEY_EV_LOADED_DATA, None)
                sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)
                st.rerun()

        elif selected_code_for_reports:
            st.info(f"銘柄コード {selected_code_for_reports} の報告書が見つかりませんでした。")

        selected_doc_id_for_processing = sm.get_value(KEY_EV_SELECTED_DOC_ID)

        if selected_doc_id_for_processing and selected_code_for_reports:
            st.subheader("2. データを処理・表示します")
            if st.button(f"選択中の報告書のデータを処理・表示", key="process_edinet_data_button", use_container_width=True):
                with st.spinner(f"{selected_doc_id_for_processing} のデータを処理中..."):
                    edinet_zip_dir_meta = app_config.FILE_METADATA.get('edinet_zip_dir', {})
                    save_dir = edinet_zip_dir_meta.get('path_colab') if not app_config.IS_CLOUD_RUN else edinet_zip_dir_meta.get('path_gcs_blob')

                    if not save_dir:
                        st.error("EDINET ZIPファイルの保存ディレクトリパスがconfig.pyで設定されていません。")
                        return

                    try:
                        loaded_data_tuple = process_edinet_document(selected_doc_id_for_processing, save_dir)
                        sm.set_value(KEY_EV_LOADED_DATA, loaded_data_tuple)
                        sm.set_value(KEY_EV_SELECTED_DFS_TO_SHOW, [])
                        sm.set_value(KEY_EV_DISPLAY_ROWS_CONFIG, {})
                        sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)
                        sm.set_value(KEY_EV_PAGE_MESSAGE, {"text": f"{selected_doc_id_for_processing} のデータ処理が完了しました。", "type": "success"})
                        st.rerun()
                    except Exception as e_proc:
                        st.error(f"データ処理中にエラーが発生しました: {e_proc}")
                        sm.set_value(KEY_EV_LOADED_DATA, None)
                        sm.set_value(KEY_EV_PAGE_MESSAGE, {"text": f"データ処理エラー: {e_proc}", "type": "error"})

        loaded_data = sm.get_value(KEY_EV_LOADED_DATA)
        if loaded_data:
            df_names_map = {
                "main_pivot": "主要経営指標", "pl_con_pivot": "損益計算書 (連結)",
                "pl_noncon_pivot": "損益計算書 (個別)", "bs_con_pivot": "貸借対照表 (連結)",
                "bs_noncon_pivot": "貸借対照表 (個別)", "other_df": "その他テキスト情報"
            }
            available_dfs = {
                df_key: df_obj for df_key, df_obj in zip(df_names_map.keys(), loaded_data) if df_obj is not None and not df_obj.empty
            }

            if not available_dfs:
                st.info("処理されたデータがありません。または、全てのデータフレームが空です。")
                return

            st.markdown("---")
            st.subheader("3. 表示するデータを選択してください:")

            cols_checkbox = st.columns(3)
            selected_dfs_to_show = sm.get_value(KEY_EV_SELECTED_DFS_TO_SHOW, [])
            temp_selected_dfs = []
            checkbox_idx = 0
            for df_key, df_display_name in df_names_map.items():
                if df_key in available_dfs:
                    with cols_checkbox[checkbox_idx % 3]:
                        if st.checkbox(df_display_name, value=(df_key in selected_dfs_to_show), key=f"cb_{df_key}"):
                            temp_selected_dfs.append(df_key)
                    checkbox_idx += 1

            if temp_selected_dfs != selected_dfs_to_show:
                sm.set_value(KEY_EV_SELECTED_DFS_TO_SHOW, temp_selected_dfs)
                st.rerun()

            def format_df_for_display(input_df, numeric_cols_order_list):
                df_display_formatted = input_df.copy()
                unit_level_name = '表示単位'
                if unit_level_name not in df_display_formatted.index.names:
                    return df_display_formatted.reset_index()
                try:
                    unit_idx_in_multiindex = df_display_formatted.index.names.index(unit_level_name)
                except ValueError:
                    return df_display_formatted.reset_index()

                for col_name in numeric_cols_order_list:
                    if col_name in df_display_formatted.columns:
                        new_col_values = []
                        for idx_tuple, val in df_display_formatted[col_name].items():
                            try: unit = idx_tuple[unit_idx_in_multiindex]
                            except IndexError: unit = "円"

                            if pd.isna(val): new_col_values.append(""); continue
                            try: val_num = float(val)
                            except (ValueError, TypeError): new_col_values.append(str(val)); continue

                            if unit == '円':
                                if abs(val_num) >= 1_000_000_000_000: new_col_values.append(f"{val_num / 1_000_000_000_000:,.2f}兆円")
                                elif abs(val_num) >= 100_000_000: new_col_values.append(f"{val_num / 100_000_000:,.2f}億円")
                                elif abs(val_num) >= 10_000: new_col_values.append(f"{val_num / 10_000:,.2f}万円")
                                else: new_col_values.append(f"{val_num:,.0f}円")
                            elif unit == '%': new_col_values.append(f"{val_num:.2f}")
                            elif unit in ['株', '人', '倍', '名', '社', '日', '年', '件']: new_col_values.append(f"{val_num:,.2f}")
                            else: new_col_values.append(f"{val_num:,.2f}")
                        df_display_formatted[col_name] = new_col_values

                df_after_reset = df_display_formatted.reset_index()
                if unit_level_name in df_after_reset.columns:
                    df_after_reset = df_after_reset.drop(columns=[unit_level_name])
                return df_after_reset

            for df_key in selected_dfs_to_show:
                if df_key in available_dfs:
                    df_to_display_original = available_dfs[df_key]
                    df_display_name = df_names_map[df_key]
                    st.markdown(f"### {df_display_name}")

                    if df_key == "other_df":
                        st.dataframe(df_to_display_original, hide_index=True)
                    else:
                        df_formatted_for_streamlit = format_df_for_display(df_to_display_original, pivot_column_order_global)
                        st.dataframe(df_formatted_for_streamlit)
                    st.markdown("---")

            if selected_dfs_to_show and api_services.is_gemini_api_configured():
                st.subheader("4. 選択したデータをLLMで分析")

                if st.button("選択したデータの分析をLLMに依頼", key="analyze_edinet_with_llm", use_container_width=True):
                    sm.set_value(KEY_EV_AI_ANALYSIS_RESULT, None)
                    sm.set_value(KEY_EV_AI_ANALYSIS_ACTIVE, True)
                    st.rerun()

            ai_result = sm.get_value(KEY_EV_AI_ANALYSIS_RESULT)
            if ai_result:
                st.markdown("#### LLMによる分析結果")
                processing_time = sm.get_value(KEY_EV_AI_PROCESSING_TIME)
                if processing_time:
                    st.caption(f"（分析処理時間: {processing_time:.2f}秒）")
                st.markdown(ai_result)

            last_prompt = sm.get_value(KEY_LAST_AI_PROMPT)
            if last_prompt and not app_config.IS_CLOUD_RUN:
                with st.expander("LLMに送信したプロンプト（デバッグ用）"):
                    st.text_area("Last Prompt", value=last_prompt, height=200, key="edinet_last_prompt_debug")

    except Exception as e:
        st.error(f"ページ描画中にエラーが発生しました: {e}")
        logger.error(f"EDINET Viewer: Error during page render: {e}", exc_info=True)
        return

    st.markdown("---")
    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("戻る (ステップ8: テクニカル分析へ)", key="edinet_back_to_s8", use_container_width=True):
            sm.set_value("app.current_step", 8)
            st.rerun()
    with col_next:
        if st.button("次へ (ステップ10: LLMによるEDINETデータの高度分析・抽出 (LLM必須))", type="primary", key="s9_next_to_s10", use_container_width=True):
            sm.set_value("app.current_step", 10)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

