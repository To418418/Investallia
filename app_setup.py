# app_setup.py

import streamlit as st
import logging
import os
import sys
import urllib.request
import json
import datetime # ★ datetimeモジュールをインポート
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed # ★ 並列処理のために追加

# config.py は main.py と同じ階層にあると仮定
# このファイルの先頭で config をインポートする
try:
    import config # アプリケーション全体のconfig
    from state_manager import StateManager # StateManager は main と同じ階層
    from file_manager import FileManager   # FileManager は main と同じ階層
    import api_services # api_services は Gemini API 設定などで直接参照される
except ImportError as e:
    logging.basicConfig(level=logging.CRITICAL) # loggingがまだ設定されていない可能性を考慮
    logging.critical(f"app_setup.py: Failed to import core dependencies (config, StateManager, etc.). Error: {e}")
    if 'streamlit' in sys.modules: # stが使えるか確認
        st.error("app_setup.py: Critical import error. Check logs.")
    raise

# --- Logging Setup ---
def setup_logging():
    """アプリケーション全体のロギングを設定します。"""
    if not logging.getLogger().hasHandlers(): # ハンドラがまだ設定されていなければ設定
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(module)s.%(funcName)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(__name__) # このモジュール用のロガーを取得
    logger.info("app_setup.py: Logging configured.")
    return logger

# --- sys.path Configuration ---
def configure_sys_path():
    """
    アプリケーションのルートディレクトリと必要なサブディレクトリ (stock_chart_app) を
    Pythonのモジュール検索パス (sys.path) に追加します。
    """
    logger_sys_path = logging.getLogger(__name__ + ".configure_sys_path")
    try:
        current_app_setup_dir = os.path.dirname(os.path.abspath(__file__))
        project_root_dir = current_app_setup_dir

        if project_root_dir not in sys.path:
            sys.path.insert(0, project_root_dir)
            logger_sys_path.info(f"[SysPath Setup] Added project root to sys.path: {project_root_dir}")

        stock_chart_app_dir = os.path.join(project_root_dir, "stock_chart_app")

        if os.path.isdir(stock_chart_app_dir) and stock_chart_app_dir not in sys.path:
            sys.path.insert(0, stock_chart_app_dir)
            logger_sys_path.info(f"[SysPath Setup] Added stock_chart_app to sys.path: {stock_chart_app_dir}")
        elif not os.path.isdir(stock_chart_app_dir):
            logger_sys_path.warning(f"[SysPath Setup] stock_chart_app directory not found at: {stock_chart_app_dir}")

    except Exception as e:
        logger_sys_path.critical(f"[SysPath Setup] Unexpected error during sys.path setup: {e}", exc_info=True)


# --- Google Cloud Secret Manager (Cloud Run 環境用) ---
if config.IS_CLOUD_RUN:
    try:
        from google.cloud import secretmanager
        logger_gcp_secret = logging.getLogger(__name__ + ".gcp_secret_manager")
        logger_gcp_secret.info("Google Cloud Secret Manager library imported successfully for Cloud Run.")
    except ImportError:
        secretmanager = None
        logging.getLogger(__name__).critical("Google Cloud Secret Manager library failed to import in Cloud Run environment. Secrets will not be loaded from GCP.")
else:
    secretmanager = None

# --- ApiKeyManager クラス ---
class ApiKeyManager:
    def __init__(self):
        self.keys: Dict[str, Optional[str]] = {}
        self.is_cloud_run: bool = config.IS_CLOUD_RUN
        self.project_id: Optional[str] = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self._keys_loaded: bool = False
        self._logger = logging.getLogger(__name__ + ".ApiKeyManager")

    def _get_project_id_from_metadata_server(self) -> Optional[str]:
        if not self.is_cloud_run: return None
        self._logger.debug("Attempting to get GCP Project ID from metadata server.")
        try:
            req = urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/project/project-id", headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=2) as response:
                project_id = response.read().decode('utf-8')
                self._logger.info(f"Successfully retrieved GCP Project ID from metadata server: {project_id}")
                return project_id
        except Exception as e:
            self._logger.warning(f"Failed to get GCP Project ID from metadata server: {e}. Will fallback to GOOGLE_CLOUD_PROJECT env var if set.")
            return os.environ.get("GOOGLE_CLOUD_PROJECT")

    def _get_secret_from_gcp(self, secret_id_in_gcp: str, version_id: str = "latest") -> Optional[str]:
        if not self.is_cloud_run or not self.project_id or secretmanager is None:
            self._logger.debug(f"Skipping GCP secret fetch for '{secret_id_in_gcp}': Not Cloud Run, no Project ID, or secretmanager library not available.")
            return None
        if not secret_id_in_gcp or not isinstance(secret_id_in_gcp, str) or any(ph in secret_id_in_gcp for ph in ["YOUR_", "_PLACEHOLDER"]):
            self._logger.warning(f"Skipping GCP secret fetch for invalid or placeholder secret_id: '{secret_id_in_gcp}'")
            return None
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.project_id}/secrets/{secret_id_in_gcp}/versions/{version_id}"
            self._logger.info(f"Accessing GCP secret: {name}")
            response = client.access_secret_version(request={"name": name})
            secret_value = response.payload.data.decode("UTF-8")
            self._logger.info(f"Successfully fetched GCP secret: '{secret_id_in_gcp}' (version: {version_id})")
            return secret_value
        except Exception as e:
            self._logger.error(f"Failed to fetch GCP secret '{secret_id_in_gcp}': {e}", exc_info=False)
            return None

    # --- ▼▼▼ ここから修正 ▼▼▼ ---
    def load_api_keys(self, key_placeholders_config: Dict[str, str]):
        if self._keys_loaded:
            self._logger.info("API keys already loaded. Skipping reload.")
            return

        self._logger.info(f"Loading API keys in parallel. Environment: {'Cloud Run' if self.is_cloud_run else 'Local/Colab'}")

        if self.is_cloud_run:
            if not self.project_id:
                self.project_id = self._get_project_id_from_metadata_server()

            if self.project_id:
                config.PROJECT_ID = self.project_id
                self._logger.info(f"GCP Project ID set to: {self.project_id}")
                # ThreadPoolExecutorを使用してGCP Secret Managerから並列でキーを取得
                with ThreadPoolExecutor(max_workers=len(key_placeholders_config)) as executor:
                    future_to_key = {
                        executor.submit(self._get_secret_from_gcp, gcp_secret_name): config_key_name
                        for config_key_name, gcp_secret_name in key_placeholders_config.items()
                    }
                    for future in as_completed(future_to_key):
                        config_key_name = future_to_key[future]
                        try:
                            self.keys[config_key_name] = future.result()
                        except Exception as exc:
                            self._logger.error(f"Error fetching secret for '{config_key_name}': {exc}", exc_info=False)
                            self.keys[config_key_name] = None
            else:
                self._logger.error("GCP Project ID could not be determined. API keys from GCP Secret Manager will not be loaded.")
                for config_key_name in key_placeholders_config.keys():
                    self.keys[config_key_name] = None
        else: # Local/Colab
            try:
                # st.secretsはメインスレッドでのアクセスが推奨されるため、先に一括で辞書に読み込む
                secrets_dict = dict(st.secrets)
                self._logger.info("Attempting to load API keys from st.secrets for Local/Colab.")

                for config_key_name, streamlit_secrets_key_name in key_placeholders_config.items():
                    val = secrets_dict.get(streamlit_secrets_key_name)
                    if isinstance(val, str) and any(ph in val for ph in ["YOUR_", "_PLACEHOLDER"]):
                        self._logger.warning(f"API key '{config_key_name}' has placeholder value. Treating as not set.")
                        self.keys[config_key_name] = None
                    else:
                        self.keys[config_key_name] = val
                        if val is not None:
                            self._logger.info(f"API key '{config_key_name}' loaded from st.secrets.")
                        else:
                            self._logger.info(f"API key '{config_key_name}' not found in st.secrets.")
            except Exception as e_st_secrets:
                self._logger.warning(f"st.secrets not available (Error: {e_st_secrets}). API keys will be None.")
                self.keys = {key_name: None for key_name in key_placeholders_config.keys()}

        self._keys_loaded = True
        self._logger.info("API key loading process finished.")
    # --- ▲▲▲ ここまで修正 ▲▲▲ ---

    def get_api_key(self, key_name: str) -> Optional[str]:
        if not self._keys_loaded:
            self.load_api_keys(config.API_KEYS_PLACEHOLDERS)
        val = self.keys.get(key_name)
        if isinstance(val, str) and any(ph in val for ph in ["YOUR_", "_PLACEHOLDER"]):
            return None
        return val

    def get_all_loaded_keys_summary(self) -> Dict[str, str]:
        if not self._keys_loaded:
            self.load_api_keys(config.API_KEYS_PLACEHOLDERS)
        summary = {}
        for key, value in self.keys.items():
            if value and not (isinstance(value, str) and any(ph in value for ph in ["YOUR_", "_PLACEHOLDER"])):
                summary[key] = "設定済"
            else:
                summary[key] = "未設定/プレースホルダ"
        return summary

# --- Initialization Functions ---
def initialize_global_managers(sm_instance: StateManager, fm_instance: FileManager):
    logger_init = logging.getLogger(__name__ + ".initialize_global_managers")
    logger_init.info("Initializing global managers and session states.")

    initialization_flag_key = "app.managers_initialized_flag_v5"

    if not sm_instance.get_value(initialization_flag_key, False):
        logger_init.info(f"Running initialization for flag: {initialization_flag_key}")
        initial_states_map = {
            "app.current_step": 0,
            "app.selected_model_in_ui": config.DEFAULT_FLASH_MODEL,
            "app.active_gemini_model": config.DEFAULT_FLASH_MODEL,
            "app.pro_model_unlocked": False,
            "app.selected_stock_code": None,
            "app.selected_stock_name": None,
            "app.global_stock_just_changed_flag": False,
            "ui.stock_search_query_input": "",
            "ui.stock_search_query_user_entered": "",
            "ui.stock_search_candidates": [],
            "ui.stock_search_message": "銘柄名またはコードを入力してください。",
            "ui.clear_search_input_flag": False,
            "tech_analysis.start_date": (datetime.date.today() - datetime.timedelta(days=365)),
            "tech_analysis.end_date": (datetime.date.today() - datetime.timedelta(days=1)),
            "tech_analysis.interval": "1d",
            "tech_analysis.selected_indicator_keys": [],
            "tech_analysis.indicator_params_values": {},
            "tech_analysis.show_chart_button_clicked": False,
            "tech_analysis.current_chart_json": None,
            "tech_analysis.ai_analysis_result": None,
            "tech_analysis.indicator_labels_for_ai": {},
        }
        for key, value in initial_states_map.items():
            if sm_instance.get_value(key) is None:
                sm_instance.set_value(key, value)
                logger_init.debug(f"StateManager: Initialized '{key}'")

        sm_instance.set_value(initialization_flag_key, True)
        logger_init.info(f"StateManager core initial states set (flag: {initialization_flag_key}).")
    else:
        logger_init.info(f"StateManager core initial states already set (checked by {initialization_flag_key}).")

    # --- (変更) 軽量化された銘柄検索用データのロード ---
    if sm_instance.get_value("data_display.all_stocks_data_loaded") is None:
        # (変更) 'stock_data_all' の代わりに新しいID 'stock_data_searcher' を指定
        logger_init.info("Attempting to load 'stock_data_searcher_light.json' via FileManager.")
        try:
            # (変更) ここで新しいファイルIDを指定して読み込む
            json_bytes = fm_instance.get_file_bytes("stock_data_searcher")
            if json_bytes:
                all_stocks_data: Dict[str, Any] = json.loads(json_bytes.decode('utf-8'))
                sm_instance.set_value("data_display.all_stocks_data_loaded", all_stocks_data)
                logger_init.info(f"'stock_data_searcher_light.json' loaded successfully ({len(all_stocks_data)} items).")
            else:
                logger_init.warning("'stock_data_searcher_light.json' is empty or could not be retrieved. Setting to empty dict.")
                sm_instance.set_value("data_display.all_stocks_data_loaded", {})
        except FileNotFoundError:
            logger_init.error("'stock_data_searcher_light.json' not found (FileNotFoundError). Setting to empty dict.")
            sm_instance.set_value("data_display.all_stocks_data_loaded", {})
        except json.JSONDecodeError:
            logger_init.error("Failed to parse 'stock_data_searcher_light.json' (JSONDecodeError). Setting to empty dict.")
            sm_instance.set_value("data_display.all_stocks_data_loaded", {})
        except Exception as e_load_stock_json:
            logger_init.error(f"Unexpected error loading 'stock_data_searcher_light.json': {e_load_stock_json}", exc_info=True)
            sm_instance.set_value("data_display.all_stocks_data_loaded", {})

    # --- デフォルトグローバル銘柄の設定 (7203 トヨタ自動車) ---
    if sm_instance.get_value("app.selected_stock_code") is None:
        default_code = "7203"
        all_stocks_data_for_default = sm_instance.get_value("data_display.all_stocks_data_loaded", {})

        if isinstance(all_stocks_data_for_default, dict) and default_code in all_stocks_data_for_default:
            stock_info = all_stocks_data_for_default.get(default_code, {})
            if isinstance(stock_info, dict):
                # (変更) 参照する項目を 'Company Name ja' と 'shortName' に合わせる
                default_name_jp = stock_info.get("Company Name ja", stock_info.get("shortName", f"銘柄({default_code})"))
                sm_instance.set_value("app.selected_stock_code", default_code)
                sm_instance.set_value("app.selected_stock_name", default_name_jp)
                logger_init.info(f"Default global stock set: Code={default_code}, Name='{default_name_jp}'")
            else:
                logger_init.warning(f"Default stock code {default_code} info is not a dict.")
        elif not all_stocks_data_for_default:
                 logger_init.warning(f"Cannot set default stock {default_code} because all_stocks_data is empty.")
        else:
                 logger_init.warning(f"Default stock code {default_code} not found in all_stocks_data.")


def load_api_keys_once(akm_instance: ApiKeyManager, sm_instance: StateManager):
    """
    APIキーを一度だけロードし、関連サービスを設定します。
    """
    logger_load_keys = logging.getLogger(__name__ + ".load_api_keys_once")
    logger_load_keys.info("load_api_keys_once called.")

    if not hasattr(akm_instance, '_keys_loaded') or not akm_instance._keys_loaded:
        logger_load_keys.info("Attempting first-time API key loading via ApiKeyManager.")
        if hasattr(config, 'API_KEYS_PLACEHOLDERS') and isinstance(config.API_KEYS_PLACEHOLDERS, dict):
            akm_instance.load_api_keys(config.API_KEYS_PLACEHOLDERS)
        else:
            logger_load_keys.error("config.API_KEYS_PLACEHOLDERS is missing or invalid. API keys cannot be loaded.")
            return

        gemini_api_key_val = akm_instance.get_api_key("GEMINI_API_KEY")
        if gemini_api_key_val:
            api_services.configure_gemini_api(gemini_api_key_val)
            logger_load_keys.info("Gemini API configured successfully.")
        else:
            logger_load_keys.warning("Gemini API key not retrieved. Gemini API services may not function.")
            api_services.configure_gemini_api(None)

        tts_json_str = akm_instance.get_api_key("GOOGLE_TTS_CREDENTIALS_JSON_STR")
        if tts_json_str:
            sm_instance.set_value("app.tts_json_str_for_recreation", tts_json_str)
            logger_load_keys.info("Google TTS credentials stored in StateManager.")
        else:
            logger_load_keys.warning("Google TTS credentials not retrieved.")
            sm_instance.set_value("app.tts_json_str_for_recreation", None)

        logger_load_keys.info("Attempting to populate stock_chart_app.config_tech.")
        try:
            from stock_chart_app import config_tech as tech_config_module
            tech_config_module.GEMINI_API_KEY = gemini_api_key_val
            tech_config_module.PRO_MODEL_UNLOCK_PASSWORD = akm_instance.get_api_key("PRO_MODEL_UNLOCK_PASSWORD")
            tech_config_module.DEFAULT_FLASH_MODEL_TECH = config.DEFAULT_FLASH_MODEL
            tech_config_module.DEFAULT_PRO_MODEL_TECH = config.DEFAULT_PRO_MODEL
            tech_config_module.IS_CLOUD_RUN_TECH = config.IS_CLOUD_RUN
            tech_config_module.IS_COLAB_TECH = not config.IS_CLOUD_RUN
            logger_load_keys.info("Successfully populated stock_chart_app.config_tech.")
        except ImportError:
            logger_load_keys.error("Failed to import stock_chart_app.config_tech. Ensure sys.path is correct.")
        except Exception as e_populate_tech_config:
            logger_load_keys.error(f"Error populating stock_chart_app.config_tech: {e_populate_tech_config}", exc_info=True)
        logger_load_keys.info("First-time API key loading and configuration process completed.")
    else:
        logger_load_keys.info("API keys and related configurations were already loaded/performed in this session.")
