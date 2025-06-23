# main/Dockerfile

# ベースイメージとしてPython 3.9 (または互換性のあるバージョン) を使用
FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt requirements.txt

# 依存関係をインストール (キャッシュを利用しないことでイメージサイズを削減)
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# Gunicornがリッスンするポート (Cloud Runは通常8080を期待)
ENV PORT 8080
EXPOSE 8080



CMD /bin/sh -c "streamlit run main.py --server.address=0.0.0.0 --server.port=\${PORT}"
