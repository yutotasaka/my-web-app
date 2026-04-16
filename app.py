from flask import Flask, render_template, request, session, redirect, url_for
import json, random, os

app = Flask(__name__)
app.secret_key = "nichiren_quiz_ultimate_game_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_FILE = os.path.join(BASE_DIR, "users.json")
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")
MAX_ENEMY_TYPE = 15 

def load_json(path):
    if not os.path.exists(path): 
        if "users.json" in path: save_json(path, {})
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read().strip() or "{}")
    except: return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_stats(name):
    users = load_json(USER_DATA_FILE)
    u_data = users.get(name, {"total_score": 0, "solved_ids": [], "max_battle_score": 0})
    total = u_data.get('total_score', 0)
    
    if total >= 125:
        form, time_limit, max_lives = "最終形態", 30, 7
    elif total >= 80:
        form, time_limit, max_lives = "第４形態", 15, 4
    elif total >= 50:
        form, time_limit, max_lives = "第３形態", 10, 3
    elif total >= 20:
        form, time_limit, max_lives = "第２形態", 7, 2
    else:
        form, time_limit, max_lives = "第１形態", 5, 1

    u_data.update({'form_name': form, 'time_limit': time_limit, 'max_lives': max_lives})
    thresholds = [20, 50, 80, 125]
    u_data['next_evolution'] = next((t - total for t in thresholds if total < t), 0)
    return u_data

def get_all_questions_flat():
    all_data = load_json(QUESTIONS_FILE)
    return [q for cat in all_data if isinstance(all_data[cat], list) for q in all_data[cat]]

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('user_name')
        if name:
            session['user_name'] = name
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/')
def index():
    if 'user_name' not in session: return redirect(url_for('login'))
    return render_template('index.html', user_name=session['user_name'], user_stats=get_user_stats(session['user_name']))

@app.route('/study_menu')
def study_menu():
    if 'user_name' not in session: return redirect(url_for('login'))
    return render_template('study_menu.html', categories=load_json(QUESTIONS_FILE).keys())

@app.route('/start/<category>')
def start_quiz(category):
    if 'user_name' not in session: return redirect(url_for('login'))
    ids = [q['id'] for q in load_json(QUESTIONS_FILE).get(category, [])]
    random.shuffle(ids)
    # new_solved_count をリセット
    session.update({'question_ids': ids[:10], 'current_index': 0, 'score': 0, 'new_solved_count': 0, 'mode': 'study', 'category': category})
    return redirect(url_for('quiz_page'))

@app.route('/start_total_study')
def start_total_study():
    if 'user_name' not in session: return redirect(url_for('login'))
    all_q = get_all_questions_flat()
    random.shuffle(all_q)
    # new_solved_count をリセット
    session.update({'question_ids': [q['id'] for q in all_q[:20]], 'current_index': 0, 'score': 0, 'new_solved_count': 0, 'mode': 'total_study', 'category': "ただの腕試し"})
    return redirect(url_for('quiz_page'))

@app.route('/battle_start')
def battle_start():
    if 'user_name' not in session: return redirect(url_for('login'))
    ids = [q['id'] for q in get_all_questions_flat()]
    random.shuffle(ids)
    # new_solved_count をリセット
    session.update({'question_ids': ids, 'current_index': 0, 'score': 0, 'new_solved_count': 0, 'miss_count': 0, 'enemy_id': 1, 'mode': 'battle', 'category': "サバイバルバトル"})
    return redirect(url_for('quiz_page'))

@app.route('/quiz', methods=['GET', 'POST'])
def quiz_page():
    if 'user_name' not in session: return redirect(url_for('login'))
    curr = session.get('current_index', 0)
    q_ids = session.get('question_ids', [])
    if not q_ids or curr >= len(q_ids):
        return end_logic(session['user_name'], session.get('score', 0), len(q_ids), False)

    q_data = next((q for q in get_all_questions_flat() if q['id'] == q_ids[curr]), None)
    user_stats = get_user_stats(session['user_name'])
    enemy_img_id = ((session.get('enemy_id', 1) - 1) % MAX_ENEMY_TYPE) + 1

    if request.method == 'POST':
        user_ans = request.form.get('answer')
        is_correct = (user_ans and user_ans != 'TIMEOUT' and (
            (q_data['type'] == 'choice' and str(user_ans) == str(q_data['answer'])) or
            (q_data['type'] != 'choice' and user_ans.strip() in (q_data['answer'] if isinstance(q_data['answer'], list) else [q_data['answer']]))
        ))

        if is_correct:
            session['score'] = session.get('score', 0) + 1
            if session.get('mode') == 'battle': session['enemy_id'] = session.get('enemy_id', 1) + 1
            
            users = load_json(USER_DATA_FILE)
            u = users.setdefault(session['user_name'], {"total_score": 0, "solved_ids": [], "max_battle_score": 0})
            
            # 新規正解の判定
            if q_data['id'] not in u['solved_ids']:
                u['total_score'] += 1
                u['solved_ids'].append(q_data['id'])
                # セッション内の新規正解数をカウントアップ
                session['new_solved_count'] = session.get('new_solved_count', 0) + 1
                save_json(USER_DATA_FILE, users)
                user_stats = get_user_stats(session['user_name'])
        else:
            if session.get('mode') == 'battle':
                session['miss_count'] = session.get('miss_count', 0) + 1
                if session['miss_count'] >= user_stats['max_lives']:
                    return end_logic(session['user_name'], session['score'], len(q_ids), True, enemy_img_id)

        correct_text = q_data['options'][int(q_data['answer'])] if q_data['type'] == 'choice' else (q_data['answer'][0] if isinstance(q_data['answer'], list) else q_data['answer'])
        return render_template('quiz.html', question=q_data, is_judged=True, is_correct=is_correct, correct_text=correct_text, commentary=q_data.get('commentary',''), index=curr+1, user_stats=user_stats, enemy_id=enemy_img_id)

    return render_template('quiz.html', question=q_data, is_judged=False, index=curr+1, user_stats=user_stats, enemy_id=enemy_img_id)

def end_logic(name, score, total, failed, enemy_id=1):
    users = load_json(USER_DATA_FILE)
    u = users.get(name, {})
    if session.get('mode') == 'battle' and score > u.get('max_battle_score', 0):
        u['max_battle_score'] = score
        save_json(USER_DATA_FILE, users)
    
    # リザルト画面に new_solved_count を渡す
    return render_template('result.html', 
                           score=score, 
                           total=total, 
                           new_solved_count=session.get('new_solved_count', 0),
                           user_stats=get_user_stats(name), 
                           failed=failed, 
                           enemy_id=enemy_id, 
                           mode=session.get('mode'))

@app.route('/next')
def next_question():
    session['current_index'] = session.get('current_index', 0) + 1
    return redirect(url_for('quiz_page'))

@app.route('/ranking')
def show_ranking():
    users = load_json(USER_DATA_FILE)
    sorted_users = sorted(users.items(), key=lambda x: x[1].get('max_battle_score', 0), reverse=True)
    return render_template('ranking.html', ranking=sorted_users)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)