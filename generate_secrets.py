# generate_secrets.py
from google.colab import userdata
import os
import json # jsonモジュールをインポート

# ColabのシークレットからAPIキーを取得
news_api_key = userdata.get('News_API_KEY')
gemini_api_key = userdata.get('Gemini_API_KEY')
google_cse_api_key = userdata.get('GOOGLE_CSE_API_KEY')
google_cse_id = userdata.get('GOOGLE_CSE_ID')
brave_api_key = userdata.get('Brave_API_KEY')
gnews_api_key = userdata.get('GNews_API_KEY')
google_cloud_credentials_json_str_from_userdata = userdata.get('GOOGLE_APPLICATION_CREDENTIALS_JSON') # 変数名を変更
model_pass = userdata.get('MODEL_PASS')
tavily_api_key = userdata.get('TAVILY_API_KEY') # TavilyとBingも追加
bing_api_key = userdata.get('BING_API_KEY')

# Streamlitがsecrets.tomlを配置するディレクトリを作成
# hack01 ディレクトリは /content/hack01 と仮定
streamlit_secrets_dir = "/content/hack01/.streamlit"
os.makedirs(streamlit_secrets_dir, exist_ok=True)

# secrets.tomlファイルの内容を作成
secrets_content_parts = []
secrets_content_parts.append(f'NEWS_API_KEY = "{news_api_key if news_api_key is not None else ""}"\n')
secrets_content_parts.append(f'GEMINI_API_KEY = "{gemini_api_key if gemini_api_key is not None else ""}"\n')
secrets_content_parts.append(f'GOOGLE_CSE_API_KEY = "{google_cse_api_key if google_cse_api_key is not None else ""}"\n')
secrets_content_parts.append(f'GOOGLE_CSE_ID = "{google_cse_id if google_cse_id is not None else ""}"\n')
secrets_content_parts.append(f'BRAVE_API_KEY = "{brave_api_key if brave_api_key is not None else ""}"\n')
secrets_content_parts.append(f'GNEWS_API_KEY = "{gnews_api_key if gnews_api_key is not None else ""}"\n')
secrets_content_parts.append(f'PRO_MODEL_UNLOCK_PASSWORD = "{model_pass if model_pass is not None else ""}"\n')
secrets_content_parts.append(f'TAVILY_API_KEY = "{tavily_api_key if tavily_api_key is not None else ""}"\n') # 追加
secrets_content_parts.append(f'BING_API_KEY = "{bing_api_key if bing_api_key is not None else ""}"\n')       # 追加


# GOOGLE_TTS_CREDENTIALS_JSON_STR の部分を修正
secrets_content_parts.append('GOOGLE_TTS_CREDENTIALS_JSON_STR = """') # TOML複数行文字列の開始 """ (直後に改行なし)
if google_cloud_credentials_json_str_from_userdata:
    try:
        # userdataから取得した文字列をPythonの辞書にパース
        parsed_json = json.loads(google_cloud_credentials_json_str_from_userdata)
        # Pythonの辞書を再度JSON文字列に変換 (インデントなし、ASCIIエスケープなし)
        # これにより、JSONとして確実に有効な文字列になる
        # TOMLの複数行基本文字列内では、バックスラッシュはリテラルとして扱われるため、
        # JSON内の \n や \" はそのまま \n, \" として書き込まれ、json.loadsで正しく解釈される。
        proper_json_string = json.dumps(parsed_json, ensure_ascii=False, indent=None, separators=(',', ':'))
        
        # TOMLの複数行基本文字列内で """ が出現しないようにエスケープする
        # （認証JSONには通常 """ は現れないはずだが念のため）
        # リテラルなバックスラッシュもエスケープの必要はない。
        escaped_for_toml_multiline = proper_json_string.replace('"""', '\\"""') # """ -> \"""
        
        secrets_content_parts.append(escaped_for_toml_multiline)
        print("DEBUG: Successfully processed GOOGLE_APPLICATION_CREDENTIALS_JSON from userdata.")
    except json.JSONDecodeError as e:
        secrets_content_parts.append("{}") # パース失敗時は空のJSONオブジェクト
        print(f"警告: userdataのGOOGLE_APPLICATION_CREDENTIALS_JSONは有効なJSONではありませんでした。エラー: {e}")
        print(f"userdataの内容（先頭200文字）: {google_cloud_credentials_json_str_from_userdata[:200]}...")
else:
    secrets_content_parts.append("{}") # userdataに値がない場合は空のJSONオブジェクト
    print("警告: userdataにGOOGLE_APPLICATION_CREDENTIALS_JSONが見つかりませんでした。")
secrets_content_parts.append('"""\n') # TOML複数行文字列の終了 """ と改行

secrets_content = "".join(secrets_content_parts)

# secrets.tomlファイルに書き出す
secrets_file_path = os.path.join(streamlit_secrets_dir, "secrets.toml")
with open(secrets_file_path, "w", encoding='utf-8') as f: # encodingを指定
    f.write(secrets_content)

print(f"secrets.toml ファイルが {secrets_file_path} に生成されました。")
print("\n--- secrets.toml の内容プレビュー (GOOGLE_TTS_CREDENTIALS_JSON_STR 部分) ---")
preview_start_index = secrets_content.find('GOOGLE_TTS_CREDENTIALS_JSON_STR = """')
if preview_start_index != -1:
    preview_end_index = secrets_content.find('"""\n', preview_start_index) + 4
    print(secrets_content[preview_start_index:preview_end_index])
else:
    print("プレビュー部分が見つかりませんでした。")
print("---------------------------------------------------------------------")
