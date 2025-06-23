# stock_utils.py
import pandas as pd
import json
import os
import logging

logger = logging.getLogger(__name__)

def create_dictionary_from_json(json_path: str) -> dict:
    """
    指定されたパスのJSONファイルを読み込み、辞書として返します。
    ファイルが見つからない場合は空の辞書を返し、エラーをログに記録します。
    """
    if not os.path.exists(json_path):
        logger.error(f"JSONファイルが見つかりません: {json_path}")
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"JSONファイルを正常に読み込みました: {json_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSONファイルのデコードエラー: {json_path}, エラー: {e}")
        return {}
    except Exception as e:
        logger.error(f"JSONファイルの読み込み中に予期せぬエラー: {json_path}, エラー: {e}")
        return {}


def create_market_cap_df_from_json_dict(all_stocks_data: dict) -> pd.DataFrame:
    """
    全銘柄データ辞書から時価総額DataFrameを作成します。
    'コード' 列はサフィックスなしの文字列として格納されます。
    """
    market_cap_list = []
    if not all_stocks_data or not isinstance(all_stocks_data, dict):
        logger.warning("create_market_cap_df_from_json_dict: 入力データが空または辞書型ではありません。")
        return pd.DataFrame()

    logger.info(f"入力された全銘柄データ数: {len(all_stocks_data)} 件。これからDataFrameを作成します。")

    processed_codes = 0
    for code, stock_data in all_stocks_data.items():
        if not isinstance(stock_data, dict):
            logger.warning(f"銘柄コード '{code}' のデータが辞書型ではありません。スキップします。型: {type(stock_data)}")
            continue

        # 銘柄名の取得 (優先順位: Company Name ja -> shortName -> Company Name -> 名称不明)
        name = stock_data.get('Company Name ja')
        if not name: name = stock_data.get('shortName') # yfinance の info() に近いキー
        if not name: name = stock_data.get('Company Name') # 英語名の場合もある
        if not name and 'profile' in stock_data and isinstance(stock_data['profile'], dict): # 詳細プロファイルからのフォールバック
            name = stock_data['profile'].get('longName')
        if not name:
            name = f"名称不明({code})"
            logger.debug(f"銘柄コード '{code}' の企業名が見つかりません。'{name}'として処理します。")

        # 時価総額の取得と変換
        market_cap_raw = stock_data.get('marketCap')
        market_cap_oku = None
        if market_cap_raw is not None:
            try:
                market_cap_oku = round(float(market_cap_raw) / 100000000, 2)
            except (ValueError, TypeError):
                logger.debug(f"銘柄コード '{code}' の時価総額 '{market_cap_raw}' を数値に変換できません。Noneとして扱います。")
        else:
            logger.debug(f"銘柄コード '{code}' に 'marketCap' キーが存在しません。時価総額はNoneとなります。")

        # --- ▼▼▼ 要望に基づきセクター情報取得ロジックを修正 ▼▼▼ ---
        # セクター情報の取得 (優先順位: 33業種 -> 17業種 -> 規模区分)
        sector = stock_data.get('33 Sector Classification ja') # 1. 33業種区分
        if not sector: sector = stock_data.get('17 Sector Classification ja') # 2. 17業種区分
        if not sector: sector = stock_data.get('Size Classification ja') # 3. 規模区分
        if not sector:
            sector = "業種不明"
            logger.debug(f"銘柄コード '{code}' のセクター情報が見つかりません。'{sector}'として処理します。")
        # --- ▲▲▲ 修正ここまで ▲▲▲ ---

        market_cap_list.append({
            'コード': str(code),
            'セクター': str(sector), # 文字列型に統一
            '銘柄名': str(name),   # 文字列型に統一
            '時価総額(億円)': market_cap_oku
        })
        processed_codes += 1

    if not market_cap_list and all_stocks_data:
        logger.warning(f"入力データは {len(all_stocks_data)} 件ありましたが、処理可能なデータがなくmarket_cap_listが空です。JSONのキー名を確認してください。")

    market_cap_df = pd.DataFrame(market_cap_list)

    if not market_cap_df.empty:
        logger.info(f"時価総額DataFrameの作成完了。{len(market_cap_df)}件（処理対象{processed_codes}件中）の銘柄データを処理。")
    elif all_stocks_data : # データはあったがDFが空
        logger.warning("入力データはありましたが、market_cap_df が空になりました。JSONの構造とキー名（'33 Sector Classification ja'など）を確認してください。")
    else: # 元データも空
        logger.info("入力データが空だったため、market_cap_df も空です。")
    return market_cap_df


def get_similar_companies(df: pd.DataFrame, target_code: str, num_neighbors_per_side: int = 2) -> pd.DataFrame:
    """
    指定された銘柄コードに基づき、同業種で時価総額が近い企業（対象企業自身も含む）を抽出する関数。
    """
    if df.empty:
        logger.warning("get_similar_companies: 入力DataFrameが空です。")
        return pd.DataFrame()
    required_cols = ['コード', 'セクター', '銘柄名', '時価総額(億円)']
    if not all(col in df.columns for col in required_cols):
        logger.error(f"get_similar_companies: DataFrameに必要な列 {required_cols} がありません。現在の列: {df.columns.tolist()}")
        return pd.DataFrame()

    df['コード'] = df['コード'].astype(str) # コード列を文字列型に統一
    target_code = str(target_code) # 比較のためこちらも文字列型に

    target_company_info_series = df[df['コード'] == target_code]
    if target_company_info_series.empty:
        logger.warning(f"銘柄コード '{target_code}' がDataFrame内に見つかりません。")
        return pd.DataFrame()

    target_company_info_df = target_company_info_series.copy()
    target_company_info = target_company_info_df.iloc[0]
    target_sector = target_company_info['セクター']
    raw_market_cap = target_company_info['時価総額(億円)']

    if pd.isna(target_sector) or target_sector == "業種不明" or not target_sector: # セクターが不明や欠損の場合
        logger.warning(f"対象企業 '{target_code}' のセクター情報が「{target_sector}」のため、同業種比較は行えません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)
    if pd.isna(raw_market_cap):
        logger.warning(f"対象企業 '{target_code}' の時価総額が欠損しています。類似企業は検索できません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)

    try:
        target_market_cap_value = float(raw_market_cap)
    except ValueError:
        logger.warning(f"対象企業 '{target_code}' の時価総額 '{raw_market_cap}' が有効な数値ではありません。類似企業は検索できません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)

    target_company_info_df.loc[:, '時価総額(億円)'] = target_market_cap_value

    sector_companies = df[df['セクター'] == target_sector].copy()
    if sector_companies.empty:
        logger.warning(f"対象企業 '{target_code}' と同業種の企業が見つかりません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)

    sector_companies.loc[:, '時価総額(億円)'] = pd.to_numeric(sector_companies['時価総額(億円)'], errors='coerce')
    sector_companies.dropna(subset=['時価総額(億円)'], inplace=True)

    if str(target_code) not in sector_companies['コード'].values:
        # 対象企業がフィルタリングで消えた場合、再度追加する（時価総額がNaNでなければ）
        if not pd.isna(target_market_cap_value):
            logger.info(f"対象企業 '{target_code}' がフィルタリングで除外されたため、再追加します。")
            sector_companies = pd.concat([sector_companies, target_company_info_df], ignore_index=True).drop_duplicates(subset=['コード'], keep='first')
        else: # 時価総額がNaNなら追加できない
            logger.warning(f"対象企業 '{target_code}' は有効な時価総額がなく、類似企業検索から除外されます。対象企業のみ返します。")
            return target_company_info_df.reset_index(drop=True)


    if sector_companies.empty:
        logger.warning(f"セクター '{target_sector}' の企業で有効な時価総額を持つものがありません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)

    sorted_sector_companies = sector_companies.sort_values(by='時価総額(億円)', ascending=True).reset_index(drop=True)

    try:
        target_idx = sorted_sector_companies[sorted_sector_companies['コード'] == target_code].index[0]
    except IndexError:
        logger.error(f"致命的エラー: 対象企業 '{target_code}' がソート後のリストに見つかりません。対象企業のみ返します。")
        return target_company_info_df.reset_index(drop=True)

    num_companies_in_sector = len(sorted_sector_companies)

    # ... (以降の類似企業抽出ロジックは前回同様、ここでは省略) ...
    similar_companies_dfs_list = []
    if num_companies_in_sector <= 1:
        logger.info(f"セクター '{target_sector}' には対象企業 '{target_code}' しか有効な時価総額を持つ企業がいません。")
    else:
        num_others_to_fetch = 2 * num_neighbors_per_side
        available_above = target_idx
        available_below = num_companies_in_sector - 1 - target_idx
        num_to_take_above = min(available_above, num_neighbors_per_side)
        num_to_take_below = min(available_below, num_neighbors_per_side)
        remaining_needed_for_total = num_others_to_fetch - (num_to_take_above + num_to_take_below)
        if remaining_needed_for_total > 0:
            can_add_more_below = available_below - num_to_take_below
            add_to_below = min(remaining_needed_for_total, can_add_more_below)
            num_to_take_below += add_to_below
            remaining_needed_for_total -= add_to_below
        if remaining_needed_for_total > 0:
            can_add_more_above = available_above - num_to_take_above
            add_to_above = min(remaining_needed_for_total, can_add_more_above)
            num_to_take_above += add_to_above
        if num_to_take_above > 0:
            above_df = sorted_sector_companies.iloc[max(0, target_idx - num_to_take_above) : target_idx]
            if not above_df.empty: similar_companies_dfs_list.append(above_df)
        if num_to_take_below > 0:
            below_df = sorted_sector_companies.iloc[target_idx + 1 : min(num_companies_in_sector, target_idx + 1 + num_to_take_below)]
            if not below_df.empty: similar_companies_dfs_list.append(below_df)

    all_results_list = [target_company_info_df.copy()]
    if similar_companies_dfs_list:
        all_results_list.extend([df.copy() for df in similar_companies_dfs_list])

    final_df = pd.concat(all_results_list).drop_duplicates(subset=['コード'], keep='first')
    final_df = final_df.sort_values(by='時価総額(億円)', ascending=False).reset_index(drop=True)

    logger.info(f"銘柄 '{target_code}' の類似企業として {len(final_df)} 件を抽出しました (自身を含む)。")
    return final_df
