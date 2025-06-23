# page_manager.py
import streamlit as st
import logging
import sys # エラー時の情報表示用

# --- 各ページモジュールのインポート ---
# これらのモジュールは main.py と同じ階層にあるか、
# app_setup.configure_sys_path() によってsys.pathが適切に設定されている必要がある。
import portfolio_page
import trade_history_page
import stock_analysis_page
import llm_chat_page
import llm_novel_page
import tts_playback_page
import data_display_page
import technical_analysis_page # テクニカル分析ページ
import edinet_viewer_page
import edinet_sort_page # --- ここを追加 ---

# api_services は各ページで直接インポートされるか、引数で渡される想定
# ここでは、Gemini APIの初期化状態チェックのためにインポート
import api_services
# config は active_gemini_model のデフォルト値参照などで使用する場合がある
import config as app_config

logger = logging.getLogger(__name__) # このモジュール用のロガー

# --- ページ番号と対応するモジュールのマッピング ---
# ステップ番号をキーとし、対応するページ処理モジュールを値とする辞書。
# 各モジュールは render_page(sm, fm, akm, active_model) という関数を持つことを期待。
PAGE_MODULE_MAPPING = {
    0: None,                      # ステップ0: ダッシュボード (このファイル内で直接処理)
    1: portfolio_page,            # ステップ1: ポートフォリオ入力
    2: trade_history_page,        # ステップ2: 取引履歴
    3: stock_analysis_page,       # ステップ3: 銘柄分析 (LLM使用可能性あり)
    4: llm_chat_page,             # ステップ4: LLMチャット (LLM必須)
    5: llm_novel_page,            # ステップ5: LLMショートノベル (LLM必須)
    6: tts_playback_page,         # ステップ6: AIテキスト読み上げ (TTS APIキー必要)
    7: data_display_page,         # ステップ7: 抽出データ表示 (LLM使用可能性あり)
    8: technical_analysis_page,   # ステップ8: テクニカル分析 (LLM使用可能性あり)
    9: edinet_viewer_page,        # ステップ9: EDINET報告書ビューア (LLM使用可能性あり)
    10: edinet_sort_page         # --- ここを追加 ---
}

# --- Gemini APIが必須または推奨されるページのステップ番号リスト ---
# stock_analysis_page (3), data_display_page (7), technical_analysis_page (8), edinet_viewer_page (9) は
# Gemini APIがなくてもチャート表示や基本機能は動作するが、AI分析機能にはAPIキーが必須。
# llm_chat_page (4), llm_novel_page (5) はAPIキーがなければ全く機能しない。
GEMINI_REQUIRED_PAGES = [4, 5, 10] # --- ここに10を追加 ---
GEMINI_RECOMMENDED_PAGES = [3, 7, 8, 9] # 銘柄分析, データ表示, テクニカル分析, EDINET

def render_current_page(current_step: int, sm, fm, akm, active_model_global: str):
    """
    現在のステップ番号 (current_step) に基づいて、適切なページコンテンツを描画します。

    Args:
        current_step (int): 表示するページのステップ番号。
        sm (StateManager): StateManagerのインスタンス。
        fm (FileManager): FileManagerのインスタンス。
        akm (ApiKeyManager): ApiKeyManagerのインスタンス。
        active_model_global (str): 現在グローバルにアクティブなGeminiモデル名。
                                   (例: 'gemini-1.5-flash-latest')
    """
    logger.info(f"render_current_page called for step: {current_step}, active_model_global: {active_model_global}")

    # --- ステップ0: ダッシュボードの描画 ---
    if current_step == 0:
        st.title("📊 投資サポート　AIエージェント「Investallia」　へようこそ！")
        st.markdown(f"選択中のLLMモデル (グローバル設定): `{active_model_global}`")

        gemini_api_status = "初期化成功 (APIキー設定済)" if api_services.is_gemini_api_configured() else "初期化失敗/キー未設定"
        st.markdown(f"Gemini API初期化状態: **{gemini_api_status}**")

        st.markdown("左のサイドバーから各機能を選択してください。")
        st.markdown("---")
        st.subheader("機能概要")
        st.markdown(
            "- **ステップ1**: ポートフォリオ入力・管理\n"
            "- **ステップ2**: 取引履歴の確認・編集\n"
            "- **ステップ3**: 選択銘柄のファンダメンタル分析 (AI活用可能性あり)\n"
            "- **ステップ4**: 自由な対話型AIチャット\n"
            "- **ステップ5**: AIによるショートノベル生成\n"
            "- **ステップ6**: テキストの音声読み上げ (Google TTS)\n"
            "- **ステップ7**: アップロード/抽出済みデータの表示 (AI活用可能性あり)\n"
            "- **ステップ8**: 高度な株価テクニカル分析 (ローソク足、各種指標、AI分析)\n"
            "- **ステップ9**: EDINET提出書類の検索・閲覧 (AI活用可能性あり)\n"
            "- **ステップ10**: LLMによるEDINETデータの高度分析・抽出 (LLM必須)" # --- ここを追加 ---
        )
        if st.button("次へ (ステップ1: ポートフォリオ入力へ)", type="primary", key="s0_next_to_s1_page_manager_v2", use_container_width=True):
            logger.info("[DASHBOARD] 'Next to Step 1' button clicked.")
            sm.set_value("app.current_step", 1) # StateManager経由でステップ変更
            st.rerun() # 変更を反映するためにUIを再実行
        return # ダッシュボード処理終了

    # --- 他のステップのページモジュールを取得 ---
    page_module_to_render = PAGE_MODULE_MAPPING.get(current_step)

    if page_module_to_render:
        page_module_name = page_module_to_render.__name__
        logger.info(f"Rendering page for step {current_step} using module: {page_module_name}")

        # --- APIキーチェック (特にGemini APIが必須/推奨のページ) ---
        gemini_api_ok = api_services.is_gemini_api_configured() # 現在のGemini API設定状況

        if current_step in GEMINI_REQUIRED_PAGES and not gemini_api_ok:
            st.error(f"ステップ {current_step} ({page_module_name}) の実行には、有効なGemini APIキーの設定が必須です。", icon="🚨")
            st.warning("サイドバーの「APIキー取得状況」を確認し、Gemini APIキーを設定してください。")
            logger.error(f"Gemini API not configured. Cannot render mandatory page: step {current_step} ({page_module_name}).")
            if st.button("ステップ0: ダッシュボードへ戻る", key=f"back_to_dash_gemini_mandatory_s{current_step}_pm_v2"):
                sm.set_value("app.current_step", 0); st.rerun()
            return # ページ描画中止

        if current_step in GEMINI_RECOMMENDED_PAGES and not gemini_api_ok:
            # APIキーがなくても基本機能は動くが、AI関連機能は使えないことを警告
            st.warning(
                f"ステップ {current_step} ({page_module_name}) の一部機能（AI分析など）にはGemini APIキーが必要ですが、現在設定されていません。"
                " 基本機能は利用可能ですが、AI機能は動作しません。", icon="⚠️"
            )
            logger.warning(f"Gemini API not configured for recommended page: step {current_step} ({page_module_name}). AI features will be disabled.")
            # この場合でもページの描画は続行する

        # --- ページのrender_page関数を呼び出し ---
        try:
            # 各ページモジュールは render_page(sm, fm, akm, active_model_global) のシグネチャを持つと期待
            page_module_to_render.render_page(sm, fm, akm, active_model_global)
            logger.info(f"Successfully rendered page for step {current_step} ({page_module_name}).")
        except Exception as e_page_render:
            logger.error(f"Error during {page_module_name}.render_page for step {current_step}: {e_page_render}", exc_info=True)
            st.error(f"ステップ {current_step} ({page_module_name}) の描画中にエラーが発生しました: {e_page_render}", icon="🚨")
            st.text("詳細なエラー情報:")
            st.text(sys.exc_info()) # トレースバック情報を表示
            if st.button(f"エラー発生: ダッシュボードへ戻る (S{current_step})", key=f"back_to_dash_render_error_s{current_step}_pm_v2"):
                sm.set_value("app.current_step", 0); st.rerun()
    else:
        # マッピングに存在しないステップ番号の場合
        st.error(f"エラー: ステップ {current_step} に対応するページモジュールが見つかりません。", icon="❗")
        logger.error(f"No page module found for step {current_step} in PAGE_MODULE_MAPPING.")
        st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("戻る", key="invalid_step_back"):
                sm.set_value("app.current_step", current_step - 1 if current_step > 0 else 0)
                st.rerun()
        with col_next:
            if st.button("ダッシュボードへ", type="primary", key="invalid_step_to_dash"):
                sm.set_value("app.current_step", 0)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

