// メインのJavaScript機能

document.addEventListener('DOMContentLoaded', function() {
    // アップロードフォームの処理
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFileUpload);
    }
    
    // ファイル選択時の処理
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelect);
    }
    
    // テーブル一覧の読み込み
    if (document.getElementById('tables')) {
        loadTables();
    }
});

async function handleFileUpload(e) {
    e.preventDefault();
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    
    if (!file) {
        showResult('ファイルを選択してください。', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            let message = `✅ アップロード成功！<br>ファイル: ${file.name}<br>`;
            
            if (result.imported_tables) {
                // DuckDBファイルの場合
                message += `インポートされたテーブル数: ${result.row_count}<br>`;
                if (result.imported_tables.length > 0) {
                    message += `テーブル: ${result.imported_tables.join(', ')}`;
                }
            } else {
                // CSV/TSVファイルの場合
                message += `テーブル名: ${result.table_name}<br>行数: ${result.row_count}`;
            }
            
            showResult(message, 'success');
            loadTables(); // AIが参照できるデータ一覧を更新
            
            // ファイル入力をリセット
            document.getElementById('fileInput').value = '';
            document.getElementById('uploadButton').style.display = 'none';
        } else {
            showResult(`❌ エラー: ${result.detail}`, 'error');
        }
    } catch (error) {
        showResult(`❌ エラー: ${error.message}`, 'error');
    }
}

function handleFileSelect() {
    const fileInput = document.getElementById('fileInput');
    const uploadButton = document.getElementById('uploadButton');
    
    if (fileInput.files.length > 0) {
        uploadButton.style.display = 'inline-block';
    } else {
        uploadButton.style.display = 'none';
    }
}

function showResult(message, type) {
    const resultDiv = document.getElementById('result');
    if (resultDiv) {
        resultDiv.innerHTML = `<div class="result ${type}">${message}</div>`;
    }
}

async function loadTables() {
    try {
        const response = await fetch('/tables');
        const data = await response.json();
        
        const tablesDiv = document.getElementById('tables');
        if (!tablesDiv) return;
        
        if (data.tables.length === 0) {
            tablesDiv.innerHTML = '<p>テーブルがありません。</p>';
            return;
        }
        
        let html = '<table><tr><th>テーブル名</th><th>説明</th></tr>';
        for (const table of data.tables) {
            // 各テーブルのメタデータを取得
            try {
                const metaResponse = await fetch(`/table/${table.name}/metadata`);
                const metaData = await metaResponse.json();
                const comment = metaData.table_comment || '説明なし';
                const rowCount = metaData.row_count;
                
                // 表示名を使用（日本語対応）
                const displayName = table.display_name || table.name;
                
                html += `<tr>
                        <td><strong><a href="/table/${table.name}">${displayName}</a></strong></td>
                        <td>${comment}</td>
                        </tr>`;
            } catch (error) {
                const displayName = table.display_name || table.name;
                html += `<tr>
                        <td>${displayName}</td>
                        <td>エラー</td>
                        </tr>`;
            }
        }
        html += '</table>';
        tablesDiv.innerHTML = html;
    } catch (error) {
        const tablesDiv = document.getElementById('tables');
        if (tablesDiv) {
            tablesDiv.innerHTML = `<p>エラー: ${error.message}</p>`;
        }
    }
}

// 削除ダイアログ関連の機能
async function showDeleteDialog() {
    try {
        const response = await fetch('/tables');
        const data = await response.json();
        
        const tableSelect = document.getElementById('tableSelect');
        tableSelect.innerHTML = '<option value="">テーブルを選択してください</option>';
        
        for (const table of data.tables) {
            const displayName = table.display_name || table.name;
            const option = document.createElement('option');
            option.value = table.name;
            option.textContent = displayName;
            tableSelect.appendChild(option);
        }
        
        document.getElementById('deleteDialog').style.display = 'flex';
    } catch (error) {
        showResult(`❌ エラー: ${error.message}`, 'error');
    }
}

function closeDeleteDialog() {
    document.getElementById('deleteDialog').style.display = 'none';
    document.getElementById('tableSelect').value = '';
}

async function confirmDeleteTable() {
    const tableSelect = document.getElementById('tableSelect');
    const selectedTable = tableSelect.value;
    
    if (!selectedTable) {
        alert('削除するテーブルを選択してください。');
        return;
    }
    
    const displayName = tableSelect.options[tableSelect.selectedIndex].textContent;
    
    if (confirm(`テーブル "${displayName}" を削除しますか？\nこの操作は取り消せません。`)) {
        try {
            const response = await fetch(`/table/${selectedTable}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                showResult(`✅ テーブル "${displayName}" を削除しました`, 'success');
                loadTables(); // テーブル一覧を更新
                closeDeleteDialog();
            } else {
                const result = await response.json();
                showResult(`❌ エラー: ${result.detail}`, 'error');
            }
        } catch (error) {
            showResult(`❌ エラー: ${error.message}`, 'error');
        }
    }
}

// データベースダウンロード機能
async function downloadDatabase() {
    try {
        const response = await fetch('/download/database');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'database.duckdb';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showResult('✅ データベースファイルをダウンロードしました', 'success');
        } else {
            const result = await response.json();
            showResult(`❌ エラー: ${result.detail}`, 'error');
        }
    } catch (error) {
        showResult(`❌ エラー: ${error.message}`, 'error');
    }
}
