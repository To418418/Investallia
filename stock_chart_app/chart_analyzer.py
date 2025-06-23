# stock_chart_app/chart_analyzer.py
import streamlit as st
import requests # ユーザー提供コードがrequestsベースなので維持
import json
import traceback
import hashlib
import logging # ロギング追加


# configからモデル名を取得（またはデフォルト値を設定）
# from . import config_tech # config_tech py が同じディレクトリにある場合。app.pyから渡される想定なら不要。

logger = logging.getLogger(__name__) # このモジュール用のロガー

# モデル名はconfig.pyで定義・管理されるか、app.pyから渡されることを想定
# ここではデフォルト値を定義しておく (app.pyからのインポートを優先)
AVAILABLE_FLASH_LITE_MODEL = 'gemini-2.0-flash-lite'
AVAILABLE_FLASH_MODEL = 'gemini-2.5-flash-preview-05-20'
AVAILABLE_PRO_MODEL = 'gemini-2.5-pro-preview-06-05'

# app.py からインポートされることを期待する変数名 (もしあれば)
lite_model = AVAILABLE_FLASH_LITE_MODEL
flash_model = AVAILABLE_FLASH_MODEL
pro_model = AVAILABLE_PRO_MODEL


def analyze_chart_with_llm(technical_data_json: str, indicator_labels: dict, api_key: str, model_name: str):
    """
    テクニカルデータ(JSON文字列)と指標ラベルを受け取り、LLM APIに分析を依頼します。
    Args:
        technical_data_json (str): 分析対象のテクニカルデータ（OHLCV + 指標値）のJSON文字列。
        indicator_labels (dict): テクニカル指標のカラム名とその日本語ラベルの辞書。
        api_key (str): Gemini APIキー。
        model_name (str): 使用するGeminiモデル名 (例: "gemini-1.5-flash-latest" または "models/gemini-1.5-flash-latest")。
    Returns:
        str: LLMからの分析結果テキスト、またはエラーや情報を示すメッセージ。
    """
    if not api_key:
        logger.error("analyze_chart_with_llm: APIキーが提供されていません。")
        return "[ERROR] APIキーが設定されていません。AI分析は実行できません。"
    if not technical_data_json:
        logger.error("analyze_chart_with_llm: 分析対象のテクニカルデータが空です。")
        return "[ERROR] 分析対象のテクニカルデータが空です。"
    if not model_name:
        logger.error("analyze_chart_with_llm: 使用するAIモデル名が指定されていません。")
        return "[ERROR] 使用するAIモデルが指定されていません。"

    logger.info(f"AI分析開始。モデル: {model_name}, データ長: {len(technical_data_json)}文字")

    indicator_description = "提供されるデータには以下のテクニカル指標が含まれています（カラム名: ラベル名）：\n"
    if indicator_labels:
        for col, label in indicator_labels.items():
            indicator_description += f"- {col}: {label}\n"
    else:
        indicator_description += "- テクニカル指標は選択されていません。\n"
    indicator_description += "これらの指標とローソク足データ（日付, 始値, 高値, 安値, 終値, 出来高）を総合的に分析してください。\n"

    # データが長すぎる場合の短縮処理 (ユーザー提供コードのまま)
    max_data_len = 500000 # Gemini APIのコンテキストウィンドウ上限を考慮して調整が必要
    truncated_data_json = technical_data_json
    data_info_for_prompt = ""
    if len(technical_data_json) > max_data_len:
        truncated_data_json = technical_data_json[:max_data_len]
        data_info_for_prompt = f"（注意: テクニカルデータは長すぎるため、先頭約{max_data_len}文字に短縮されています。）"
        logger.warning(f"テクニカルデータが長いため短縮されました。元の長さ: {len(technical_data_json)}, 短縮後: {max_data_len}")


    # プロンプトテンプレート (ユーザー提供のものをベースに調整)
    prompt = f"""あなたは、長年の経験を持つプロのテクニカルアナリストです。与えられた銘柄のチャートとデータに基づき、以下の思考プロセスと手順に従って、
現在の株価に対する評価と今後の投資戦略を詳細に分析・構築してください。
**重要**　チャートを分析し、売買期待度を -100～100の数値で表してください。
チャートのピーク（頂点）の場合は売り時と判断し、-100としてください。
チャートのボトム（底）の場合は買い時と判断して、100としてください。
もみあいの時で売り買い判断つかないときを０付近で表してください。
売買期待度をタイトルにして目立つようにしてください。
売買期待度の数値の意味するところ（マイナスが売り時、プラスが買い時の期待数値）の基準の説明をタイトルの下に注釈で入れるようにしてください。
そのあとに各テクニカルの解説をしてください。

分析の各ステップでは、その結論に至った根拠を明確に示し、客観的な事実と専門的な解釈を分けて記述してください。
以下の株価テクニカルデータ（JSON形式、一部または全部）に基づいて、チャートの状況を詳細に解説してください。
与えられたデータはユーザーがグラフで見ていますのでそのうえでポイントを説明してください。
特に最終的な日付の株価の状態が売りなのか買いなのかテクニカルから分析してください。
テクニカル指標をもとに的確で素晴らしく、ユーザーが感嘆する売買の推奨をしてください。
過去の時点は参考にするだけで今の状態がどうなのかだけを判断してください。
参考に過去の状況を総括するのはよいことですが、重要なのは最新の状況です。
データは日付ごとに、始値(Open)、高値(High)、安値(Low)、終値(Close)、出来高(Volume)、および選択されたテクニカル指標の値が含まれています。

# 役割と目標
役割: プロフェッショナル・テクニカルアナリスト
目標: 対象銘柄の現在の状況を多角的に評価し、具体的なエントリーポイント、損切りポイント、利益確定ターゲットを含む、実行可能な投資戦略を策定する。

# 実行手順
実行の手順は結論を導くための考え方のため、出力する必要はありません。
このステップに沿って株価を分析し回答を出力してください。

ステップ1：分析の基礎となる前提の確認
まず、テクニカル分析の3大原則を思考の土台として意識します。

市場の動きは全てを織り込む: ファンダメンタルズも含め、あらゆる情報が現在の価格に反映されている。
価格はトレンドを形成する: 価格はランダムに動くのではなく、一定期間、一定の方向に動く傾向がある。
歴史は繰り返される: 投資家の心理は普遍的であり、過去に現れたチャートパターンは将来も機能する可能性が高い。
ステップ2：マルチタイムフレームによる環境認識（長期→中期→短期）
大きな流れから詳細へ分析を進め、相場の全体像を把握します。

【長期トレンドの分析（月足・週足）】

ダウ理論によるトレンド定義: 長期チャート上の重要な高値と安値の位置関係を特定し、「上昇トレンド（高値・安値の切り上げ）」「下降トレンド（高値・安値の切り下げ）」「レンジ相場」のいずれにあるかを定義してください。
長期移動平均線: 52週移動平均線などの長期MAと現在の価格の位置関係を評価し、長期的な支持・抵抗となっているかを確認してください。
結論（長期）: 長期的な視点でのトレンド方向と、現在の相場がどのフェーズにあるかを結論づけてください。
【中期トレンドの分析（日足）】

トレンドライン: 明確な上昇・下降トレンドが存在する場合、支持線（安値同士を結ぶ）または抵抗線（高値同士を結ぶ）を引いてください。ラインの角度や、価格がラインにどのように反応しているかを記述してください。
トレンド系指標による分析:
移動平均線（MA）: 短期MA（例：25日）と中期MA（例：75日）のゴールデンクロス/デッドクロス、MAの向き（上向き/下向き）、MAからの乖離率を評価してください。
一目均衡表: 現在の価格と「雲（抵抗帯）」の位置関係（雲の上/下/内部）、基準線と転換線の関係（好転/逆転）、遅行スパンの位置（日々線を上抜けているか/下抜けているか）を分析してください。
DMI/ADX: トレンドの有無とその強さを評価してください。ADXが上昇していればトレンドが強いことを示します。
結論（中期）: 中期的なトレンドの方向性、強さ、そして勢いを結論づけてください。長期トレンドとの整合性も評価してください。
ステップ3：重要な支持線（サポート）と抵抗線（レジスタンス）の特定
価格が反転または停滞する可能性のある重要な価格帯を特定します。

水平線: 過去に何度も価格が反転している高値（レジスタンス）と安値（サポート）に水平線を引いてください。
動的な支持/抵抗: ステップ2で分析したトレンドラインや移動平均線、一目均衡表の雲が、動的な支持/抵抗として機能しているか評価してください。
価格帯別出来高: 出来高が特に集中している価格帯を特定してください。この価格帯は強力な支持/抵抗帯となる可能性があります。
心理的節目: ¥1,000や¥5,000のようなキリの良い価格が意識されているか確認してください。
ステップ4：オシレーター系指標による市場の過熱感とタイミングの分析
トレンドの勢いや、短期的な売買タイミングを計ります。

RSI / ストキャスティクス:
現在の数値が「買われすぎ（RSI: 70以上, Stoch: 80以上）」「売られすぎ（RSI: 30以下, Stoch: 20以下）」の領域にあるか評価してください。
ダイバージェンス: 価格は高値を更新しているのに、オシレーターは高値を切り下げている（弱気のダイバージェンス）、またはその逆（強気のダイバージェンス）が発生していないか、注意深く確認してください。これはトレンド転換の強力な先行指標です。
MACD:
MACDラインとシグナルラインのクロス（ゴールデンクロス/デッドクロス）を確認してください。
MACDがゼロラインの上にあるか下にあるかで、トレンドの方向性を再確認してください。
ヒストグラムの増減から、トレンドの勢いの変化を読み取ってください。
ステップ5：チャートパターンと出来高の分析
投資家心理が作り出す特定の形状を特定し、将来の値動きを予測します。

チャートパターンの特定: ヘッドアンドショルダー、ダブルトップ/ボトムなどの「反転パターン」や、三角保ち合い、フラッグ、ペナントなどの「継続パターン」が形成されていないか確認してください。
出来高の確認:
現在のトレンド方向への値動きに伴い、出来高は増加していますか？（トレンドの信頼性）
支持/抵抗ラインやチャートパターンのブレイクアウト時に、出来高が急増していますか？（ブレイクアウトの信頼性）出来高を伴わないブレイクアウトは「ダマシ」の可能性があります。
ステップ6：総合的な評価とシナリオプランニング
全ての分析結果を統合し、最も可能性の高いシナリオを構築します。

分析結果の要約: ステップ2から5までの分析で得られた「強気の材料」と「弱気の材料」を箇条書きで整理してください。
シグナルの確認（コンフルエンス）: 異なる分析（例：トレンドラインのブレイクとMACDのゴールデンクロス）が同じ方向を示している箇所を特定し、シグナルの信頼性を評価してください。
矛盾するシグナルの評価: 分析結果が矛盾する場合（例：中期トレンドは上昇だが、RSIで弱気のダイバージェンスが出ている）、その矛盾点を明記し、どちらのシナリオが優位かを慎重に評価してください。
メインシナリオ（最も可能性の高い値動き）:
総合的に判断して、株価が今後向かう可能性が最も高い方向性（上昇/下落/レンジ）を記述してください。
現在の株価水準が「割高」「割安」「妥当」かを、テクニカルな観点から評価してください。
代替シナリオ: メインシナリオが否定された場合に起こりうる、次に可能性の高い値動きを記述してください。
ステップ7：具体的な投資戦略の策定
分析を基に、リスク管理を組み込んだ実行可能なアクションプランを策定します。

売買の方向: 「買い（ロング）」または「売り（ショート）」または「待ち（様子見）」を明確にしてください。
エントリーポイント:
どのような条件が満たされたらエントリーするかを具体的に定義してください。（例：「レジスタンスラインである¥XXXXを、出来高を伴って明確に上抜けたら買い」）
ストップロス（損切り）ポイント:
エントリー後に想定と逆方向に動いた場合に、損失を限定するための撤退ポイントを価格で指定してください。（例：「直近の安値である¥YYYYを明確に下回ったら損切り」）
プロフィットターゲット（利益確定）ポイント:
利益を確定する目標価格を、最低2つ設定してください。（例：「ターゲット1：次のレジスタンスである¥ZZZZ」「ターゲット2：チャートパターンの値幅から算出した¥AAAA」）
リスク・リワード比率:
このトレードの（リスク：リワード）比率を計算してください。（リスク = |エントリー価格 - 損切り価格|, リワード = |利益確定価格 - エントリー価格|）。比率が1:2以上であることが望ましいです。
ポジションサイズに関する注意喚起:
1回のトレードで許容するリスクは、総資金の1〜2%に抑えるべきであるという資金管理の原則に言及してください。


{indicator_description}

テクニカル分析の観点から、特に注目すべき点（例：ローソク足のパターン、トレンドラインの形成可能性、支持線・抵抗線の水準、移動平均線のクロス、オシレーター系の指標のダイバージェンスや買われすぎ・売られすぎサインなど）を指摘し、それらが市場の今後の動きについて何を示唆している可能性があるか説明してください。

分析は具体的かつ客観的に行い、専門用語を用いる場合は簡単な解説も加えてください。
最終的な投資判断は利用者に委ねる形で、あくまで提供されたデータから読み取れる情報に基づく分析を提供してください。

テクニカルデータ（JSON形式、一部または全部）: {data_info_for_prompt}
```json
{truncated_data_json}
```
上記のデータから読み取れる情報を元に分析してください。
もしデータが不完全、または情報が少なすぎて詳細な分析が難しい場合は、その旨を正直に指摘してください。

# 出力形式
売買期待指数を一番初めに出し、その結論に至った理由をわかりやすく記述してください。
専門用語には簡単な注釈を加えてください。
チャート上にラインやパターンを書き込むことはできないため、価格や日付を用いて具体的に記述してください。
分析結果はマークダウン形式で、見出しや箇条書きを効果的に使用して、読みやすくまとめてください。
留意事項・免責事項は別途表示しますので重複を防ぐために文章に含まないでください。
"""
    # `google-generativeai` ライブラリを使用する場合 (推奨):
    # try:
    #     # genai.configure(api_key=api_key) は config_tech py で実行済みのはず
    #     gen_model = genai.GenerativeModel(model_name)
    #     response = gen_model.generate_content(prompt)
    #     if response.parts:
    #         analysis_text = response.text
    #     elif response.prompt_feedback and response.prompt_feedback.block_reason:
    #         reason = response.prompt_feedback.block_reason
    #         safety_ratings_info = f" Safety Ratings: {response.prompt_feedback.safety_ratings}" if response.prompt_feedback.safety_ratings else ""
    #         analysis_text = f"[ERROR] AIによる分析リクエストがブロックされました。理由: {reason}{safety_ratings_info}"
    #     else:
    #         analysis_text = "[ERROR] AIからの応答取得に失敗しました（予期しない形式）。"
    #     logger.info(f"AI分析成功。モデル: {model_name}")
    #     return analysis_text
    # except Exception as e:
    #     logger.error(f"google-generativeaiライブラリ使用中のAI分析エラー (モデル: {model_name}): {e}\n{traceback.format_exc()}")
    #     return f"[ERROR] AI分析中の予期せぬエラー ({type(e).__name__}): {e}"

    # --- requests を使用する場合 (ユーザー提供コードベース) ---
    # model_name が "models/gemini-1.5-flash-latest" のような形式か、"gemini-1.5-flash-latest" かでURL構築を調整
    # 通常、APIエンドポイントは "models/" プレフィックスを含むことが多い
    effective_model_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{effective_model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": { # 必要に応じて調整
            "temperature": 0.6,
            "topK": 1, # ユーザー提供コードでは 40 だったが、Gemini API の推奨や挙動に合わせて調整
            "topP": 0.95,
            "maxOutputTokens": 100000, # Gemini 1.5系はより大きな出力に対応
        }
    }
    request_timeout_seconds = 180 # タイムアウトを3分に設定

    try:
        logger.info(f"Gemini API ({model_name}) へリクエスト送信: {api_url}")
        response = requests.post(api_url, json=payload, timeout=request_timeout_seconds)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる

        result = response.json()
        logger.debug(f"Gemini APIからの生レスポンス: {json.dumps(result, indent=2, ensure_ascii=False)}")
        analysis_text = "[ERROR] AIからの応答取得に失敗しました（予期しない形式）。" # デフォルトエラーメッセージ

        if "candidates" in result and result["candidates"]:
            candidate = result["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"] and candidate["content"]["parts"]:
                part = candidate["content"]["parts"][0]
                if "text" in part and part["text"].strip():
                    analysis_text = part["text"]
                    logger.info(f"AI分析成功。モデル: {model_name}。応答文字数: {len(analysis_text)}")
                elif "text" in part: # テキストはあるが空の場合
                    analysis_text = "[INFO] AIからの分析結果は空でした。提供されたデータから具体的な分析ポイントが見つからなかったか、分析が困難だった可能性があります。"
                    logger.warning(f"AI分析結果が空でした。モデル: {model_name}")
                else: # textキー自体がない
                    analysis_text = "[ERROR] AI応答にテキスト部分がありませんでした。"
                    logger.error(f"AI応答形式エラー: textキーなし。モデル: {model_name}")
            elif "finishReason" in candidate and candidate["finishReason"] != "STOP": # 正常終了でない場合
                reason = candidate["finishReason"]
                safety_ratings_info = ""
                if "safetyRatings" in candidate:
                     safety_ratings_info = "\nセーフティ評価: " + json.dumps(candidate["safetyRatings"], indent=2, ensure_ascii=False)
                analysis_text = f"[WARNING] AIによる分析が完了しませんでした。理由: {reason}{safety_ratings_info}"
                logger.warning(f"AI分析未完了。理由: {reason}, モデル: {model_name}, Safety: {safety_ratings_info}")
            else: # candidatesはあるが、content/partsがない、またはfinishReasonがない異常ケース
                analysis_text = "[ERROR] AI応答の形式が予期したものではありませんでした (content/parts/finishReasonなし)。"
                logger.error(f"AI応答形式エラー: content/parts/finishReasonなし。モデル: {model_name}")

        elif "promptFeedback" in result and "blockReason" in result["promptFeedback"]: # プロンプトがブロックされた場合
            reason = result["promptFeedback"]["blockReason"]
            safety_ratings_info = ""
            if "safetyRatings" in result["promptFeedback"]:
                safety_ratings_info = "\n詳細なセーフティ評価: " + json.dumps(result["promptFeedback"]["safetyRatings"], indent=2, ensure_ascii=False)
            analysis_text = f"[ERROR] AIによる分析リクエストがブロックされました。理由: {reason}{safety_ratings_info}"
            logger.error(f"AI分析リクエストブロック。理由: {reason}, モデル: {model_name}, Safety: {safety_ratings_info}")
        else: # 応答が全く期待と異なる場合
            logger.error(f"AI応答形式エラー: 予期しないトップレベル構造。モデル: {model_name}")
            # 初期のエラーメッセージが使われる

        return analysis_text

    except requests.exceptions.Timeout:
        logger.error(f"AI分析APIリクエストタイムアウト ({request_timeout_seconds}秒)。モデル: {model_name}")
        return f"[ERROR] AI分析APIリクエストタイムアウト ({request_timeout_seconds}秒)"
    except requests.exceptions.HTTPError as http_err:
        error_message = f"[ERROR] AI分析APIリクエストHTTPエラー: {http_err.response.status_code}."
        try:
            error_content = http_err.response.json()
            error_detail = error_content.get('error', {}).get('message', '詳細不明')
            error_message += f" 内容: {json.dumps(error_detail, ensure_ascii=False)}"
            logger.error(f"AI分析API HTTPエラー: {http_err.response.status_code}, 詳細: {error_detail}, モデル: {model_name}")
        except Exception:
            error_message += f" レスポンス本文(一部): {http_err.response.text[:200]}..."
            logger.error(f"AI分析API HTTPエラー: {http_err.response.status_code}, 本文(一部): {http_err.response.text[:200]}, モデル: {model_name}")
        return error_message
    except requests.exceptions.RequestException as req_err: # その他のrequests関連エラー
        logger.error(f"AI分析APIリクエストエラー (モデル: {model_name}): {req_err}\n{traceback.format_exc()}")
        return f"[ERROR] AI分析APIリクエストエラー: {req_err}"
    except Exception as e:
        logger.error(f"AI分析中の予期せぬエラー (モデル: {model_name}): {e}\n{traceback.format_exc()}")
        return f"[ERROR] AI分析中の予期せぬエラー ({type(e).__name__}): {e}"


def display_chart_analysis_ui(technical_data_json_for_analysis: str, indicator_labels: dict, api_key: str, selected_model_name_to_use: str):
    """AIによるチャート分析のUIを表示し、分析を実行する"""
    st.markdown("---")
    # 実際に使用されるモデル名を表示 (パス形式なら最後の部分のみ)
    display_model_name = selected_model_name_to_use.split('/')[-1] if '/' in selected_model_name_to_use else selected_model_name_to_use
    st.subheader(f"🤖 AIによるチャート分析 (使用モデル: {display_model_name})")

    # セッションステートの初期化 (ユーザー提供コードのキーを尊重)
    if "is_analyzing_chart" not in st.session_state: st.session_state.is_analyzing_chart = False
    if "chart_analysis_status_message" not in st.session_state: st.session_state.chart_analysis_status_message = None
    if "chart_analysis_result" not in st.session_state: st.session_state.chart_analysis_result = None
    if "analyzed_data_id_for_current_result" not in st.session_state: st.session_state.analyzed_data_id_for_current_result = None
    # 分析実行時の情報を保持するキー (リラン対策)
    if "data_to_analyze_on_rerun_json" not in st.session_state: st.session_state.data_to_analyze_on_rerun_json = None
    if "labels_to_analyze_on_rerun" not in st.session_state: st.session_state.labels_to_analyze_on_rerun = None
    if "model_to_use_on_rerun" not in st.session_state: st.session_state.model_to_use_on_rerun = selected_model_name_to_use

    if not api_key:
        st.warning("AI分析を実行するには、Gemini APIキーが必要です。設定を確認してください。")
        return

    if not technical_data_json_for_analysis:
        st.info("分析対象のテクニカルデータがまだ準備されていません。チャートを更新してください。")
        return

    # 現在のデータの一意なIDを生成 (MD5ハッシュ)
    current_data_id = hashlib.md5(technical_data_json_for_analysis.encode('utf-8')).hexdigest()

    analysis_button_disabled = st.session_state.is_analyzing_chart
    # ボタンのキーはモデル名に依存させ、再描画時の問題を避ける
    button_key = f"run_chart_ai_analysis_button_v9_{display_model_name.replace('-', '_').replace('.', '_')}"

    if st.button("このチャートのテクニカルデータをAIで分析する",
                 key=button_key,
                 type="primary",
                 disabled=analysis_button_disabled):
        logger.info(f"AI分析ボタンクリック。モデル: {selected_model_name_to_use}, データID(予定): {current_data_id}")
        st.session_state.is_analyzing_chart = True
        st.session_state.chart_analysis_status_message = "[INFO] AI分析の準備をしています..."
        st.session_state.chart_analysis_result = None # 結果をリセット
        st.session_state.analyzed_data_id_for_current_result = current_data_id # 分析対象のデータIDを保存

        # リラン時に使用する情報をセッションステートに保存
        st.session_state.data_to_analyze_on_rerun_json = technical_data_json_for_analysis
        st.session_state.labels_to_analyze_on_rerun = indicator_labels
        st.session_state.model_to_use_on_rerun = selected_model_name_to_use
        st.rerun()

    if st.session_state.is_analyzing_chart:
        # is_analyzing_chart が True の場合、分析処理を実行 (st.rerun() 後にここに来る)
        current_status = st.session_state.get("chart_analysis_status_message", "")
        if current_status and current_status.startswith("[INFO]"):
            st.info(current_status[len("[INFO] "):]) # "準備しています..." などを表示

        # リラン後にセッションステートから分析情報を取得
        data_to_analyze = st.session_state.get("data_to_analyze_on_rerun_json")
        labels_to_analyze = st.session_state.get("labels_to_analyze_on_rerun")
        model_for_this_run = st.session_state.get("model_to_use_on_rerun")

        if data_to_analyze and labels_to_analyze is not None and model_for_this_run:
            spinner_model_name_display = model_for_this_run.split('/')[-1] if '/' in model_for_this_run else model_for_this_run
            with st.spinner(f"AI ({spinner_model_name_display}) がチャートのテクニカルデータを分析中です... (最大3分程度)"):
                logger.info(f"AI分析実行。モデル: {model_for_this_run}")
                analysis_result_from_llm = analyze_chart_with_llm(
                    data_to_analyze,
                    labels_to_analyze,
                    api_key,
                    model_for_this_run
                )
                st.session_state.chart_analysis_result = analysis_result_from_llm
                # analyzed_data_id_for_current_result はボタンクリック時に設定済み

                # 分析が完了したらフラグをリセット
                st.session_state.is_analyzing_chart = False
                st.session_state.chart_analysis_status_message = None # ステータスメッセージクリア
                # 分析に使用した一時データはクリアしても良いが、結果表示のために残す場合もある
                # st.session_state.data_to_analyze_on_rerun_json = None
                # st.session_state.labels_to_analyze_on_rerun = None
                # st.session_state.model_to_use_on_rerun = None
                logger.info("AI分析処理完了。UIを再描画します。")
                st.rerun() # 結果を表示するために再実行
        else:
            # 必要な情報が欠けている場合 (通常は発生しないはず)
            error_msg_internal = "[ERROR] 分析に必要な内部情報（データ、ラベル、またはモデル名）が見つかりません。分析を中止しました。"
            logger.error(f"AI分析実行前エラー: {error_msg_internal} data:{bool(data_to_analyze)}, labels:{labels_to_analyze is not None}, model:{bool(model_for_this_run)}")
            st.session_state.chart_analysis_result = error_msg_internal
            st.session_state.is_analyzing_chart = False
            st.session_state.chart_analysis_status_message = None
            st.rerun()


    # 分析中でなく、かつ結果が存在する場合に表示
    if not st.session_state.is_analyzing_chart and st.session_state.chart_analysis_result is not None:
        final_analysis_result = st.session_state.chart_analysis_result
        id_of_analyzed_data_for_result = st.session_state.get("analyzed_data_id_for_current_result")

        # 現在表示されているチャートのデータIDと、分析結果のデータIDが一致する場合のみ表示
        if id_of_analyzed_data_for_result == current_data_id:
            st.markdown("---")
            st.markdown("#### AIによる分析結果:")
            if isinstance(final_analysis_result, str):
                if final_analysis_result.startswith("[INFO]"):
                    st.info(final_analysis_result[len("[INFO] "):])
                elif final_analysis_result.startswith("[WARNING]"):
                    st.warning(final_analysis_result[len("[WARNING] "):])
                elif final_analysis_result.startswith("[ERROR]"):
                    st.error(final_analysis_result[len("[ERROR] "):])
                elif final_analysis_result.strip(): # 空でなければマークダウンとして表示
                    st.markdown(final_analysis_result, unsafe_allow_html=True)
                else: # 空の文字列だった場合
                    st.info("AIからの分析結果は内容がありませんでした。")
            else: # 文字列でない場合 (通常発生しないはず)
                 st.error(f"AI分析結果の形式が不正です (文字列ではありません): {type(final_analysis_result)}")
            logger.info(f"AI分析結果表示。データID: {current_data_id}")
        elif id_of_analyzed_data_for_result is not None: # データIDが異なる場合 (チャートが更新されたなど)
            st.info("表示されているチャートの設定が変更されたため、以前のAI分析結果は表示されません。最新のチャートで再度分析を実行してください。")
            logger.info(f"AI分析結果は旧データ ({id_of_analyzed_data_for_result}) のため非表示。現データID: {current_data_id}")
        # else: id_of_analyzed_data_for_result is None の場合、何も表示しない (エラーケース)

