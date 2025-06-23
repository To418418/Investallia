# main.py
import streamlit as st
import logging
import sys


# --- ▼▼▼ エラー修正対応 (改良版) ▼▼▼ ---
# Python 3.12 で廃止された 'distutils' への依存と、それに伴う TypeError を解決するためのパッチ。
# 'japanize-matplotlib' が 'LooseVersion' オブジェクトと文字列を直接比較しようとしてエラーになる問題に対処します。
try:
    from packaging.version import Version
    import types
    import functools

    # 文字列との比較をサポートするカスタムのVersionクラスを定義
    @functools.total_ordering
    class CustomLooseVersion(Version):
        """
        packaging.version.Version を継承し、文字列との比較を可能にするクラス。
        '<' や '==' などで文字列と比較された場合、その文字列をVersionオブジェクトに変換してから処理する。
        """
        def _compare(self, other, method):
            # 比較対象が文字列の場合、Versionオブジェクトに変換する
            if isinstance(other, str):
                try:
                    other = Version(other)
                except Exception:
                    # 変換できない文字列の場合は、元の動作に任せる
                    return NotImplemented
            # 親クラスの比較メソッドを呼び出す
            return getattr(super(), method)(other)

        # 各比較メソッドをオーバーライド
        def __eq__(self, other):
            return self._compare(other, '__eq__')

        def __lt__(self, other):
            return self._compare(other, '__lt__')

    # 'distutils.version' がまだロードされていなければ、ダミーを作成します。
    if 'distutils.version' not in sys.modules:
        # 'distutils.version' という名前で空のモジュールオブジェクトを作成
        mod = types.ModuleType('distutils.version')
        # 作成したモジュールに、代替となるカスタムの LooseVersion クラスを設定
        mod.LooseVersion = CustomLooseVersion
        # Pythonがモジュールを検索する辞書に登録
        sys.modules['distutils.version'] = mod
        logging.info("Applied a custom patch for 'distutils.version' to support string comparison for japanize-matplotlib.")

except ImportError:
    # 'packaging' ライブラリは通常 streamlit に含まれますが、念のため警告を出します。
    logging.warning(
        "The 'packaging' library is not installed. This may cause issues with libraries like 'japanize-matplotlib' on Python 3.12+. "
        "Please install it using 'pip install packaging'."
    )
except Exception as e:
    logging.error(f"Failed to apply patch for 'distutils.version': {e}", exc_info=True)
# --- ▲▲▲ エラー修正対応完了 ▲▲▲ ---


# --- 初期設定の呼び出し ---
# app_setup.py が logging と sys.path を最初に設定することを期待
import app_setup
app_setup.setup_logging() # ロギングを最初にセットアップ (app_setup内でハンドラ重複チェックあり)
logger = logging.getLogger(__name__) # app_setup後にこのファイルのロガーを取得
logger.info("main.py: Logger initialized after app_setup.setup_logging().")

# sys.pathの設定 (app_setupモジュール内で行われる)
# configure_sys_path は app_setup モジュール読み込み時に自動実行されないため、明示的に呼び出す。
app_setup.configure_sys_path()
logger.info("main.py: sys.path configured via app_setup.configure_sys_path().")

# --- 必須モジュールのインポート (パス設定後) ---
try:
    import config as app_config # アプリケーション全体の設定 (config.py)
    from state_manager import StateManager
    from file_manager import FileManager
    # ui_manager と page_manager は main.py と同じ階層にあることを想定
    import ui_manager
    import page_manager
    logger.info("main.py: Core modules (config, StateManager, FileManager, ui_manager, page_manager) imported successfully.")
except ImportError as e_import_core:
    # logging は app_setup で設定済みのはずなので、ここでの critical は通常表示される
    logger.critical(f"main.py: CRITICAL ERROR - Failed to import one or more core modules: {e_import_core}", exc_info=True)
    # Streamlitが起動していればエラーメッセージを表示試行
    if 'streamlit' in sys.modules and hasattr(st, 'error'):
        st.error(f"アプリケーションの起動に必要なコアモジュールの読み込みに失敗しました: {e_import_core}. ログを確認してください。")
    # この時点で致命的なので、アプリケーションを停止させるか、ユーザーに手動での確認を促す
    raise # 再度例外を発生させてプログラムを停止

# --- Streamlit ページ設定 (セッションで一度だけ実行) ---
# セッションステートにフラグを持たせ、一度だけ実行されるようにする
# フラグ名にバージョンを含めることで、アプリ更新時に再設定を促せる
app_config_flag_key = 'app.page_config_set_flag_main_v3' # バージョンアップ
if app_config_flag_key not in st.session_state:
    try:
        st.set_page_config(
            page_title="投資サポート　AIエージェント",
            page_icon="💹", # 絵文字アイコン
            layout="wide",      # wide レイアウトをデフォルトに
            initial_sidebar_state="expanded", # サイドバーを最初から開く
            menu_items={
                'Get Help': 'https://www.example.com/help', # ヘルプURL（ダミー）
                'Report a bug': "https://www.example.com/bug", # バグ報告URL（ダミー）
                'About': "# 投資サポート　AIエージェント\n## バージョン 3.0.1\nユーザー中心の金融分析プラットフォーム"
            }
        )
        st.session_state[app_config_flag_key] = True # 実行済みフラグを立てる
        logger.info(f"Streamlit page config set successfully (flag: {app_config_flag_key}).")
    except Exception as e_set_page_config:
        logger.error(f"Failed to set Streamlit page config: {e_set_page_config}", exc_info=True)
        # st.error などでユーザーに通知することも検討


def main():
    """
    アプリケーションのメイン実行関数。
    初期化、UI描画、ページルーティングを行う。
    """
    logger.info(f"--- main() execution started. Environment: {'Cloud Run' if app_config.IS_CLOUD_RUN else 'Colab/Local'} ---")

    # --- グローバルマネージャーの初期化 (セッションステートに保存) ---
    # StateManager
    if 'state_manager' not in st.session_state:
        st.session_state.state_manager = StateManager()
        logger.info("StateManager initialized and stored in session_state.")
    sm = st.session_state.state_manager # 短縮名でアクセス

    # FileManager
    if 'file_manager' not in st.session_state:
        st.session_state.file_manager = FileManager(
            file_metadata=app_config.FILE_METADATA, # config.py からファイルメタデータを渡す
            gcs_bucket_name=app_config.GCS_BUCKET_NAME if app_config.IS_CLOUD_RUN else None
        )
        logger.info("FileManager initialized and stored in session_state.")
    fm = st.session_state.file_manager # 短縮名

    # ApiKeyManager (app_setup.py内で生成・初期化されることを期待)
    if 'api_key_manager' not in st.session_state:
        # app_setup.ApiKeyManager() を呼び出してインスタンスを生成し、セッションに保存
        st.session_state.api_key_manager = app_setup.ApiKeyManager()
        logger.info("ApiKeyManager initialized via app_setup.ApiKeyManager() and stored in session_state.")
    akm = st.session_state.api_key_manager # 短縮名

    # --- アプリケーション初期設定 (セッションステート、APIキーロードなど) ---
    # initialize_global_managers は StateManager の初期値を設定
    app_setup.initialize_global_managers(sm, fm) # FileManagerも渡して全銘柄データロードなどを実行
    # load_api_keys_once は APIキーをロードし、関連サービス (Gemini, TTS, stock_chart_app.config_tech) を設定
    app_setup.load_api_keys_once(akm, sm) # StateManagerも渡してTTS認証情報などを保存

    # --- UI描画 ---

    # === グローバル銘柄検索ヘッダーの描画 ===
    # このヘッダーは全てのページの最上部に表示される (ui_manager.py に処理を委譲)
    all_stocks_data_loaded = sm.get_value("data_display.all_stocks_data_loaded")
    if all_stocks_data_loaded is not None: # Noneでないことを確認 (空の辞書も含む)
        if not isinstance(all_stocks_data_loaded, dict):
            logger.error(f"all_stocks_data_loaded is not a dict, but {type(all_stocks_data_loaded)}. Cannot render stock search header.")
            st.error("銘柄データの形式が不正です。検索機能は利用できません。")
        else:
            # ui_manager.render_stock_search_header を呼び出し
            ui_manager.render_stock_search_header(sm, all_stocks_data_loaded)
    else:
        # このケースは通常 initialize_global_managers で空の辞書が設定されるため発生しにくい
        logger.warning("all_stocks_data_loaded is None (should have been initialized by app_setup). Stock search header might not function correctly.")
        st.warning("全銘柄データがロードされていません。銘柄検索は利用できません。")
    # === グローバル銘柄検索ヘッダーの描画 終了 ===


    # サイドバーUIの描画 (ui_manager.py に処理を委譲)
    # サイドバーはナビゲーション、モデル選択、APIキー状況表示などを担当
    ui_manager.render_sidebar(sm, akm, app_config) # app_configモジュール自体を渡す


    # メインコンテンツエリアの描画 (page_manager.py に処理を委譲)
    # StateManagerから現在のステップ番号とアクティブなモデル名を取得
    current_step_for_page = sm.get_value("app.current_step", 0) # デフォルトは0 (ダッシュボード)
    active_gemini_model_for_page = sm.get_value('app.active_gemini_model', app_config.DEFAULT_FLASH_MODEL)

    logger.info(f"Rendering main content for current_step: {current_step_for_page}, active_gemini_model: {active_gemini_model_for_page}")

    # page_manager.render_current_page を呼び出して、選択されたページのコンテンツを描画
    page_manager.render_current_page(current_step_for_page, sm, fm, akm, active_gemini_model_for_page)

    logger.info(f"--- End of main() execution for this Streamlit run. Current 'app.current_step': {sm.get_value('app.current_step')} ---")


if __name__ == '__main__':
    # スクリプトが直接実行された場合にmain()関数を呼び出す
    # (Streamlit アプリでは `streamlit run main.py` のように実行されるため、
    #  このブロックは主に直接的なPython実行やテストの際に意味を持つが、
    #  Streamlit の標準的な慣習として記述されることが多い)
    main()
