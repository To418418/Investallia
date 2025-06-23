# stock_chart_app/config_tech.py
import logging

# --- Logger ---
# This logger can be used by other modules within stock_chart_app if needed.
# app.py will get its logger instance from this module after setup.
logger = logging.getLogger(__name__)
# Basic configuration for the logger in case it's used before global setup,
# but global setup in app_setup.py should ideally configure all loggers.
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- API Keys and Configuration Placeholders ---
# These will be populated by app_setup.py using ApiKeyManager at runtime.
# Do not assign default string values here other than None, as they might be
# misinterpreted as actual keys if app_setup.py fails to overwrite them.

GEMINI_API_KEY = None
PRO_MODEL_UNLOCK_PASSWORD = None # Password to unlock the Pro model

# Model names (can be overridden by app_setup.py if needed, but good to have defaults)
# These defaults are aligned with the main config.py to ensure consistency if app_setup fails.
# However, app_setup.py should be the single source of truth for these from main config.
# Fallback values, ideally populated from main config via app_setup.py
DEFAULT_FLASH_MODEL_TECH = 'gemini-2.0-flash-lite' # Specific for tech analysis if needed, or use global
DEFAULT_PRO_MODEL_TECH = 'gemini-2.5-pro-preview-06-05' # Specific for tech analysis if needed, or use global


# --- Environment Flags (populated by app_setup.py) ---
# These help determine behavior if, for example, certain file paths or
# API access methods differ between Cloud Run and local/Colab.
IS_CLOUD_RUN_TECH = False
IS_COLAB_TECH = True # Default assumption if not Cloud Run

# --- Technical Analysis Feature Specific Settings ---
# Example: Default window for SMA, if not provided by user input
# DEFAULT_SMA_WINDOW = 20
# Example: Chart theme preference
# CHART_THEME = 'plotly_dark' # or 'plotly_white', etc.

# Note: The direct import 'from config import ...' has been removed
# to avoid potential path issues and circular dependencies.
# app_setup.py is responsible for providing values from the main config.py
# to this module's variables (GEMINI_API_KEY, etc.).

logger.info("stock_chart_app.config_tech.py loaded. API keys and dynamic configs are pending population by app_setup.py.")

