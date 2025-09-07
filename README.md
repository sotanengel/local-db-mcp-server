# Local DB MCP Server

プログラミングに詳しくない人でも手元の環境で立ち上げられるMCPサーバーです。

## 機能

### Web UI機能
- CSV/TSVファイルのアップロード
- DuckDBファイルのインポート
- Web UIでのデータ管理・編集
- テーブル定義の編集（コメント、カラム名変更）

### MCPサーバー機能
- AIがデータベースにアクセス可能
- テーブル一覧の取得
- テーブルスキーマ・メタデータの取得
- SQLクエリの実行
- テーブル検索機能

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
docker compose up --build
```

### 3. アクセス
- **Web UI**: http://localhost:8000
- **API ドキュメント**: http://localhost:8000/docs
- **MCPサーバー**: Dockerコンテナ内で実行（stdio通信）

## 使用方法

### CSV/TSVファイルのアップロード

1. Web UI (http://localhost:8000) にアクセス
2. CSVまたはTSVファイルをアップロード
3. データがDuckDBに保存されます

### MCPサーバーの使用

MCPサーバーは以下のツールを提供します：

#### 利用可能なツール

1. **list_tables** - データベース内のすべてのテーブル一覧を取得
2. **get_table_schema** - 指定されたテーブルのスキーマ情報を取得
3. **get_table_metadata** - テーブルのメタデータ（説明、レコード数、カラム情報）を取得
4. **execute_query** - SQLクエリを実行して結果を返す
5. **get_table_data** - 指定されたテーブルのデータを取得
6. **search_tables** - テーブル名や説明でテーブルを検索

#### MCPクライアントでの設定例

```json
{
  "mcpServers": {
    "local-db": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "local-db-mcp-server-mcp-server-1",
        "python",
        "mcp_server.py"
      ]
    }
  }
}
```

### Web API エンドポイント

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
# Web UIコンテナ
docker compose exec web-ui bash

# MCPサーバーコンテナ
docker compose exec mcp-server bash
```

### MCPサーバーのテスト
```bash
# MCPサーバーのテストを実行
docker compose exec mcp-server python test_mcp_server.py
```
