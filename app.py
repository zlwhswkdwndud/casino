import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__, 
            template_folder='templates',  # 템플릿 폴더 명시
            static_folder='static')      # 혹시 모를 정적 파일 폴더 명시

# 데이터베이스 연결 함수
def get_db_connection():
    # Render 환경에서 경로 문제를 방지하기 위해 절대 경로 사용
    db_path = os.path.join(os.getcwd(), 'economy.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        # 유저 정보를 가져오는 쿼리 (방장님 DB 구조에 맞게 수정 가능)
        users = conn.execute('SELECT * FROM users ORDER BY money DESC LIMIT 10').fetchall()
        conn.close()
        return render_template('main.html', users=users)
    except Exception as e:
        # DB가 아직 없거나 테이블이 없을 경우를 대비한 안전장치
        return render_template('main.html', error=str(e), users=[])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
