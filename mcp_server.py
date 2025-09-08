#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import sys
import duckdb
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from typing import Any, Dict, List

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = "/app/data/database.duckdb"

class LocalDBMCPServer:
    def __init__(self):
        self.server = Server("local-db-mcp-server")
        self.db_path = DATABASE_PATH
        self._setup_handlers()

    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            return [
                Tool(
                    name="execute_query", 
                    description="Execute a SQL query against the local DuckDB database. For SELECT statements, you can optionally specify 'limit' to cap the number of returned rows (default: 100). The result is returned as a formatted table in text.",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_table_info",
                    description="Retrieve information about database tables. If 'table_name' is provided, returns detailed schema information (columns, data types, nullability, default values) and the row count for that table. If omitted, returns a list of all tables in the database with their row counts.",
                    inputSchema={
                        "type": "object",
                        "properties": {"table_name": {"type": "string"}},
                        "required": []
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            if name == "execute_query":
                query = arguments.get("query")
                limit = arguments.get("limit", 100)
                return await self._execute_query(query, limit)
            elif name == "get_table_info":
                table_name = arguments.get("table_name")
                return await self._get_table_info(table_name)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _get_connection(self):
        try:
            return duckdb.connect(self.db_path)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def _get_table_info(self, table_name: str = None) -> List[TextContent]:
        try:
            logger.info(f"Getting table info for: {table_name or 'all tables'}")
            conn = await self._get_connection()
            
            if table_name:
                # 特定のテーブルの詳細情報を取得
                # テーブルが存在するかチェック
                tables_result = conn.execute("SHOW TABLES").fetchall()
                table_names = [row[0] for row in tables_result]
                
                if table_name not in table_names:
                    conn.close()
                    return [TextContent(type="text", text=f"テーブル '{table_name}' が見つかりません。\n利用可能なテーブル: {', '.join(table_names) if table_names else 'なし'}")]
                
                # テーブルの詳細情報を取得
                columns_info = conn.execute(f"DESCRIBE {table_name}").fetchall()
                row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                
                response = [f"## テーブル: {table_name}\n"]
                response.append(f"**行数**: {row_count:,}\n")
                response.append("### カラム情報\n")
                response.append("```")
                response.append("| カラム名 | データ型 | NULL許可 | デフォルト値 |")
                response.append("|----------|----------|----------|--------------|")
                
                for col in columns_info:
                    col_name = col[0]
                    col_type = col[1]
                    nullable = "YES" if col[2] else "NO"
                    default = col[3] if col[3] is not None else ""
                    response.append(f"| {col_name} | {col_type} | {nullable} | {default} |")
                
                response.append("```")
                
            else:
                # 全テーブルの一覧を取得
                tables_result = conn.execute("SHOW TABLES").fetchall()
                
                if not tables_result:
                    conn.close()
                    return [TextContent(type="text", text="データベースにテーブルがありません。")]
                
                response = ["## データベース内のテーブル一覧\n"]
                response.append("```")
                response.append("| テーブル名 | 行数 |")
                response.append("|------------|------|")
                
                for table_row in tables_result:
                    table_name = table_row[0]
                    try:
                        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                        response.append(f"| {table_name} | {row_count:,} |")
                    except Exception as e:
                        response.append(f"| {table_name} | エラー |")
                
                response.append("```")
                response.append("\n特定のテーブルの詳細情報を取得するには、`table_name`パラメータを指定してください。")
            
            conn.close()
            logger.info("Table info retrieved successfully")
            return [TextContent(type="text", text="\n".join(response))]
            
        except Exception as e:
            logger.error(f"Error getting table info: {e}")
            return [TextContent(type="text", text=f"テーブル情報の取得に失敗しました: {str(e)}")]

    async def _execute_query(self, query: str, limit: int) -> List[TextContent]:
        try:
            logger.info(f"Executing query: {query[:100]}...")
            conn = await self._get_connection()
            
            # SELECT文にLIMITを追加
            if query.strip().upper().startswith("SELECT") and "LIMIT" not in query.upper():
                query = f"{query.rstrip(';')} LIMIT {limit}"
                logger.info(f"Added LIMIT {limit} to SELECT query")
            
            result = conn.execute(query).fetchall()
            columns = [desc[0] for desc in conn.description] if conn.description else []
            conn.close()
            
            logger.info(f"Query executed successfully, returned {len(result)} rows")
            
            if not result:
                return [TextContent(type="text", text="クエリの結果がありません")]
            
            # テーブル形式で表示
            response = [f"## クエリ結果 ({len(result)}行)\n"]
            response.append("```")
            response.append("| " + " | ".join(columns) + " |")
            response.append("|" + "|".join(["---"] * len(columns)) + "|")
            
            for row in result:
                formatted_row = []
                for value in row:
                    if value is None:
                        formatted_row.append("NULL")
                    else:
                        formatted_row.append(str(value))
                response.append("| " + " | ".join(formatted_row) + " |")
            
            response.append("```")
            
            return [TextContent(type="text", text="\n".join(response))]
            
        except Exception as e:
            logger.error(f"Error executing query '{query[:50]}...': {e}")
            return [TextContent(type="text", text=f"クエリの実行に失敗しました: {str(e)}")]

    async def run(self):
        if not os.path.exists(self.db_path):
            conn = duckdb.connect(self.db_path)
            conn.close()

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="local-db-mcp-server",
                    server_version="1.0.0",
                    capabilities={
                        "tools": {}
                    }
                )
            )

async def main():
    server = LocalDBMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
