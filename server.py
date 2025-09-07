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
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
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
        
        # DuckDBに接続してテーブルを作成
        conn = get_db_connection()
        
        # ファイル形式に応じて一時ファイルを作成
        if file.filename.endswith('.duckdb'):
            # DuckDBファイルはバイナリなので直接保存
            with tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb') as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
        else:
            # CSV/TSVファイルはテキストとして保存
            try:
                content_str = content.decode('utf-8')
            except UnicodeDecodeError:
                # UTF-8でデコードできない場合はShift_JISを試す
                try:
                    content_str = content.decode('shift_jis')
                except UnicodeDecodeError:
                    # それでもダメな場合はエラー
                    raise HTTPException(status_code=400, detail="ファイルの文字エンコーディングがサポートされていません。UTF-8またはShift_JISで保存してください。")
            
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
            
            # テーブル情報を取得
            result = conn.execute(f"SELECT COUNT(*) as count FROM \"{table_name}\"").fetchone()
            
        finally:
            # 一時ファイルを削除
            os.unlink(temp_file_path)
        
        conn.close()
        
        return {
            "message": f"ファイル '{file.filename}' が正常にアップロードされました",
            "table_name": table_name,
            "original_table_name": original_table_name,
            "row_count": result[0]
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
        result = conn.execute(f"SELECT * FROM \"{table_name}\" LIMIT {limit}").fetchall()
        columns = [desc[0] for desc in conn.description]
        conn.close()
        
        data = [dict(zip(columns, row)) for row in result]
        return {"table": table_name, "data": data, "limit": limit}
        
    except Exception as e:
        logger.error(f"クエリエラー: {e}")
        raise HTTPException(status_code=500, detail=f"クエリエラー: {str(e)}")

@app.get("/table/{table_name}/schema")
async def get_table_schema(table_name: str):
    """テーブルのスキーマ情報を取得"""
    try:
        conn = get_db_connection()
        result = conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()
        conn.close()
        
        schema = [{"column": row[0], "type": row[1], "null": row[2], "key": row[3], "default": row[4], "extra": row[5]} for row in result]
        return {"table": table_name, "schema": schema}
        
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

@app.get("/table/{table_name}/metadata")
async def get_table_metadata(table_name: str):
    """テーブルのメタデータを取得"""
    try:
        conn = get_db_connection()
        
        # テーブル情報を取得
        result = conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()
        row_count = result[0]
        
        # スキーマ情報を取得
        schema_result = conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()
        columns = [{"name": row[0], "type": row[1]} for row in schema_result]
        
        # テーブルコメントを取得
        try:
            table_comment_result = conn.execute(f"SELECT comment FROM duckdb_tables() WHERE table_name = '{table_name}'").fetchone()
            table_comment = table_comment_result[0] if table_comment_result and table_comment_result[0] else ""
        except:
            table_comment = ""
        
        # カラムコメントを取得
        try:
            column_comments_result = conn.execute(f"""
                SELECT column_name, comment 
                FROM duckdb_columns() 
                WHERE table_name = '{table_name}' AND comment IS NOT NULL
            """).fetchall()
            column_comments = {row[0]: row[1] for row in column_comments_result}
        except:
            column_comments = {}
        
        # カラム情報にコメントを追加
        for column in columns:
            column["comment"] = column_comments.get(column["name"], "")
        
        conn.close()
        
        return {
            "table": table_name,
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
        conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
        conn.close()
        
        return {"message": f"テーブル '{table_name}' を削除しました"}
        
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
