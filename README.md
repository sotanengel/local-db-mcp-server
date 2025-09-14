# Local DB MCP Server

AIエージェントが`ユーザーが提供したデータ`を分析できるようにするMPCサーバーです。

データの格納もUI経由で行うことができるため、誰でも簡単にAIエージェントに分かりやすい形式でデータを提供することができます。

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

## 初期設定

### 1. リポジトリをクローン
```bash
git clone https://github.com/sotanengel/local-db-mcp-server
cd local-db-mcp-server
```

### 2. Dockerのアプリケーションをダウンロード
[公式サイト](https://www.docker.com/ja-jp/)よりアプリケーションをダウンロードしてください。
ダウンロード後はアプリケーションを起動してください。

### 3. Dockerコンテナを起動
```bash
docker compose up --build
```

## 使用方法

### データの格納する

AIエージェントに利用させたいデータを以下の手順で登録してください。

1. [データの格納画面](http://localhost:8001) にアクセス

<img width="1256" height="708" alt="image" src="https://github.com/user-attachments/assets/f6e1055f-afe0-4514-a6ae-90212af29eb8" />

2. CSVまたはTSVファイルをアップロード

<img width="1220" height="170" alt="image" src="https://github.com/user-attachments/assets/9009d771-2d15-4dad-bd76-d6955fc7550a" />

### データに説明を追加する

AIエージェントがデータ分析を行う際に、テーブルの情報が明確に定義されていると分析の精度が上がるため以下の手順で設定を行なってください。

1. テーブル情報を定義したいテーブル名をクリックする

<img width="1214" height="357" alt="image" src="https://github.com/user-attachments/assets/41fea3c9-9fd3-435a-8cf6-65a9b899f44a" />

2. 画面上部の`テーブルの定義を編集`をクリック

<img width="1204" height="146" alt="image" src="https://github.com/user-attachments/assets/28a0ac87-c7e5-47a5-bbcd-36ed2d812694" />

3. 入力欄に定義を入力し、保存する

<img width="1227" height="563" alt="image" src="https://github.com/user-attachments/assets/44bbfac5-3fb4-4eff-a4fa-4a925f7bd8c5" />


### AIエージェントがデータを利用する

AIエージェントは以下のツールを利用できます。

#### 利用可能なツール

1. **list_tables** - データベース内のすべてのテーブル一覧を取得
2. **get_table_schema** - 指定されたテーブルのスキーマ情報を取得
3. **get_table_metadata** - テーブルのメタデータ（説明、レコード数、カラム情報）を取得
4. **execute_query** - SQLクエリを実行して結果を返す

#### AIエージェントへのMCPサーバーの登録方法

##### Cursor への登録手順（mcp.json）

Cursor からこの MCP サーバー（`local-db`）を使うには、MCP 設定ファイル `mcp.json` を作成します。

- プロジェクト専用: プロジェクト直下に `.cursor/mcp.json`
- グローバル: `~/.cursor/mcp.json`

どちらか一方でOKです（プロジェクト内に置くとそのプロジェクトでのみ有効）。

設定例（macOS 推奨設定）:

```json
{
  "mcpServers": {
    "local-db": {
      "command": "/usr/local/bin/docker",
      "args": [
        "exec",
        "-i",
        "local-db-mcp-server-mcp-server-1",
        "python",
        "mcp_server.py"
      ],
      "env": {},
      "disabled": false,
      "autoApprove": ["execute_query", "get_table_info"]
    }
  }
}
```
