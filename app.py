from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'prisoners_dilemma' # enable session
socketio = SocketIO(app)

DATA_KEY = ['status', 'score', 'score_now', 'score_total', 'N_round', 'N_game', 'remain', 'decision']
KEY_VALUE = ['', '0', [], 0, 0, 0, 0, None]
data = {key: {} for key in DATA_KEY}
sid = {}

@app.route('/')
def index():
    return render_template('index.html')

def show_lobby(name, id):
    js = {
        'username': name,
        'score': data['score'][name],
        'user_list': data['status']
    }
    socketio.emit('lobby_page', js, to=id)

@socketio.on('initialize')
def initialize():
    if 'username' not in session or session['username'] not in data['status']:
        return socketio.emit('login_page', request.sid, to=request.sid)
    name = session['username']
    global sid
    sid = {key:val for key, val in sid.items() if val != request.sid}
    sid[name] = request.sid
    if data['status'][name] == '':
        show_lobby(name, request.sid)
    else:
        js = {
            'username': name,
            'opponent': data['status'][name],
            'your_score': data['score_now'][name],
            'opponent_score': data['score_now'][data['status'][name]],
            'decision': data['decision'][name]
        }
        socketio.emit('game_page', js, to=request.sid)

@app.route('/login', methods=['POST'])
def login():
    js = request.get_json()
    name = js['username']
    if name in data['status'] and name in sid:
        return 'Username already taken!', 409
    id = js['sid']
    session['username'] = name
    sid[name] = id
    if name not in data['status']:
        for key, value in zip(DATA_KEY, KEY_VALUE):
            data[key][name] = value
    data['score_now'][name] = [] # FIX: mutable object will share same reference
    socketio.emit('update_user_list', data['status'])
    return {'username': name, 'score': data['score'][name], 'user_list': data['status']}, 200

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    name = session['username']
    session.pop('username', None)
    session.pop('sid', None)
    sid.pop(name, None)
    if data['score_total'][name] == 0: 
        for key in DATA_KEY:
            data[key].pop(name, None)
    socketio.emit('update_user_list', data['status'])
    return redirect('/')

@socketio.on('issue_challenge')
def handle_challenge(js):
    receiver = js['receiver']
    challenger = session['username']
    if data['status'][receiver] != '':
        socketio.emit('challenge_failed', to=sid[challenger])
    else:
        data['status'][receiver] = challenger
        data['status'][challenger] = receiver
        N = random.randint(5, 9)
        data['remain'][receiver] = N
        data['remain'][challenger] = N
        socketio.emit('update_user_list', data['status'])
        socketio.emit('challenge_issued', receiver, to=sid[challenger])
        socketio.emit('challenge_accepted', challenger, to=sid[receiver])

def compute_score(your_option, enemy_option):
    if your_option == 'split' and enemy_option == 'split':
        return 3, 3
    elif your_option == 'split' and enemy_option == 'steal':
        return 0, 5
    elif your_option == 'steal' and enemy_option == 'split':
        return 5, 0
    else:
        return 1, 1

def update_game(score, player):
    data['score_now'][player].append(score)
    data['remain'][player] -= 1
    data['N_round'][player] += 1
    data['score_total'][player] += score
    data['score'][player] = str(round(data['score_total'][player] / data['N_round'][player], 2))
    data['decision'][player] = None

def game_end(player):
    data['status'][player] = ''
    data['score_now'][player] = []
    data['N_game'][player] += 1
    data['remain'][player] = 0
    data['decision'][player] = None

@socketio.on('submit_option')
def handle_decision(your_option):
    you = session['username']
    enemy = data['status'][you]
    data['decision'][you] = your_option
    enemy_option = data['decision'][enemy]
    if enemy_option is not None:
        your_score, enemy_score = compute_score(your_option, enemy_option)
        update_game(your_score, you)
        update_game(enemy_score, enemy)
        your_js = {
            'your_option': your_option,
            'enemy_option': enemy_option,
            'your_score': your_score,
            'enemy_score': enemy_score,
        }
        enemy_js = {
            'your_option': enemy_option,
            'enemy_option': your_option,
            'your_score': enemy_score,
            'enemy_score': your_score,
        }
        socketio.emit('game_result', your_js, to=request.sid)
        socketio.emit('game_result', enemy_js, to=sid[enemy])
        if data['remain'][you] == 0:
            game_end(you)
            game_end(enemy)
            socketio.emit('game_end', to=request.sid)
            socketio.emit('game_end', to=sid[enemy])
            socketio.emit('update_user_list', data['status'])
            show_lobby(you, request.sid)
            show_lobby(enemy, sid[enemy])

@socketio.on('terminate_game')
def terminate_game():
    you = session['username']
    enemy = data['status'][you]
    game_end(you)
    game_end(enemy)
    socketio.emit('game_end', to=request.sid)
    socketio.emit('game_end', to=sid[enemy])
    socketio.emit('update_user_list', data['status'])
    show_lobby(you, request.sid)
    show_lobby(enemy, sid[enemy])

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    qualified = {k: v for k, v in data['score'].items() if data['N_game'][k] >= 7}
    sorted_res = dict(sorted(qualified.items(), key=lambda item: item[1], reverse=True))
    return render_template('leaderboard.html', leaderboard=sorted_res)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=True)
