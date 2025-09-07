# MCPサーバー設定ガイド

このプロジェクトには、MCPサーバーに接続するための複数の設定ファイルが含まれています。

## 設定ファイルの種類

### 1. `mcp.json` - Docker用設定（推奨）
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
      ],
      "env": {}
    }
  }
}
```

### 2. `mcp-local.json` - ローカル実行用設定
```json
{
  "mcpServers": {
    "local-db": {
      "command": "python",
      "args": [
        "mcp_server.py"
      ],
      "env": {
        "DATABASE_PATH": "./test_database.duckdb"
      }
    }
  }
}
```

## 使用方法

### CursorでMCPサーバーを使用する場合

1. **Docker環境を使用する場合（推奨）**:
   ```bash
   # まずDockerコンテナを起動
   docker compose up -d
   
   # Cursorの設定ファイルにコピー
   cp mcp.json ~/.cursor/mcp.json
   ```

2. **ローカル環境を使用する場合**:
   ```bash
   # 必要な依存関係をインストール
   pip install -r requirements.txt
   
   # Cursorの設定ファイルにコピー
   cp mcp-local.json ~/.cursor/mcp.json
   ```

### 他のMCPクライアントで使用する場合

適切な設定ファイルを選択して、クライアントの設定に追加してください。

## 利用可能なツール

MCPサーバーが提供するツール：

1. **`list_tables`**: データベース内のテーブル一覧を取得
2. **`execute_query`**: SQLクエリを実行して結果を取得

## トラブルシューティング

### Dockerコンテナが起動しない場合
```bash
# コンテナの状態を確認
docker compose ps

# ログを確認
docker compose logs

# 再構築
docker compose down
docker compose build --no-cache
docker compose up -d
```

### MCPサーバーに接続できない場合
1. コンテナ名が正しいか確認: `local-db-mcp-server-mcp-server-1`
2. 設定ファイルのパスが正しいか確認
3. Cursorを再起動

## テスト

MCPサーバーが正常に動作しているかテストする場合：
```bash
docker exec -it local-db-mcp-server-mcp-server-1 python test_mcp_server.py
```








