# config.py
import os

# --- 環境判別 ---
IS_CLOUD_RUN = os.getenv('K_SERVICE') is not None

# --- APIキープレースホルダー ---
# アプリ内部で使用するキー名 (左辺) と、
# GCP Secret Manager 上のシークレット名またはローカルのsecrets.tomlのキー名 (右辺) を対応させます。
# Cloud Run環境では、右辺はGCP Secret Managerのシークレット名と一致させる必要があります。
API_KEYS_PLACEHOLDERS = {
    "NEWS_API_KEY": "NEWS_API_KEY",
    "GEMINI_API_KEY": "GEMINI_API_KEY",
    "GOOGLE_CSE_API_KEY": "GOOGLE_CSE_API_KEY",
    "GOOGLE_CSE_ID": "GOOGLE_CSE_ID",
    "BRAVE_API_KEY": "BRAVE_API_KEY",
    "GNEWS_API_KEY": "GNEWS_API_KEY",
    "PRO_MODEL_UNLOCK_PASSWORD": "PRO_MODEL_UNLOCK_PASSWORD",
    "GOOGLE_TTS_CREDENTIALS_JSON_STR": "GOOGLE_TTS_CREDENTIALS_JSON_STR",
    "TAVILY_API_KEY": "TAVILY_API_KEY",
    "BING_API_KEY": "BING_API_KEY",
}

# --- モデル設定 ---
# 利用可能なモデルの定義 (ユーザー要望に応じて3つに)
AVAILABLE_FLASH_LITE_MODEL = 'gemini-2.0-flash-lite'
AVAILABLE_FLASH_MODEL = 'gemini-2.5-flash-preview-05-20'
AVAILABLE_PRO_MODEL = 'gemini-2.5-pro-preview-06-05'

# アプリケーションのデフォルトとして使用されるモデル (UIの初期選択や内部ロジック用)
# 元の変数名は他のモジュールとの互換性のため維持します
DEFAULT_FLASH_MODEL = AVAILABLE_FLASH_LITE_MODEL # UIの初期選択など
DEFAULT_PRO_MODEL = AVAILABLE_PRO_MODEL      # パスワードが必要なモデル


# --- 定数 ---
ROWS_PER_PAGE_TRADE_HISTORY = 50
INITIAL_ROWS_TO_SHOW_TRADE_HISTORY = 5
INITIAL_ROWS_TO_SHOW_EDINET = 20 # EDINETデータ表示用

# --- GCS設定 (Cloud Run環境用) ---
GCS_BUCKET_NAME = 'run-sources-gcp-hackathon-project01-asia-northeast1' # ご自身のバケット名

# --- ファイルメタデータ ---
FILE_METADATA = {
    "persona_analyst": {
        "description": "アナリストのペルソナ設定ファイル",
        "type": "text",
        "encoding": "utf-8",
        "path_colab": "DefaultData/persona_Analyst.txt",
        "path_gcs_blob": "MaterialData/DefaultData/persona_Analyst.txt"
    },
    "persona_fp": {
        "description": "FPのペルソナ設定ファイル",
        "type": "text",
        "encoding": "utf-8",
        "path_colab": "DefaultData/persona_FP.txt",
        "path_gcs_blob": "MaterialData/DefaultData/persona_FP.txt"
    },
    "persona_professor": {
        "description": "大学教授のペルソナ設定ファイル",
        "type": "text",
        "encoding": "utf-8",
        "path_colab": "DefaultData/persona_Professor.txt",
        "path_gcs_blob": "MaterialData/DefaultData/persona_Professor.txt"
    },
    "persona_junior": {
        "description": "後輩女子のペルソナ設定ファイル",
        "type": "text",
        "encoding": "utf-8",
        "path_colab": "DefaultData/persona_junior_girl.txt",
        "path_gcs_blob": "MaterialData/DefaultData/persona_junior_girl.txt"
    },
    "choicedata_dir": {
        "description": "様々なキャラクターのペルソナが格納されるディレクトリのパス",
        "type": "dir",
        "path_colab": "ChoiceData/",
        "path_gcs_blob": "MaterialData/ChoiceData/"
    },
    "default_trade_history": {
        "description": "デフォルトの取引履歴CSVファイル",
        "type": "csv",
        "encoding_options": ['utf-8', 'utf-8-sig', 'cp932', 'shift_jis', 'euc-jp'],
        "path_colab": "DefaultData/trade_01.csv",
        "path_gcs_blob": "MaterialData/DefaultData/trade_01.csv",
        "expected_columns": ["ID", "約定日", "銘柄", "数量", "単価", "売買"]
    },
    "google_tts_credentials": {
        "description": "Google TTS APIの認証情報JSON (文字列として取得)",
        "type": "json_string_secret",
        "secret_id_gcp": API_KEYS_PLACEHOLDERS["GOOGLE_TTS_CREDENTIALS_JSON_STR"],
        "secret_key_st": API_KEYS_PLACEHOLDERS["GOOGLE_TTS_CREDENTIALS_JSON_STR"]
    },
    "stock_data_all": {
        "description": "全銘柄情報を含むJSONファイル",
        "type": "json_bytes", # FileManagerでバイトとして読み込むため
        "path_colab": "DefaultData/stock_data_all.json",
        "path_gcs_blob": "MaterialData/DefaultData/stock_data_all.json"
    },
    "edinet_zip_dir": {
        "description": "EDINETからダウンロードした有価証券報告書のzipファイルが格納されているディレクトリのパス",
        "type": "dir",
        "path_colab": "DefaultData/EdinetData/",
        "path_gcs_blob": "MaterialData/EdinetData/"
    },
    "listed_company_summary": {
        "description": "EDINET提出文書サマリーCSVファイル (例: listed_company_1y_summary.csv)",
        "type": "csv",
        "encoding_options": ['utf-8', 'utf-8-sig', 'cp932', 'shift_jis'],
        "path_colab": "DefaultData/EdinetData/listed_company_1y_summary.csv",
        "path_gcs_blob": "MaterialData/EdinetData/listed_company_1y_summary.csv"
    },
    # --- ▼▼▼ edinet_sort_page.py用に以下を定義・確認 ▼▼▼ ---
    "edinet_separate_dir": {
        "description": "EDINETからダウンロードした有価証券報告書の項目別JSONファイルが保存されているディレクトリ",
        "type": "dir",
        "path_colab": "DefaultData/EdinetSeparateData/",
        "path_gcs_blob": "MaterialData/EdinetSeparateData/"
    },
    "item_df": {
        "description": "EDINETの有価証券報告書の項目名と保存パス等の一覧ファイル（csv）",
        "type": "csv",
        "encoding_options": ['utf-8', 'utf-8-sig', 'cp932', 'shift_jis'],
        "path_colab": "DefaultData/item_index.csv",
        "path_gcs_blob": "MaterialData/DefaultData/item_index.csv"
    },
    "stock_name_map": {
        "description": "銘柄コードと銘柄名の一覧のJSONファイル",
        "type": "json_bytes",
        "path_colab": "DefaultData/stock_name_map.json",
        "path_gcs_blob": "MaterialData/DefaultData/stock_name_map.json"
    },
   "stock_data_searcher": {
        "description": "銘柄検索用の軽量JSONファイル",
        "type": "json_bytes",
        "path_colab": "DefaultData/stock_data_searcher_light.json",
        "path_gcs_blob": "MaterialData/DefaultData/stock_data_searcher_light.json"
    },
    # --- ▲▲▲ 追加・確認ここまで ▲▲▲ ---
}

# --- ニュースサービス関連設定 ---
NEWS_SERVICE_CONFIG = {
    "active_apis": {
        "newsapi": True, "gnews": False, "brave": False, "tavily": False,
        "google_cse": True, "bing": False,
    },
    "max_news_per_api": 10, "duplicate_title_prefix_length": 10,
    "api_request_delay": 0.5, "cache_expiry_hours": 6,
    "cache_dir_colab": "news_cache_colab", "cache_dir_gcs_prefix": "news_cache/"
}

# --- 初期データ (ポートフォリオページ用) ---
# グローバル銘柄管理に移行したため、ここでの個別銘柄設定は削除
INITIAL_PORTFOLIO_DATA = {
    "balance_df": [
        {"項目": "預貯金", "金額(万円)": 200}, {"項目": "有価証券", "金額(万円)": 800},
        {"項目": "暗号資産", "金額(万円)": 200}, {"項目": "年金", "金額(万円)": 500}
    ],
    "stock_df": [
        {"銘柄": "トヨタ自動車", "証券コード": "7203", "金額(万円)": 250, "評価損益(万円)": -20},
        {"銘柄": "日立製作所",   "証券コード": "6501", "金額(万円)": 280, "評価損益(万円)": 38},
        {"銘柄": "ソニーグループ", "証券コード": "6758", "金額(万円)": 270, "評価損益(万円)": 34}
    ],
}

# --- Cloud RunプロジェクトID (main.pyのApiKeyManagerで設定される) ---
PROJECT_ID = None


