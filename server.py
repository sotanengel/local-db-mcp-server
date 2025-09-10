#!/usr/bin/env python3
"""
MCP Server with DuckDB
リファクタリング済みの簡潔なMCPサーバー実装
"""

import asyncio
import json
import logging
import urllib.parse
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import time
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPIアプリケーション
app = FastAPI(title="Local DB MCP Server", version="1.0.0")

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# DuckDB接続
DB_PATH = "/app/data/database.duckdb"

def get_db_connection():
    """DuckDB接続を取得"""
    return duckdb.connect(DB_PATH)

def import_duckdb_file(conn, temp_file_path):
    """DuckDBファイルをインポート"""
    try:
        # インポート用の一時接続を作成
        import_conn = duckdb.connect(temp_file_path)
        
        # インポート元のテーブル一覧を取得
        tables = import_conn.execute("SHOW TABLES").fetchall()
        
        # 各テーブルをメインデータベースにコピー
        for table in tables:
            table_name = table[0]
            # テーブル名を安全にエスケープ
            safe_table_name = table_name.replace('"', '""')
            
            # テーブルが既に存在する場合は置き換え
            conn.execute(f'DROP TABLE IF EXISTS "{safe_table_name}"')
            
            # テーブルをコピー（ATTACHを使用してより安全に）
            try:
                # まずATTACHでデータベースを接続
                conn.execute(f"ATTACH '{temp_file_path}' AS source_db")
                # テーブルをコピー
                conn.execute(f'CREATE TABLE "{safe_table_name}" AS SELECT * FROM source_db."{safe_table_name}"')
                # ATTACHを解除
                conn.execute("DETACH source_db")
            except Exception as e:
                # ATTACHが失敗した場合は元の方法を試す
                logger.warning(f"ATTACH method failed for table {table_name}, trying alternative method: {e}")
                conn.execute(f'CREATE TABLE "{safe_table_name}" AS SELECT * FROM \'{temp_file_path}\'."{safe_table_name}"')
            
            # テーブルコメントをコピー
            try:
                table_comment = import_conn.execute(f"SELECT comment FROM duckdb_tables() WHERE table_name = '{table_name}'").fetchone()
                if table_comment and table_comment[0]:
                    # コメント内のシングルクォートをエスケープ
                    safe_comment = table_comment[0].replace("'", "''")
                    conn.execute(f'COMMENT ON TABLE "{safe_table_name}" IS \'{safe_comment}\'')
            except Exception as e:
                logger.warning(f"Failed to copy table comment for {table_name}: {e}")
            
            # カラムコメントをコピー
            try:
                column_comments = import_conn.execute(f"""
                    SELECT column_name, comment 
                    FROM duckdb_columns() 
                    WHERE table_name = '{table_name}' AND comment IS NOT NULL
                """).fetchall()
                for column_name, comment in column_comments:
                    # カラム名とコメントを安全にエスケープ
                    safe_column_name = column_name.replace('"', '""')
                    safe_comment = comment.replace("'", "''")
                    conn.execute(f'COMMENT ON COLUMN "{safe_table_name}"."{safe_column_name}" IS \'{safe_comment}\'')
            except Exception as e:
                logger.warning(f"Failed to copy column comments for {table_name}: {e}")
        
        import_conn.close()
        
    except Exception as e:
        logger.error(f"DuckDBファイルインポートエラー: {e}")
        raise e

def _decode_with_fallbacks(content: bytes) -> str:
    """Try multiple encodings to decode bytes to text.
    Order: utf-8 -> cp932(Shift_JIS) -> utf-16-sig
    """
    for enc in ("utf-8", "cp932", "utf-16-sig"):
        try:
            return content.decode(enc)
        except Exception:
            continue
    raise UnicodeDecodeError("unknown", content, 0, 0, "Unsupported encoding. Save as UTF-8/Shift_JIS.")

def _resolve_table_name(conn: duckdb.DuckDBPyConnection, path_name: str) -> str:
    """Resolve an incoming path table name (which may be URL-encoded or not)
    to an existing table name in DuckDB. Returns the matched name or raises HTTP 404.
    """
    try:
        existing = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"テーブル一覧取得エラー: {str(e)}")

    candidates = [
        path_name,
        urllib.parse.unquote(path_name),
        urllib.parse.quote(path_name, safe='')
    ]
    for cand in candidates:
        if cand in existing:
            return cand

    raise HTTPException(status_code=404, detail=f"テーブル '{urllib.parse.unquote(path_name)}' が見つかりません")

@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {"status": "healthy", "service": "mcp-duckdb-server"}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """ホームページ"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/table/{table_name}", response_class=HTMLResponse)
async def view_table_page(request: Request, table_name: str):
    """テーブル表示専用ページ"""
    display_name = urllib.parse.unquote(table_name)
    return templates.TemplateResponse("table_view.html", {
        "request": request,
        "table_name": table_name,
        "display_name": display_name
    })

@app.get("/table/{table_name}/edit", response_class=HTMLResponse)
async def edit_table_page(request: Request, table_name: str):
    """テーブル定義編集専用ページ"""
    display_name = urllib.parse.unquote(table_name)
    return templates.TemplateResponse("table_edit.html", {
        "request": request,
        "table_name": table_name,
        "display_name": display_name
    })

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """CSV/TSVファイルをアップロードしてDuckDBに保存"""
    try:
        # ファイル内容を読み込み
        content = await file.read()
        
        # テーブル名を生成（ファイル名から拡張子を除く）
        original_table_name = Path(file.filename).stem
        table_name = urllib.parse.quote(original_table_name, safe='')
        # 日本語など非ASCIIが含まれる場合は仮の英数字テーブル名に置き換える
        def _needs_safe_name(name: str) -> bool:
            try:
                name.encode('ascii')
                return False
            except Exception:
                return True
        decoded_original = urllib.parse.unquote(original_table_name)
        rename_to_safe = _needs_safe_name(decoded_original)
        safe_table_name = f"table_{int(time.time())}" if rename_to_safe else table_name
        
        # DuckDBに接続してテーブルを作成
        conn = get_db_connection()
        
        # ファイル形式に応じて一時ファイルを作成
        if file.filename.endswith('.duckdb'):
            # DuckDBファイルはバイナリなので直接保存
            with tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb') as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
        else:
            # CSV/TSVファイルはテキストとして保存（エンコーディング自動判定）
            try:
                content_str = _decode_with_fallbacks(content)
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="ファイルのエンコーディングを判定できませんでした。UTF-8 もしくは Shift_JIS(CP932) で保存してください。")

            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.csv', delete=False) as temp_file:
                temp_file.write(content_str)
                temp_file_path = temp_file.name
        
        try:
            # ファイル形式に応じて処理を分岐
            if file.filename.endswith('.csv'):
                conn.execute(f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{temp_file_path}')")
            elif file.filename.endswith('.tsv'):
                conn.execute(f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{temp_file_path}', delim='\\t')")
            elif file.filename.endswith('.duckdb'):
                # DuckDBファイルのインポート処理
                import_duckdb_file(conn, temp_file_path)
                # DuckDBファイルの場合はテーブル数ではなく、インポートされたテーブル数を返す
                tables_result = conn.execute("SHOW TABLES").fetchall()
                return {
                    "message": f"DuckDBファイル '{file.filename}' が正常にインポートされました",
                    "table_name": "imported_database",
                    "original_table_name": original_table_name,
                    "row_count": len(tables_result),
                    "imported_tables": [table[0] for table in tables_result]
                }
            else:
                raise HTTPException(status_code=400, detail="CSV、TSV、またはDuckDBファイルのみサポートしています")
            
            # 必要なら仮の安全なテーブル名にリネームし、元名をコメントとして保持
            if rename_to_safe and safe_table_name != table_name:
                conn.execute(f'ALTER TABLE "{table_name}" RENAME TO "{safe_table_name}"')
                # コメントに元の表示名を残す
                safe_comment = decoded_original.replace("'", "''")
                conn.execute(f"COMMENT ON TABLE \"{safe_table_name}\" IS '{safe_comment}'")
                table_name = safe_table_name
            
            # テーブル情報を取得（行数/カラム数のバリデーション）
            result = conn.execute(f"SELECT COUNT(*) as count FROM \"{table_name}\"").fetchone()
            schema_rows = conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()
            row_count = int(result[0]) if result and result[0] is not None else 0
            column_count = len(schema_rows)

            if column_count == 0:
                # 後片付けしてエラー返却
                conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
                raise HTTPException(status_code=400, detail="アップロードに失敗しました。カラムが検出できませんでした（区切り文字やエンコーディングをご確認ください）。")

            if row_count == 0:
                conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
                raise HTTPException(status_code=400, detail="アップロードに失敗しました。データ行が検出できませんでした（ヘッダーのみ、または空ファイルの可能性）。")
            
        finally:
            # 一時ファイルを削除
            os.unlink(temp_file_path)
        
        conn.close()
        
        return {
            "message": f"ファイル '{file.filename}' が正常にアップロードされました",
            "table_name": table_name,
            "original_table_name": original_table_name,
            "row_count": row_count
        }
        
    except Exception as e:
        logger.error(f"ファイルアップロードエラー: {e}")
        raise HTTPException(status_code=500, detail=f"アップロードエラー: {str(e)}")

@app.get("/tables")
async def list_tables():
    """利用可能なAIが参照できるデータ一覧を取得"""
    try:
        conn = get_db_connection()
        result = conn.execute("SHOW TABLES").fetchall()
        conn.close()
        
        tables = []
        for row in result:
            table_name = row[0]
            try:
                display_name = urllib.parse.unquote(table_name)
            except:
                display_name = table_name
            
            tables.append({
                "name": table_name,
                "display_name": display_name
            })
        
        return {"tables": tables}
        
    except Exception as e:
        logger.error(f"AIが参照できるデータ一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"エラー: {str(e)}")

@app.get("/query/{table_name}")
async def query_table(table_name: str, limit: int = 10):
    """テーブルのデータをクエリ"""
    try:
        conn = get_db_connection()
        resolved = _resolve_table_name(conn, table_name)
        result = conn.execute(f"SELECT * FROM \"{resolved}\" LIMIT {limit}").fetchall()
        columns = [desc[0] for desc in conn.description]
        conn.close()
        
        data = [dict(zip(columns, row)) for row in result]
        return {"table": resolved, "data": data, "limit": limit}
        
    except Exception as e:
        logger.error(f"クエリエラー: {e}")
        raise HTTPException(status_code=500, detail=f"クエリエラー: {str(e)}")

@app.get("/table/{table_name}/schema")
async def get_table_schema(table_name: str):
    """テーブルのスキーマ情報を取得"""
    try:
        conn = get_db_connection()
        resolved = _resolve_table_name(conn, table_name)
        result = conn.execute(f"DESCRIBE \"{resolved}\"").fetchall()
        conn.close()
        
        schema = [{"column": row[0], "type": row[1], "null": row[2], "key": row[3], "default": row[4], "extra": row[5]} for row in result]
        return {"table": resolved, "schema": schema}
        
    except Exception as e:
        logger.error(f"スキーマ取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"スキーマ取得エラー: {str(e)}")

@app.put("/table/{table_name}/column/{column_name}")
async def update_column_name(table_name: str, column_name: str, new_name: str):
    """カラム名を変更"""
    try:
        conn = get_db_connection()
        conn.execute(f"ALTER TABLE \"{table_name}\" RENAME COLUMN {column_name} TO {new_name}")
        conn.close()
        
        return {"message": f"カラム '{column_name}' を '{new_name}' に変更しました"}
        
    except Exception as e:
        logger.error(f"カラム名変更エラー: {e}")
        raise HTTPException(status_code=500, detail=f"カラム名変更エラー: {str(e)}")

@app.put("/table/{table_name}/rename")
async def rename_table(table_name: str, new_name: str = Body(..., embed=True)):
    """テーブル名を変更する"""
    try:
        conn = get_db_connection()
        # 現在の実テーブル名を解決
        resolved = _resolve_table_name(conn, table_name)

        # 既存衝突チェック
        exists = conn.execute("SHOW TABLES").fetchall()
        existing_names = {row[0] for row in exists}
        # 目標名はURLエンコードせず、そのまま識別子として扱う（必ずクオートする）
        if new_name in existing_names:
            conn.close()
            raise HTTPException(status_code=400, detail="同名のテーブルが既に存在します")

        # リネーム
        conn.execute(f'ALTER TABLE "{resolved}" RENAME TO "{new_name}"')
        conn.close()

        return {"message": "テーブル名を変更しました", "old": resolved, "new": new_name}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"テーブル名変更エラー: {e}")
        raise HTTPException(status_code=500, detail=f"テーブル名変更エラー: {str(e)}")

@app.get("/table/{table_name}/metadata")
async def get_table_metadata(table_name: str):
    """テーブルのメタデータを取得"""
    try:
        conn = get_db_connection()
        resolved = _resolve_table_name(conn, table_name)
        
        # テーブル情報を取得
        result = conn.execute(f"SELECT COUNT(*) FROM \"{resolved}\"").fetchone()
        row_count = result[0]
        
        # スキーマ情報を取得
        schema_result = conn.execute(f"DESCRIBE \"{resolved}\"").fetchall()
        columns = [{"name": row[0], "type": row[1]} for row in schema_result]
        
        # テーブルコメントを取得
        try:
            table_comment_result = conn.execute(f"SELECT comment FROM duckdb_tables() WHERE table_name = '{resolved}'").fetchone()
            table_comment = table_comment_result[0] if table_comment_result and table_comment_result[0] else ""
        except:
            table_comment = ""
        
        # カラムコメントを取得
        try:
            column_comments_result = conn.execute(f"""
                SELECT column_name, comment 
                FROM duckdb_columns() 
                WHERE table_name = '{resolved}' AND comment IS NOT NULL
            """).fetchall()
            column_comments = {row[0]: row[1] for row in column_comments_result}
        except:
            column_comments = {}
        
        # カラム情報にコメントを追加
        for column in columns:
            column["comment"] = column_comments.get(column["name"], "")
        
        conn.close()
        
        return {
            "table": resolved,
            "row_count": row_count,
            "table_comment": table_comment,
            "columns": columns
        }
        
    except Exception as e:
        logger.error(f"メタデータ取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"メタデータ取得エラー: {str(e)}")

@app.put("/table/{table_name}/comment")
async def update_table_comment(table_name: str, comment: str):
    """テーブルのコメントを更新"""
    try:
        conn = get_db_connection()
        conn.execute(f"COMMENT ON TABLE \"{table_name}\" IS '{comment}'")
        conn.close()
        
        return {"message": f"テーブル '{table_name}' のコメントを更新しました", "comment": comment}
        
    except Exception as e:
        logger.error(f"テーブルコメント更新エラー: {e}")
        raise HTTPException(status_code=500, detail=f"テーブルコメント更新エラー: {str(e)}")

@app.put("/table/{table_name}/column/{column_name}/comment")
async def update_column_comment(table_name: str, column_name: str, comment: str):
    """カラムのコメントを更新"""
    try:
        conn = get_db_connection()
        conn.execute(f"COMMENT ON COLUMN \"{table_name}\".{column_name} IS '{comment}'")
        conn.close()
        
        return {"message": f"カラム '{column_name}' のコメントを更新しました", "comment": comment}
        
    except Exception as e:
        logger.error(f"カラムコメント更新エラー: {e}")
        raise HTTPException(status_code=500, detail=f"カラムコメント更新エラー: {str(e)}")

@app.delete("/table/{table_name}")
async def delete_table(table_name: str):
    """テーブルを削除"""
    try:
        conn = get_db_connection()
        resolved = _resolve_table_name(conn, table_name)
        conn.execute(f"DROP TABLE IF EXISTS \"{resolved}\"")
        conn.close()
        
        return {"message": f"テーブル '{resolved}' を削除しました"}
        
    except Exception as e:
        logger.error(f"テーブル削除エラー: {e}")
        raise HTTPException(status_code=500, detail=f"テーブル削除エラー: {str(e)}")

@app.get("/download/database")
async def download_database():
    """DuckDBデータベースファイルをダウンロード"""
    try:
        # データベースファイルが存在するかチェック
        if not os.path.exists(DB_PATH):
            raise HTTPException(status_code=404, detail="データベースファイルが見つかりません")
        
        # ファイルサイズを取得
        file_size = os.path.getsize(DB_PATH)
        
        # ファイルレスポンスを返す
        return FileResponse(
            path=DB_PATH,
            filename="database.duckdb",
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=database.duckdb"}
        )
        
    except Exception as e:
        logger.error(f"データベースダウンロードエラー: {e}")
        raise HTTPException(status_code=500, detail=f"ダウンロードエラー: {str(e)}")

if __name__ == "__main__":
    # データディレクトリを作成
    Path("/app/data").mkdir(exist_ok=True)
    Path("/app/logs").mkdir(exist_ok=True)
    
    logger.info("Local DB MCP Server を起動中...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
