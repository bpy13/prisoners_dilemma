const READY = '';

var sid = '';
var username = '';
var score = 0;
var enemy = '';
var your_score = 0;
var enemy_score = 0;

const socket = io();
socket.emit('initialize');

function hidePages() {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('lobby-page').style.display = 'none';
    document.getElementById('game-page').style.display = 'none';
}

function updateLobby(user_list) {
    const lobbyList = document.getElementById('lobby-list');
    lobbyList.innerHTML = '';
    for (let i = 0; i < Object.keys(user_list).length; i++) {
        const name = Object.keys(user_list)[i];
        const status = user_list[name];
        if (status != READY) continue;
        if (name == username) continue;
        const listItem = document.createElement('a');
        listItem.textContent = name;
        listItem.onclick = () => issueChallenge(name);
        listItem.classList.add('user-link');
        lobbyList.appendChild(listItem);
    }
}

function showLobby(data) {
    username = data.username;
    score = data.score;
    document.getElementById('nav-name').textContent = username;
    document.getElementById('nav-score').textContent = `Score: ${score}`;
    updateLobby(data.user_list);
    hidePages();
    document.getElementById('lobby-page').style.display = 'block';
}

socket.on('login_page', function(data) {
    sid = data;
    hidePages();
    document.getElementById('login-page').style.display = 'block';
});

socket.on('lobby_page', function(data) {
    showLobby(data);
});

function confirmLogin() {
    const name = document.getElementById('login-name').value;
    if (name == '') {
        return alert('Please enter a username!');
    }
    if (confirm(`Proceeds with username "${name}"?`)) {
        fetch('login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: name, sid: sid }),
        }).then(response => {
            if (response.ok) return response.json();
            else throw new Error('Username already taken!');
        })
        .then(data => {
            showLobby(data);
        }).catch(error => {
            alert(error.message);
        })
        .then(() => {
            location.reload(); // upon login, reload the page
        }); // to ensure session changes via Flask is updated at socketIO
    }
}

function confirmLogout() {
    if (confirm("Confirm logout?")) {
        document.getElementById('logout-form').submit();
    }
}

socket.on('update_user_list', function(user_list) {
    updateLobby(user_list);
});

function issueChallenge(username) {
    if (confirm(`Proceeds to challenge ${username}?`)) {
        socket.emit('issue_challenge', { receiver: username });
    }
}

function challengeRandom() {
    const lobbyList = document.getElementsByClassName('user-link');
    if (lobbyList.length === 0) return alert('No available player!');
    const idx = Math.floor(Math.random() * lobbyList.length);
    issueChallenge(lobbyList[idx].textContent);
}

function showGame(enemy_name, your_list, enemy_list) {
    enemy = enemy_name;
    your_score = 0;
    enemy_score = 0;
    for (let i = 0; i < your_list.length; i++) {
        your_score += your_list[i];
        enemy_score += enemy_list[i];
    }
    document.getElementById('score-you').textContent = `${username}: ${your_score}`;
    document.getElementById('score-enemy').textContent = `${enemy}: ${enemy_score}`;
    hidePages();
    document.getElementById('game-page').style.display = 'block';
}

socket.on('game_page', function(data) {
    username = data.username;
    showGame(data.opponent, data.your_score, data.opponent_score);
    if (data.decision != null) {
        document.getElementById('option').style.display = 'none';
        document.getElementById('wait').style.display = 'block';
    }
})

socket.on('challenge_issued', function(receiver) {
    enemy = receiver;
    alert(`You have challenged ${enemy}!`);
    showGame(enemy, [], []);
})

socket.on('challenge_accepted', function(challenger) {
    enemy = challenger;
    alert(`${enemy} has challenged you!`);
    showGame(enemy, [], []);
})

function submitOption(move) {
    if (confirm(`Are you sure you want to ${move}?`)) {
        socket.emit('submit_option', move);
        document.getElementById('option').style.display = 'none';
        document.getElementById('wait').style.display = 'block';
    }
}

socket.on('game_result', function(data) {
    your_score += data.your_score;
    enemy_score += data.enemy_score;
    alert(`Your action: ${data.your_option}\nOpponent's action: ${data.enemy_option}\nYour score: +${data.your_score}`)
    document.getElementById('score-you').textContent = `${username}: ${your_score}`;
    document.getElementById('score-enemy').textContent = `${enemy}: ${enemy_score}`;
    document.getElementById('option').style.display = 'block';
    document.getElementById('wait').style.display = 'none';
})

socket.on('game_end', function() {
    alert(`Game ended!\nYour score: ${your_score}\nOpponent's score: ${enemy_score}`);
    your_score = 0;
    enemy_score = 0;
})

function terminateGame() {
    if (confirm("Proceeds to leave before the game ends?")) {
        socket.emit('terminate_game');
    }
}
