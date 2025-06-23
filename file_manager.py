# file_manager.py
import streamlit as st
import pandas as pd
import os
import json
import logging
from io import StringIO, BytesIO
from chardet.universaldetector import UniversalDetector
from typing import List

# config から設定をインポート
import config as app_config


# Cloud Run環境でのみGCSライブラリをインポート
if app_config.IS_CLOUD_RUN:
    try:
        from google.cloud import storage
    except ImportError:
        storage = None
        logging.error("GCS Storageライブラリのインポートに失敗しました。Cloud Run環境では必須です。")
else:
    storage = None

logger = logging.getLogger(__name__)

class FileManager:
    """
    ファイル読み込み（ローカルおよびGCS）とファイルメタデータ管理を行うクラス。
    """
    def __init__(self, file_metadata: dict, gcs_bucket_name: str = None):
        """
        FileManagerを初期化します。

        Args:
            file_metadata (dict): ファイルのメタデータ情報を含む辞書。
                                 キーはファイル識別子、値はパスやエンコーディング情報など。
            gcs_bucket_name (str, optional): GCSバケット名。Cloud Run環境で必要。
        """
        self.metadata = file_metadata
        self.gcs_bucket_name = gcs_bucket_name
        self.gcs_client = None
        if app_config.IS_CLOUD_RUN:
            if not self.gcs_bucket_name:
                logger.error("Cloud Run環境が検出されましたが、GCSバケット名が提供されていません。")
            if storage:
                self.gcs_client = storage.Client()
            else:
                logger.error("Cloud Run環境が検出されましたが、GCS Storageライブラリがロードされていません。")

    def _get_file_meta(self, file_id: str) -> dict:
        """指定されたファイルIDのメタデータを取得する。"""
        meta = self.metadata.get(file_id)
        if not meta:
            raise FileNotFoundError(f"ファイルID '{file_id}' のメタデータが見つかりません。")
        return meta

    def _read_local_file_bytes(self, path: str) -> bytes:
        """ローカルファイルからバイトデータを読み込む。"""
        abs_path = os.path.abspath(path)
        logger.info(f"ローカルファイル '{abs_path}' を読み込みます。")
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"ローカルファイルが見つかりません: {abs_path}")
        with open(abs_path, 'rb') as f:
            return f.read()

    def _read_gcs_file_bytes(self, blob_name: str) -> bytes:
        """GCSからファイルバイトデータを読み込む。"""
        if not app_config.IS_CLOUD_RUN or not self.gcs_client:
            raise EnvironmentError("GCS操作はCloud Run環境で、かつStorageクライアントが利用可能な場合のみサポートされます。")
        if not self.gcs_bucket_name:
            raise ValueError("GCSバケット名が設定されていません。")

        logger.info(f"GCSファイル gs://{self.gcs_bucket_name}/{blob_name} を読み込みます。")
        try:
            bucket = self.gcs_client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(blob_name)
            if not blob.exists():
                raise FileNotFoundError(f"GCSファイルが見つかりません: gs://{self.gcs_bucket_name}/{blob_name}")
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"GCSファイル gs://{self.gcs_bucket_name}/{blob_name} の読み込みエラー: {e}", exc_info=True)
            raise

    def get_file_bytes(self, file_id: str) -> bytes:
        """
        指定されたファイルIDのバイトデータを取得します。
        環境 (Colab/GCS) を自動的に判別します。
        """
        meta = self._get_file_meta(file_id)
        if app_config.IS_CLOUD_RUN:
            gcs_blob_path = meta.get("path_gcs_blob")
            if not gcs_blob_path:
                raise ValueError(f"ファイルID '{file_id}' のGCSパス (path_gcs_blob) がメタデータに定義されていません。")
            return self._read_gcs_file_bytes(gcs_blob_path)
        else:
            colab_path = meta.get("path_colab")
            if not colab_path:
                raise ValueError(f"ファイルID '{file_id}' のColabパス (path_colab) がメタデータに定義されていません。")
            return self._read_local_file_bytes(colab_path)

    @st.cache_data(ttl=3600)
    def load_text(_self, file_id: str, default_encoding: str = 'utf-8') -> str:
        """
        指定されたファイルIDのテキストデータを読み込みます。
        """
        meta = _self._get_file_meta(file_id)
        encoding = meta.get("encoding", default_encoding)
        file_bytes = _self.get_file_bytes(file_id)
        logger.info(f"ファイルID '{file_id}' をエンコーディング '{encoding}' でデコードします。")
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError as e:
            logger.error(f"ファイルID '{file_id}' のデコードエラー (エンコーディング: {encoding}): {e}", exc_info=True)
            raise UnicodeDecodeError(f"ファイル '{meta.get('path_colab', meta.get('path_gcs_blob'))}' のデコードに失敗しました (試行エンコーディング: {encoding})。メタデータを確認してください。") from e

    def _try_parse_csv_with_encodings(self, file_bytes: bytes, encodings_to_try: list, source_filename_log: str) -> tuple[pd.DataFrame | None, str | None]:
        """複数のエンコーディングを試してCSVをパースする内部関数。"""
        detected_encoding_info = ""
        detector = UniversalDetector()
        detector.feed(file_bytes)
        detector.close()
        detected_result = detector.result
        detected_encoding = detected_result['encoding'] if detected_result and detected_result['confidence'] > 0.7 else None

        if detected_encoding:
            detected_encoding_info = f"(chardet検出: {detected_encoding}, 信頼度: {detected_result.get('confidence', 0):.2f})"
            if detected_encoding.lower() not in [enc.lower() for enc in encodings_to_try]:
                encodings_to_try.insert(0, detected_encoding)
            else:
                encodings_to_try.insert(0, encodings_to_try.pop(encodings_to_try.index(next(enc for enc in encodings_to_try if enc.lower() == detected_encoding.lower()))))
            encodings_to_try = list(dict.fromkeys(encodings_to_try))

        trial_log = []
        for encoding_attempt in encodings_to_try:
            try:
                decoded_content = file_bytes.decode(encoding_attempt)
                if not decoded_content.strip():
                    trial_log.append(f"✗ {encoding_attempt}: デコード後、内容が空です。")
                    continue

                replacement_char_count = decoded_content.count('\ufffd')
                if len(decoded_content) > 100 and replacement_char_count > len(decoded_content) * 0.05:
                    trial_log.append(f"⚠️ {encoding_attempt}: 文字化けの可能性 (置換文字 {replacement_char_count}個)。")

                df = pd.read_csv(StringIO(decoded_content))
                trial_log.append(f"✓ {encoding_attempt}: パース成功 ({len(df)}行)")
                logger.info(f"CSVファイル '{source_filename_log}' をエンコーディング '{encoding_attempt}' でパース成功。\n試行ログ:\n" + "\n".join(trial_log) + f"\n{detected_encoding_info}")
                return df, encoding_attempt
            except UnicodeDecodeError as e:
                trial_log.append(f"✗ {encoding_attempt}: デコード失敗 - {str(e)[:50]}...")
            except pd.errors.EmptyDataError:
                trial_log.append(f"✗ {encoding_attempt}: CSVデータが空です (ヘッダーもなし)。")
            except pd.errors.ParserError as e:
                trial_log.append(f"✗ {encoding_attempt}: CSVパース失敗 - {str(e)[:50]}...")
            except Exception as e:
                trial_log.append(f"✗ {encoding_attempt}: 予期せぬエラー - {str(e)[:50]}...")

        logger.warning(f"CSVファイル '{source_filename_log}' の全てのエンコーディング試行に失敗。\n試行ログ:\n" + "\n".join(trial_log) + f"\n{detected_encoding_info}")
        return None, None

    @st.cache_data(ttl=3600)
    def load_csv(_self, file_id: str) -> tuple[pd.DataFrame | None, str | None, str | None]:
        """
        指定されたファイルIDのCSVデータを読み込みます。
        """
        meta = _self._get_file_meta(file_id)
        if meta.get("type") != "csv":
            return None, None, f"ファイルID '{file_id}' はCSVタイプではありません (タイプ: {meta.get('type')})。"

        encodings_to_try = meta.get("encoding_options", ['utf-8', 'cp932', 'shift_jis'])
        source_filename_for_log = meta.get("path_colab", meta.get("path_gcs_blob", file_id))

        try:
            file_bytes = _self.get_file_bytes(file_id)
            df, successful_encoding = _self._try_parse_csv_with_encodings(file_bytes, list(encodings_to_try), source_filename_for_log)

            if df is not None:
                expected_cols = meta.get("expected_columns")
                if expected_cols and not all(col in df.columns for col in expected_cols):
                    logger.warning(f"CSVファイル '{source_filename_for_log}' のカラムが期待と異なります。期待: {expected_cols}, 実際: {list(df.columns)}")
                return df, successful_encoding, None
            else:
                return None, None, f"ファイル '{source_filename_for_log}' のCSVパースに全てのエンコーディングで失敗しました。"

        except FileNotFoundError as e:
            logger.error(f"CSVファイルロードエラー (ファイルID: {file_id}): {e}", exc_info=True)
            return None, None, str(e)
        except Exception as e:
            logger.error(f"CSVファイルロード中に予期せぬエラー (ファイルID: {file_id}): {e}", exc_info=True)
            return None, None, f"予期せぬエラーが発生しました: {e}"

    def get_json_string_secret(self, file_id: str, api_key_manager) -> str | None:
        """
        指定されたファイルIDのJSON文字列シークレットを取得します。
        """
        meta = self._get_file_meta(file_id)
        if meta.get("type") != "json_string_secret":
            logger.error(f"ファイルID '{file_id}' は json_string_secret タイプではありません。")
            return None

        secret_key_name = meta.get("secret_key_st")
        if app_config.IS_CLOUD_RUN:
            secret_key_name = meta.get("secret_id_gcp", secret_key_name)

        if not secret_key_name:
            logger.error(f"ファイルID '{file_id}' のシークレットキー名がメタデータに定義されていません。")
            return None

        secret_value = api_key_manager.get_api_key(secret_key_name)

        if not secret_value:
            logger.warning(f"ファイルID '{file_id}' (キー名: {secret_key_name}) のシークレット値を取得できませんでした。")
            return None
        try:
            json.loads(secret_value)
            logger.info(f"ファイルID '{file_id}' のJSON文字列シークレットを正常に取得・検証しました。")
            return secret_value
        except json.JSONDecodeError:
            logger.error(f"ファイルID '{file_id}' (キー名: {secret_key_name}) から取得した値は有効なJSON文字列ではありません。")
            return None

    # ★★★★★ ここからがチャレンジチャット機能のために追加されたメソッドです ★★★★★
    @st.cache_data(ttl=300)
    def list_files(_self, dir_id: str) -> List[str]:
        """
        指定されたディレクトリID内のファイル名の一覧を取得します。
        サブディレクトリは含めず、ファイルのみを返します。
        """
        meta = _self._get_file_meta(dir_id)
        if meta.get("type") != "dir":
            raise ValueError(f"ファイルID '{dir_id}' はディレクトリタイプではありません。")

        filenames = []
        if app_config.IS_CLOUD_RUN:
            if not _self.gcs_client:
                raise EnvironmentError("GCSクライアントが初期化されていません。")

            gcs_prefix = meta.get("path_gcs_blob", "")
            if not gcs_prefix.endswith('/'):
                gcs_prefix += '/'

            bucket = _self.gcs_client.bucket(_self.gcs_bucket_name)
            blobs = _self.gcs_client.list_blobs(bucket, prefix=gcs_prefix, delimiter='/')

            for blob in blobs:
                if not blob.name.endswith('/'):
                    filename = blob.name.replace(gcs_prefix, '', 1)
                    if filename:
                       filenames.append(filename)
            logger.info(f"GCSディレクトリ '{gcs_prefix}' から {len(filenames)} 個のファイルをリストアップしました。")
        else:
            local_path = meta.get("path_colab")
            if not os.path.isdir(local_path):
                raise FileNotFoundError(f"ローカルディレクトリが見つかりません: {local_path}")

            for item in os.listdir(local_path):
                if os.path.isfile(os.path.join(local_path, item)):
                    filenames.append(item)
            logger.info(f"ローカルディレクトリ '{local_path}' から {len(filenames)} 個のファイルをリストアップしました。")

        return filenames

    @st.cache_data(ttl=3600)
    def read_text_from_dir(_self, dir_id: str, filename: str, encoding: str = 'utf-8') -> str:
        """
        指定されたディレクトリID内の特定のファイル名を読み込み、テキストとして返します。
        """
        meta = _self._get_file_meta(dir_id)
        if meta.get("type") != "dir":
            raise ValueError(f"ファイルID '{dir_id}' はディレクトリタイプではありません。")

        if app_config.IS_CLOUD_RUN:
            gcs_prefix = meta.get("path_gcs_blob", "")
            if not gcs_prefix.endswith('/'):
                gcs_prefix += '/'
            blob_path = f"{gcs_prefix}{filename}"
            file_bytes = _self._read_gcs_file_bytes(blob_path)
        else:
            local_path = meta.get("path_colab")
            full_path = os.path.join(local_path, filename)
            file_bytes = _self._read_local_file_bytes(full_path)

        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError as e:
            logger.error(f"ファイル '{filename}' のデコードエラー (エンコーディング: {encoding}): {e}")
            raise
    # ★★★★★ ここまでが追加されたメソッドです ★★★★★



