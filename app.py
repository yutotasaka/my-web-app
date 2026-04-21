from flask import Flask, render_template, request, session, redirect, url_for
import json, random, os
import redis

app = Flask(__name__)
# セッションの暗号化キー（Render等の環境変数から取得、なければデフォルト）
app.secret_key = os.environ.get("SECRET_KEY", "nichiren_quiz_ultimate_game_key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")
MAX_ENEMY_TYPE = 15 

# --- Redis接続設定 ---
# Upstash等のRedis URL環境変数から取得
REDIS_URL = os.environ.get('REDIS_URL', 'rediss://default:AZ2mAAIncDExYmYzMWMwOGQ3MzI0Y2E4YmFiMGYzOTQ4MmU5YmVkN3AxNDAzNTg@rational-dinosaur-40358.upstash.io:6379')
r = redis.from_url(
    REDIS_URL, 
    decode_responses=True, 
    ssl_cert_reqs=None  # セキュリティ証明書の検証スキップ（接続エラー対策）
)

# --- ユーティリティ関数 ---
def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read().strip() or "{}")
    except: return {}

def load_json_redis(name):
    """Redisからユーザーデータを取得（なければ初期値）"""
    data = r.get(f"user:{name}")
    if data:
        return json.loads(data)
    return {"total_score": 0, "solved_ids": [], "max_battle_score": 0}

def save_json_redis(name, data):
    """Redisにユーザーデータを保存"""
    r.set(f"user:{name}", json.dumps(data, ensure_ascii=False))

def get_all_users_from_redis():
    """ランキング用に全キーを取得してデータ集計"""
    users = {}
    keys = r.keys("user:*")
    for key in keys:
        name = key.replace("user:", "")
        users[name] = load_json_redis(name)
    return users

def get_user_stats(name):
    """ユーザーの進化ステータス計算（Redisデータ基準）"""
    u_data = load_json_redis(name)
    total = u_data.get('total_score', 0)
    
    # 累計正解数による進化分岐
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
    """JSONの全カテゴリを平坦なリストにする"""
    all_data = load_json(QUESTIONS_FILE)
    questions = []
    for cat in all_data:
        if isinstance(all_data[cat], list):
            questions.extend(all_data[cat])
    return questions

# --- ルート定義 ---

@app.route('/')
def index():
    if 'user_name' not in session: return redirect(url_for('login'))
    return render_template('index.html', user_name=session['user_name'], user_stats=get_user_stats(session['user_name']))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('user_name')
        if name:
            session['user_name'] = name
            # ログイン時にRedisにデータがなければ作成（初期化）
            if not r.exists(f"user:{name}"):
                save_json_redis(name, {"total_score": 0, "solved_ids": [], "max_battle_score": 0})
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/study_menu')
def study_menu():
    if 'user_name' not in session: return redirect(url_for('login'))
    return render_template('study_menu.html', categories=load_json(QUESTIONS_FILE).keys())

@app.route('/start/<category>')
def start_quiz(category):
    if 'user_name' not in session: return redirect(url_for('login'))
    
    # 指定カテゴリの全問題を取得してシャッフル（全問修行モード）
    ids = [q['id'] for q in load_json(QUESTIONS_FILE).get(category, [])]
    random.shuffle(ids)
    
    session.update({
        'question_ids': ids, 
        'current_index': 0, 
        'score': 0, 
        'new_solved_count': 0, 
        'mode': 'study', 
        'category': category
    })
    return redirect(url_for('quiz_page'))

@app.route('/start_total_study')
def start_total_study():
    if 'user_name' not in session: return redirect(url_for('login'))
    all_q = get_all_questions_flat()
    random.shuffle(all_q)
    # 総合演習はランダム20問
    session.update({
        'question_ids': [q['id'] for q in all_q[:20]], 
        'current_index': 0, 
        'score': 0, 
        'new_solved_count': 0, 
        'mode': 'total_study', 
        'category': "総合腕試し"
    })
    return redirect(url_for('quiz_page'))

@app.route('/battle_start')
def battle_start():
    if 'user_name' not in session: return redirect(url_for('login'))
    ids = [q['id'] for q in get_all_questions_flat()]
    random.shuffle(ids)
    session.update({
        'question_ids': ids, 
        'current_index': 0, 
        'score': 0, 
        'new_solved_count': 0, 
        'miss_count': 0, 
        'enemy_id': 1, 
        'mode': 'battle', 
        'category': "サバイバルバトル"
    })
    return redirect(url_for('quiz_page'))

@app.route('/quiz', methods=['GET', 'POST'])
def quiz_page():
    if 'user_name' not in session: return redirect(url_for('login'))
    
    curr = session.get('current_index', 0)
    q_ids = session.get('question_ids', [])
    
    if not q_ids or curr >= len(q_ids):
        return end_logic(session['user_name'], session.get('score', 0), len(q_ids), False)

    # 現在の問題データを取得
    all_q = get_all_questions_flat()
    q_data = next((q for q in all_q if q['id'] == q_ids[curr]), None)
    
    user_stats = get_user_stats(session['user_name'])
    enemy_img_id = ((session.get('enemy_id', 1) - 1) % MAX_ENEMY_TYPE) + 1

    if request.method == 'POST':
        user_ans = request.form.get('answer')
        
        # 判定ロジック
        is_correct = False
        if user_ans and user_ans != 'TIMEOUT':
            if q_data['type'] == 'choice':
                is_correct = (str(user_ans) == str(q_data['answer']))
            else:
                answers = q_data['answer'] if isinstance(q_data['answer'], list) else [q_data['answer']]
                is_correct = (user_ans.strip() in answers)

        if is_correct:
            session['score'] = session.get('score', 0) + 1
            if session.get('mode') == 'battle': 
                session['enemy_id'] = session.get('enemy_id', 1) + 1
            
            # Redisデータの更新（新規正解のみカウント）
            u = load_json_redis(session['user_name'])
            if q_data['id'] not in u['solved_ids']:
                u['total_score'] += 1
                u['solved_ids'].append(q_data['id'])
                session['new_solved_count'] = session.get('new_solved_count', 0) + 1
                save_json_redis(session['user_name'], u)
                user_stats = get_user_stats(session['user_name'])
        else:
            if session.get('mode') == 'battle':
                session['miss_count'] = session.get('miss_count', 0) + 1
                if session['miss_count'] >= user_stats['max_lives']:
                    return end_logic(session['user_name'], session['score'], len(q_ids), True, enemy_img_id)

        # HTML側に渡す正解テキストの整形
        if q_data['type'] == 'choice':
            correct_text = q_data['options'][int(q_data['answer'])]
        else:
            correct_text = q_data['answer'][0] if isinstance(q_data['answer'], list) else q_data['answer']

        # HTMLのJS側で音を鳴らすため、is_judgedフラグをTrueにして返す
        return render_template('quiz.html', 
                               question=q_data, 
                               is_judged=True, 
                               is_correct=is_correct, 
                               correct_text=correct_text, 
                               commentary=q_data.get('commentary',''), 
                               index=curr+1, 
                               user_stats=user_stats, 
                               enemy_id=enemy_img_id)

    return render_template('quiz.html', 
                           question=q_data, 
                           is_judged=False, 
                           index=curr+1, 
                           user_stats=user_stats, 
                           enemy_id=enemy_img_id)

def end_logic(name, score, total, failed, enemy_id=1):
    u = load_json_redis(name)
    # バトルモードならハイスコア更新チェック
    if session.get('mode') == 'battle' and score > u.get('max_battle_score', 0):
        u['max_battle_score'] = score
        save_json_redis(name, u)
    
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
    users_dict = get_all_users_from_redis()
    # バトルスコア順にソート
    sorted_users = sorted(users_dict.items(), key=lambda x: x[1].get('max_battle_score', 0), reverse=True)
    return render_template('ranking.html', ranking=sorted_users)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    # Render等のポート指定に対応
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)