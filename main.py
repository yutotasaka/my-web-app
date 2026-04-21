import os
import json
import random
import sys
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
# セッションの暗号化キー（Render等の環境変数から取得、なければデフォルト）
app.secret_key = os.environ.get("SECRET_KEY", "nichiren_quiz_ultimate_key")

# --- パス設定 (exe化対策) ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")

# --- ユーティリティ関数 ---
def load_json(path):
    """JSONファイルを読み込む補助関数"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read().strip() or "{}")
    except:
        return {}

def get_user_stats():
    """ユーザーの累計正解数に基づいた形態とステータスを計算"""
    total_score = session.get('total_score', 0)
    
    # 形態進化の定義（閾値は適宜調整してください）
    if total_score >= 125:
        form, time, lives = "最終形態", 30, 7
    elif total_score >= 80:
        form, time, lives = "第４形態", 15, 4
    elif total_score >= 50:
        form, time, lives = "第３形態", 10, 3
    elif total_score >= 20:
        form, time, lives = "第２形態", 7, 2
    else:
        form, time, lives = "第１形態", 5, 1

    # 次の進化までの残り数
    thresholds = [20, 50, 80, 125]
    next_evol = next((t - total_score for t in thresholds if total_score < t), 0)

    return {
        "form_name": form,
        "time_limit": time,
        "max_lives": lives,
        "total_score": total_score,
        "next_evolution": next_evol
    }

# --- ルート定義 ---

@app.route('/')
def index():
    """メインメニュー画面"""
    if 'user_name' not in session:
        return render_template('login.html')
    
    user_stats = get_user_stats()
    return render_template('index.html', user_name=session['user_name'], user_stats=user_stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user_name'] = request.form.get('user_name', 'ゲスト')
        session['total_score'] = session.get('total_score', 0)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/start/<category>')
def start_quiz(category):
    """章別学習開始（全問題を出題）"""
    if 'user_name' not in session: 
        return redirect(url_for('login'))
    
    questions_data = load_json(QUESTIONS_FILE)
    category_data = questions_data.get(category, [])
    
    if not category_data:
        return redirect(url_for('index'))

    # 全問題のIDを取得してシャッフル
    ids = [q['id'] for q in category_data]
    random.shuffle(ids)
    
    session.update({
        'question_ids': ids, 
        'current_index': 0, 
        'score': 0, 
        'mode': 'study', 
        'category': category
    })
    return redirect(url_for('quiz_page'))

@app.route('/quiz')
def quiz_page():
    """クイズ表示画面"""
    if 'question_ids' not in session:
        return redirect(url_for('index'))
    
    idx = session['current_index']
    ids = session['question_ids']
    
    # 全て解き終わったら結果画面へ
    if idx >= len(ids):
        return redirect(url_for('result'))

    # 現在の問題データを特定
    questions_data = load_json(QUESTIONS_FILE)
    current_id = ids[idx]
    current_q = None
    for cat_list in questions_data.values():
        for q in cat_list:
            if q['id'] == current_id:
                current_q = q
                break
    
    user_stats = get_user_stats()
    return render_template('quiz.html', question=current_q, stats=user_stats, index=idx+1)

@app.route('/answer', methods=['POST'])
def answer():
    """回答判定（音は鳴らさず、フラグを渡してHTML/JSに鳴らさせる）"""
    user_ans = request.form.get('answer')
    q_id = request.form.get('question_id')
    
    questions_data = load_json(QUESTIONS_FILE)
    current_q = None
    for cat_list in questions_data.values():
        for q in cat_list:
            if q['id'] == q_id:
                current_q = q
                break
    
    if not current_q:
        return redirect(url_for('index'))

    # 判定
    is_correct = False
    if current_q['type'] == 'choice':
        is_correct = (str(user_ans) == str(current_q['answer']))
    else:
        # 記述式：リスト形式と文字列形式の両方に対応
        answers = current_q['answer'] if isinstance(current_q['answer'], list) else [current_q['answer']]
        is_correct = (user_ans.strip() in [str(a).strip() for a in answers])

    if is_correct:
        session['score'] = session.get('score', 0) + 1
        session['total_score'] = session.get('total_score', 0) + 1

    # 正解テキストの準備
    if current_q['type'] == 'choice':
        correct_text = current_q['options'][int(current_q['answer'])]
    else:
        correct_text = current_q['answer'][0] if isinstance(current_q['answer'], list) else current_q['answer']

    return render_template('quiz.html', 
                           question=current_q, 
                           is_correct=is_correct, 
                           is_judged=True,
                           correct_text=correct_text,
                           commentary=current_q.get('commentary', '解説はありません。'),
                           stats=get_user_stats())

@app.route('/next')
def next_question():
    session['current_index'] = session.get('current_index', 0) + 1
    return redirect(url_for('quiz_page'))

@app.route('/result')
def result():
    """結果表示"""
    score = session.get('score', 0)
    total = len(session.get('question_ids', []))
    return render_template('result.html', score=score, total=total)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 実行ポートをRender等に合わせて変更可能に
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)