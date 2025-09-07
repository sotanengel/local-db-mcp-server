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
                Tool(name="execute_query", description="SQLクエリを実行", inputSchema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                    "required": ["query"]
                })
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            if name == "execute_query":
                query = arguments.get("query")
                limit = arguments.get("limit", 100)
                return await self._execute_query(query, limit)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _get_connection(self):
        try:
            return duckdb.connect(self.db_path)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def _execute_query(self, query: str, limit: int) -> List[TextContent]:
        try:
            conn = await self._get_connection()
            
            # SELECT文にLIMITを追加
            if query.strip().upper().startswith("SELECT") and "LIMIT" not in query.upper():
                query = f"{query.rstrip(';')} LIMIT {limit}"
            
            result = conn.execute(query).fetchall()
            columns = [desc[0] for desc in conn.description] if conn.description else []
            conn.close()
            
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
            logger.error(f"Error executing query: {e}")
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
