# ui_manager.py
import streamlit as st
import logging
from typing import Dict, Any, List

import config as app_config
from stock_searcher import search_stocks_by_query

logger = logging.getLogger(__name__)

def render_stock_search_header(sm, all_stocks_data: Dict[str, Any]):
    """
    メイン画面上部に高度な銘柄検索UIと選択中銘柄情報を表示します。
    グローバル銘柄選択が変更されたらフラグを立てます。
    """
    logger.debug("render_stock_search_header called.")
    st.markdown("---")

    search_query_session_key = "ui.stock_search_query_input"

    if sm.get_value("ui.clear_search_input_flag", False):
        # このキーは st.text_input の key なので、st.session_state を直接操作する
        if search_query_session_key in st.session_state:
            st.session_state[search_query_session_key] = ""
        sm.set_value(search_query_session_key, "") #念のためStateManagerも更新
        sm.set_value("ui.clear_search_input_flag", False)
        logger.debug(f"Cleared search input field via flag for key: {search_query_session_key}")
        # st.rerun() # ここでのrerunは不要。次の描画でクリアされる。

    main_cols_header = st.columns([3, 2])

    with main_cols_header[0]:
        st.subheader("株式銘柄検索・選択")

        if not all_stocks_data or not isinstance(all_stocks_data, dict):
            st.warning("銘柄データがロードされていないか、形式が不正です。検索機能は利用できません。")
            sm.set_value(search_query_session_key, "")
            sm.set_value("ui.stock_search_candidates", [])
            sm.set_value("ui.stock_search_message", "")
            return

        with st.form(key="stock_search_form_v3"): # フォームキー変更
            form_cols = st.columns([4, 1])
            with form_cols[0]:
                st.text_input(
                    "銘柄名またはコード:",
                    key=search_query_session_key, # st.session_state[search_query_session_key] が直接使われる
                    help="例: トヨタ、7203、Softbank など。入力後「検索」を押してください。"
                )
            with form_cols[1]:
                search_button_clicked = st.form_submit_button(label="検索")

        if search_button_clicked:
            current_query_from_form = st.session_state.get(search_query_session_key, "")
            sm.set_value("ui.stock_search_query_user_entered", current_query_from_form)
            logger.info(f"Search button clicked. Query: '{current_query_from_form}'")

            sm.set_value("ui.stock_search_candidates", [])

            if current_query_from_form:
                search_result = search_stocks_by_query(current_query_from_form, all_stocks_data)
                if search_result.get("confirmed_stock"):
                    confirmed = search_result["confirmed_stock"]
                    # グローバル銘柄が実際に変更されたかチェック
                    old_code = sm.get_value("app.selected_stock_code")
                    if old_code != confirmed["code"]:
                        sm.set_value("app.global_stock_just_changed_flag", True) # ★フラグを立てる★
                        logger.info(f"Global stock changed from {old_code} to {confirmed['code']}. Flag set.")

                    sm.set_value("app.selected_stock_code", confirmed["code"])
                    sm.set_value("app.selected_stock_name", confirmed["name_jp"])
                    sm.set_value("ui.stock_search_message", f"✅ {search_result['reason']}")
                    sm.set_value("ui.clear_search_input_flag", True)
                    logger.info(f"Stock confirmed: {confirmed['code']} - {confirmed['name_jp']}")
                elif search_result.get("candidates"):
                    candidates_data = search_result["candidates"]
                    sm.set_value("ui.stock_search_candidates", candidates_data)
                    sm.set_value("ui.stock_search_message", f"💡 {search_result['reason']} (候補から選択してください)")
                    logger.info(f"Candidates found: {len(candidates_data)}")
                elif search_result.get("not_found"):
                    sm.set_value("ui.stock_search_message", f"⚠️ {search_result['reason']}")
                    logger.info("No stock found.")
            else:
                sm.set_value("ui.stock_search_message", "銘柄名またはコードを入力してください。")
            st.rerun()

        search_message = sm.get_value("ui.stock_search_message", "")
        # ... (メッセージ表示ロジックは変更なし) ...
        if search_message:
            if "✅" in search_message: st.success(search_message)
            elif "💡" in search_message: st.info(search_message)
            elif "⚠️" in search_message: st.warning(search_message)
            else: st.caption(search_message)


        candidates: List[Dict[str, Any]] = sm.get_value("ui.stock_search_candidates", [])
        if candidates:
            st.write("検索候補:")
            num_cols_candidates = 3
            candidate_button_cols = st.columns(num_cols_candidates)
            col_idx_candidates = 0

            for idx, cand_data in enumerate(candidates):
                button_key_cand = f"cand_btn_{cand_data['code']}_{idx}_v3" # キー名変更
                current_col_cand = candidate_button_cols[col_idx_candidates % num_cols_candidates]

                with current_col_cand:
                    if st.button(cand_data["display_text"], key=button_key_cand, use_container_width=True):
                        old_code_cand = sm.get_value("app.selected_stock_code")
                        if old_code_cand != cand_data["code"]:
                            sm.set_value("app.global_stock_just_changed_flag", True) # ★フラグを立てる★
                            logger.info(f"Global stock changed from {old_code_cand} to {cand_data['code']} via candidate button. Flag set.")

                        sm.set_value("app.selected_stock_code", cand_data["code"])
                        sm.set_value("app.selected_stock_name", cand_data["name_jp"])
                        sm.set_value("ui.stock_search_message", f"✅ 銘柄 '{cand_data['name_jp']}' を選択しました。")
                        sm.set_value("ui.stock_search_candidates", [])
                        sm.set_value("ui.clear_search_input_flag", True)
                        logger.info(f"Stock selected from candidate buttons: {cand_data['code']}")
                        st.rerun()
                col_idx_candidates += 1

    with main_cols_header[1]:
        selected_code_display = sm.get_value("app.selected_stock_code")
        selected_name_display = sm.get_value("app.selected_stock_name")
        st.caption("現在選択中の銘柄")
        if selected_code_display and selected_name_display:
            st.markdown(f"##### {selected_name_display} ({selected_code_display})")
        else:
            st.markdown("##### 銘柄が選択されていません")
    st.markdown("---")


def render_sidebar(sm, akm, app_config_module):
    logger.debug("render_sidebar called.")
    st.sidebar.title("ナビゲーションと設定")
    st.sidebar.markdown("---")
    nav_options = {
        "ステップ0: ダッシュボード": 0, "ステップ1: ポートフォリオ入力": 1, "ステップ2: 取引履歴": 2,
        "ステップ3: 銘柄分析": 3, "ステップ4: LLMチャット": 4, "ステップ5: LLMショートノベル": 5,
        "ステップ6: AIテキスト読み上げ": 6, "ステップ7: 抽出データ表示": 7,
        "ステップ8: テクニカル分析": 8, "ステップ9: EDINET報告書ビューア": 9,
        "ステップ10: EDINET高度分析": 10  # --- ここを追加 ---
    }
    nav_radio_key = "app_mode_radio_ui_manager_v4"
    def navigation_changed_callback_sidebar():
        selected_step_text = st.session_state.get(nav_radio_key)
        if selected_step_text is None: return
        new_step = nav_options.get(selected_step_text)
        if new_step is not None and sm.get_value("app.current_step") != new_step:
            sm.set_value("app.current_step", new_step)
            st.rerun()
    current_step_from_sm_for_radio = sm.get_value("app.current_step", 0)
    radio_options_list = list(nav_options.keys())
    default_radio_index_nav_init = 0
    try:
        current_selection_text_for_radio_init = next(text_key for text_key, step_val in nav_options.items() if step_val == current_step_from_sm_for_radio)
        default_radio_index_nav_init = radio_options_list.index(current_selection_text_for_radio_init)
    except (StopIteration, ValueError): sm.set_value("app.current_step", 0)
    st.sidebar.radio( "ステップ:", options=radio_options_list, index=default_radio_index_nav_init, key=nav_radio_key, on_change=navigation_changed_callback_sidebar)
    st.sidebar.markdown("---")

    # --- ▼▼▼ モデル選択部分の修正 ▼▼▼ ---
    st.sidebar.subheader("🤖 Geminiモデル選択")
    # config.pyで定義した3つのモデルを使って選択肢を生成
    model_options_map_sidebar = {
        f"Flash Lite ({app_config_module.AVAILABLE_FLASH_LITE_MODEL})": app_config_module.AVAILABLE_FLASH_LITE_MODEL,
        f"Flash 2.5 ({app_config_module.AVAILABLE_FLASH_MODEL})": app_config_module.AVAILABLE_FLASH_MODEL,
        f"Pro 2.5 ({app_config_module.AVAILABLE_PRO_MODEL})": app_config_module.AVAILABLE_PRO_MODEL
    }
    model_radio_key_sidebar = "gemini_model_selector_ui_manager_v5" # キーを更新

    # モデル選択が変更されたときのコールバック関数
    def model_selection_changed_callback_sidebar():
        selected_model_display_name = st.session_state.get(model_radio_key_sidebar)
        if selected_model_display_name is None: return

        newly_selected_model_actual = model_options_map_sidebar[selected_model_display_name]

        if sm.get_value('app.selected_model_in_ui') != newly_selected_model_actual:
            sm.set_value('app.selected_model_in_ui', newly_selected_model_actual)

            # Proモデル "以外" が選択された場合は、即座にアクティブモデルに設定し、Proのロックは解除
            if newly_selected_model_actual != app_config_module.DEFAULT_PRO_MODEL:
                sm.set_value('app.pro_model_unlocked', False)
                sm.set_value('app.active_gemini_model', newly_selected_model_actual)

            # Proモデルが選択された場合、active_gemini_model はパスワード認証後に更新されるのでここでは何もしない
            st.rerun()

    current_ui_model_selection = sm.get_value('app.selected_model_in_ui', app_config_module.DEFAULT_FLASH_MODEL)
    model_options_display_list = list(model_options_map_sidebar.keys())
    model_options_values_list = list(model_options_map_sidebar.values())
    default_model_radio_index = 0
    try:
        default_model_radio_index = model_options_values_list.index(current_ui_model_selection)
    except ValueError:
        sm.set_value('app.selected_model_in_ui', app_config_module.DEFAULT_FLASH_MODEL)

    st.sidebar.radio(
        "モデル:",
        options=model_options_display_list,
        index=default_model_radio_index,
        key=model_radio_key_sidebar,
        on_change=model_selection_changed_callback_sidebar
    )

    # Proモデルのパスワード認証ロジック
    pro_model_password_config = akm.get_api_key("PRO_MODEL_UNLOCK_PASSWORD")
    if sm.get_value('app.selected_model_in_ui') == app_config_module.DEFAULT_PRO_MODEL:
        if not pro_model_password_config:
            st.sidebar.error("Proモデル解除パスワード未設定。他のモデルを使用してください。", icon="🚨")
            # Proが使えないので、自動的にデフォルトのFlash Liteに戻す
            if sm.get_value('app.active_gemini_model') != app_config_module.DEFAULT_FLASH_MODEL or sm.get_value('app.selected_model_in_ui') != app_config_module.DEFAULT_FLASH_MODEL or sm.get_value('app.pro_model_unlocked'):
                sm.set_value('app.active_gemini_model', app_config_module.DEFAULT_FLASH_MODEL)
                sm.set_value('app.selected_model_in_ui', app_config_module.DEFAULT_FLASH_MODEL)
                sm.set_value('app.pro_model_unlocked', False)
                st.rerun()
        elif sm.get_value('app.pro_model_unlocked'):
            st.sidebar.success(f"Proモデル ({app_config_module.DEFAULT_PRO_MODEL}) 有効化済。")
            if sm.get_value('app.active_gemini_model') != app_config_module.DEFAULT_PRO_MODEL:
                sm.set_value('app.active_gemini_model', app_config_module.DEFAULT_PRO_MODEL)
                st.rerun()
        else:
            st.sidebar.warning("Proモデル利用にはパスワード認証が必要です。", icon="⚠️")
            pro_password_input_sidebar = st.sidebar.text_input("Proモデル解除パスワード:", type="password", key="pro_model_unlock_pass_input_ui_manager_v5")
            if st.sidebar.button("Proモデル有効化", key="unlock_pro_model_button_ui_manager_v5"):
                if pro_password_input_sidebar == pro_model_password_config:
                    sm.set_value('app.pro_model_unlocked', True)
                    sm.set_value('app.active_gemini_model', app_config_module.DEFAULT_PRO_MODEL)
                    st.rerun()
                else:
                    st.sidebar.error("パスワードが違います。", icon="🚨")
    else: # Proモデル以外が選択されている場合
        selected_ui_model_not_pro = sm.get_value('app.selected_model_in_ui')
        # 状態の同期: active_modelがUIの選択と異なる、またはpro_modelがロックされたままの場合
        if sm.get_value('app.active_gemini_model') != selected_ui_model_not_pro or sm.get_value('app.pro_model_unlocked'):
            sm.set_value('app.active_gemini_model', selected_ui_model_not_pro)
            sm.set_value('app.pro_model_unlocked', False)
            st.rerun()

    # --- ▲▲▲ モデル選択部分の修正 ▲▲▲ ---


    st.sidebar.markdown("---")
    import api_services
    gemini_api_status_display = "初期化成功" if api_services.is_gemini_api_configured() else "初期化失敗/キー未設定"
    st.sidebar.info(f"有効LLM: `{sm.get_value('app.active_gemini_model', 'N/A')}`\nGemini API Status: {gemini_api_status_display}")
    if app_config_module.IS_CLOUD_RUN: st.sidebar.caption(f"実行環境: Google Cloud Run\nプロジェクトID: {app_config_module.PROJECT_ID or 'N/A'}")
    else: st.sidebar.caption("実行環境: Colab / ローカル")
    st.sidebar.markdown("---")
    st.sidebar.subheader("APIキー取得状況")
    st.sidebar.json(akm.get_all_loaded_keys_summary())
    st.sidebar.markdown("---")
    st.sidebar.caption(f"統合金融ダッシュボード v3.0.1\nLLM: {sm.get_value('app.active_gemini_model', 'N/A')}")
    logger.debug("render_sidebar finished.")
