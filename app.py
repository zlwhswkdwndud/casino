import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

def get_db_connection():
    db_path = os.path.join(os.getcwd(), 'economy.db')
    conn = sqlite3.connect(db_path)
    # 데이터를 딕셔너리 형태로 가져오게 설정
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    users_list = []
    error_msg = None
    try:
        conn = get_db_connection()
        # 유저 테이블이 있는지 확인하고 데이터 가져오기
        cursor = conn.execute("SELECT name, money FROM users ORDER BY money DESC LIMIT 10")
        users_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        error_msg = "아직 등록된 유저가 없거나 데이터베이스를 생성 중입니다."
    
    return render_template('main.html', users=users_list, error=error_msg)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
