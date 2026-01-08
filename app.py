import os
import sqlite3
import random
import requests
from flask import Flask, render_template, request, session, redirect, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aing_master_key_777")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

GRADE_DATA = {
    "브론즈": {"rate": 0.08, "limit": 1000000, "up_cost": 10000000, "next": "실버"},
    "실버": {"rate": 0.06, "limit": 10000000, "up_cost": 50000000, "next": "골드"},
    "골드": {"rate": 0.05, "limit": 50000000, "up_cost": 200000000, "next": "플래티넘"},
    "플래티넘": {"rate": 0.04, "limit": 200000000, "up_cost": 1000000000, "next": "다이아"},
    "다이아": {"rate": 0.02, "limit": 1000000000, "up_cost": 0, "next": None}
}

def get_db():
    conn = sqlite3.connect('economy.db')
    conn.row_factory = sqlite3.Row
    return conn

def send_alert(title, msg, color=0xff79c6):
    if not DISCORD_WEBHOOK_URL: return
    payload = {"embeds": [{"title": title, "description": msg, "color": color}]}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

@app.route('/')
def index():
    if 'user_id' not in session: return "로그인이 필요합니다."
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    all_users = db.execute('SELECT id, name FROM users').fetchall()
    db.close()
    return render_template('main.html', user=user, all_users=all_users, GRADE_DATA=GRADE_DATA)

# --- [은행 통합 API] ---
@app.route('/api/bank', methods=['POST'])
def bank_api():
    data = request.json
    action = data.get('action')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    try:
        if action == 'send': # 송금
            amt = int(data['amount'])
            to_id = data['to_id']
            if user['money'] < amt: return jsonify({"error": "잔액 부족"}), 400
            fee = int(amt * 0.1)
            db.execute('UPDATE users SET money=money-? WHERE id=?', (amt, user['id']))
            db.execute('UPDATE users SET money=money+? WHERE id=?', (amt-fee, to_id))
            send_alert("💸 송금", f"**{user['name']}** -> 상대방\n금액: {amt:,}원 (수수료 {fee:,}원)")

        elif action == 'loan': # 대출
            amt = int(data['amount'])
            limit = GRADE_DATA[user['grade']]['limit']
            if user['loan'] + amt > limit: return jsonify({"error": "한도 초과"}), 400
            db.execute('UPDATE users SET money=money+?, loan=loan+? WHERE id=?', (amt, amt, user['id']))
            send_alert("🏦 대출", f"**{user['name']}**님이 {amt:,}원을 빌렸습니다.")

        elif action == 'repay': # 상환
            amt = int(data['amount'])
            if user['money'] < amt or user['loan'] < amt: return jsonify({"error": "금액 오류"}), 400
            db.execute('UPDATE users SET money=money-?, loan=loan-? WHERE id=?', (amt, amt, user['id']))
            send_alert("✅ 상환", f"**{user['name']}**님이 {amt:,}원을 갚았습니다.")

        elif action == 'upgrade': # 등급 구매
            info = GRADE_DATA[user['grade']]
            if user['money'] < info['up_cost']: return jsonify({"error": "돈 부족"}), 400
            db.execute('UPDATE users SET money=money-?, grade=? WHERE id=?', (info['up_cost'], info['next'], user['id']))
            send_alert("👑 승급", f"**{user['name']}**님이 **{info['next']}** 등급을 구매!")

        db.commit()
        return jsonify({"msg": "성공적으로 처리되었습니다."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# --- [카지노 통합 API] ---
@app.route('/api/casino/slot', methods=['POST'])
def slot_api():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    bet = int(request.json['bet'])
    if user['money'] < bet: return jsonify({"error": "잔액 부족"}), 400
    
    syms = ["🍒", "🍋", "🍊", "🔔", "💎", "7️⃣", "💩"]
    res = [random.choice(syms) for _ in range(3)]
    
    u_cnt = len(set(res))
    win = 0
    if u_cnt == 1:
        if res[0] == "7️⃣": win = bet * 50
        elif res[0] == "💩": win = bet * -2 # 2배 압수
        else: win = bet * 10
    elif u_cnt == 2: win = int(bet * 1.5)
    
    db.execute('UPDATE users SET money=money-?+? WHERE id=?', (bet, win, user['id']))
    db.commit()
    db.close()
    return jsonify({"results": res, "win": win})

if __name__ == '__main__':
    app.run(debug=True)