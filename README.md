# Investallia
投資AIエージェント「Investallia」をデプロイするためのコード

金融情報分析＆LLMアシスタントアプリ

本アプリケーションは、投資判断を多角的にサポートするための統合金融情報分析ツールです。ポートフォリオ管理、企業財務データ分析、最新ニュースの収集、AIチャットボットによる対話型分析など、多岐にわたる機能を備えています。

デモサイト: https://hack-app-378173134631.asia-northeast1.run.app/

主な機能
ポートフォリオ管理 (ステップ1): 保有銘柄のポートフォリオを管理・可視化します。
取引履歴分析 (ステップ2): 過去の取引履歴をインポートし、パフォーマンスを分析します。
銘柄分析 (ステップ3): 上場企業の財務データや指標を詳細に分析します。
LLMチャット (ステップ4): 専門家ペルソナを持つAIと対話しながら、銘柄や経済について質問・相談ができます。
LLMショートノベル (ステップ5): 経済や投資をテーマにしたショートノベルをAIが生成します。
AIテキスト読み上げ (ステップ6): 生成されたテキストや分析結果を自然な音声で読み上げます。
抽出データ表示 (ステップ7): 分析に使用した元データを表示・確認できます。
テクニカル分析 (ステップ8): 株価チャートと各種テクニカル指標を用いて分析します。
EDINET報告書ビューア (ステップ9 & 10): EDINETから取得した有価証券報告書を項目別に閲覧・分析できます。
技術スタック
言語: Python
フレームワーク: Streamlit
LLM: Google Gemini (2.5 Pro, 2.5 Flash, 2.0 Flash Lite)
コンテナ: Docker
主要ライブラリ: Pandas, Plotly, etc. (詳細はrequirements.txtを参照)
ファイル構成
📁 hack01/
│
│   📁 DefaultData/ : アプリケーションの基本データ
│   │   📁 EdinetData/ : EDINET有価証券報告書データ
│   │   📁 EdinetSeparateData/ : 項目別に分割されたEDINETデータ
│   │   📁 ChoiceData/ : チャットボット用の追加ペルソナデータ
│   │   ├── 📄 data_j.xls : 東証上場銘柄一覧
│   │   ├── 📄 trade_01.csv : 取引履歴デモデータ
│   │   └── 📄 (その他、分析用各種データファイル)
│
├── 📄 Dockerfile
├── 📄 requirements.txt
├── 📄 config.py : アプリケーションの基本設定
├── 📄 main.py : アプリケーションのエントリポイント
│
├── 📄 api_services.py : 外部API連携
├── 📄 app_setup.py : アプリケーションのセットアップ
├── 📄 file_manager.py : ファイル管理
├── 📄 generate_secrets.py : シークレット情報（APIキー）の生成・管理
├── 📄 news_services.py : ニュース取得・管理
├── 📄 page_manager.py : 各ページの表示管理
├── 📄 state_manager.py : セッション状態管理
├── 📄 stock_searcher.py : 銘柄検索機能
├── 📄 ui_manager.py : UIコンポーネント管理
├── 📄 ui_styles.py : UIスタイルシート
├── 📄 stock_utils.py : 関連銘柄検索
│
├── 📄 portfolio_page.py : (ステップ1) ポートフォリオ
├── 📄 trade_history_page.py : (ステップ2) 取引履歴
├── 📄 stock_analysis_page.py : (ステップ3) 銘柄分析
├── 📄 llm_chat_page.py : (ステップ4) LLMチャット
├── 📄 llm_novel_page.py : (ステップ5) LLMノベル
├── 📄 tts_playback_page.py : (ステップ6) テキスト読み上げ
├── 📄 data_display_page.py : (ステップ7) データ表示
├── 📄 technical_analysis_page.py : (ステップ8) テクニカル分析
├── 📄 edinet_sort_page.py : (ステップ9) EDINETビューア
├── 📄 edinet_viewer_page.py : (ステップ10) EDINET高度分析
│
└── 📁 stock_chart_app/ : テクニカル分析機能のモジュール群
セットアップ方法
1. リポジトリのクローン
Bash

git clone https://github.com/[あなたのユーザー名]/[リポジトリ名].git
cd [リポジトリ名]
2. 依存ライブラリのインストール
Bash

pip install -r requirements.txt
3. APIキーの設定
本アプリケーションは、複数の外部APIを利用します。ルートディレクトリに .env ファイルを作成し、必要なAPIキーを以下のように記述してください。

generate_secrets.py は、デプロイ環境（Google Cloud Runなど）でシークレットマネージャーから環境変数を読み込むためのスクリプトです。ローカルで実行する場合は、.env ファイルを使用するのが簡単です。

.env ファイルの例

NEWS_API_KEY="YOUR_NEWS_API_KEY"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
GOOGLE_CSE_API_KEY="YOUR_GOOGLE_CSE_API_KEY"
GOOGLE_CSE_ID="YOUR_GOOGLE_CSE_ID"
BRAVE_API_KEY="YOUR_BRAVE_API_KEY"
GNEWS_API_KEY="YOUR_GNEWS_API_KEY"
PRO_MODEL_UNLOCK_PASSWORD="YOUR_PASSWORD"
GOOGLE_TTS_CREDENTIALS_JSON_STR='YOUR_GOOGLE_CLOUD_TTS_CREDENTIALS_JSON_CONTENT'
TAVILY_API_KEY="YOUR_TAVILY_API_KEY"
BING_API_KEY="YOUR_BING_API_KEY"
APIキー取得先
環境変数名	サービス名	取得先	備考
GEMINI_API_KEY	Google AI (Gemini)	https://ai.google.dev/gemini-api/docs/api-key?hl=ja	必須。 LLMチャット、ノベル機能で利用。
GOOGLE_TTS_CREDENTIALS_JSON_STR	Google Cloud Text-to-Speech	https://cloud.google.com/text-to-speech?hl=ja	必須。 テキスト読み上げ機能で利用。GCPでサービスアカウントを作成し、キー（JSONファイル）を発行。JSONファイルの中身全体を文字列として設定します。
NEWS_API_KEY	NewsAPI	https://newsapi.org/	ニュース取得APIの1つ。
GOOGLE_CSE_API_KEY&lt;br>GOOGLE_CSE_ID	Google Custom Search Engine	参考記事	ニュース取得APIの1つ。
BRAVE_API_KEY	Brave Search API	https://brave.com/ja/search/api/	ニュース取得APIの1つ。
GNEWS_API_KEY	GNews	https://gnews.io/	ニュース取得APIの1つ。
TAVILY_API_KEY	Tavily API	https://www.tavily.com/	ニュース取得APIの1つ。
BING_API_KEY	Bing Web Search API	https://www.microsoft.com/en-us/bing/apis/bing-web-search-api	ニュース取得APIの1つ。
PRO_MODEL_UNLOCK_PASSWORD	-	任意	高性能なgemini-2.5-proモデルを利用する際に要求されるパスワードを自分で設定します。

Google スプレッドシートにエクスポート
※ニュースAPIについて
ニュースの取得には複数のAPIが利用可能です。config.py 内の NEWS_SERVICE_CONFIG で、使用したいAPIを True に設定してください。全てのAPIキーが必須というわけではありません。

4. アプリケーションの実行
ローカルでの実行
Bash

streamlit run main.py
ブラウザで http://localhost:8501 を開きます。

Dockerでの実行
Dockerイメージをビルドします。
Bash

docker build -t financial-app .
ビルドしたイメージでコンテナを実行します。（.envファイルがある場合）
Bash

docker run -p 8501:8501 --env-file .env financial-app
免責事項
本アプリケーションが提供する情報は、投資判断の参考となる情報提供を目的としたものであり、投資勧誘を目的としたものではありません。投資に関する最終的な決定は、ご自身の判断と責任において行ってください。本アプリケーションの情報に基づいて被ったいかなる損害についても、製作者は一切の責任を負いません。

