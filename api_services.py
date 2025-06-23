# api_services.py
import streamlit as st
import google.generativeai as genai
import pandas as pd
import yfinance as yf
import re
import logging

logger = logging.getLogger(__name__)

# --- Gemini API 関連 ---
_gemini_api_key_configured = False # モジュールレベルで設定状態を保持
_gemini_api_key_value = None # 設定されたAPIキーを保持（デバッグ用）


def configure_gemini_api(api_key: str | None): # Noneも許容するように型ヒント修正
    """Gemini APIキーを設定する。アプリケーション起動時に一度だけ呼ばれることを想定。"""
    global _gemini_api_key_configured, _gemini_api_key_value
    _gemini_api_key_value = api_key # 渡されたキーをまず保持

    if not api_key:
        logger.warning("Gemini APIキーが提供されていません (Noneまたは空)。設定できません。")
        _gemini_api_key_configured = False
        return
    if not isinstance(api_key, str) or api_key.strip() == "" or \
       any(ph_part in api_key for ph_part in ["YOUR_", "_PLACEHOLDER", "_SECRET_ID_OR_PLACEHOLDER"]):
        logger.error(f"提供されたGemini APIキーが無効またはプレースホルダーです: '{api_key[:10]}...'")
        _gemini_api_key_configured = False
        return

    try:
        genai.configure(api_key=api_key)
        _gemini_api_key_configured = True
        logger.info("Gemini APIキーが正常に設定され、クライアントが初期化されました。")
    except Exception as e:
        logger.error(f"Gemini APIキーの設定中にエラーが発生しました: {e}", exc_info=True)
        _gemini_api_key_configured = False

def is_gemini_api_configured() -> bool:
    """Gemini APIが設定済みかどうかを返す"""
    return _gemini_api_key_configured

def generate_gemini_response(prompt_text: str, model_name: str, temperature: float | None = None) -> str:
    """
    指定されたプロンプトとモデル名でGemini APIから応答を生成する。
    APIキーは事前に configure_gemini_api で設定されている必要がある。

    Args:
        prompt_text (str): LLMへのプロンプト。
        model_name (str): 使用するGeminiモデル名 (例: 'gemini-1.5-flash-latest')。
        temperature (float | None, optional): 生成の多様性を制御する温度。
                                               0.0に近いほど決定的、1.0に近いほど多様。
                                               Noneの場合はAPIのデフォルト値が使用される。

    Returns:
        str: LLMからの応答テキスト、またはエラーメッセージ。
    """
    if not _gemini_api_key_configured:
        err_msg = "[LLM エラー] Gemini APIキーが正しく設定されていません。"
        if _gemini_api_key_value is None:
            err_msg += " APIキーが取得できていないか、Noneです。"
        elif isinstance(_gemini_api_key_value, str) and \
             any(ph_part in _gemini_api_key_value for ph_part in ["YOUR_", "_PLACEHOLDER", "_SECRET_ID_OR_PLACEHOLDER"]):
            err_msg += f" APIキーがプレースホルダーのまま ('{_gemini_api_key_value[:10]}...') のようです。"
        else:
            err_msg += " 初期設定に失敗した可能性があります。ログを確認してください。"
        logger.error(err_msg + " (generate_gemini_response呼び出し時点)")
        return err_msg

    if not model_name:
        logger.error("Geminiモデル名が指定されていません。")
        return "[LLM エラー] 使用するGeminiモデル名が指定されていません。"

    logger.info(f"Gemini APIにリクエスト送信開始 (モデル: {model_name}, 温度: {temperature})。プロンプト(先頭100字): {prompt_text[:100]}...")
    try:
        model = genai.GenerativeModel(model_name)

        generation_config = None
        if temperature is not None:
            generation_config = genai.types.GenerationConfig(temperature=temperature)
            logger.info(f"GenerationConfigを使用: temperature={temperature}")

        response = model.generate_content(
            prompt_text,
            generation_config=generation_config
        )

        if hasattr(response, 'text') and response.text:
            logger.info(f"Gemini APIから応答受信成功 (モデル: {model_name})。")
            return response.text
        elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            logger.info(f"Gemini APIから応答受信成功 (候補パーツから結合, モデル: {model_name})。")
            return "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
        else:
            logger.warning(f"Gemini APIからの応答が空か、予期しない形式です (モデル: {model_name})。Response: {response}")
            return "[LLM エラー] 応答内容が空か、予期しない形式です。"

    except Exception as e:
        error_message = str(e)
        if hasattr(e, 'message') and e.message:
                 error_message = e.message
        logger.error(f"Gemini APIリクエスト中にエラーが発生しました (モデル: {model_name}): {error_message}", exc_info=True)
        return f"[LLM エラー] Gemini APIリクエスト中にエラーが発生しました (モデル: {model_name}): {error_message}"


# --- yfinance API 関連 ---
@st.cache_data(ttl=1800)
def get_ticker_financial_data(ticker_code_input: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict | None, str | None]:
    ticker_code_processed = ""
    try:
        normalized_ticker = str(ticker_code_input).strip().upper()

        if re.fullmatch(r"^[0-9]{4}$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][0-9]{2}[A-Z]$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][A-Z][0-9]{2}$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][A-Z][0-9][A-Z]$", normalized_ticker):
            if not normalized_ticker.endswith(".T"):
                ticker_code_processed = f"{normalized_ticker}.T"
            else:
                ticker_code_processed = normalized_ticker
        else:
            ticker_code_processed = normalized_ticker

        logger.info(f"yfinanceデータ取得開始: 元コード '{ticker_code_input}', 処理後コード '{ticker_code_processed}'")

        if not ticker_code_processed:
            err_msg = f"ティッカーコードの処理に失敗しました: '{ticker_code_input}'"
            logger.error(err_msg)
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, err_msg

        ticker = yf.Ticker(ticker_code_processed)
        info = ticker.info

        if not info or not info.get('symbol'):
            if ticker_code_processed.endswith(".T"):
                ticker_code_no_t = ticker_code_processed[:-2]
                logger.info(f"基本情報(info)取得失敗、'.T'なしでリトライ: {ticker_code_no_t}")
                ticker_retry = yf.Ticker(ticker_code_no_t)
                info_retry = ticker_retry.info
                if info_retry and info_retry.get('symbol'):
                    ticker = ticker_retry
                    info = info_retry
                    ticker_code_processed = ticker_code_no_t
                    logger.info(f"'.T'なしでのリトライ成功: {ticker_code_no_t}")
                else:
                    err_msg = f"ティッカー '{ticker_code_processed}' および '{ticker_code_no_t}' の基本情報(info)が見つかりません。"
                    logger.warning(err_msg)
                    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, err_msg
            else:
                err_msg = f"ティッカー '{ticker_code_processed}' の基本情報(info)が見つかりません。"
                logger.warning(err_msg)
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, err_msg

        financials_df = ticker.financials if hasattr(ticker, 'financials') and ticker.financials is not None else pd.DataFrame()
        quarterly_financials_df = ticker.quarterly_financials if hasattr(ticker, 'quarterly_financials') and ticker.quarterly_financials is not None else pd.DataFrame()

        dividends_data = ticker.dividends if hasattr(ticker, 'dividends') else None
        dividends_df = dividends_data.reset_index() if dividends_data is not None and not dividends_data.empty else pd.DataFrame()

        earnings_dates_data = ticker.earnings_dates if hasattr(ticker, 'earnings_dates') else None
        earnings_dates_df = earnings_dates_data.reset_index() if earnings_dates_data is not None and not earnings_dates_data.empty else pd.DataFrame()

        recommendations_data = ticker.recommendations if hasattr(ticker, 'recommendations') else None
        recommendations_df = recommendations_data.reset_index() if recommendations_data is not None and not recommendations_data.empty else pd.DataFrame()

        logger.info(f"yfinanceデータ取得成功: {ticker_code_processed}")
        return financials_df, quarterly_financials_df, dividends_df, earnings_dates_df, recommendations_df, info, None

    except Exception as e:
        err_msg = f"yfinanceで '{ticker_code_processed if ticker_code_processed else ticker_code_input}' のデータ取得中にエラー: {e}"
        logger.error(err_msg, exc_info=True)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, err_msg

@st.cache_data(ttl=1800)
def get_stock_price_history(ticker_code_input: str, period: str = "1y", interval: str = "1mo") -> tuple[pd.DataFrame | None, str | None]:
    ticker_code_processed = ""
    try:
        normalized_ticker = str(ticker_code_input).strip().upper()
        if re.fullmatch(r"^[0-9]{4}$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][0-9]{2}[A-Z]$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][A-Z][0-9]{2}$", normalized_ticker) or \
           re.fullmatch(r"^[1-9][A-Z][0-9][A-Z]$", normalized_ticker):
            if not normalized_ticker.endswith(".T"):
                ticker_code_processed = f"{normalized_ticker}.T"
            else:
                ticker_code_processed = normalized_ticker
        else:
            ticker_code_processed = normalized_ticker

        logger.info(f"yfinance株価履歴取得開始: {ticker_code_processed} (period: {period}, interval: {interval})")
        ticker = yf.Ticker(ticker_code_processed)
        hist_df = ticker.history(period=period, interval=interval)

        if hist_df.empty:
            logger.warning(f"株価履歴データ(history)が空です: {ticker_code_processed}")
            if ticker_code_processed.endswith(".T"):
                ticker_code_no_t = ticker_code_processed[:-2]
                logger.info(f"株価履歴取得、'.T'なしでリトライ: {ticker_code_no_t}")
                ticker_retry = yf.Ticker(ticker_code_no_t)
                hist_df_retry = ticker_retry.history(period=period, interval=interval)
                if not hist_df_retry.empty:
                    logger.info(f"'.T'なしでの株価履歴取得成功: {ticker_code_no_t}")
                    return hist_df_retry, None
                else:
                    logger.warning(f"'.T'なしでの株価履歴も空: {ticker_code_no_t}")
            return None, f"ティッカー '{ticker_code_processed}' の株価履歴データが見つかりません。"

        logger.info(f"yfinance株価履歴取得成功: {ticker_code_processed}")
        return hist_df, None

    except Exception as e:
        err_msg = f"yfinanceで '{ticker_code_processed if ticker_code_processed else ticker_code_input}' の株価履歴取得中にエラー: {e}"
        logger.error(err_msg, exc_info=True)
        return None, err_msg
