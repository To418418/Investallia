# llm_chat_page.py

import streamlit as st
import json
import re
import pandas as pd # データフレームをLLMプロンプトに渡すため
import logging
import random # ★チャレンジ機能用にインポート
import os # ★チャレンジ機能用にインポート


import ui_styles # HTML生成用
import config as app_config
import api_services
import news_services as news_services
# StateManager, FileManager, ApiKeyManager は引数で渡される

logger = logging.getLogger(__name__)

# --- StateManagerで使用するキー ---
KEY_GENERATED_HTML = "chat.generated_html"
KEY_LLM_ERROR_MESSAGE = "chat.llm_error_message"
KEY_STATUS_MESSAGES = "chat.status_messages"
KEY_PERSONA_DEBUG_LOGS = "chat.persona_debug_logs" # {persona_file_id: [log_messages]}
KEY_RAW_LLM_RESPONSE = "chat.raw_llm_response"
KEY_LAST_GENERATED_PROMPT = "chat.last_generated_prompt"
KEY_USER_CONSULT_QUESTION = "llm_chat.user_consult_question" # ユーザーが編集可能な相談内容
KEY_CHAT_TEMPERATURE = "chat.temperature" # チャット生成時の多様性（temperature）

# ★★★★★ チャレンジチャット用 StateManagerキー ★★★★★
KEY_CHALLENGE_SELECTED_DEFAULT_PERSONAS = "challenge_chat.selected_default_personas"
KEY_CHALLENGE_GENERATION_TRIGGERED = "challenge_chat.generation_triggered"
KEY_CHALLENGE_STATUS_MESSAGES = "challenge_chat.status_messages"
KEY_CHALLENGE_GENERATED_HTML = "challenge_chat.generated_html"
KEY_CHALLENGE_ERROR_MESSAGE = "challenge_chat.error_message"
KEY_CHALLENGE_LAST_PROMPT = "challenge_chat.last_prompt"
KEY_CHALLENGE_RAW_RESPONSE = "challenge_chat.raw_response"

# --- 元のヘルパー関数 (変更なし) ---
def load_persona_with_fm(fm, persona_file_id: str, sm, page_key_prefix:str = "chat") -> tuple[str | None, str | None]:
    """FileManagerを使ってペルソナファイルを読み込む。デバッグログも記録。"""
    debug_logs_key = f"{page_key_prefix}.persona_debug_logs"
    debug_logs = sm.get_value(debug_logs_key, {})
    current_persona_logs = debug_logs.get(persona_file_id, [])
    current_persona_logs.append(f"--- ペルソナファイル '{persona_file_id}' 読み込み開始 (FileManager使用, Page: {page_key_prefix}) ---")
    try:
        content = fm.load_text(persona_file_id)
        current_persona_logs.append(f"FileManager.load_text('{persona_file_id}') 成功。")
        debug_logs[persona_file_id] = current_persona_logs
        sm.set_value(debug_logs_key, debug_logs)
        return content, None
    except Exception as e:
        err_msg = f"ペルソナファイル '{persona_file_id}' 読み込み中にエラー: {e}"
        current_persona_logs.append(f"エラー: {err_msg}")
        logger.error(err_msg, exc_info=True)
        debug_logs[persona_file_id] = current_persona_logs
        sm.set_value(debug_logs_key, debug_logs)
        return None, err_msg

def process_chat_data(llm_generated_chat_string: str) -> str:
    """LLMが生成したチャット文字列を処理し、不要な部分を除去する。"""
    if not isinstance(llm_generated_chat_string, str):
        logger.error(f"LLMチャットデータが文字列でない。型: {type(llm_generated_chat_string)}")
        return f'[{{ "sender": "システム", "message": "LLMデータ型エラー: 応答が文字列ではありません。", "time": "エラー", "isCurrentUser": false, "icon": "⚠️" }}]'
    processed_str = llm_generated_chat_string.strip()
    if processed_str.startswith("[LLM エラー]"):
        logger.warning(f"LLMがエラーメッセージを返しました: {processed_str}")
        error_detail_escaped = json.dumps(processed_str)
        return f'[{{ "sender": "システム", "message": {error_detail_escaped}, "time": "エラー", "isCurrentUser": false, "icon": "⚠️" }}]'
    match_md = re.search(r"```(?:javascript|json)?\s*([\s\S]*?)\s*```", processed_str, re.DOTALL | re.IGNORECASE)
    if match_md:
        processed_str = match_md.group(1).strip()
    match_assignment = re.match(r"^(?:const|let|var)\s+\w+\s*(?:[:\w\s]*)=\s*([\s\S]*?)(?:;)?$", processed_str, re.IGNORECASE | re.DOTALL)
    if match_assignment:
        processed_str = match_assignment.group(1).strip()
    if processed_str.endswith(';'):
        processed_str = processed_str[:-1].strip()
    try:
        json.loads(processed_str)
        return processed_str
    except json.JSONDecodeError as e:
        error_msg_detail = f"チャットデータのJSONパースエラー: {e}. 元のLLM出力(一部): {processed_str[:200]}..."
        logger.error(error_msg_detail, exc_info=True)
        error_msg_for_js = json.dumps(error_msg_detail)
        return f'[{{ "sender": "システム", "message": {error_msg_for_js}, "time": "エラー", "isCurrentUser": false, "icon": "⚠️" }}]'

# ★★★★★ 新しいプロンプト生成関数 (チャレンジチャット用) ★★★★★
def _create_challenge_chat_prompt(all_personas_data: dict, consult_question: str, stock_name: str, stock_code: str, context_data: dict) -> str:
    """チャレンジチャット用に、ワンショット学習形式のプロンプトを生成する。"""
    character_and_icons_list = ["- 主人公(ユーザー): 😎"]
    icon_candidates = ["📈", "👨‍🏫", "👩‍💼", "🧑‍🎨", "🕵️‍♀️", "👨‍🚀", "🥷", "🧙‍♂️", "🧛‍♀️", "🧑‍🌾", "👨‍🍳", "👩‍💻"]
    random.shuffle(icon_candidates)
    persona_details_list = []
    default_characters = {k: v for k, v in all_personas_data.items() if not k.startswith("ランダムキャラクター")}
    random_characters = {k: v for k, v in all_personas_data.items() if k.startswith("ランダムキャラクター")}
    for name, persona_text in default_characters.items():
        icon = icon_candidates.pop(0) if icon_candidates else "💬"
        character_and_icons_list.append(f"- {name}: {icon}")
        persona_details_list.append(f"### {name} の設定\n{persona_text}")
    for name, persona_text in random_characters.items():
        icon = icon_candidates.pop(0) if icon_candidates else "💬"
        character_and_icons_list.append(f"- {name} (ペルソナ内から名前を特定): {icon}")
        persona_details_list.append(f"""### {name} の設定
**重要：このキャラクターの正式な名前は、以下のペルソナ設定の中に「名前：<名前>」などの形式で記載されています。必ずその名前を見つけ出し、`sender`として使用してください。**
---
{persona_text}
---""")
    character_and_icons_section = "\n".join(character_and_icons_list)
    persona_section = "\n\n".join(persona_details_list)
    one_shot_example = (
        "### **タスクの例**\n\n"
        "#### **例：入力情報**\n"
        "- **会話のテーマ:** A社の新製品について\n"
        "- **登場人物とアイコン:**\n"
        "    - 主人公(ユーザー): 😊\n"
        "    - 鈴木 一郎: 📊\n"
        "    - ランダムキャラクター1 (ペルソナ内から名前を特定): 💡\n"
        "- **各登場人物のペルソナ設定:**\n"
        "    ### 鈴木 一郎 の設定\n"
        "    データ重視のアナリスト。\n"
        "    ### ランダムキャラクター1 の設定\n"
        "    **重要：このキャラクターの正式な名前は、以下のペルソナ設定の中に「名前：<名前>」などの形式で記載されています。必ずその名前を見つけ出し、`sender`として使用してください。**\n"
        "    ---\n"
        "    名前：高橋 恵子\n"
        "    職業：元経済記者\n"
        "    性格：鋭い質問をする。\n"
        "    ---\n"
        "- **参考情報:**\n"
        "    (省略)\n\n"
        "#### **例：正しいJSON出力**\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "sender": "主人公",\n'
        '    "message": "鈴木さん、A社の新製品、どう思いますか？",\n'
        '    "time": "14:00",\n'
        '    "isCurrentUser": true,\n'
        '    "icon": "😊"\n'
        "  },\n"
        "  {\n"
        '    "sender": "鈴木 一郎",\n'
        '    "message": "データを見る限り、市場の初期反応は良好です。",\n'
        '    "time": "14:01",\n'
        '    "isCurrentUser": false,\n'
        '    "icon": "📊"\n'
        "  },\n"
        "  {\n"
        '    "sender": "高橋 恵子",\n'
        '    "message": "初期反応は、ね。でも、競合のB社が黙っていないでしょう。供給網のリスクは？",\n'
        '    "time": "14:02",\n'
        '    "isCurrentUser": false,\n'
        '    "icon": "💡"\n'
        "  }\n"
        "]\n"
        "```"
    )
    # ★要望反映: プロンプトに株価履歴を追加
    main_task = f"""あなたは、一流の脚本家であり、指定されたJSON形式で、行動経済学と金融市場に精通した、対話生成のスペシャリストAIです。

あなたの使命は、提供された情報に基づき、ユーザーに深い洞察と自己省察を促す、極めて高品質でリアルな架空のチャット会話を生成することです。
以下の指示に厳密に従い、チャットデータのみをJSON配列として出力してください。それ以外のテキストは一切含めないでください。

# 会話の要件
1. 登場人物は「主人公(ユーザー)」と専門家3名、投資仲間1名です。主人公のアイコンは「😎」にしてください。他の登場人物にはそれぞれユニークな絵文字アイコンを設定してください。
2. 各登場人物は、提供されたペルソナ情報に基づいて発言してください。
3. 主人公(ユーザー)の発言は "isCurrentUser": true とし、それ以外の登場人物の発言は "isCurrentUser": false としてください。
4. 各メッセージには "sender"（発言者名）, "message"（発言内容）, "time"（時刻形式の文字列）, "isCurrentUser"（ブール値）, "icon"（絵文字）のキーを必ず含めてください。メッセージ内の改行は "\\n" で表現してください。
5. 会話は、投資に関する議論（例: 特定銘柄の分析、市場動向、投資戦略、リスク管理など）を中心に展開し、自然な流れで起承転結のあるストーリーにしてください。
6. 会話の目的は、主人公が投資に関する多様な視点や知識を得て、客観的な自己省察を深めることを支援することです。行動経済学的な観点からのアドバイスも適宜含めてください。
7. 会話の長さは、全体で10～20ターン程度を目安にしてください。
8. ユーザーが自分事と感じれるように会話を考え、冒頭の始まりはインパクトのある会話を設定してください。
9. 出来るだけ一般論ではなく以下の情報を参考にしてこの内容を織り込むようにしてください。


# マスタープラン：思考プロセス
まず、以下の思考ステップを内部で実行し、最高の会話シナリオを構築してください。この思考プロセスは最終出力に含めないでください。

## ペルソナとデータの分析:
登場人物全員のペルソナ、専門性、口調を深く理解する。
主人公の取引履歴と資産状況から、その投資スタイル、成功体験、そして潜在的な課題（例：損切りが遅い、特定のセクターに固執している等）を推測する。
提供された企業情報（財務、ニュース、株価）の要点を抽出し、会話の論拠として使用できるポイントを複数特定する。

## 核心テーマと対立軸の設定:
会話全体の核心となるテーマを設定します（例：「対象銘柄は今が買い時か、それとも待つべきか？」）。
専門家間での意見の対立軸を明確に設計します（例：ファンダメンタルズ分析家 vs テクニカル分析家、グロース派 vs バリュー派など）。
この対立が会話のダイナミズムを生み出します。

## 物語（プロット）の設計:
以下の「起承転結」構造に基づき、会話の具体的な流れを設計します。
【起】導入: 主人公が抱える具体的な悩みや疑問を提示します。インパクトを出すため、専門家の一人がデータに基づき、主人公の思考の癖を鋭く指摘する形で開始するのが効果的です。
【承】展開: 複数の専門家が、それぞれの専門的見地からデータ（財務、ニュース、チャート等）を引用し、多角的な分析を展開します。ここでは意見が活発に交わされ、時には対立します。
【転】転換: 主人公が、専門家たちの議論や指摘を通じて、自身の思考の偏り（例：確証バイアス、サンクコスト効果など）に気づく、物語のターニングポイントを設けます。行動経済学の専門家が、この気づきを理論的に裏付け、優しく解説する役割を担います。
【結】結論: 主人公が、得られた多様な視点を統合し、具体的な次のアクションプランや、今後の投資に対する姿勢の変化を表明して会話を締めくくります。完全な答えではなく、「次に何をすべきか」という道筋が見える形で終わらせてください。

# 主人公の基本情報
- **会話のテーマ:** {consult_question}
- **注目企業:** {stock_name} ({stock_code})
- **登場人物とアイコン:**
{character_and_icons_section}
- **主人公の参考情報:**
    - 取引履歴: {context_data['trade_history']}
    - 資産状況: {context_data['balance']}
- **各登場人物のペルソナ設定:**
{persona_section}
- **注目企業の参考情報:**
    - 年次財務諸表(一部): {context_data['financials']}
    - 四半期財務諸表(一部): {context_data['quarterly_financials']}
    - 関連ニュース(一部): {context_data['company_news']}
    - 市場関連ニュース(一部): {context_data['market_news']}
    - 直近30日間の終値データ:
{context_data['price_history']}
#### **本番：正しいJSON出力 (この下に生成してください)**

# 出力フォーマット (JSON配列形式の厳守)
"""
    return f"あなたは、JSON形式でチャットを生成する専門AIです。以下の例を参考に、本番のタスクを実行してください。\n\n{main_task}\n\n{one_shot_example}"

def _run_challenge_chat_generation(sm, fm, akm, active_model):
    status_list = sm.get_value(KEY_CHALLENGE_STATUS_MESSAGES, [])
    status_placeholder = st.empty()
    try:
        status_list.append("関連データを取得中..."); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        stock_code = sm.get_value("app.selected_stock_code", "7203"); stock_name = sm.get_value("app.selected_stock_name", "トヨタ自動車")
        raw_df_trade_data = sm.get_value("trade_history.raw_df", pd.DataFrame()); balance_df_data = sm.get_value("portfolio.balance_df", pd.DataFrame())
        fin_df, q_fin_df, _, _, _, _, error_fin = api_services.get_ticker_financial_data(stock_code)
        if error_fin: logger.warning(f"財務データ取得エラー({stock_name}): {error_fin}")
        # ★要望反映: 株価履歴(30日)を取得
        price_hist_df, price_err = api_services.get_stock_price_history(stock_code, period="30d", interval="1d")
        if price_err: logger.warning(f"株価履歴(30d)の取得に失敗({stock_name}): {price_err}")
        price_hist_markdown = "取得失敗"
        if price_hist_df is not None and not price_hist_df.empty:
            price_hist_df_for_md = price_hist_df[['Close']].copy()
            price_hist_df_for_md.index = price_hist_df_for_md.index.strftime('%Y-%m-%d')
            price_hist_df_for_md.rename(columns={'Close': '終値'}, inplace=True)
            price_hist_markdown = price_hist_df_for_md.to_markdown()

        news_data = news_services.fetch_all_stock_news(stock_name, app_config.NEWS_SERVICE_CONFIG["active_apis"], akm)
        comp_news_df = pd.DataFrame(news_data.get("all_company_news_deduplicated", [])); mkt_news_df = pd.DataFrame(news_data.get("all_market_news_deduplicated", []))
        # ★要望反映: 取得した株価履歴をコンテキストに追加
        context_data_for_prompt = {
            "trade_history": raw_df_trade_data.to_markdown(index=False) if not raw_df_trade_data.empty else "取引履歴なし",
            "balance": balance_df_data.to_markdown(index=False) if not balance_df_data.empty else "資産状況なし",
            "financials": fin_df.head().to_markdown(index=True) if fin_df is not None and not fin_df.empty else "データなし",
            "quarterly_financials": q_fin_df.head().to_markdown(index=True) if q_fin_df is not None and not q_fin_df.empty else "データなし",
            "company_news": comp_news_df.head(3).to_markdown(index=False) if not comp_news_df.empty else "関連ニュースなし",
            "market_news": mkt_news_df.head(3).to_markdown(index=False) if not mkt_news_df.empty else "市場ニュースなし",
            "price_history": price_hist_markdown
        }
        status_list.append("関連データ取得完了。"); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        status_list.append("ペルソナ読み込み中..."); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        all_personas = {}
        default_persona_map = {"アナリスト": "persona_analyst", "大学教授": "persona_professor", "FP": "persona_fp", "後輩": "persona_junior"}
        selected_defaults = sm.get_value(KEY_CHALLENGE_SELECTED_DEFAULT_PERSONAS, [])
        for name in selected_defaults:
            key = default_persona_map.get(name)
            if key:
                content, err = load_persona_with_fm(fm, key, sm, page_key_prefix="challenge_chat")
                if err: raise ValueError(f"デフォルトペルソナ '{name}' の読み込みに失敗: {err}")
                all_personas[name] = content
        random_char_files = fm.list_files("choicedata_dir")
        if not random_char_files: raise FileNotFoundError("`choicedata_dir` にペルソナファイルが見つかりません。")
        num_to_select = min(2, len(random_char_files)); selected_random_files = random.sample(random_char_files, k=num_to_select)
        for i, filename in enumerate(selected_random_files):
            char_key = f"ランダムキャラクター {i+1}"; content = fm.read_text_from_dir("choicedata_dir", filename); all_personas[char_key] = content
        status_list.append("全キャラクターのペルソナ読み込み完了。"); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        consult_question = sm.get_value(KEY_USER_CONSULT_QUESTION, "特になし"); temperature = sm.get_value(KEY_CHAT_TEMPERATURE, 0.7)
        final_prompt = _create_challenge_chat_prompt(all_personas, consult_question, stock_name, stock_code, context_data_for_prompt)
        sm.set_value(KEY_CHALLENGE_LAST_PROMPT, final_prompt)
        status_list.append(f"プロンプト生成完了。LLM ({active_model}, Temp: {temperature}) にリクエスト中..."); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        llm_response = api_services.generate_gemini_response(final_prompt, active_model, temperature=temperature)
        sm.set_value(KEY_CHALLENGE_RAW_RESPONSE, llm_response)
        if llm_response.startswith("[LLM エラー]"): raise ValueError(llm_response)
        status_list.append("LLM応答受信。チャットデータ処理中..."); status_placeholder.info("処理状況:\n" + "\n".join(status_list))
        js_safe_data = process_chat_data(llm_response); html_content = ui_styles.generate_chat_html(js_safe_data)
        sm.set_value(KEY_CHALLENGE_GENERATED_HTML, html_content)
        status_list.append("チャレンジチャット生成完了！"); sm.set_value(KEY_CHALLENGE_STATUS_MESSAGES, status_list); status_placeholder.success("処理状況:\n" + "\n".join(status_list))
    except Exception as e:
        logger.error(f"チャレンジチャット生成中にエラーが発生: {e}", exc_info=True)
        sm.set_value(KEY_CHALLENGE_ERROR_MESSAGE, str(e))
    finally:
        sm.set_value(KEY_CHALLENGE_STATUS_MESSAGES, sm.get_value(KEY_CHALLENGE_STATUS_MESSAGES, []))


def render_page(sm, fm, akm, active_model):
    st.header("🤖 AIチャットシミュレーター (Refactored)")
    st.markdown(f"AIが投資に関する架空のチャット会話を生成します。(使用モデル: `{active_model}`) ")
    st.subheader("登場人物紹介")
    with st.expander("チャットに登場するキャラクターたち", expanded=False):
        # 不可視文字を修正
        st.markdown(
            "- **主人公 (あなた)**: 投資に興味を持つ個人投資家。アイコン: 😎\n"
            "- **アナリスト**: 冷静沈着な市場分析の専門家。データに基づいた判断を重視。\n"
            "- **行動経済学者**: 経済理論や歴史に詳しい学者。長期的な視点からの洞察を提供。\n"
            "- **FP (ファイナンシャルプランナー)**: ライフプランニングと資産形成のアドバイザー。リスク管理を重視。\n"
            "- **後輩**: 最近投資を始めたばかりの初心者。素朴な疑問や感情的な反応も。"
        )
    st.markdown("---")
    current_selected_stock_name = sm.get_value("app.selected_stock_name", "選択中の銘柄")
    default_initial_question = f"{current_selected_stock_name}の今後の株価や見通しについて、専門家の意見を聞きたいです。"
    user_consult_question_val = sm.get_value(KEY_USER_CONSULT_QUESTION, default_initial_question)
    st.subheader("💬 相談内容")
    edited_consult_question = st.text_area("以下の内容でAIに相談します。必要に応じて編集してください:", value=user_consult_question_val, key=KEY_USER_CONSULT_QUESTION, height=100, help="ここで入力した内容が、AIへの相談のベースとなります。")
    st.markdown("---")
    st.subheader("🎨 生成の多様性調整")
    chat_temperature_val = sm.get_value(KEY_CHAT_TEMPERATURE, 0.7)
    edited_chat_temperature = st.slider("チャット生成の表現の多様性（Temperature）:", min_value=0.0, max_value=1.0, value=chat_temperature_val, step=0.05, key=KEY_CHAT_TEMPERATURE, help="値を高くするとより創造的で多様な表現になりますが、破綻しやすくもなります。低くすると安定的ですが単調になる傾向があります。")
    st.markdown("---")
    status_placeholder = st.empty(); error_display_area = st.empty()
    llm_error_msg = sm.get_value(KEY_LLM_ERROR_MESSAGE); current_status_messages = sm.get_value(KEY_STATUS_MESSAGES, [])
    if llm_error_msg: error_display_area.error(f"チャット生成エラー:\n{llm_error_msg}", icon="🚨")
    if current_status_messages:
        is_error = any("エラー" in msg.lower() or "失敗" in msg.lower() for msg in current_status_messages)
        status_text = "処理状況:\n" + "\n".join(current_status_messages)
        if is_error and not llm_error_msg: status_placeholder.error(status_text)
        elif "完了" in status_text and not llm_error_msg: status_placeholder.success(status_text)
        else: status_placeholder.info(status_text)

    if st.button("AIに投資仲間の会話を生成させる", type="primary", key="generate_chat_button_v4"):
        sm.set_value(KEY_GENERATED_HTML, None); sm.set_value(KEY_LLM_ERROR_MESSAGE, None)
        sm.set_value(KEY_RAW_LLM_RESPONSE, None); sm.set_value(KEY_LAST_GENERATED_PROMPT, None)
        sm.set_value(KEY_PERSONA_DEBUG_LOGS, {}); sm.set_value(KEY_STATUS_MESSAGES, ["チャット生成プロセスを開始します..."])
        st.rerun()

    if sm.get_value(KEY_STATUS_MESSAGES) == ["チャット生成プロセスを開始します..."]:
        try:
            current_status_list = sm.get_value(KEY_STATUS_MESSAGES, [])
            current_status_list.append("関連データを取得中..."); status_placeholder.info("処理状況:\n" + "\n".join(current_status_list))
            personas_data = {p.split('_')[1].upper(): fm.load_text(p) for p in ["persona_analyst", "persona_fp", "persona_professor", "persona_junior"]}
            consult_stock_code = sm.get_value("app.selected_stock_code", "7203"); consult_stock_name = sm.get_value("app.selected_stock_name", "トヨタ自動車")
            consult_question = sm.get_value(KEY_USER_CONSULT_QUESTION, default_initial_question)
            raw_df_trade = sm.get_value("trade_history.raw_df", pd.DataFrame()); balance_df = sm.get_value("portfolio.balance_df", pd.DataFrame())
            fin_df, q_fin_df, _, _, _, _, _ = api_services.get_ticker_financial_data(consult_stock_code)

            # ★要望反映: 注目企業の直近30日間の終値データを取得
            price_hist_df, price_err = api_services.get_stock_price_history(consult_stock_code, period="30d", interval="1d")
            if price_err:
                logger.warning(f"株価履歴(30d)の取得に失敗: {price_err}")
                price_hist_markdown = "株価履歴(30日分)の取得に失敗しました。"
            elif price_hist_df is not None and not price_hist_df.empty:
                price_hist_df_for_md = price_hist_df[['Close']].copy()
                price_hist_df_for_md.index = price_hist_df_for_md.index.strftime('%Y-%m-%d')
                price_hist_df_for_md.rename(columns={'Close': '終値'}, inplace=True)
                price_hist_markdown = price_hist_df_for_md.to_markdown()
            else:
                price_hist_markdown = "株価履歴(30日分)が見つかりませんでした。"

            news_data = news_services.fetch_all_stock_news(consult_stock_name, app_config.NEWS_SERVICE_CONFIG["active_apis"], akm)
            news_df = pd.DataFrame(news_data.get("all_company_news_deduplicated", [])); market_df = pd.DataFrame(news_data.get("all_market_news_deduplicated", []))

            one_shot_example_normal = (
                "### タスクの例\n#### 例：正しいJSON出力\n"
                "```json\n"
                '[\n  {"sender": "主人公", "message": "こんにちは！", "time": "10:00", "isCurrentUser": true, "icon": "😎"},\n'
                '  {"sender": "アナリスト", "message": "こんにちは。本日の市場は...", "time": "10:01", "isCurrentUser": false, "icon": "📈"}\n'
                ']\n'
                "```"
            )
            # ★要望反映: プロンプトに株価履歴を追加
            main_task_normal = f"""あなたは、指定されたJSON形式で架空のチャット会話を生成する専門AIです。
以下の指示に厳密に従い、チャットデータのみをJSON配列として出力してください。それ以外のテキストは一切含めないでください。

# 会話の要件
1. 登場人物は「主人公(ユーザー)」と専門家3名、投資仲間1名です。主人公のアイコンは「😎」にしてください。他の登場人物にはそれぞれユニークな絵文字アイコンを設定してください。
2. 各登場人物は、提供されたペルソナ情報に基づいて発言してください。
3. 主人公(ユーザー)の発言は "isCurrentUser": true とし、それ以外の登場人物の発言は "isCurrentUser": false としてください。
4. 各メッセージには "sender"（発言者名）, "message"（発言内容）, "time"（時刻形式の文字列）, "isCurrentUser"（ブール値）, "icon"（絵文字）のキーを必ず含めてください。メッセージ内の改行は "\\n" で表現してください。
5. 会話は、投資に関する議論（例: 特定銘柄の分析、市場動向、投資戦略、リスク管理など）を中心に展開し、自然な流れで起承転結のあるストーリーにしてください。
6. 会話の目的は、主人公が投資に関する多様な視点や知識を得て、客観的な自己省察を深めることを支援することです。行動経済学的な観点からのアドバイスも適宜含めてください。
7. 会話の長さは、全体で10～15ターン程度を目安にしてください。
8. ユーザーが自分事と感じれるように会話を考え、冒頭の始まりはインパクトのある会話を設定してください。

## 主人公の基本情報
- **会話のテーマ:** {consult_question}
- **登場人物とペルソナ:**
  - 主人公(ユーザー): アイコン 😎
  - アナリスト: アイコン 📈\n{personas_data.get("ANALYST")}
  - 大学教授: アイコン 👨‍🏫\n{personas_data.get("PROFESSOR")}
  - FP: アイコン 👩‍💼\n{personas_data.get("FP")}
  - 後輩女子: アイコン 🎓\n{personas_data.get("JUNIOR")}

- **最重要情報:**
  - 注目企業: {consult_stock_name}
  - 主人公の取引履歴: {raw_df_trade.to_markdown(index=False) if not raw_df_trade.empty else "なし"}
  - 主人公の資産状況: {balance_df.to_markdown(index=False) if not balance_df.empty else "なし"}
  - 企業の年次財務(一部): {fin_df.head().to_markdown() if fin_df is not None and not fin_df.empty else "なし"}
  - 企業の四半期財務(一部): {q_fin_df.head().to_markdown() if q_fin_df is not None and not q_fin_df.empty else "なし"}
  - 関連ニュース(一部): {news_df.head(3).to_markdown(index=False) if not news_df.empty else "なし"}
  - 市場ニュース(一部): {market_df.head(3).to_markdown(index=False) if not market_df.empty else "なし"}
  - 注目企業の直近30日間の終値:
{price_hist_markdown}
#### **本番：正しいJSON出力 (この下に生成してください)**

# 出力フォーマット (JSON配列形式の厳守)
"""
            prompt_text = f"あなたはJSONでチャットを生成するAIです。以下の例を参考にタスクを実行してください。\n\n{main_task_normal}\n\n{one_shot_example_normal}"
            sm.set_value(KEY_LAST_GENERATED_PROMPT, prompt_text)
            current_status_list.append("プロンプト生成完了。LLMにリクエスト中..."); status_placeholder.info("処理状況:\n" + "\n".join(current_status_list))

            temperature = sm.get_value(KEY_CHAT_TEMPERATURE, 0.7)
            llm_response = api_services.generate_gemini_response(prompt_text, active_model, temperature=temperature)
            sm.set_value(KEY_RAW_LLM_RESPONSE, llm_response)
            if llm_response.startswith("[LLM エラー]"): raise ValueError(llm_response)

            current_status_list.append("LLM応答受信。処理中..."); status_placeholder.info("処理状況:\n" + "\n".join(current_status_list))
            js_safe_data = process_chat_data(llm_response)
            sm.set_value(KEY_GENERATED_HTML, ui_styles.generate_chat_html(js_safe_data)); sm.set_value(KEY_LLM_ERROR_MESSAGE, None)
            current_status_list.append("チャット生成完了！"); sm.set_value(KEY_STATUS_MESSAGES, current_status_list); status_placeholder.success("処理状況:\n" + "\n".join(current_status_list))
        except Exception as e:
            logger.error(f"通常チャット生成中のエラー: {e}", exc_info=True); sm.set_value(KEY_LLM_ERROR_MESSAGE, str(e))
        finally:
            if sm.get_value(KEY_STATUS_MESSAGES) != ["チャット生成プロセスを開始します..."]: st.rerun()

    generated_html_content = sm.get_value(KEY_GENERATED_HTML)
    if generated_html_content: st.subheader("生成されたチャット"); st.components.v1.html(generated_html_content, height=800, scrolling=True)
    elif not llm_error_msg and not current_status_messages: st.info("上のボタンを押して、AIによるチャット会話を生成してください。")

    # ★★★★★ ここからデバッグ機能の追加 ★★★★★
    with st.expander("通常チャットのデバッグ情報", expanded=False):
        st.text_area("送信したプロンプト", sm.get_value(KEY_LAST_GENERATED_PROMPT, "プロンプトはまだ生成されていません。"), height=200, key="normal_prompt_debug_area")
        st.text_area("LLMの生の応答", sm.get_value(KEY_RAW_LLM_RESPONSE, "LLMからの応答はまだありません。"), height=200, key="normal_raw_response_debug_area")
    # ★★★★★ ここまでデバッグ機能の追加 ★★★★★

    st.markdown("---"); st.subheader("🔥 チャレンジチャット生成")
    st.markdown("デフォルトキャラクターと、`ChoiceData/`フォルダからランダムに選ばれた2名のキャラクターによる、予測不能なチャットを生成します。")
    st.markdown("**参加させるデフォルトキャラクターを選択してください:**"); cols = st.columns(4)
    with cols[0]: st.checkbox("アナリスト", value=True, key="challenge_cb_analyst")
    with cols[1]: st.checkbox("大学教授", value=True, key="challenge_cb_professor")
    with cols[2]: st.checkbox("FP", value=True, key="challenge_cb_fp")
    with cols[3]: st.checkbox("後輩", value=True, key="challenge_cb_junior")

    st.subheader("登場人物紹介")
    with st.expander("チャレンジチャットに登場するランダムキャラクターたち", expanded=False):
        st.markdown(
            "1.- **主人公**: - (若年層の投資家。物語の視点人物)\n\n"
            "- **＜投資仲間たち＞**\n\n"

            "2.- **三島 怜佳 (みしま れいか)**: 不動産に強い、論理的で怜悧な先輩。\n\n"
            "3.- **如月 綺羅々 (きさらぎ きらら)**: 流行を追うハイテンションな後輩FinTuber。\n\n"
            "4.- **龍見 譲二 (たつみ じょうじ)**: 過去を持つ、寡黙なジャズ喫茶の師匠。\n\n"
            "5.- **YUKI (ユキ)**: 全てを数式で解く、謎に包まれた天才。\n\n"
            "6.- **颯山 海斗 (はやま かいと)**: 勝利のため手段を選ばない野心的なライバル。\n\n"
            "7.- **須藤 健一 (すどう けんいち)**: 市場に敗れ、全てを憎む元投資家。\n\n"
            "**＜周辺の人物たち＞**\n\n"
            "8.- **長瀬 詩織 (ながせ しおり)**: 市場の闇を追う、懐疑的な経済記者。\n\n"
            "9.- **有栖川 紗良子 (ありすがわ さよこ)**: 未来の文化に投資する、旧家の令嬢。\n\n"
            "10.- **雨宮 誠 (あまみや まこと)**: 市場の秩序を司る、金融庁のキャリア官僚。\n\n"
            "11.- **ジュリアン・クロフト**: 日本企業を狙う、物言う外国人投資家。\n\n"
            "12.- **柏木 涼 (かしわぎ りょう)**: 市場の裏側を支える、皮肉屋のエンジニア。\n\n"
            "12.- **西園寺 馨 (さいおんじ かおる)**: 投資家の心を診る、秘密主義のセラピスト。\n\n"
            "13.- **村田 吾郎 (むらた ごろう)**: 表と裏の全てを知る、老獪なフィクサー。\n"
        )
    st.markdown("---")

    if st.button("チャレンジチャットを生成！", type="primary", key="generate_challenge_chat_button"):
        selected_personas_list = [name for name, key in {"アナリスト": "challenge_cb_analyst", "大学教授": "challenge_cb_professor", "FP": "challenge_cb_fp", "後輩女子": "challenge_cb_junior"}.items() if st.session_state.get(key)]
        sm.set_value(KEY_CHALLENGE_SELECTED_DEFAULT_PERSONAS, selected_personas_list)
        sm.set_value(KEY_CHALLENGE_GENERATION_TRIGGERED, True)
        sm.set_value(KEY_CHALLENGE_STATUS_MESSAGES, ["チャレンジチャット生成プロセスを開始します..."])
        sm.set_value(KEY_CHALLENGE_GENERATED_HTML, None); sm.set_value(KEY_CHALLENGE_ERROR_MESSAGE, None)
        sm.set_value(KEY_CHALLENGE_LAST_PROMPT, None); sm.set_value(KEY_CHALLENGE_RAW_RESPONSE, None)
        st.rerun()

    if sm.get_value(KEY_CHALLENGE_GENERATION_TRIGGERED):
        _run_challenge_chat_generation(sm, fm, akm, active_model)
        sm.set_value(KEY_CHALLENGE_GENERATION_TRIGGERED, False); st.rerun()

    challenge_error = sm.get_value(KEY_CHALLENGE_ERROR_MESSAGE)
    if challenge_error: st.error(f"チャレンジチャット生成エラー:\n{challenge_error}", icon="🚨")
    challenge_status_messages = sm.get_value(KEY_CHALLENGE_STATUS_MESSAGES, [])
    if challenge_status_messages and not challenge_error:
        final_message = challenge_status_messages[-1] if challenge_status_messages else ""
        if "完了" in final_message: st.success("処理状況:\n" + "\n".join(challenge_status_messages))
        elif challenge_status_messages != ["チャレンジチャット生成プロセスを開始します..."]: st.info("処理状況:\n" + "\n".join(challenge_status_messages))
    challenge_html = sm.get_value(KEY_CHALLENGE_GENERATED_HTML)
    if challenge_html: st.subheader("生成されたチャレンジチャット"); st.components.v1.html(challenge_html, height=800, scrolling=True)

    # ★★★★★ ここからデバッグ機能の追加 ★★★★★
    with st.expander("チャレンジチャットのデバッグ情報", expanded=False):
        st.text_area("送信したプロンプト", sm.get_value(KEY_CHALLENGE_LAST_PROMPT, "プロンプトはまだ生成されていません。"), height=200, key="challenge_prompt_debug_area")
        st.text_area("LLMの生の応答", sm.get_value(KEY_CHALLENGE_RAW_RESPONSE, "LLMからの応答はまだありません。"), height=200, key="challenge_raw_response_debug_area")
    # ★★★★★ ここまでデバッグ機能の追加 ★★★★★

    st.markdown("---"); st.caption("このチャットはAIによって生成されたものであり、実際の人物や出来事とは関係ありません。")
    st.markdown('<div class="navigation-buttons-container" style="margin-top: 3rem;">', unsafe_allow_html=True)
    col_back_nav, col_next_nav = st.columns(2)
    with col_back_nav:
        if st.button("戻る (ステップ3: 銘柄分析へ)", key="s4_back_to_s3", use_container_width=True): sm.set_value("app.current_step", 3); st.rerun()
    with col_next_nav:
        if st.button("次へ (ステップ5: LLMノベルへ)", type="primary", key="s4_next_to_s5", use_container_width=True): sm.set_value("app.current_step", 5); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
