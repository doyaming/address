from flask import Flask, render_template, request, jsonify, redirect, url_for
import pyodbc
import mysql.connector
from datetime import datetime
import json

app = Flask(__name__)

# 資料庫配置
MYSQL_HOST = '10.7.61.88'
MYSQL_PORT = 3306
MYSQL_USER = 't12652'
MYSQL_PASSWORD = 't12652'
MYSQL_DATABASE = 'address'


def get_mysql_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )

def get_db_connection():
    connection_string = (
        f'DRIVER={{ODBC Driver 18 for SQL Server}};'
        f'SERVER=10.6.2.18,1433;'
        f'DATABASE=ExamineServer3;'
        f'UID=examineuser;'
        f'PWD=123456;'
        f'TrustServerCertificate=yes;'
        'Timeout=30;'
    )
    return pyodbc.connect(connection_string)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_records():
    try:
        search_value = request.form.get('search_value', '').strip()
        search_type = request.form.get('search_type', 'barcode')
        
        if not search_value:
            return jsonify({'error': '請輸入查詢條件'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if search_type == 'barcode':
            query = """
                SELECT BarCodeStr, ProjectNo, AnamnesisNo, Name, ID 
                FROM CheckProjectNameList 
                WHERE BarCodeStr = ?
            """
            cursor.execute(query, (search_value,))
            records = cursor.fetchall()
        else:  # search_type == 'id'
            # 先查詢所有符合身分證號的記錄
            query = """
                SELECT BarCodeStr, ProjectNo, AnamnesisNo, Name, ID 
                FROM CheckProjectNameList 
                WHERE ID = ?
            """
            cursor.execute(query, (search_value,))
            initial_records = cursor.fetchall()
            
            if not initial_records:
                cursor.close()
                conn.close()
                return jsonify({'error': '查無資料'}), 404
            
            # 如果只有一筆記錄，直接返回
            if len(initial_records) == 1:
                records = initial_records
            else:
                # 有多筆記錄，需要根據 EditDate 選擇最新的一筆
                # 過濾掉可能的 None 記錄並提取 ProjectNo (索引1)
                project_nos = []
                for record in initial_records:
                    if record and len(record) > 1 and record[1]:
                        project_nos.append(record[1])
                
                if not project_nos:
                    # 如果沒有有效的 ProjectNo，返回第一筆記錄
                    records = [initial_records[0]]
                else:
                    # 查詢 CheckProject 表的 EditDate
                    placeholders = ','.join(['?' for _ in project_nos])
                    edit_date_query = f"""
                        SELECT ProjectNo, EditDate 
                        FROM CheckProject 
                        WHERE ProjectNo IN ({placeholders})
                        ORDER BY EditDate DESC
                    """
                    cursor.execute(edit_date_query, tuple(project_nos))
                    edit_date_records = cursor.fetchall()
                    
                    if edit_date_records and edit_date_records[0]:
                        # 選擇EditDate最新的ProjectNo
                        latest_project_no = edit_date_records[0][0]  # ProjectNo在索引0
                        
                        # 從原始記錄中找到對應的記錄
                        records = []
                        for record in initial_records:
                            if record and len(record) > 1 and record[0] == latest_project_no:
                                records.append(record)
                        
                        # 如果沒找到對應記錄，返回第一筆
                        if not records:
                            records = [initial_records[0]]
                    else:
                        # 如果無法從CheckProject取得EditDate，就返回第一筆
                        records = [initial_records[0]]
        
        if not records:
            cursor.close()
            conn.close()
            return jsonify({'error': '查無資料'}), 404
        
        # 轉換成字典格式
        result = []
        for record in records:
            result.append({
                'BarCodeStr': record[0],
                'ProjectNo': record[1],
                'AnamnesisNo': record[2],
                'Name': record[3],
                'ID': record[4]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({'records': result})
        
    except Exception as e:
        return jsonify({'error': f'資料庫查詢錯誤: {str(e)}'}), 500

@app.route('/submit_address', methods=['POST'])
def submit_address():
    mysql_conn = None
    mysql_cursor = None
    sqlserver_conn = None
    sqlserver_cursor = None
    
    try:
        # 獲取表單資料
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '未收到資料'}), 400
        
        # 檢查必要欄位
        required_fields = ['BarCodeStr', 'ProjectNo', 'AnamnesisNo', 'Name', 'address']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'缺少必要欄位: {field}'}), 400
        
        # 組合完整地址（不包含道路名稱和備註）
        full_address = f"{data.get('zipCode', '')}{data.get('city', '')}{data.get('district', '')}{data.get('address', '')}"
        
        # 儲存到 MySQL
        mysql_conn = get_mysql_connection()
        mysql_cursor = mysql_conn.cursor(buffered=True)  # 使用 buffered cursor
        
        # 檢查address資料庫是否存在，不存在則創建
        mysql_cursor.execute("CREATE DATABASE IF NOT EXISTS address")
        try:
            mysql_cursor.fetchall()  # 清空結果集
        except:
            pass
        
        mysql_cursor.execute("USE address")
        try:
            mysql_cursor.fetchall()  # 清空結果集
        except:
            pass
        
        # 檢查addressdate表是否存在，不存在則創建
        create_table_query = """
        CREATE TABLE IF NOT EXISTS addressdate (
            id INT AUTO_INCREMENT PRIMARY KEY,
            BarCodeStr VARCHAR(50),
            ProjectNo VARCHAR(50),
            AnamnesisNo VARCHAR(50),
            Name VARCHAR(100),
            Address TEXT,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        mysql_cursor.execute(create_table_query)
        try:
            mysql_cursor.fetchall()  # 清空結果集
        except:
            pass
        
        # 檢查remark欄位是否存在，不存在則新增
        try:
            mysql_cursor.execute("SHOW COLUMNS FROM addressdate LIKE 'remark'")
            remark_exists = mysql_cursor.fetchone()
            if not remark_exists:
                mysql_cursor.execute("ALTER TABLE addressdate ADD COLUMN remark TEXT")
                try:
                    mysql_cursor.fetchall()  # 清空結果集
                except:
                    pass
        except mysql.connector.Error as e:
            print(f"警告：處理remark欄位時發生錯誤: {e}")
        
        # 檢查updated_at欄位是否存在，不存在則新增
        try:
            mysql_cursor.execute("SHOW COLUMNS FROM addressdate LIKE 'updated_at'")
            updated_at_exists = mysql_cursor.fetchone()
            if not updated_at_exists:
                mysql_cursor.execute("ALTER TABLE addressdate ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
                try:
                    mysql_cursor.fetchall()  # 清空結果集
                except:
                    pass
        except mysql.connector.Error as e:
            print(f"警告：處理updated_at欄位時發生錯誤: {e}")
        
        # 檢查是否已存在相同的 BarCodeStr
        check_query = "SELECT id FROM addressdate WHERE BarCodeStr = %s"
        mysql_cursor.execute(check_query, (data['BarCodeStr'],))
        existing_record = mysql_cursor.fetchone()
        
        if existing_record:
            # 如果存在，執行更新
            update_query = """
            UPDATE addressdate 
            SET ProjectNo = %s, AnamnesisNo = %s, Name = %s, Address = %s, remark = %s, updated_at = CURRENT_TIMESTAMP
            WHERE BarCodeStr = %s
            """
            mysql_cursor.execute(update_query, (
                data['ProjectNo'],
                data['AnamnesisNo'],
                data['Name'],
                full_address,
                data.get('notes', ''),
                data['BarCodeStr']
            ))
            try:
                mysql_cursor.fetchall()  # 清空結果集
            except:
                pass
            mysql_message = '地址資料已成功更新'
        else:
            # 如果不存在，執行插入
            insert_query = """
            INSERT INTO addressdate (BarCodeStr, ProjectNo, AnamnesisNo, Name, Address, remark)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            mysql_cursor.execute(insert_query, (
                data['BarCodeStr'],
                data['ProjectNo'],
                data['AnamnesisNo'],
                data['Name'],
                full_address,
                data.get('notes', '')
            ))
            try:
                mysql_cursor.fetchall()  # 清空結果集
            except:
                pass
            mysql_message = '地址資料已成功儲存'
        
        mysql_conn.commit()
        
        # MySQL儲存成功後，更新SQL Server的CheckProjectNameList表
        try:
            sqlserver_conn = get_db_connection()
            sqlserver_cursor = sqlserver_conn.cursor()
            
            # 更新SQL Server的CheckProjectNameList表中的Address和ReportSendAddress欄位
            update_sqlserver_query = """
                UPDATE CheckProjectNameList 
                SET Address = ?, ReportSendAddress = ? 
                WHERE BarCodeStr = ?
            """
            sqlserver_cursor.execute(update_sqlserver_query, (full_address, full_address, data['BarCodeStr']))
            
            # 檢查是否有資料被更新
            if sqlserver_cursor.rowcount > 0:
                sqlserver_conn.commit()
                sqlserver_message = f', 伊克希曼地址欄位已更新({sqlserver_cursor.rowcount}筆)'
            else:
                sqlserver_message = ', 但在SQL Server中未找到對應的BarCodeStr記錄'
            
        except Exception as sqlserver_error:
            # 如果SQL Server更新失敗，記錄錯誤但不影響MySQL的成功結果
            print(f"SQL Server更新錯誤: {sqlserver_error}")
            sqlserver_message = f', 但SQL Server更新失敗: {str(sqlserver_error)}'
        
        return jsonify({
            'success': True, 
            'message': mysql_message + sqlserver_message
        })
        
    except Exception as e:
        if mysql_conn:
            mysql_conn.rollback()
        return jsonify({'error': f'儲存錯誤: {str(e)}'}), 500
    
    finally:
        # 確保資源被正確釋放
        try:
            if mysql_cursor:
                mysql_cursor.close()
            if mysql_conn:
                mysql_conn.close()
            if sqlserver_cursor:
                sqlserver_cursor.close()
            if sqlserver_conn:
                sqlserver_conn.close()
        except:
            pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6001)