# edinet_sort_page.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import logging
import re
import os
import traceback
from io import BytesIO

# --- 既存のアプリケーションモジュールをインポート ---
import config as app_config
import api_services
from state_manager import StateManager
from file_manager import FileManager

logger = logging.getLogger(__name__)

# --- StateManagerで使用するキー (V1ベースにV2の要素を追加) ---
KEY_ES_QUERY = "edinet_sort.query"
KEY_ES_ITEM_DF = "edinet_sort.item_df"
KEY_ES_STOCK_NAME_MAP = "edinet_sort.stock_name_map"
KEY_ES_MAIN_KEYS = "edinet_sort.main_keys"
KEY_ES_PROCESSING_STATUS = "edinet_sort.processing_status"
KEY_ES_LLM_ITEM_SUGGESTIONS_RAW = "edinet_sort.llm_item_suggestions_raw"
KEY_ES_DATAFRAMES_DICT = "edinet_sort.dataframes_dict"
KEY_ES_SORT_DF_TEXT = "edinet_sort.sort_df_text"
KEY_ES_STRATEGIES_RAW = "edinet_sort.strategies_raw"
KEY_ES_SELECTED_STRATEGIES = "edinet_sort.selected_strategies"
KEY_ES_GENERATED_CODE = "edinet_sort.generated_code"
KEY_ES_RESULT_DF = "edinet_sort.result_df"
KEY_ES_ERROR_MESSAGE = "edinet_sort.error_message"
KEY_ES_REJECTED_STRATEGIES = "edinet_sort.rejected_strategies" # V2から移植
KEY_ES_USER_FEEDBACK = "edinet_sort.user_feedback"           # V2から移植
KEY_ES_LLM_CODE_RAW = "edinet_sort.llm_code_raw"
KEY_ES_FINAL_ANALYSIS_RESULT = "edinet_sort.final_analysis_result"
KEY_ES_FINAL_ANALYSIS_RUNNING = "edinet_sort.final_analysis_running"


# --- edinet_sort.py から移植・修正した関数群 ---

def sanitize_filename(filename: str) -> str:
    """
    ファイル名として使えない文字をアンダースコアに置換する。
    """
    invalid_chars_pattern = r'[\s\u3000\\/:*?"<>|\[\]()]'
    sanitized_name = re.sub(invalid_chars_pattern, '_', filename)
    return sanitized_name

def classify_context_id_final(context_id):
    """分類ルールを単純化し、汎用的な「分類対象」カテゴリを導入した最終版関数"""
    period_info = 'N/A'; consolidation = '連結'; category = '不明'
    match = re.match(r'([A-Za-z0-9]+(Duration|Instant))', context_id)
    if match: period_info = match.group(1); further_detail = context_id[len(period_info):].strip('_')
    else: further_detail = context_id
    if 'NonConsolidatedMember' in further_detail: consolidation = '個別'; further_detail = further_detail.replace('NonConsolidatedMember', '').strip('_')
    if not further_detail: category = '本体財務諸表'
    elif re.search(r'(Share|Stock)Member$', further_detail, re.IGNORECASE): category = '株式・株主情報'
    elif re.search(r'Member$', further_detail): category = '分類対象'
    elif further_detail: category = 'その他'
    return {'PeriodInfo': period_info, 'Consolidation': consolidation, 'Category': category}

def process_financial_data_final(json_data, stock_name_map, period_map):
    """
    JSONデータを変換、マージ、ソートまで行う最終版の統合関数 (V2から移植)
    """
    if not json_data or not isinstance(json_data, dict):
        logger.warning("process_financial_data_final: 入力json_dataが空または不正です。")
        return pd.DataFrame()

    all_companies_data = {}

    for company_code, context_values in json_data.items():
        transformed_data = {}
        classification_counter = 1

        if not isinstance(context_values, dict): continue

        for raw_context_id, value in context_values.items():
            cleaned_id = re.sub(r'jpcrp[a-zA-Z0-9_-]*', '', raw_context_id)
            classified_info = classify_context_id_final(cleaned_id)
            category = classified_info['Category']
            period = classified_info['PeriodInfo']
            consolidation = classified_info['Consolidation']

            generic_part = None
            if category == '本体財務諸表':
                generic_part = period_map.get(period)
            elif category == '株式・株主情報':
                # V1のロジックに合わせて単純化
                generic_part = '株式・その他'
            elif category == '分類対象':
                generic_part = '分類'

            if generic_part is None: continue

            if generic_part == '分類':
                if classification_counter <= 5:
                    final_id = f"{consolidation}_{generic_part}{classification_counter}"
                    transformed_data[final_id] = value
                classification_counter += 1
            else:
                final_id = f"{consolidation}_{generic_part}"
                transformed_data[final_id] = value

        all_companies_data[company_code] = transformed_data

    if not all_companies_data:
        return pd.DataFrame()

    intermediate_df = pd.DataFrame.from_dict(all_companies_data, orient='index')
    if intermediate_df.empty:
        return pd.DataFrame()

    intermediate_df.dropna(axis=1, how='all', inplace=True)

    merged_cols_dict = {}
    processed_generic_parts = set()

    for col in intermediate_df.columns:
        parts = col.split('_', 1)
        if len(parts) < 2: continue
        generic_part = parts[1]

        if generic_part in processed_generic_parts: continue

        renketsu_col = f'連結_{generic_part}'
        kobetsu_col = f'個別_{generic_part}'
        merged_series = None

        if renketsu_col in intermediate_df:
            merged_series = intermediate_df[renketsu_col]
            if kobetsu_col in intermediate_df:
                merged_series = merged_series.combine_first(intermediate_df[kobetsu_col])
        elif kobetsu_col in intermediate_df:
            merged_series = intermediate_df[kobetsu_col]

        if merged_series is not None:
            merged_cols_dict[generic_part] = merged_series
            processed_generic_parts.add(generic_part)

    if not merged_cols_dict:
        return pd.DataFrame()

    final_df = pd.DataFrame(merged_cols_dict)

    ordered_time_periods = list(period_map.values())
    time_cols_sorted = [p for p in ordered_time_periods if p in final_df.columns]
    classification_cols = sorted([c for c in final_df.columns if c.startswith('分類')], key=lambda x: int(re.search(r'\d+', x).group()))
    other_cols_sorted = sorted([c for c in final_df.columns if c not in time_cols_sorted and c not in classification_cols])
    final_column_order = time_cols_sorted + classification_cols + other_cols_sorted

    final_column_order = [col for col in final_column_order if col in final_df.columns]
    if not final_column_order:
        return pd.DataFrame()

    final_df = final_df[final_column_order]
    final_df = final_df.sort_index().reset_index().rename(columns={'index': '銘柄コード'})

    if '銘柄コード' in final_df.columns:
        final_df.insert(1, '銘柄名', final_df['銘柄コード'].astype(str).map(stock_name_map))
        final_df.dropna(subset=['銘柄名'], inplace=True)

    return final_df

def find_item_name(item_name_query: str, item_df: pd.DataFrame) -> str | None:
    """指定されたクエリに最も一致する正式な項目名をitem_dfから検索します。(V1から流用)"""
    if item_df is None or item_df.empty: return None

    # 1. 完全一致
    exact_match = item_df[item_df['項目名'] == item_name_query]
    if not exact_match.empty:
        return exact_match['項目名'].iloc[0]

    # 2. "[テキストブロック]" を追加して完全一致
    item_name_with_suffix = item_name_query + " [テキストブロック]"
    suffix_match = item_df[item_df['項目名'] == item_name_with_suffix]
    if not suffix_match.empty:
        return suffix_match['項目名'].iloc[0]

    # 3. 部分一致 (最も一致度が高いものを選択するロジックは単純化)
    partial_match = item_df[item_df['項目名'].str.contains(re.escape(item_name_query), na=False)]
    if not partial_match.empty:
        return partial_match['項目名'].iloc[0]

    return None

def create_display_df(df):
    """表示用にテキストデータを切り詰める"""
    df_for_display = df.copy()
    for col in df_for_display.columns:
        if df_for_display[col].dtype == 'object':
            df_for_display[col] = df_for_display[col].apply(lambda x: (x[:100] + '...') if isinstance(x, str) and len(x) > 100 else x)
    return df_for_display

def create_dfs(llm_answer_raw, item_df, fm, stock_name_map, period_map):
    """LLMの提案項目に基づき、item_dfのパスからJSONを読み込みDataFrame群を生成する"""
    dataframes_dict = {}
    sort_df_text = ""
    exclude_columns = ['銘柄コード', '銘柄名']
    dir_id = 'edinet_separate_dir' # config.pyで定義

    if not llm_answer_raw or not llm_answer_raw.strip():
        raise ValueError("LLMから空の回答が返されました。")

    try:
        cleaned_json_string = llm_answer_raw.strip().removeprefix('```json').removesuffix('```').strip()
        item_names_from_llm = json.loads(cleaned_json_string)

        if isinstance(item_names_from_llm, dict) and 'error' in item_names_from_llm:
            raise ValueError(f"LLMからのエラー応答: {item_names_from_llm['error']}")

        sort_df_text += f"ユーザー質問に返答するためLLMが提案した関連するであろう項目:\n {item_names_from_llm}\n項目ごとのデータフレームを作成しdataframes_dictに格納。\n以下各dataframesの概要\n\n"

        for i, item_query in enumerate(item_names_from_llm):
            found_item_name = find_item_name(item_query, item_df)

            if found_item_name is None:
                logger.warning(f"⚠️ 警告: '{item_query}' に一致する項目がitem_dfに見つかりません。スキップします。")
                continue

            # item_df からファイルパスを取得
            item_info = item_df[item_df['項目名'] == found_item_name]
            # '保存パス' カラムの存在と有効性をチェック
            if item_info.empty or '保存パス' not in item_info.columns or pd.isna(item_info['保存パス'].iloc[0]):
                logger.warning(f"項目 '{found_item_name}' の保存パスが item_df に見つからないか、無効です。スキップします。")
                continue

            # pathlib.Pathやos.path.basenameでファイル名のみを安全に抽出
            file_path_from_df = item_info['保存パス'].iloc[0]
            target_filename = os.path.basename(file_path_from_df)

            # FileManagerを使用してJSONファイルを読み込む
            try:
                json_string = fm.read_text_from_dir(dir_id, target_filename)
                data = json.loads(json_string)
            except FileNotFoundError:
                logger.warning(f"⚠️ 警告: ファイル '{target_filename}' がディレクトリ '{dir_id}' に見つかりませんでした。スキップします。")
                continue
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 警告: ファイル '{target_filename}' のJSONパースに失敗しました。スキップします。")
                continue
            except Exception as e:
                logger.error(f"ファイル '{target_filename}' の読み込み中に予期せぬエラー: {e}")
                continue

            # 取得したデータを処理してDataFrameを生成
            df = process_financial_data_final(data, stock_name_map, period_map)
            df.dropna(how='all', axis=1, inplace=True)

            if not df.empty:
                # ★★★ 修正: 辞書には数値変換前のDFを格納し、統計情報作成用に別のDFで数値変換を行う ★★★
                # 1. 辞書には元のデータ(文字列含む)を格納
                dataframes_dict[found_item_name] = df.copy()

                # 2. 統計情報や後続処理のために、数値変換したDFを別途用意
                df_for_numeric_ops = df.copy()
                columns_to_convert = df_for_numeric_ops.columns.drop(exclude_columns, errors='ignore')
                df_for_numeric_ops[columns_to_convert] = df_for_numeric_ops[columns_to_convert].apply(pd.to_numeric, errors='coerce')

                # 3. LLMに渡す要約テキストは、数値変換後のDFで統計計算し、表示は元のDFで行う
                sort_df_text += f"DataFrame{i+1} dict key:{found_item_name}\n"
                sort_df_text += "df shape : " + str(df.shape) + "\n"
                sort_df_text += 'df describe \n'
                sort_df_text += df_for_numeric_ops.describe([0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).to_markdown() + "\n"
                sort_df_text += "df head(5)\n"
                sort_df_text += create_display_df(df.head(5)).to_markdown(index=False) + "\n\n"
                # ★★★ 修正ここまで ★★★
            else:
                logger.info(f"項目 '{found_item_name}' の処理後、データフレームが空になったためスキップします。")

        return dataframes_dict, sort_df_text

    except json.JSONDecodeError:
        raise ValueError("LLMの回答がJSON形式として正しくありません。")
    except Exception as e:
        raise e

# --- プロンプト生成関数 ---
def return_prompt1(query, keys):
    return f"""
あなたは金融の専門知識を持つ、優秀なデータ抽出AIアシスタントです。後続のプログラムで自動処理を行うため、指示に厳密に従って回答してください。
## あなたのタスク
ユーザーの質問内容を分析し、「有価証券報告書の項目一覧」の中から関連性が高い項目名を最大で10個程度選び出し、JSON配列形式で出力してください。
## 厳守すべきルール
1.  回答は **JSON形式の配列（リスト）** のみとしてください。
2.  項目名は「有価証券報告書の項目一覧」に記載されているものと **完全に一致** させてください。
3.  回答は純粋なJSON配列のみとし、解説や前後の文章、および ```json や ``` といったMarkdownのコードブロックマーカーを絶対に含めないでください。
---
## ユーザーの質問
{query}
---
## 有価証券報告書の項目一覧
{keys}
---
## 出力形式の例
["項目名A", "項目名B", "項目名C"]
"""

def prompt_for_strategies(query, sort_df_text, rejected_strategies=None, user_feedback=None):
    """分析方針を提案させるためのプロンプト (V2から移植)"""
    rejected_text = ""
    if rejected_strategies:
        rejected_text += "\n##【重要】ユーザーが却下した過去の提案\n"
        rejected_text += "以下の提案はユーザーの意図と合わなかったため、これらとは**異なる視点**で、全く新しい提案をしてください。\n"
        for strategy in rejected_strategies:
            rejected_text += f"- {strategy['title']}: {strategy['description']}\n"
        rejected_text += "---\n"

    feedback_text = ""
    if user_feedback:
        feedback_text += "\n##【最重要】ユーザーからの追加の要望\n"
        feedback_text += "以下の要望を最優先で考慮し、全く新しい提案をしてください。\n"
        feedback_text += f"- {user_feedback}\n"
        feedback_text += "---\n"

    return f"""
あなたは優秀な金融データアナリストです。ユーザーの質問と利用可能なデータ概要を基に、これから行うべき分析の選択肢を提案してください。
## あなたのタスク
ユーザーの質問に答えるための、具体的な分析方針を3～5個提案してください。各方針は、どのデータ（DataFrame）を使い、どのような処理を行うかを明確に記述してください。
提案した分析方針をユーザーが選択し、その方法に従いLLMが処理を行います。
処理する際に材料となるデータが多いほうが正確な分析をすることができます。

## 厳守すべきルール
1.  回答は必ずJSON形式のみで出力してください。解説やMarkdownマーカーは不要です。
2.  JSONのルート要素は "strategies" というキーを持つオブジェクトとします。
3.  "strategies" の値は、各方針を表すオブジェクトの配列（リスト）です。
4.  各方針オブジェクトは、`id` (int), `title` (str), `description` (str) の3つのキーを持ってください。
5.  `description` には、どのDataFrame（`DataFrame... dict key:...`のキー名）を使うかを必ず明記してください。
{rejected_text}
{feedback_text}
---
## ユーザーの質問
{query}
---
## 提供されるデータの概要
{sort_df_text}
---
## 出力形式の例
{{
  "strategies": [
    {{ "id": 1, "title": "単一指標でのランキング", "description": "「売上高、経営指標等」の'当期'の数値を使用して、企業を降順にソートし、上位企業を抽出します。" }},
    {{ "id": 2, "title": "計算指標による評価", "description": "「売上高、経営指標等」と「営業利益又は営業損失（△）」を銘柄コードでマージし、売上高営業利益率を算出してランキングします。" }}
  ]
}}
---
"""

def prompt_for_code(query, sort_df_text, selected_strategy):
    return f"""
あなたは、金融ドメインに精通した超一流のPythonプログラマーです。後続のプログラムで自動処理を行うため、以下の指示に**絶対的に、かつ厳密に**従ってください。
## あなたのタスク
ユーザーの質問、提供データ、そしてユーザーが選択した「分析方針」に基づき、最終的な結果を出力するPythonコードを生成してください。生成するコードは、外部から提供される `dataframes_dict` という辞書を処理するものです。
「分析方針」に基づき処理を行いますが、ユーザーの質問に対応することが最重要事項です。
処理を行い大量のデータからユーザーが必要としているデータに抽出・加工することが目的です。
抽出されたデータは再度優秀なAIが分析を行いますのでデータの内容がわかるよう、工夫してください。
のちに別のAIに作成された最終dfのマークダウンとユーザーの質問が渡され対応するようになります。
そのため、dfに必要な情報を集約するようにしてください。
再度分析がされますのでユーザーの質問にAIが幅広く回答できるようにdfの情報はある程度多くても構いません。

## 厳守すべきルール
1.  回答は **Pythonコードのみ** とし、解説やMarkdownマーカー(```)を絶対に含めないでください。
2.  **【最重要】絶対に、いかなる理由があっても、コード内にダミーの `dataframes_dict` や `pd.DataFrame` をハードコーディングで定義しないでください。**
3.  **【最重要】`dataframes_dict` からDataFrameを選択する際は、「提供されるデータの概要」に記載されているキー名（`DataFrame... dict key:...`のキー名）を、一字一句違わずに完全にコピーして使用してください。**
4.  **最終的な結果は、`result_df` という名前のPandas DataFrame変数に必ず格納してください。**
5.  コードは堅牢にしてください。`re`, `pandas`, `numpy` は自由にインポートして構いません。
6.  列を数値に変換する際は `pd.to_numeric(df['列名'], errors='coerce')` を使用してください。
7.  DataFrameをマージする際は、`pd.merge(df1, df2, on=['銘柄コード', '銘柄名'], how='inner')` のように、銘柄コードと銘柄名をキーにしてください。
8.  最終的にDataFrameのカラム名を分かりやすいものに変更してください。（例：売上高_当期）
---
## ユーザーの質問
{query}
---
## ユーザーが選択した分析方針
{selected_strategy}
---
## 提供されるデータの概要
{sort_df_text}
---
"""

def return_result_df(llm_code_raw, dataframes_dict):
    """LLMが生成したPythonコードを実行し、結果のDataFrameを返す"""
    final_result_df = None
    cleaned_code = llm_code_raw.strip().removeprefix('```python').removesuffix('```').strip()
    if not cleaned_code:
        raise ValueError("LLMから空のコードが返されました。")
    try:
        exec_globals = {'dataframes_dict': dataframes_dict, 'pd': pd, 'np': np, 're': re}
        exec(cleaned_code, exec_globals)
        if 'result_df' in exec_globals and isinstance(exec_globals.get('result_df'), pd.DataFrame):
            final_result_df = exec_globals['result_df']
        else:
            logger.warning("実行結果のDataFrame ('result_df') は生成されませんでした。")
        return final_result_df, cleaned_code
    except Exception as e:
        logger.error(f"LLMが生成したコードの実行中にエラーが発生しました: {e}\n--- 生成されたコード ---\n{cleaned_code}\n--------------------")
        traceback.print_exc()
        raise type(e)(f"コード実行時エラー: {e}\n\n--- 実行コード ---\n{cleaned_code}") from e

def prompt_for_final_analysis(query: str, df_markdown: str) -> str:
    """最終的なDataFrameを基に分析レポートを生成させるためのプロンプト"""
    return f"""
あなたは、プロの金融アナリストです。提供されたデータ（DataFrame）とユーザーの元の質問に基づき、洞察に満ちた分析レポートを作成してください。

## あなたのタスク
1. ユーザーの質問の意図を正確に把握してください。
2. 提供されたDataFrameの内容を分析し、質問に答えるための重要なポイントを特定してください。
3. 分析結果、結論、そして補足情報（例えば、データの限界や次の分析への提案など）を、分かりやすく構造化されたマークダウン形式で記述してください。

## 厳守すべきルール
- 必ずマークダウン形式で回答してください。見出し、リスト、太字などを効果的に使用し、読みやすいレポートを作成してください。
- 結論は明確に記述してください。
- 数値を引用する際は、正確に記述してください。
- 専門用語には簡単な注釈を加えることが望ましいです。

---
## ユーザーの元の質問
{query}

---
## 分析対象データ (Markdown形式)
{df_markdown}
---
"""

# --- Streamlit ページレンダリング関数 ---
def render_page(sm: StateManager, fm: FileManager, akm, active_model: str):
    st.title("ステップ10: EDINET高度分析 (LLM活用)")
    st.markdown("EDINETの項目別データとLLMを活用し、自由な質問に基づいたデータ抽出・分析を行います。")

    # --- 初期データロード ---
    if sm.get_value(KEY_ES_ITEM_DF) is None:
        with st.spinner("分析用のマスターデータを読み込んでいます..."):
            try:
                df, _, err = fm.load_csv('item_df')
                if err: raise FileNotFoundError(err)

                # ★★★ エラー修正: '項目名' カラムの存在チェックを追加 ★★★
                if '項目名' not in df.columns:
                    logger.error(f"item_df.csv に '項目名' カラムが見つかりません。現在のカラム: {list(df.columns)}")
                    raise ValueError(f"item_index.csv に '項目名' カラムが見つかりません。ファイルの内容を確認してください。現在のカラムリスト: {list(df.columns)}")

                sm.set_value(KEY_ES_ITEM_DF, df)

                main_keys_list = []
                # '銘柄数' カラムがあればそれに基づきフィルタリング
                if '銘柄数' in df.columns:
                    df['銘柄数'] = pd.to_numeric(df['銘柄数'], errors='coerce')
                    # 2000以上の企業で報告されている一般的な項目に絞る
                    filtered_df = df[df['銘柄数'] >= 2000].copy() # SettingWithCopyWarning を避けるために .copy() を追加
                    main_keys_list = list(sorted(str(item) for item in filtered_df['項目名'].unique()))
                else:
                    st.warning("item_df.csvに'銘柄数'カラムが見つかりません。全ての項目をLLMの選択対象とします。")
                    main_keys_list = list(sorted(str(item) for item in df['項目名'].unique()))

                sm.set_value(KEY_ES_MAIN_KEYS, main_keys_list)
                # ★★★ 修正ここまで ★★★

                json_bytes = fm.get_file_bytes("stock_name_map")
                stock_map = json.loads(json_bytes.decode('utf-8'))
                sm.set_value(KEY_ES_STOCK_NAME_MAP, stock_map)

            except Exception as e:
                st.error(f"初期データの読み込みに失敗しました: {e}")
                logger.error(f"EDINET Sort Page: 初期データ読み込みエラー: {e}", exc_info=True)
                return

    # --- UI要素 ---
    st.markdown("---")
    st.subheader("1. 分析したい内容を質問してください")
    default_query = "営業利益が高い企業はどこですか？上位10社をリストアップしてください。"
    query = st.text_area(
        "質問内容:",
        value=sm.get_value(KEY_ES_QUERY, default_query),
        height=100,
        key=KEY_ES_QUERY
    )

    if st.button("分析を開始", type="primary", use_container_width=True):
        keys_to_reset = [
            KEY_ES_PROCESSING_STATUS, KEY_ES_LLM_ITEM_SUGGESTIONS_RAW,
            KEY_ES_DATAFRAMES_DICT, KEY_ES_SORT_DF_TEXT, KEY_ES_STRATEGIES_RAW,
            KEY_ES_SELECTED_STRATEGIES, KEY_ES_GENERATED_CODE, KEY_ES_RESULT_DF,
            KEY_ES_ERROR_MESSAGE, KEY_ES_REJECTED_STRATEGIES, KEY_ES_USER_FEEDBACK,
            KEY_ES_LLM_CODE_RAW,
            KEY_ES_FINAL_ANALYSIS_RESULT, KEY_ES_FINAL_ANALYSIS_RUNNING,
        ]
        for key in keys_to_reset:
            sm.set_value(key, None)

        if not query.strip():
            st.warning("質問内容を入力してください。")
            return

        sm.set_value(KEY_ES_PROCESSING_STATUS, "step1_started")
        st.rerun()

    # --- ステータスに基づいた処理の実行 ---
    status = sm.get_value(KEY_ES_PROCESSING_STATUS)
    error_message = sm.get_value(KEY_ES_ERROR_MESSAGE)
    if error_message:
        st.error(error_message)
        sm.set_value(KEY_ES_PROCESSING_STATUS, "error")

    if status == "step1_started":
        with st.spinner("[ステップ1/5] LLMに関連項目を問い合わせています..."):
            try:
                main_keys = sm.get_value(KEY_ES_MAIN_KEYS)
                if not main_keys: raise ValueError("分析対象の項目リストが空です。")
                prompt1 = return_prompt1(query, main_keys)
                llm_answer_raw = api_services.generate_gemini_response(prompt1, app_config.AVAILABLE_FLASH_LITE_MODEL)
                if llm_answer_raw.startswith("[LLM エラー]"): raise ValueError(llm_answer_raw)
                sm.set_value(KEY_ES_LLM_ITEM_SUGGESTIONS_RAW, llm_answer_raw)
                sm.set_value(KEY_ES_PROCESSING_STATUS, "step2_started")
                st.rerun()
            except Exception as e:
                sm.set_value(KEY_ES_ERROR_MESSAGE, f"[ステップ1 エラー] {e}")
                st.rerun()

    if status == "step2_started":
        with st.spinner("[ステップ2/5] 関連DataFrameを生成・要約しています..."):
            try:
                llm_answer_raw = sm.get_value(KEY_ES_LLM_ITEM_SUGGESTIONS_RAW)
                item_df = sm.get_value(KEY_ES_ITEM_DF)
                stock_name_map = sm.get_value(KEY_ES_STOCK_NAME_MAP)

                period_map = {
                    'CurrentYearDuration': '当期', 'CurrentYearInstant': '当期時点',
                    'Prior1YearDuration': '前期', 'Prior1YearInstant': '前期時点',
                    'Prior2YearDuration': '2期前', 'Prior2YearInstant': '2期前時点',
                    'Prior3YearDuration': '3期前', 'Prior3YearInstant': '3期前時点',
                    'Prior4YearDuration': '4期前', 'Prior4YearInstant': '4期前時点',
                    'Prior5YearDuration': '5期前', 'Prior5YearInstant': '5期前時点',
                    'FilingDateInstant': '提出日時点',
                }

                dataframes_dict, sort_df_text = create_dfs(llm_answer_raw, item_df, fm, stock_name_map, period_map)
                sm.set_value(KEY_ES_DATAFRAMES_DICT, dataframes_dict)
                sm.set_value(KEY_ES_SORT_DF_TEXT, sort_df_text)
                sm.set_value(KEY_ES_PROCESSING_STATUS, "step3_started")
                st.rerun()
            except Exception as e:
                sm.set_value(KEY_ES_ERROR_MESSAGE, f"[ステップ2 エラー] {e}")
                st.rerun()

    if status == "step3_started":
        with st.spinner("[ステップ3/5] LLMに分析方針の提案を依頼しています..."):
            try:
                sort_df_text = sm.get_value(KEY_ES_SORT_DF_TEXT)
                if not sort_df_text: raise ValueError("分析対象のデータ概要がありません。")
                rejected = sm.get_value(KEY_ES_REJECTED_STRATEGIES)
                feedback = sm.get_value(KEY_ES_USER_FEEDBACK)
                prompt_str = prompt_for_strategies(query, sort_df_text, rejected, feedback)
                strategies_raw = api_services.generate_gemini_response(prompt_str, app_config.AVAILABLE_FLASH_MODEL)
                if strategies_raw.startswith("[LLM エラー]"): raise ValueError(strategies_raw)
                sm.set_value(KEY_ES_STRATEGIES_RAW, strategies_raw)
                sm.set_value(KEY_ES_PROCESSING_STATUS, "step3_completed")
                st.rerun()
            except Exception as e:
                sm.set_value(KEY_ES_ERROR_MESSAGE, f"[ステップ3 エラー] {e}")
                st.rerun()

    if status and status.startswith("step3_completed"):
        st.markdown("---")
        st.subheader("2. 生成されたデータと分析方針")

        # ★★★ 修正: llm_answer_raw のデバッグ表示を追加 ★★★
        with st.expander("デバッグ情報: LLMからの項目提案（生データ）"):
            llm_item_suggestions_raw = sm.get_value(KEY_ES_LLM_ITEM_SUGGESTIONS_RAW)
            if llm_item_suggestions_raw:
                st.code(llm_item_suggestions_raw, language="json")
            else:
                st.info("LLMからの項目提案データがありません。")

        with st.expander("LLMが抽出した関連データフレームの一覧", expanded=False):
            dataframes_dict_display = sm.get_value(KEY_ES_DATAFRAMES_DICT)
            if dataframes_dict_display:
                for df_name, df_obj in dataframes_dict_display.items():
                    st.markdown(f"**項目: `{df_name}`**")
                    st.dataframe(df_obj.head(3))
            else:
                st.info("プレビュー対象のデータフレームが生成されませんでした。")

        strategies_raw_display = sm.get_value(KEY_ES_STRATEGIES_RAW)
        if strategies_raw_display:
            try:
                cleaned_json = strategies_raw_display.strip().removeprefix('```json').removesuffix('```').strip()
                strategies_data = json.loads(cleaned_json)
                strategies_list = strategies_data.get("strategies", [])

                with st.form("strategy_selection_form"):
                    st.markdown("**分析方法を選択してください（複数選択可、実行は最初の1つ）:**")
                    selected_strategies_map = {}
                    for strategy in strategies_list:
                        is_checked = st.checkbox(
                            f"**{strategy['title']}**: {strategy['description']}",
                            key=f"strategy_{strategy['id']}"
                        )
                        if is_checked:
                            selected_strategies_map[strategy['id']] = strategy

                    st.markdown("---")
                    st.markdown("提案が意図と違う場合:")
                    user_feedback_input = st.text_area("追加の要望や修正点を入力してください（任意）", key="user_feedback_for_reprompt")

                    col1, col2 = st.columns(2)
                    with col1:
                        submit_button = st.form_submit_button("選択した方法で分析コードを生成", use_container_width=True)
                    with col2:
                        reprompt_button = st.form_submit_button("入力した要望を基に再提案を依頼", use_container_width=True)

                    if submit_button:
                        if not selected_strategies_map:
                            st.warning("少なくとも1つの分析方法を選択してください。")
                        else:
                            sm.set_value(KEY_ES_SELECTED_STRATEGIES, list(selected_strategies_map.values()))
                            sm.set_value(KEY_ES_PROCESSING_STATUS, "step4_started")
                            st.rerun()

                    if reprompt_button:
                        current_rejected = sm.get_value(KEY_ES_REJECTED_STRATEGIES, [])
                        current_rejected.extend(strategies_list)
                        sm.set_value(KEY_ES_REJECTED_STRATEGIES, current_rejected)
                        sm.set_value(KEY_ES_USER_FEEDBACK, user_feedback_input)
                        sm.set_value(KEY_ES_PROCESSING_STATUS, "step3_started") # 再提案のためステップ3に戻す
                        st.rerun()

            except Exception as e:
                st.error(f"分析方針の表示中にエラー: {e}")
                st.text(strategies_raw_display)

    if status == "step4_started":
        with st.spinner("[ステップ4/5] 選択された方針に基づき、LLMが分析コードを生成・実行します..."):
            try:
                selected_strategies = sm.get_value(KEY_ES_SELECTED_STRATEGIES)
                if not selected_strategies:
                    raise ValueError("分析方針が選択されていません。")

                # 複数選択されていても、最初のものを使用する
                first_strategy = selected_strategies[0]
                strategy_info = f"タイトル: {first_strategy['title']}, 詳細: {first_strategy['description']}"

                sort_df_text = sm.get_value(KEY_ES_SORT_DF_TEXT)
                code_prompt = prompt_for_code(query, sort_df_text, strategy_info)
                llm_code_raw = api_services.generate_gemini_response(code_prompt, app_config.AVAILABLE_PRO_MODEL)
                sm.set_value(KEY_ES_LLM_CODE_RAW, llm_code_raw)
                if llm_code_raw.startswith("[LLM エラー]"): raise ValueError(llm_code_raw)

                dataframes_dict = sm.get_value(KEY_ES_DATAFRAMES_DICT)
                result_df, generated_code = return_result_df(llm_code_raw, dataframes_dict)

                sm.set_value(KEY_ES_GENERATED_CODE, generated_code)
                sm.set_value(KEY_ES_RESULT_DF, result_df)
                sm.set_value(KEY_ES_PROCESSING_STATUS, "step5_completed")
                st.rerun()

            except Exception as e:
                sm.set_value(KEY_ES_ERROR_MESSAGE, f"[ステップ4 エラー]\n{e}")
                st.rerun()

    if status == "step5_completed":
        st.markdown("---")
        st.subheader("3. 分析の実行内容と結果")

        with st.expander("実行された分析の詳細"):
            st.markdown("##### 選択された分析方針")
            selected_strategies_display = sm.get_value(KEY_ES_SELECTED_STRATEGIES)
            if selected_strategies_display:
                for strategy in selected_strategies_display:
                    st.markdown(f"- **{strategy['title']}**: {strategy['description']}")
            else:
                st.info("選択された方針の情報がありません。")

            st.markdown("##### 分析の基になったデータ")
            dataframes_dict_display = sm.get_value(KEY_ES_DATAFRAMES_DICT)
            if dataframes_dict_display:
                for df_name, df_obj in dataframes_dict_display.items():
                    st.markdown(f"**項目: `{df_name}`**")
                    st.dataframe(df_obj)
            else:
                st.info("分析の基になったデータフレームがありません。")

            st.markdown("##### LLMが生成したPythonコード")
            generated_code_display = sm.get_value(KEY_ES_GENERATED_CODE)
            if generated_code_display:
                st.code(generated_code_display, language="python")

            st.markdown("##### LLMからの生コード（デバッグ用）")
            llm_code_raw_display = sm.get_value(KEY_ES_LLM_CODE_RAW)
            if llm_code_raw_display:
                st.text(llm_code_raw_display)

        st.markdown("#### 最終分析結果 DataFrame")
        result_df_display = sm.get_value(KEY_ES_RESULT_DF)
        if result_df_display is not None and not result_df_display.empty:
            st.dataframe(result_df_display)

            st.markdown("---")
            st.subheader("4. AIによる追加分析レポート")

            if sm.get_value(KEY_ES_FINAL_ANALYSIS_RESULT) is None:
                if st.button("この結果をAIに分析させる", type="primary", use_container_width=True):
                    sm.set_value(KEY_ES_FINAL_ANALYSIS_RUNNING, True)
                    st.rerun()

            if sm.get_value(KEY_ES_FINAL_ANALYSIS_RUNNING):
                with st.spinner("AIアナリストが分析レポートを生成中です..."):
                    try:
                        df_markdown = result_df_display.to_markdown()
                        final_prompt = prompt_for_final_analysis(query, df_markdown)
                        analysis_result = api_services.generate_gemini_response(final_prompt, active_model)

                        if analysis_result.startswith("[LLM エラー]"):
                            raise ValueError(analysis_result)

                        sm.set_value(KEY_ES_FINAL_ANALYSIS_RESULT, analysis_result)
                        sm.set_value(KEY_ES_FINAL_ANALYSIS_RUNNING, False)
                        st.rerun()

                    except Exception as e:
                        st.error(f"AIによる分析中にエラーが発生しました: {e}")
                        logger.error(f"Final analysis failed: {e}", exc_info=True)
                        sm.set_value(KEY_ES_FINAL_ANALYSIS_RUNNING, False)

            final_analysis_result = sm.get_value(KEY_ES_FINAL_ANALYSIS_RESULT)
            if final_analysis_result:
                st.markdown(final_analysis_result)

        elif result_df_display is not None:
            st.info("分析結果は空でした。")
        else:
            st.warning("分析結果のDataFrameは生成されませんでした。")

    # --- ナビゲーション ---
    st.markdown("---")
    col_back, _ = st.columns(2)
    with col_back:
        if st.button("戻る (ステップ9: EDINETビューアへ)", key="edinet_sort_back_to_s9", use_container_width=True):
            sm.set_value("app.current_step", 9)
            st.rerun()
