# Local DB MCP Server

プログラミングに詳しくない人でも手元の環境で立ち上げられるMCPサーバーです。

## 機能

- CSV/TSVファイルのアップロード
- DuckDBデータベースへの保存
- Web UIでのデータ管理
- MCPプロトコルでのデータアクセス

## 必要な環境

- Docker
- Docker Compose

## 起動方法

### 1. リポジトリをクローン
```bash
git clone <repository-url>
cd local-db-mcp-server
```

### 2. Dockerコンテナを起動
```bash
docker-compose up --build
```

### 3. アクセス
- Web UI: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs

## 使用方法

### CSV/TSVファイルのアップロード

1. Web UI (http://localhost:8000) にアクセス
2. CSVまたはTSVファイルをアップロード
3. データがDuckDBに保存されます

### API エンドポイント

- `GET /health` - ヘルスチェック
- `GET /tables` - AIが参照できるデータ一覧
- `GET /query/{table_name}` - テーブルデータの取得
- `POST /upload` - ファイルアップロード

## データの永続化

データはDocker内のボリュームに保存され、コンテナを再起動してもデータは保持されます。ホスト側のファイルシステムには直接保存されません。

## 停止方法

```bash
docker compose down
```

## データの完全削除

Docker内のデータも含めて完全に削除する場合：

```bash
docker compose down -v
```

これにより、Dockerボリュームも削除され、すべてのデータが失われます。

## 開発

### ログの確認
```bash
docker-compose logs -f
```

### コンテナ内でのシェル実行
```bash
docker-compose exec mcp-server bash
```
