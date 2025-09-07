FROM python:3.13-slim

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新と必要なツールのインストール
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# データディレクトリを作成
RUN mkdir -p /app/data

# ポートを公開
EXPOSE 8000

# アプリケーションを起動
CMD ["python", "server.py"]
