#!/usr/bin/env python3
"""
MCPサーバーのテストスクリプト

MCPサーバーが正常に動作するかをテストします。
"""

import asyncio
import json
import sys
from pathlib import Path

# MCPサーバーをインポート
from mcp_server import LocalDBMCPServer

async def test_mcp_server():
    """MCPサーバーのテストを実行"""
    print("🧪 MCPサーバーのテストを開始します...")
    
    # サーバーインスタンスを作成
    server = LocalDBMCPServer()
    
    # テスト用のツール呼び出しをシミュレート
    test_cases = [
        {
            "name": "list_tables",
            "args": {},
            "description": "テーブル一覧の取得"
        },
        {
            "name": "execute_query",
            "args": {"query": "SELECT COUNT(*) FROM test_data"},
            "description": "SQLクエリの実行"
        },
        {
            "name": "execute_query",
            "args": {"query": "SELECT * FROM test_data LIMIT 3"},
            "description": "テーブルデータの取得"
        }
    ]
    
    # 各テストケースを実行
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 テスト {i}: {test_case['description']}")
        print(f"   ツール: {test_case['name']}")
        print(f"   引数: {test_case['args']}")
        
        try:
            # ツールを呼び出し
            if test_case['name'] == "list_tables":
                result = await server._list_tables()
            elif test_case['name'] == "execute_query":
                query = test_case['args']['query']
                limit = test_case['args'].get('limit', 100)
                result = await server._execute_query(query, limit)
            else:
                print(f"   ❌ エラー: 未知のツール: {test_case['name']}")
                continue
            
            if result:
                print(f"   ✅ 成功: {len(result)} 件の結果を取得")
                # 最初の結果の一部を表示
                if result[0].text:
                    preview = result[0].text[:200] + "..." if len(result[0].text) > 200 else result[0].text
                    print(f"   📄 結果プレビュー: {preview}")
            else:
                print(f"   ⚠️  警告: 結果が空です")
                
        except Exception as e:
            print(f"   ❌ エラー: {str(e)}")
    
    print(f"\n🎉 テスト完了!")

async def test_database_connection():
    """データベース接続のテスト"""
    print("\n🔗 データベース接続のテスト...")
    
    try:
        server = LocalDBMCPServer()
        conn = await server._get_connection()
        
        # 簡単なクエリを実行
        result = conn.execute("SELECT 1 as test").fetchone()
        conn.close()
        
        if result and result[0] == 1:
            print("   ✅ データベース接続成功")
            return True
        else:
            print("   ❌ データベース接続失敗")
            return False
            
    except Exception as e:
        print(f"   ❌ データベース接続エラー: {str(e)}")
        return False

async def main():
    """メイン関数"""
    print("🚀 Local DB MCP Server テスト")
    print("=" * 50)
    
    # データベース接続テスト
    db_ok = await test_database_connection()
    
    if db_ok:
        # MCPサーバーテスト
        await test_mcp_server()
    else:
        print("\n❌ データベース接続に失敗したため、MCPサーバーのテストをスキップします。")
        print("   データベースファイルが存在することを確認してください。")

if __name__ == "__main__":
    asyncio.run(main())