# stock_searcher.py
import unicodedata
import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """
    入力テキストを正規化する関数。
    - 全角英数字記号を半角に変換
    - 大文字を小文字に変換
    """
    if not isinstance(text, str): # textがNoneや他の型の場合を考慮
        return ""
    try:
        # NFKC正規化（互換文字などを標準的な文字に変換し、全角英数字などを半角に）
        normalized = unicodedata.normalize('NFKC', text)
        return normalized.lower() # 小文字に統一
    except Exception as e:
        logger.error(f"Error normalizing text '{text}': {e}")
        return str(text).lower() # エラー時は元のテキストを小文字化して返す

def search_stocks_by_query(query: str, stocks_data_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    株式を検索する関数。stock_data_all.json の形式に合わせて調整。

    Args:
        query (str): ユーザーからの検索クエリ。
        stocks_data_dict (Dict[str, Dict[str, Any]]): 全株式データ。
            キーが銘柄コード、値が銘柄情報（'Company Name ja', 'shortName' を含む辞書）。
            例: {"7203": {"Company Name ja": "トヨタ自動車", "shortName": "Toyota Motor", ...}, ...}

    Returns:
        dict: 検索結果。以下のいずれかのキーを持つ。
              'confirmed_stock': 銘柄が確定した場合、その銘柄情報 (コード、日本語名、英語名)。
              'candidates': 複数の候補が見つかった場合、候補のリスト [(コード, 表示名), ...] 。
              'not_found': 見つからなかった場合 True。
              'reason': 確定または候補が見つかった理由。
    """
    normalized_query = normalize_text(query)
    logger.debug(f"Normalized query: '{normalized_query}' from original: '{query}'")

    if not normalized_query:
        return {"not_found": True, "reason": "入力が空です。"}

    # stock_data_dict が辞書であることを確認
    if not isinstance(stocks_data_dict, dict):
        logger.error(f"stocks_data_dict is not a dictionary, but {type(stocks_data_dict)}")
        return {"not_found": True, "reason": "銘柄データが不正です。"}

    # 準備: 検索しやすいように銘柄データのリストを作成
    # 各要素は {'code': str, 'name_jp': str, 'name_en': str, 'original_data': dict}
    searchable_stocks_list = []
    for code, stock_info in stocks_data_dict.items():
        if not isinstance(stock_info, dict):
            logger.warning(f"Skipping invalid stock_info for code {code}: {stock_info}")
            continue
        name_jp = stock_info.get("Company Name ja", "")
        name_en = stock_info.get("shortName", stock_info.get("Company Name en", "")) # shortName優先、なければCompany Name en

        # 英語名がNoneや空文字列の場合のフォールバック
        if not name_en and "Company Name" in stock_info: # "Company Name" が英語名の場合があるため
             name_en = stock_info.get("Company Name", "")

        searchable_stocks_list.append({
            "code": str(code), # コードは文字列として扱う
            "name_jp": str(name_jp),
            "name_en": str(name_en),
            "original_data": stock_info # 元のデータも保持しておく
        })

    # 1. 銘柄コードによる完全一致検索 (数字4桁を想定)
    if re.fullmatch(r'\d{4}', normalized_query):
        logger.debug(f"Attempting code exact match for: {normalized_query}")
        for stock in searchable_stocks_list:
            if normalized_query == stock['code']:
                logger.info(f"Code exact match found: {stock['code']}")
                return {
                    "confirmed_stock": {
                        "code": stock['code'],
                        "name_jp": stock['name_jp'],
                        "name_en": stock['name_en'],
                        "original": stock['original_data']
                    },
                    "reason": f"銘柄コード '{query}' に完全一致しました。"
                }

    # 2. 正式名称による完全一致検索 (日本語名、英語名)
    logger.debug(f"Attempting name exact match for: {normalized_query}")
    for stock in searchable_stocks_list:
        if normalized_query == normalize_text(stock['name_jp']):
            logger.info(f"Japanese name exact match found: {stock['name_jp']}")
            return {
                "confirmed_stock": {
                    "code": stock['code'],
                    "name_jp": stock['name_jp'],
                    "name_en": stock['name_en'],
                    "original": stock['original_data']
                },
                "reason": f"日本語名 '{stock['name_jp']}' に完全一致しました。"
            }
        if stock['name_en'] and normalized_query == normalize_text(stock['name_en']): # 英語名が存在する場合のみ
            logger.info(f"English name exact match found: {stock['name_en']}")
            return {
                "confirmed_stock": {
                    "code": stock['code'],
                    "name_jp": stock['name_jp'],
                    "name_en": stock['name_en'],
                    "original": stock['original_data']
                },
                "reason": f"英語名 '{stock['name_en']}' に完全一致しました。"
            }

    # 3. 部分一致検索 (日本語名、英語名、銘柄コード)
    logger.debug(f"Attempting partial match for: {normalized_query}")
    partial_match_candidates = []
    for stock in searchable_stocks_list:
        # 日本語名での部分一致
        if stock['name_jp'] and normalized_query in normalize_text(stock['name_jp']):
            partial_match_candidates.append(stock)
            continue
        # 英語名での部分一致
        if stock['name_en'] and normalized_query in normalize_text(stock['name_en']):
            partial_match_candidates.append(stock)
            continue
        # 銘柄コードでの部分一致 (前方一致など)
        if normalized_query in stock['code']:
            partial_match_candidates.append(stock)
            continue

    # 重複を削除 (同じ銘柄が複数回追加される可能性のため)
    # code を基準に重複を排除
    unique_candidates_dict = {candidate['code']: candidate for candidate in partial_match_candidates}
    partial_match_candidates = list(unique_candidates_dict.values())


    if len(partial_match_candidates) == 1:
        stock = partial_match_candidates[0]
        logger.info(f"Single partial match found: {stock['code']}")
        return {
            "confirmed_stock": {
                "code": stock['code'],
                "name_jp": stock['name_jp'],
                "name_en": stock['name_en'],
                "original": stock['original_data']
            },
            "reason": f"'{query}' に部分一致する銘柄が1件見つかりました。"
        }
    elif len(partial_match_candidates) > 1:
        logger.info(f"Multiple partial matches found: {len(partial_match_candidates)}")
        # selectbox用に (code, "表示名 (コード)") のリストを作成
        candidates_for_selectbox = []
        for stock in sorted(partial_match_candidates, key=lambda s: (s['name_jp'] or '', s['code'])): # 日本語名、コードでソート
            display_name = f"{stock['name_jp'] or 'N/A'} ({stock['name_en'] or 'N/A'}) - {stock['code']}"
            candidates_for_selectbox.append(
                {
                    "code": stock['code'],
                    "name_jp": stock['name_jp'],
                    "name_en": stock['name_en'],
                    "display_text": display_name,
                    "original": stock['original_data']
                }
            )
        return {
            "candidates": candidates_for_selectbox,
            "reason": f"'{query}' に部分一致する銘柄が複数見つかりました。"
        }

    # 4. コード検索を再度試みる (完全一致、数字4桁以外の場合)
    #    例えば "7203.T" のような入力や、上記のコード完全一致でヒットしなかった場合。
    #    normalized_query が直接コードと一致するかどうか。
    logger.debug(f"Attempting alternative code match for: {normalized_query}")
    if not re.fullmatch(r'\d{4}', normalized_query): # 既に数字4桁で試しているので、それ以外
        for stock in searchable_stocks_list:
            if normalized_query == stock['code'].lower(): # 大文字小文字無視でコード比較
                logger.info(f"Alternative code match found: {stock['code']}")
                return {
                    "confirmed_stock": {
                        "code": stock['code'],
                        "name_jp": stock['name_jp'],
                        "name_en": stock['name_en'],
                        "original": stock['original_data']
                    },
                    "reason": f"銘柄コード (代替形式) '{query}' に一致しました。"
                }

    logger.info(f"No match found for query: '{query}' (normalized: '{normalized_query}')")
    return {"not_found": True, "reason": f"'{query}' に一致する銘柄は見つかりませんでした。"}

if __name__ == '__main__':
    # --- テスト用のサンプルデータ ---
    # stock_data_all.json の形式を模倣
    sample_stocks_data = {
        "7203": {"Exchange": "TYO", "Company Name": "TOYOTA MOTOR CORPORATION", "Company Name ja": "トヨタ自動車株式会社", "shortName": "Toyota Motor", "sector": "輸送用機器"},
        "9984": {"Exchange": "TYO", "Company Name": "SoftBank Group Corp.", "Company Name ja": "ソフトバンクグループ株式会社", "shortName": "SoftBank Group", "sector": "情報・通信業"},
        "6501": {"Exchange": "TYO", "Company Name": "Hitachi, Ltd.", "Company Name ja": "株式会社日立製作所", "shortName": "Hitachi", "sector": "電気機器"},
        "9432": {"Exchange": "TYO", "Company Name": "NIPPON TELEGRAPH AND TELEPHONE CORPORATION", "Company Name ja": "日本電信電話株式会社", "shortName": "NTT", "sector": "情報・通信業"},
        "1301": {"Exchange": "TYO", "Company Name": "KYOKUYO CO.,LTD.", "Company Name ja": "株式会社極洋", "shortName": "KYOKUYO", "sector": "水産・農林業"},
        "2502": {"Exchange": "TYO", "Company Name": "ASAHI GROUP HOLDINGS,LTD.", "Company Name ja": "アサヒグループホールディングス株式会社", "shortName": "ASAHI GROUP HD", "sector": "食料品"},
        "8001": {"Exchange": "TYO", "Company Name": "ITOCHU Corporation", "Company Name ja": "伊藤忠商事株式会社", "shortName": "ITOCHU", "sector": "卸売業"},
        "7267": {"Exchange": "TYO", "Company Name": "Honda Motor Co., Ltd.", "Company Name ja": "本田技研工業株式会社", "shortName": "Honda Motor", "sector": "輸送用機器"},
        "invalid": "this is not a dict" # 不正なデータ
    }

    test_queries = [
        "7203", "トヨタ", "softbank", "ｿﾌﾄﾊﾞﾝｸ", "株式会社日立製作所", "Honda", "honda motor",
        "kyokuyo", "asahi", "1301", "９９８４", "いとうちゅう", "RandomQuery", ""
    ]

    print("--- 株式検索テスト ---")
    for q_idx, test_query in enumerate(test_queries):
        print(f"\n[{q_idx+1}] 検索クエリ: '{test_query}'")
        result = search_stocks_by_query(test_query, sample_stocks_data)
        if result.get('confirmed_stock'):
            stock = result['confirmed_stock']
            print(f"  確定銘柄: {stock['name_jp']} ({stock['name_en']}) - {stock['code']}")
            print(f"  理由: {result['reason']}")
        elif result.get('candidates'):
            print(f"  候補 ({len(result['candidates'])}件): {result['reason']}")
            for i, cand_stock_info in enumerate(result['candidates']):
                print(f"    {i+1}: {cand_stock_info['display_text']}")
        elif result.get('not_found'):
            print(f"  結果なし: {result['reason']}")
        else:
            print("  予期せぬ結果")

    print("\n--- エラーケーステスト (不正なデータ) ---")
    error_result = search_stocks_by_query("test", {"7203": "not a dict"})
    print(error_result)

