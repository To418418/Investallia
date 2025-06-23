# tts_playback_page.py
import streamlit as st
import json
import logging
import os
import tempfile
import re
import datetime
import io
import html
from typing import Tuple, List, Dict, Any

# --- pydubライブラリのインポート ---
try:
    from pydub import AudioSegment
except ImportError:
    st.error("pydubライブラリが必要です。`pip install pydub`を実行してください。")
    AudioSegment = None

# --- Google Cloud Text-to-Speech ライブラリのインポート ---
try:
    from google.cloud import texttospeech
    from google.oauth2 import service_account
except ImportError:
    texttospeech = None
    service_account = None
    logging.warning("google-cloud-texttospeech または google-auth ライブラリがインストールされていません。TTS機能は利用できません。")

# --- プロジェクト内モジュールのインポート ---
import api_services
import config as app_config

logger = logging.getLogger(__name__)

# --- StateManagerで使用するキー ---
KEY_TTS_SELECTED_SOURCE = "tts.selected_source_key"
KEY_TTS_AUDIO_BYTES = "tts.audio_bytes"
KEY_TTS_CLIENT_INIT_ERROR = "tts.client_init_error"
KEY_TTS_SYNTH_ERROR = "tts.synth_error"
KEY_TTS_DEBUG_LOG = "tts.debug_log" # デバッグログ用のキーを追加
DEMO_TEXT_FOR_TTS = "こんにちは。これはAIテキスト読み上げ機能のデモンストレーションです。Google Cloud Text-to-Speechを使用して、音声を生成することができます。まずはLLMで文章を作成してください。"
DEMO_TEXT_KEY = "デモ音声 (固定テキスト)"


def preprocess_text(text: str) -> str:
    """Geminiに渡す前のテキストを前処理します。"""
    logger.info("テキストの前処理を開始します...")
    processed_text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF" u"\U00002600-\U000027BF" u"\U0001F900-\U0001F9FF"
        u"\u200d" "]+",
        flags=re.UNICODE,
    )
    processed_text = emoji_pattern.sub(r'', processed_text)
    processed_text = re.sub(r'\n{2,}', '\n', processed_text)
    logger.info("テキストの前処理が完了しました。")
    return processed_text.strip()


def generate_ssml_fragments(text_content: str, model_to_use: str, previous_error: str = None) -> str | None:
    """
    Geminiを使い、SSMLの断片を生成させます。
    エラーがあった場合は、修正を依頼するプロンプトを追加します。
    """
    if not api_services.is_gemini_api_configured():
        logger.error("Gemini APIが設定されていないため、SSMLを生成できません。")
        return None

    retry_prompt_section = ""
    if previous_error:
        retry_prompt_section = f"""
# 最重要: 再試行の指示
前回の生成結果は以下のエラーで失敗しました。
<error>
{previous_error}
</error>
このエラーを参考にして、問題のある部分を修正したSSMLを再生成してください。特に特殊文字のエスケープやタグの構造に注意してください。
"""

    prompt = f"""
あなたはプロのオーディオドラマ台本作家です。以下の#テキストを分析し、会話の断片をSSML形式で生成してください。
{retry_prompt_section}
# 厳格なルール
1.  **話者の特定**: テキストから登場人物やナレーターを特定します。話者が1人の場合は「ナレーター」とします。
2.  **音声の割り当て**: 特定した各話者に、以下の「利用可能な音声リスト」からユニークな音声を割り当てます。リストの上から順番に使用してください。
3.  **SSML構造**:
    - 各発言は `<p><voice name="...">...</voice></p>` タグで囲ってください。
    - 会話の間に短い間（ま）が必要な場合は、`<break time="500ms"/>` を挿入してください。
4.  **特殊文字のエスケープ（最重要）**: テキスト内に `&`, `<`, `>` の記号が含まれる場合は、それぞれ必ず `&amp;`, `&lt;`, `&gt;` にエスケープしてください。アポストロフィ(')や引用符(")はエスケープしないでください。
5.  **禁止事項**:
    - **絶対に `<speak>` タグで囲まないでください。**
    - `<em>` や `<strong>` などの強調タグは使用しないでください。
    - 出力はSSMLコードの断片のみとし、説明文やマークダウンのマーカーは一切含めないでください。

# 利用可能な音声リスト
- ja-JP-Wavenet-C (男性)
- ja-JP-Wavenet-A (女性)
- ja-JP-Wavenet-D (男性)
- ja-JP-Wavenet-B (女性)
- ja-JP-Standard-A (女性)
- ja-JP-Standard-C (男性)
- ja-JP-Standard-B (女性)
- ja-JP-Standard-D (男性)

# テキスト
{text_content}
"""

    logger.info(f"GeminiにSSMLフラグメントの生成をリクエストします (モデル: {model_to_use}, リトライ: {'Yes' if previous_error else 'No'})...")
    try:
        response_text = api_services.generate_gemini_response(prompt, model_to_use)
        if response_text.startswith("[LLM エラー]"):
            logger.error(f"Geminiからの応答エラー: {response_text}")
            return None

        clean_response = re.sub(r'^```(xml)?\s*|\s*```$', '', response_text.strip())
        final_response = clean_response.replace("&apos;", "'")
        logger.info("SSMLフラグメントの生成に成功しました。")
        return final_response

    except Exception as e:
        logger.error(f"SSMLフラグメントの生成中に予期せぬエラーが発生しました: {e}", exc_info=True)
        return None

def split_ssml_fragments(ssml_fragments: str, chunk_size_limit: int = 4900) -> List[str]:
    """SSMLの断片をAPIの制限内に収まるように分割し、それぞれを<speak>タグで囲みます。"""
    elements = re.findall(r'<p>.*?</p>|<break\s+time="[^"]*"\s*/>', ssml_fragments, re.DOTALL)
    chunks, current_chunk_content = [], ""
    for elem in elements:
        if len(f"<speak>{current_chunk_content}{elem}</speak>".encode('utf-8')) > chunk_size_limit and current_chunk_content:
            chunks.append(f"<speak>{current_chunk_content}</speak>")
            current_chunk_content = elem
        else:
            current_chunk_content += elem
    if current_chunk_content: chunks.append(f"<speak>{current_chunk_content}</speak>")
    return chunks

def text_to_speech_google_cloud(ssml_chunk: str, output_filename: str, tts_client, speaking_rate: float) -> str | None:
    """Google Cloud Text-to-Speech APIを使用して、SSMLチャンクを音声ファイルに変換します。"""
    try:
        synthesis_input = texttospeech.SynthesisInput(ssml=ssml_chunk)
        voice_params = texttospeech.VoiceSelectionParams(language_code="ja-JP")
        # ★★★ 修正: 音声エンコーディングをWAVに変更 ★★★
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16, # MP3からWAVに変更
            speaking_rate=speaking_rate
        )
        response = tts_client.synthesize_speech(request={"input": synthesis_input, "voice": voice_params, "audio_config": audio_config})
        with open(output_filename, "wb") as out:
            out.write(response.audio_content)
        return output_filename
    except Exception as e:
        logger.error(f"TTS音声合成中にエラー: {e}", exc_info=True)
        logger.error(f"エラーが発生したSSMLチャンク: {ssml_chunk}")
        raise e


def synthesize_audio_with_retry(text_content: str, sm, akm, active_model: str, speaking_rate: float) -> Tuple[bytes | None, str | None]:
    """
    テキストから音声合成を行うメイン関数。最大3回のリトライ機能付き。
    """
    if AudioSegment is None: return None, "pydubライブラリがロードされていません。"
    tts_client = get_tts_client(sm, None, akm)
    if not tts_client: return None, sm.get_value(KEY_TTS_CLIENT_INIT_ERROR, "TTSクライアントの初期化に失敗しました。")

    max_retries = 3
    last_error = None
    debug_log = []

    def add_debug_log(message):
        nonlocal debug_log
        log_message = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}"
        debug_log.append(log_message)
        logger.info(log_message)

    add_debug_log("音声合成プロセス開始...")

    with st.spinner("テキストを前処理中..."):
        preprocessed_text = preprocess_text(text_content)
    add_debug_log("テキストの前処理完了。")

    for attempt in range(max_retries):
        add_debug_log(f"--- 試行 {attempt + 1}/{max_retries} ---")

        try:
            with st.spinner(f"AIによるSSML生成中... (試行 {attempt + 1})"):
                generated_fragments = generate_ssml_fragments(preprocessed_text, active_model, previous_error=str(last_error) if last_error else None)

            if not generated_fragments:
                last_error = "SSMLの生成に失敗しました（Geminiからの応答が空です）。"
                add_debug_log(f"エラー: {last_error}")
                continue

            add_debug_log("SSML生成成功。")

            with st.spinner("SSMLをチャンクに分割中..."):
                ssml_chunks = split_ssml_fragments(generated_fragments)
                if not ssml_chunks: ssml_chunks = [f"<speak>{generated_fragments}</speak>"]
            add_debug_log(f"{len(ssml_chunks)}個のチャンクに分割完了。")

            temp_files = []
            synthesis_success = True
            for i, chunk in enumerate(ssml_chunks):
                with st.spinner(f"音声チャンク {i+1}/{len(ssml_chunks)} を合成中..."):
                    # ★★★ 修正: 一時ファイルの拡張子を .wav に変更 ★★★
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_out:
                        temp_filename = tmp_out.name
                    try:
                        result_file = text_to_speech_google_cloud(chunk, temp_filename, tts_client, speaking_rate)
                        temp_files.append(result_file)
                    except Exception as e:
                        last_error = e
                        synthesis_success = False
                        add_debug_log(f"エラー: チャンク{i+1}の合成に失敗 - {e}")
                        add_debug_log(f"問題のSSMLチャンク: {chunk}")
                        break

            if not synthesis_success:
                for f in temp_files:
                    if os.path.exists(f): os.remove(f)
                continue

            add_debug_log("全チャンクの音声合成成功。ファイルを結合中...")
            with st.spinner("音声ファイルを結合中..."):
                combined_audio = AudioSegment.empty()
                for f in temp_files:
                    # ★★★ 修正: from_mp3 を from_wav に変更 ★★★
                    combined_audio += AudioSegment.from_wav(f)

            final_audio_buffer = io.BytesIO()
            # ★★★ 修正: エクスポート形式を wav に変更 ★★★
            combined_audio.export(final_audio_buffer, format="wav")
            add_debug_log("音声合成プロセス完了！")

            sm.set_value(KEY_TTS_DEBUG_LOG, debug_log)
            for f in temp_files:
                if os.path.exists(f): os.remove(f)
            return final_audio_buffer.getvalue(), None

        except Exception as e:
            last_error = e
            add_debug_log(f"エラー: 試行 {attempt + 1} で予期せぬエラー - {e}")

    final_error_message = f"音声合成に失敗しました（{max_retries}回試行）。最後の記録されたエラー: {last_error}"
    add_debug_log(f"最終エラー: {final_error_message}")
    sm.set_value(KEY_TTS_DEBUG_LOG, debug_log)
    return None, final_error_message


def get_tts_client(sm, fm, akm):
    """Google Cloud Text-to-Speech クライアントを初期化して返します。"""
    if texttospeech is None or service_account is None:
        sm.set_value(KEY_TTS_CLIENT_INIT_ERROR, "TTSライブラリがロードされていません。")
        return None
    tts_json_str_raw = sm.get_value("app.tts_json_str_for_recreation")
    if not tts_json_str_raw:
        tts_json_str_raw = akm.get_api_key("GOOGLE_TTS_CREDENTIALS_JSON_STR")
    if not tts_json_str_raw:
        err_msg = "TTS認証情報JSON文字列を取得できませんでした。"
        sm.set_value(KEY_TTS_CLIENT_INIT_ERROR, err_msg)
        return None
    credentials_info = None
    try:
        credentials_info = json.loads(tts_json_str_raw)
    except json.JSONDecodeError as e:
        logger.warning(f"TTS JSONの直接パースに失敗({e})。private_keyの改行をエスケープして再試行します。")
        try:
            pattern = re.compile(r'("private_key":\s*")(.+?)(")', re.DOTALL)
            match = pattern.search(tts_json_str_raw)
            if not match: raise ValueError("JSON文字列内に 'private_key' が見つかりませんでした。")
            key_value = match.group(2)
            escaped_key_value = key_value.replace('\n', '\\n')
            processed_json_str = tts_json_str_raw[:match.start(2)] + escaped_key_value + tts_json_str_raw[match.end(2):]
            credentials_info = json.loads(processed_json_str)
            logger.info("private_keyの改行エスケープによりJSONパース成功。")
        except Exception as inner_e:
            err_msg = f"TTS認証情報の自動修正に失敗しました: {inner_e}"
            sm.set_value(KEY_TTS_CLIENT_INIT_ERROR, err_msg)
            return None
    try:
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = texttospeech.TextToSpeechClient(credentials=credentials)
        sm.set_value(KEY_TTS_CLIENT_INIT_ERROR, None)
        return client
    except Exception as e:
        err_msg = f"認証情報からTTSクライアント作成中にエラー: {e}"
        sm.set_value(KEY_TTS_CLIENT_INIT_ERROR, err_msg)
        return None


def render_page(sm, fm, akm, active_model):
    """AIテキスト読み上げページのUIを描画します。"""
    st.title("🔊 AIテキスト読み上げ（SSML強化・リトライ機能付き）")
    st.markdown("過去にAIが生成したテキストを、Geminiで会話形式に変換し、話者ごとに異なる声で再生します。")

    if not get_tts_client(sm, fm, akm):
        client_init_error = sm.get_value(KEY_TTS_CLIENT_INIT_ERROR, "TTSクライアントの初期化に失敗しました。")
        st.error(f"TTSサービス利用不可: {client_init_error}", icon="🚨")
        return

    # --- 読み上げ対象コンテンツの収集 ---
    available_contents = {}

    # --- ▼▼▼ ここから修正・追加 ▼▼▼ ---

    # ポートフォリオページからの分析結果
    ai_result_portfolio = sm.get_value("portfolio.ai_result")
    if ai_result_portfolio and isinstance(ai_result_portfolio, str) and not ai_result_portfolio.startswith("["):
        available_contents["ポートフォリオAI分析結果"] = ai_result_portfolio

    # 取引履歴ページからの分析結果
    ai_result_trade = sm.get_value("trade_history.ai_analysis_result")
    if ai_result_trade and isinstance(ai_result_trade, str) and not ai_result_trade.startswith("["):
        available_contents["取引履歴AI分析結果"] = ai_result_trade

    # テクニカル分析ページからの分析結果
    ai_result_tech = sm.get_value("tech_analysis.ai_analysis_result")
    if ai_result_tech and isinstance(ai_result_tech, str) and not ai_result_tech.startswith("["):
        available_contents["テクニカルAI分析結果"] = ai_result_tech

    # EDINETビューアページからの分析結果
    ai_result_edinet = sm.get_value("edinet_viewer.ai_analysis_result")
    if ai_result_edinet and isinstance(ai_result_edinet, str) and not ai_result_edinet.startswith("["):
        available_contents["EDINET報告書AI分析結果"] = ai_result_edinet

    # EDINET高度分析ページからの分析結果
    ai_result_edinet_sort = sm.get_value("edinet_sort.final_analysis_result")
    if ai_result_edinet_sort and isinstance(ai_result_edinet_sort, str) and not ai_result_edinet_sort.startswith("["):
        available_contents["EDINET高度分析レポート"] = ai_result_edinet_sort

    # --- ▲▲▲ ここまで修正・追加 ▲▲▲ ---

    # stock_analysis_page.py のキーが v6 になっているので、それに合わせる
    ai_analysis_text_stock = sm.get_value("stock_analysis_v6.ai_analysis_text")
    if ai_analysis_text_stock and isinstance(ai_analysis_text_stock, str) and not ai_analysis_text_stock.startswith("["):
        available_contents["銘柄AI分析結果"] = ai_analysis_text_stock

    raw_chat_resp_str = sm.get_value("chat.raw_llm_response")
    if raw_chat_resp_str:
        try:
            cleaned_chat_str_for_tts = raw_chat_resp_str.strip()
            match_md_chat_tts = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_chat_str_for_tts, re.DOTALL | re.IGNORECASE)
            if match_md_chat_tts: cleaned_chat_str_for_tts = match_md_chat_tts.group(1).strip()
            chat_data_list_for_tts = json.loads(cleaned_chat_str_for_tts)
            if isinstance(chat_data_list_for_tts, list) and chat_data_list_for_tts:
                full_conversation_text_parts = []
                for msg_item in chat_data_list_for_tts:
                    if isinstance(msg_item, dict):
                        sender, message = msg_item.get("sender", "不明"), msg_item.get("message", "")
                        if isinstance(message, str) and message.strip() and sender.lower() != "system" and "エラー" not in message:
                            full_conversation_text_parts.append(f"{sender}さん、「{message}」")
                if full_conversation_text_parts:
                    available_contents["チャット会話全体"] = "。\n".join(full_conversation_text_parts)
        except Exception as e:
            logger.warning(f"チャット履歴(raw)処理中エラー（TTS用）: {e}")
    novel_text_processed = sm.get_value("novel.generated_content")
    if novel_text_processed and isinstance(novel_text_processed, str) and not novel_text_processed.startswith("["):
        available_contents["生成された小説"] = novel_text_processed
    raw_challenge_chat_resp_str = sm.get_value("challenge_chat.raw_response")
    if raw_challenge_chat_resp_str:
        try:
            cleaned_str = raw_challenge_chat_resp_str.strip()
            match_md = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_str, re.DOTALL | re.IGNORECASE)
            if match_md: cleaned_str = match_md.group(1).strip()
            chat_data = json.loads(cleaned_str)
            if isinstance(chat_data, list) and chat_data:
                full_conv_parts = []
                for msg in chat_data:
                    if isinstance(msg, dict):
                        sender, message = msg.get("sender", "不明"), msg.get("message", "")
                        if sender.lower() != "system" and isinstance(message, str) and message.strip():
                            full_conv_parts.append(f"{sender}さん、「{message}」")
                if full_conv_parts:
                    available_contents["チャレンジチャット会話全体"] = "。\n".join(full_conv_parts)
        except Exception as e:
            logger.warning(f"チャレンジチャット履歴(raw)処理中エラー（TTS用）: {e}")
    challenge_novel_text_processed = sm.get_value("challenge_novel.generated_content")
    if challenge_novel_text_processed and isinstance(challenge_novel_text_processed, str) and challenge_novel_text_processed.strip() and not challenge_novel_text_processed.startswith("["):
        available_contents["チャレンジ生成された小説"] = challenge_novel_text_processed

    # --- UI描画 ---
    if not available_contents:
        available_contents[DEMO_TEXT_KEY] = DEMO_TEXT_FOR_TTS
        st.info("読み上げ可能なテキストがありません。他のページでAIにテキストを生成させてください。")
    else:
        available_contents[DEMO_TEXT_KEY] = DEMO_TEXT_FOR_TTS

    source_options = list(available_contents.keys())
    selected_source_key_ui = st.selectbox("読上コンテンツ選択:", source_options, index=0, key="tts_source_select_ui_ssml_final_v5")
    text_to_read_final = available_contents[selected_source_key_ui]
    st.text_area("読上対象テキストプレビュー:", text_to_read_final, height=150, disabled=True)
    selected_rate = st.slider("読上速度:", min_value=0.8, max_value=3.0, value=1.4, step=0.05, key="tts_speaking_rate_slider_ssml_final_v5")

    if st.button(f"🔊 「{selected_source_key_ui}」から音声を生成する", key="tts_generate_button_ssml_final_v5", type="primary"):
        sm.set_value(KEY_TTS_AUDIO_BYTES, None)
        sm.set_value(KEY_TTS_SYNTH_ERROR, None)
        sm.set_value(KEY_TTS_DEBUG_LOG, [])

        audio_content, synth_err = synthesize_audio_with_retry(
            text_to_read_final, sm, akm, active_model, selected_rate
        )

        if synth_err:
            sm.set_value(KEY_TTS_SYNTH_ERROR, synth_err)
        if audio_content:
            sm.set_value(KEY_TTS_AUDIO_BYTES, audio_content)

        st.rerun()

    # --- 結果表示 ---
    debug_log = sm.get_value(KEY_TTS_DEBUG_LOG)
    if debug_log:
        with st.expander("デバッグと試行ログ", expanded=True):
            st.code("\n".join(debug_log), language="log")

    synth_error_val = sm.get_value(KEY_TTS_SYNTH_ERROR)
    if synth_error_val:
        st.error(f"最終的な音声生成エラー: {synth_error_val}", icon="🚨")

    audio_bytes_to_play = sm.get_value(KEY_TTS_AUDIO_BYTES)
    if audio_bytes_to_play:
        st.success("音声の生成が完了しました！")
        st.subheader("生成された音声")
        # ★★★ 修正: 再生フォーマットを wav に変更 ★★★
        st.audio(audio_bytes_to_play, format="audio/wav")

    # ナビゲーション
    st.markdown("---")
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("戻る (ステップ5へ)", use_container_width=True): sm.set_value("app.current_step", 5); st.rerun()
    with col_next:
        if st.button("次へ (ステップ7へ)", type="primary", use_container_width=True): sm.set_value("app.current_step", 7); st.rerun()
