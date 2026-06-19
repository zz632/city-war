// ===== 城池战争 - 前端主逻辑 =====

let socket = null;
let myPlayerId = null;
let myRoomId = null;
let myCities = 100;
let selectedAction = null;  // 当前选中的行动
let actionSubmitted = false; // 是否已提交
let _lastRenderedRound = 0;  // 上次渲染的回合号，用于判断是否需要保持行动状态
let duelTargetId = null;    // 约战目标
let amSpectator = false;    // 是否是观战者
let authToken = localStorage.getItem('auth_token') || '';
let isOnlineMode = false;
let loggedInDisplayName = '';
let turnstileSiteKey = '';
let turnstileWidgetId = null;

function authHeaders() {
    return authToken ? { 'Authorization': 'Bearer ' + authToken } : {};
}

document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;
    if (page === 'home') initHome();
    else if (page === 'lobby') initLobby();
    else if (page === 'game') initGame();
});

// ===== Toast =====
function toast(msg, type = 'info') {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = 'toast ' + type;
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => el.classList.remove('show'), 2500);
}

// ===== 首页 =====
function initHome() {
    // 加载 Turnstile Site Key
    fetch('/api/auth/turnstile_key').then(r => r.json()).then(data => {
        turnstileSiteKey = data.site_key || '';
    }).catch(() => {});

    // 检测是否在线模式
    fetch('/api/auth/online_mode').then(r => r.json()).then(data => {
        isOnlineMode = data.online;
        if (isOnlineMode) {
            // 在线模式：隐藏游客按钮
            document.getElementById('guest-entry').style.display = 'none';
            checkExistingLogin();
        } else {
            // 本地模式：显示游客按钮
            document.getElementById('guest-entry').style.display = 'block';
            checkExistingLogin();
        }
    }).catch(() => {
        document.getElementById('guest-entry').style.display = 'block';
        showAuthSection();
    });

    // 登录/注册切换
    document.getElementById('showRegister').addEventListener('click', e => {
        e.preventDefault();
        document.getElementById('auth-login').style.display = 'none';
        document.getElementById('auth-register').style.display = 'block';
    });
    document.getElementById('showLogin').addEventListener('click', e => {
        e.preventDefault();
        document.getElementById('auth-register').style.display = 'none';
        document.getElementById('auth-login').style.display = 'block';
    });

    // 登录
    document.getElementById('loginBtn').addEventListener('click', doLogin);
    document.getElementById('loginPassword').addEventListener('keypress', e => { if (e.key === 'Enter') doLogin(); });

    // 注册
    document.getElementById('registerBtn').addEventListener('click', doRegister);
    document.getElementById('regPassword').addEventListener('keypress', e => { if (e.key === 'Enter') doRegister(); });

    // 发送验证码
    document.getElementById('sendCodeBtn').addEventListener('click', sendVerificationCode);

    // 退出登录
    document.getElementById('logoutBtn').addEventListener('click', doLogout);

    // 游客模式
    document.getElementById('guestBtn').addEventListener('click', () => {
        showGameSection();
    });

    // 游戏进入
    const enterBtn = document.getElementById('enterBtn');
    const playerNameInput = document.getElementById('playerName');
    const roomCodeInput = document.getElementById('roomCode');

    enterBtn.addEventListener('click', () => {
        const name = isOnlineMode ? loggedInDisplayName : playerNameInput.value.trim();
        if (!name) {
            toast('请输入你的名字', 'error');
            playerNameInput.focus();
            return;
        }
        const code = roomCodeInput.value.trim();
        if (code) {
            joinRoom(name, code);
        } else {
            createRoom(name);
        }
    });

    roomCodeInput.addEventListener('keypress', e => { if (e.key === 'Enter') enterBtn.click(); });
    playerNameInput.addEventListener('keypress', e => { if (e.key === 'Enter') enterBtn.click(); });
}

function showAuthSection() {
    document.getElementById('auth-section').style.display = 'block';
    document.getElementById('game-section').style.display = 'none';
}

function showGameSection() {
    document.getElementById('auth-section').style.display = 'none';
    document.getElementById('game-section').style.display = 'block';
    if (isOnlineMode || loggedInDisplayName) {
        // 在线模式或已登录：隐藏名字输入，显示登录信息
        document.getElementById('local-name-field').style.display = 'none';
        document.getElementById('logged-in-info').style.display = 'flex';
        document.getElementById('logged-in-name').textContent = loggedInDisplayName || '游客';
    } else {
        // 本地游客模式：显示名字输入
        document.getElementById('local-name-field').style.display = 'block';
        document.getElementById('logged-in-info').style.display = 'none';
    }
}

async function checkExistingLogin() {
    if (!authToken) {
        showAuthSection();
        return;
    }
    try {
        const res = await fetch('/api/auth/check', { headers: authHeaders() });
        const data = await res.json();
        if (data.success) {
            loggedInDisplayName = data.display_name;
            showGameSection();
        } else {
            authToken = '';
            localStorage.removeItem('auth_token');
            showAuthSection();
        }
    } catch (e) {
        showAuthSection();
    }
}

async function doLogin() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) { toast('请输入用户名和密码', 'error'); return; }
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (data.success) {
            authToken = data.token;
            loggedInDisplayName = data.display_name;
            localStorage.setItem('auth_token', authToken);
            showGameSection();
        } else {
            toast(data.message || '登录失败', 'error');
        }
    } catch (e) {
        toast('网络错误', 'error');
    }
}

function removeTurnstileWidget() {
    try {
        if (window.turnstile && turnstileWidgetId !== null) {
            turnstile.remove(turnstileWidgetId);
        }
    } catch (e) { /* ignore */ }
    turnstileWidgetId = null;
}

function showTurnstileModal() {
    const modal = document.getElementById('turnstileModal');
    const container = document.getElementById('turnstileContainer');
    if (!modal || !container) return;
    container.innerHTML = '';
    modal.style.display = 'flex';

    if (turnstileSiteKey && window.turnstile) {
        turnstileWidgetId = turnstile.render(container, {
            sitekey: turnstileSiteKey,
            theme: 'dark',
            size: 'normal',
            callback: function(token) {
                // 人机验证通过，关闭模态框并发送验证码
                modal.style.display = 'none';
                doSendCode(token).finally(() => {
                    removeTurnstileWidget();
                });
            },
            'error-callback': function() {
                toast('人机验证出错，请重试', 'error');
                modal.style.display = 'none';
                removeTurnstileWidget();
            },
            'expired-callback': function() {
                toast('验证已过期，请重试', 'error');
            }
        });
    } else {
        // 未配置 Turnstile 或 JS 未加载，直接发送
        modal.style.display = 'none';
        doSendCode('');
    }
}

async function sendVerificationCode() {
    const email = document.getElementById('regEmail').value.trim();
    if (!email) { toast('请输入邮箱', 'error'); return; }

    // 如果配置了 Turnstile，先弹出人机验证
    if (turnstileSiteKey) {
        showTurnstileModal();
        return;
    }
    // 未配置 Turnstile，直接发送
    doSendCode('');
}

async function doSendCode(turnstileToken) {
    const email = document.getElementById('regEmail').value.trim();
    if (!email) return;

    const btn = document.getElementById('sendCodeBtn');
    btn.disabled = true;
    btn.textContent = '发送中...';
    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        const res = await fetch('/api/auth/send_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, turnstile_token: turnstileToken || '' }),
            signal: controller.signal
        });
        clearTimeout(timeout);
        const data = await res.json();
        if (data.success) {
            toast(data.message || '验证码已发送', 'success');
            // 开发模式下自动填入验证码
            if (data.dev_code) {
                document.getElementById('regCode').value = data.dev_code;
                toast('开发模式：验证码已自动填入', 'info');
            }
            // 60秒倒计时
            let countdown = 60;
            btn.textContent = countdown + 's';
            const timer = setInterval(() => {
                countdown--;
                if (countdown <= 0) {
                    clearInterval(timer);
                    btn.textContent = '发送验证码';
                    btn.disabled = false;
                } else {
                    btn.textContent = countdown + 's';
                }
            }, 1000);
        } else {
            toast(data.message || '发送失败', 'error');
            btn.disabled = false;
            btn.textContent = '发送验证码';
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            toast('请求超时，请重试', 'error');
        } else {
            toast('网络错误：' + e.message, 'error');
        }
        btn.disabled = false;
        btn.textContent = '发送验证码';
    }
}

async function doRegister() {
    const username = document.getElementById('regUsername').value.trim();
    const display_name = document.getElementById('regDisplayName').value.trim();
    const password = document.getElementById('regPassword').value;
    const email = document.getElementById('regEmail').value.trim();
    const code = document.getElementById('regCode').value.trim();
    if (!username || !password) { toast('请填写用户名和密码', 'error'); return; }
    // 在线模式下验证邮箱和验证码不为空
    if (isOnlineMode && (!email || !code)) { toast('请填写邮箱和验证码', 'error'); return; }
    try {
        const body = { username, display_name, password };
        if (email) body.email = email;
        if (code) body.code = code;
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            authToken = data.token;
            loggedInDisplayName = data.display_name;
            localStorage.setItem('auth_token', authToken);
            showGameSection();
        } else {
            toast(data.message || '注册失败', 'error');
        }
    } catch (e) {
        toast('网络错误', 'error');
    }
}

function doLogout() {
    authToken = '';
    loggedInDisplayName = '';
    localStorage.removeItem('auth_token');
    showAuthSection();
}

async function createRoom(name) {
    try {
        const res = await fetch('/api/rooms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ player_name: name })
        });
        const data = await res.json();
        if (data.success) {
            myPlayerId = data.player.id;
            myRoomId = data.room.id;
            window.location.href = '/lobby/' + myRoomId + '?pid=' + myPlayerId + (authToken ? '&token=' + authToken : '');
        } else {
            toast(data.message || '创建失败', 'error');
        }
    } catch (e) {
        toast('网络错误', 'error');
    }
}

async function joinRoom(name, code) {
    try {
        const res = await fetch('/api/rooms/' + code + '/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ player_name: name })
        });
        const data = await res.json();
        if (data.success) {
            myPlayerId = data.player.id;
            myRoomId = code;
            const tokenParam = authToken ? '&token=' + authToken : '';
            if (data.is_spectator) {
                window.location.href = '/game/' + myRoomId + '?pid=' + myPlayerId + tokenParam;
            } else {
                window.location.href = '/lobby/' + myRoomId + '?pid=' + myPlayerId + tokenParam;
            }
        } else {
            toast(data.message || '加入失败', 'error');
        }
    } catch (e) {
        toast('网络错误', 'error');
    }
}

// ===== 通用聊天 =====
function setupChat() {
    const chatInput = document.getElementById('chatInput');
    const chatSend = document.getElementById('chatSend');
    if (chatSend) chatSend.addEventListener('click', sendChat);
    if (chatInput) chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendChat(); });
}

function sendChat() {
    const input = document.getElementById('chatInput');
    if (!input || !input.value.trim() || !socket) return;
    socket.emit('chat_message', {
        room_id: myRoomId,
        player_id: myPlayerId,
        message: input.value.trim()
    });
    input.value = '';
}

function appendChat(data) {
    // 存活玩家看不到观战者消息
    if (!amSpectator && data.is_spectator) return;

    const box = document.getElementById('chatMessages');
    if (!box) return;
    const div = document.createElement('div');
    div.className = 'chat-msg';
    if (data.is_spectator) div.style.opacity = '0.5';
    div.innerHTML = '<span class="chat-msg-name">' + esc(data.player_name) + '</span> <span class="chat-msg-text">' + esc(data.message) + '</span>';
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// ===== 大厅页 =====
function initLobby() {
    const roomId = document.getElementById('lobbyRoomId')?.dataset.roomid;
    const params = new URLSearchParams(window.location.search);
    myPlayerId = params.get('pid');
    myRoomId = roomId;

    if (!roomId) return;

    socket = io();

    socket.on('connect', () => {
        socket.emit('lobby_join', { room_id: roomId, player_id: myPlayerId });
    });

    socket.on('lobby_update', data => {
        renderLobbyPlayers(data.players || []);
        updateLobbyButtons(data.players || []);
    });

    socket.on('game_started', data => {
        window.location.href = '/game/' + roomId + '?pid=' + myPlayerId;
    });

    socket.on('error_msg', data => toast(data.message, 'error'));

    socket.on('chat_message', data => appendChat(data));

    // 催促通知（房主收到）
    socket.on('urge_received', data => {
        toast(data.player_name + ' 催促你开始游戏！', 'info');
    });

    // 开始按钮
    const startBtn = document.getElementById('startBtn');
    if (startBtn) startBtn.addEventListener('click', () => {
        socket.emit('start_game', { room_id: roomId, player_id: myPlayerId });
    });

    // 催促按钮
    const urgeBtn = document.getElementById('urgeBtn');
    if (urgeBtn) urgeBtn.addEventListener('click', () => {
        socket.emit('urge_start', { room_id: roomId, player_id: myPlayerId });
        toast('已催促房主', 'info');
    });

    // 聊天
    setupChat();

    // 初始拉取
    fetchLobbyState(roomId);
}

async function fetchLobbyState(roomId) {
    try {
        const res = await fetch('/api/room/' + roomId + '/status');
        const data = await res.json();
        if (data.success) {
            renderLobbyPlayers(data.room.players || []);
            updateLobbyButtons(data.room.players || []);
        }
    } catch (e) {}
}

function renderLobbyPlayers(players) {
    const list = document.getElementById('playerList');
    if (!list) return;
    list.innerHTML = '';
    const arr = Array.isArray(players) ? players : Object.values(players);
    arr.forEach(p => {
        const li = document.createElement('li');
        li.className = 'player-item' + (p.id === myPlayerId ? ' self' : '');

        // 名称旁的标签（左边）
        const nameTags = [];
        if (p.id === myPlayerId) nameTags.push('<span class="badge badge-blue" style="font-size:10px">我</span>');
        if (p.is_host) nameTags.push('<span class="badge badge-gold" style="font-size:10px">房主</span>');

        // 游戏状态badge（右边）
        let statusBadge = '';
        if (p.is_spectator) {
            statusBadge = '<span class="badge badge-blue">观战</span>';
        } else if (p.is_ready) {
            statusBadge = '<span class="badge badge-green">已准备</span>';
        } else {
            statusBadge = '<span class="badge badge-gray">等待中</span>';
        }

        li.innerHTML = `
            <span class="player-name">
                <span class="player-dot"></span>
                ${esc(p.name)}
                ${nameTags.join(' ')}
            </span>
            ${statusBadge}
        `;
        list.appendChild(li);
    });
}

function updateLobbyButtons(players) {
    const startBtn = document.getElementById('startBtn');
    const urgeBtn = document.getElementById('urgeBtn');
    if (!startBtn || !urgeBtn) return;

    const arr = Array.isArray(players) ? players : Object.values(players);
    const me = arr.find(p => p.id === myPlayerId);
    if (!me) return;

    if (me.is_host) {
        startBtn.style.display = '';
        urgeBtn.style.display = 'none';
    } else {
        startBtn.style.display = 'none';
        urgeBtn.style.display = '';
    }
}

// ===== 游戏页 =====
function initGame() {
    const roomId = document.getElementById('gameRoomId')?.dataset.roomid;
    const params = new URLSearchParams(window.location.search);
    myPlayerId = params.get('pid');
    myRoomId = roomId;

    if (!roomId) return;

    socket = io();

    socket.on('connect', () => {
        socket.emit('game_join', { room_id: roomId, player_id: myPlayerId });
    });

    socket.on('game_state', data => renderGameState(data));

    socket.on('round_result', data => renderRoundResult(data));

    socket.on('next_round', data => {
        renderGameState(data);
        if (!amSpectator) {
            showActionPanel();
        }
        const continueBtn = document.getElementById('continueBtn');
        if (continueBtn) {
            continueBtn.disabled = false;
            continueBtn.innerHTML = '继续行动';
        }
        toast('第 ' + data.round + ' 回合开始', 'info');
    });

    socket.on('chat_message', data => appendChat(data));

    socket.on('error_msg', data => toast(data.message, 'error'));

    socket.on('skill_used', data => {
        toast(data.message, 'success');
        // 记录到上帝视角历史
        const round = parseInt(document.getElementById('statRound')?.textContent || '1');
        _godViewHistory.push({ round: round, type: 'action', text: data.message });
        // 更新玩家状态
        if (data.players) {
            renderGameState({ players: data.players, round: round });
        }
    });

    // 其他人使用技能卡时，只更新玩家公开状态，保留自己的技能卡
    socket.on('players_update', data => {
        if (data.players) {
            updatePlayerPublicState(data.players);
        }
    });

    socket.on('player_action_ready', data => {
        // 记录到上帝视角历史
        if (data.action_detail) {
            const round = parseInt(document.getElementById('statRound')?.textContent || '1');
            const detail = data.action_detail;
            const actionNames = { 'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟' };
            const gestureNames = { 'rock': '石头', 'paper': '布', 'scissors': '剪刀' };
            let text = data.player_name + ' 提交行动 [' + (actionNames[detail.type] || detail.type) + ']';
            if (detail.target_name) text += ' | 目标：' + detail.target_name;
            if (detail.bet) text += ' | 赌注：' + detail.bet + ' 城池';
            if (detail.gesture) text += ' | 出手：' + (gestureNames[detail.gesture] || detail.gesture);
            _godViewHistory.push({ round: round, type: 'action', text: text });
            if (amSpectator) {
                renderGodView(window._lastPlayers || []);
            }
        }

        if (data.player_id === myPlayerId) {
            onActionAccepted(data.action_type || selectedAction);
        } else {
            toast(data.player_name + ' 已提交行动', 'info');
        }
    });

     socket.on('game_ended', data => {
         const name = data.winner ? data.winner.name : '无人';
         toast('游戏结束！' + name + ' 获胜！', 'success');

         // 隐藏所有操作面板
         const panels = ['actionPanel', 'duelPanel', 'auctionPanel', 'skillCardArea', 'spectatorArea', 'godViewPanel'];
         panels.forEach(id => {
             const el = document.getElementById(id);
             if (el) el.style.display = 'none';
         });
         // 隐藏行动面板标题
         const apTitle = document.getElementById('actionPanelTitle');
         if (apTitle) apTitle.style.display = 'none';

         // 确保会议面板显示
         const mp = document.getElementById('meetingPanel');
         if (mp) mp.style.display = 'block';

         // 将继续按钮改为退出游戏按钮
         const continueBtn = document.getElementById('continueBtn');
         if (continueBtn) {
             continueBtn.style.display = 'block';
             continueBtn.disabled = false;
             continueBtn.textContent = '退出游戏';
             continueBtn.onclick = () => {
                 socket.emit('leave_game', { room_id: myRoomId, player_id: myPlayerId });
                 window.location.href = '/lobby/' + myRoomId + '?pid=' + myPlayerId;
             };
         }
     });

    // 结盟请求通知（卡片式）
    socket.on('alliance_request', data => {
        if (data.to_player_id === myPlayerId) {
            showAllianceCard(data.from_player_id, data.from_player_name);
        }
    });

    // 约战事件
    socket.on('duel_started', data => showDuelPanel(data));

    socket.on('duel_shot_result', data => onDuelShotResult(data));

    socket.on('duel_next_turn', data => onDuelNextTurn(data));

    socket.on('duel_ended', data => onDuelEnded(data));

    // 拍卖事件
    socket.on('auction_started', data => showAuctionPanel(data));

    socket.on('auction_updated', data => {
        const bidEl = document.getElementById('auctionCurrentBid');
        const bidderEl = document.getElementById('auctionHighestBidder');
        if (bidEl) bidEl.textContent = data.current_bid;
        if (bidderEl) bidderEl.textContent = data.highest_bidder_name ? '最高出价：' + data.highest_bidder_name : '';
        // 更新输入框最小值
        const inp = document.getElementById('auctionBidInput');
        if (inp) inp.min = data.current_bid + 10;
    });

    socket.on('auction_ended', data => {
        if (data.passed) {
            toast('拍卖结束，无人出价', 'info');
        } else {
            toast('拍卖结束！' + data.winner_name + ' 以 ' + data.bid + ' 城池拍得【' + (data.skill_card?.name || '技能卡') + '】', 'success');
        }
        hideAuctionPanel();
        // 清理倒计时
        if (window._auctionTimer) { clearInterval(window._auctionTimer); window._auctionTimer = null; }
        // 更新玩家状态
        if (data.players) {
            const round = parseInt(document.getElementById('statRound')?.textContent || '1');
            renderGameState({ players: data.players, round: round });
        }
    });

    // 操作按钮 - 点击只选中，不立刻提交
    document.querySelectorAll('.act-btn[data-action]').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.dataset.action;
            selectAction(action);
        });
    });

    // 猜拳按钮
    document.querySelectorAll('.gesture-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const gesture = btn.dataset.gesture;
            if (selectedAction === 'jungle') {
                submitAction('jungle', null, gesture);
            }
        });
    });

    // 继续行动按钮
    const continueBtn = document.getElementById('continueBtn');
    if (continueBtn) continueBtn.addEventListener('click', () => {
        socket.emit('ready_next_round', { room_id: myRoomId, player_id: myPlayerId });
        continueBtn.disabled = true;
        continueBtn.textContent = '等待其他玩家...';
    });

    // 聊天
    setupChat();
}

function selectAction(action) {
    selectedAction = action;
    actionSubmitted = false;

    // 隐藏猜拳区域
    const ga = document.getElementById('gestureArea');
    if (ga) ga.style.display = 'none';

    // 隐藏提示
    const hint = document.getElementById('actionHint');
    if (hint) { hint.style.display = 'none'; }

    // 重置玩家卡片选择
    document.querySelectorAll('.p-card').forEach(c => {
        c.classList.remove('selected');
        c.onclick = null;
    });

    // 根据行动类型处理
    if (action === 'attack') {
        showHint('请点击一名玩家作为攻城目标');
        enableTargetSelection(action);
    } else if (action === 'duel') {
        showHint('请点击一名玩家发起约战');
        enableTargetSelection(action);
    } else if (action === 'jungle') {
        if (ga) ga.style.display = 'block';
        showHint('选择你的手势');
    } else if (action === 'defend') {
        submitAction('defend');
    } else if (action === 'repair') {
        submitAction('repair');
    } else if (action === 'alliance') {
        // 前端预校验
        const aliveCards = document.querySelectorAll('.p-card:not(.dead):not(.self)');
        const aliveCount = aliveCards.length + 1; // +1 for self
        if (aliveCount <= 2) {
            toast('场上仅剩2名玩家，无法结盟', 'error');
            return;
        }
        showHint('请点击一名玩家发起结盟');
        enableTargetSelection(action);
    } else if (action === 'dissolve_alliance') {
        submitAction('dissolve_alliance');
    }
}

function enableTargetSelection(action) {
    document.querySelectorAll('.p-card').forEach(card => {
        if (!card.classList.contains('self') && !card.classList.contains('dead')) {
            card.onclick = () => {
                document.querySelectorAll('.p-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                if (action === 'duel') {
                    duelTargetId = card.dataset.pid;
                    showDuelBetPanel();
                } else if (action === 'skill') {
                    // 技能卡使用目标
                    const targetId = card.dataset.pid;
                    if (window._pendingSkillCard) {
                        submitSkill(window._pendingSkillCard, targetId);
                    }
                } else {
                    submitAction(action, card.dataset.pid);
                }
            };
        }
    });
}

function showDuelBetPanel() {
    // 用输入框代替按钮
    const hint = document.getElementById('actionHint');
    if (!hint) return;

    // 计算最大赌注
    const targetCard = document.querySelector(`.p-card[data-pid="${duelTargetId}"]`);
    const targetCities = targetCard ? parseInt(targetCard.querySelector('.p-card-cities').textContent) : 100;
    const maxBet = Math.floor(Math.min(myCities, targetCities) * 0.6);

    hint.innerHTML = `
        <div style="text-align:center">
            <div style="margin-bottom:8px">输入约战赌注（最多 ${maxBet} 城池）</div>
            <div style="display:flex;gap:6px;justify-content:center;align-items:center">
                <input type="number" id="duelBetInput" class="field-input" style="width:100px;text-align:center;padding:6px" min="1" max="${maxBet}" value="20">
                <button class="btn btn-danger" style="padding:6px 16px;font-size:13px" onclick="submitDuelFromInput()">确认约战</button>
            </div>
        </div>
    `;
    hint.style.display = 'block';

    // 回车提交
    setTimeout(() => {
        const inp = document.getElementById('duelBetInput');
        if (inp) inp.addEventListener('keypress', e => { if (e.key === 'Enter') submitDuelFromInput(); });
    }, 50);
}

// ===== 结盟通知卡片 =====
function showAllianceCard(fromPlayerId, fromPlayerName) {
    // 移除已有的卡片
    const old = document.getElementById('allianceCard');
    if (old) old.remove();

    // 如果自己已结盟，不显示请求
    const myData = (window._lastPlayers || []).find(p => p.id === myPlayerId);
    if (myData && myData.alliance_with) return;

    const card = document.createElement('div');
    card.id = 'allianceCard';
    card.className = 'alliance-notify-card';
    card.innerHTML = `
        <div class="alliance-notify-title">${esc(fromPlayerName)} 请求与你结盟</div>
        <div class="alliance-notify-btns">
            <button class="btn btn-primary alliance-accept-btn" style="padding:5px 14px;font-size:12px" data-from-id="${esc(fromPlayerId)}">同意</button>
            <button class="btn btn-outline alliance-reject-btn" style="padding:5px 14px;font-size:12px">拒绝</button>
        </div>
    `;
    // 绑定事件（避免 onclick 内联注入）
    card.querySelector('.alliance-accept-btn').addEventListener('click', () => {
        acceptAlliance(fromPlayerId);
    });
    card.querySelector('.alliance-reject-btn').addEventListener('click', () => {
        dismissAllianceCard();
    });
    // 插入到操作面板之前
    const ap = document.getElementById('actionPanel');
    if (ap && ap.parentNode) {
        ap.parentNode.insertBefore(card, ap);
    }
}

function acceptAlliance(fromPlayerId) {
    submitAction('alliance', fromPlayerId);
    dismissAllianceCard();
}

function dismissAllianceCard() {
    const card = document.getElementById('allianceCard');
    if (card) card.remove();
}

// 动态控制结盟/解盟按钮
function updateAllianceButton(myData, allPlayers) {
    const allianceBtn = document.querySelector('.act-btn[data-action="alliance"]') ||
                        document.querySelector('.act-btn[data-action="dissolve_alliance"]');
    if (!allianceBtn) return;

    const hasAlliance = myData && myData.alliance_with;
    if (hasAlliance) {
        // 已结盟 → 显示解盟按钮
        const partner = allPlayers.find(p => p.id === myData.alliance_with);
        allianceBtn.dataset.action = 'dissolve_alliance';
        allianceBtn.innerHTML = `
            <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 108 0 4 4 0 00-8 0zm12 14v-2a4 4 0 00-3-3.87"/><line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" stroke-width="2"/></svg>
            解盟` + (partner ? '（' + esc(partner.name) + '）' : '');
    } else {
        // 未结盟 → 显示结盟按钮
        allianceBtn.dataset.action = 'alliance';
        allianceBtn.innerHTML = `
            <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 108 0 4 4 0 00-8 0zm12 14v-2a4 4 0 00-3-3.87"/></svg>
            结盟`;
    }
}

function submitDuelFromInput() {
    const inp = document.getElementById('duelBetInput');
    if (!inp) return;
    const bet = parseInt(inp.value);
    if (!bet || bet <= 0) {
        toast('请输入有效的赌注', 'error');
        return;
    }
    if (!duelTargetId) return;
    submitAction('duel', duelTargetId, null, bet);
    duelTargetId = null;
}

function showHint(text) {
    const hint = document.getElementById('actionHint');
    if (hint) {
        hint.textContent = text;
        hint.style.display = 'block';
    }
}

function submitAction(action, targetId, gesture, bet) {
    const data = { room_id: myRoomId, player_id: myPlayerId, action_type: action };
    if (targetId) data.target_id = targetId;
    if (gesture) data.gesture = gesture;
    if (bet) data.bet = bet;

    socket.emit('submit_action', data);
}

// 后端确认行动有效后的处理
function onActionAccepted(action) {
    actionSubmitted = true;
    selectedAction = action;

    // 高亮选中按钮
    document.querySelectorAll('.act-btn[data-action]').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.act-btn[data-action="${action}"]`);
    if (btn) btn.classList.add('active');

    // 显示已提交状态
    const actionNames = {
        'attack': '攻城', 'defend': '守城', 'jungle': '打野',
        'duel': '约战', 'repair': '修城', 'alliance': '结盟',
        'dissolve_alliance': '解盟'
    };
    showHint('已选择：' + (actionNames[action] || action) + '（可点击其他操作更改）');

    // 隐藏猜拳区域
    const ga = document.getElementById('gestureArea');
    if (ga) ga.style.display = 'none';

    // 重置玩家卡片点击
    document.querySelectorAll('.p-card').forEach(c => {
        c.classList.remove('selected');
        c.onclick = null;
    });

    toast('行动已提交', 'success');
}

function renderGameState(data) {
    const roundEl = document.getElementById('statRound');
    const citiesEl = document.getElementById('statCities');
    const cardsEl = document.getElementById('statCards');
    const phaseEl = document.getElementById('statPhase');

    const currentRound = data.round || 1;
    const isNewRound = currentRound !== _lastRenderedRound;
    _lastRenderedRound = currentRound;

    if (roundEl) roundEl.textContent = currentRound;
    if (phaseEl) phaseEl.textContent = _phaseLabel(data.phase);

    // 判断自己是否是观战者
    let myData = null;
    let mySkills = [];
    const spectators = [];

    const grid = document.getElementById('playerGrid');
    if (!grid || !data.players) return;
    grid.innerHTML = '';
    const arr = Array.isArray(data.players) ? data.players : Object.values(data.players);
    window._lastPlayers = arr;
    arr.forEach(p => {
        if (p.id === myPlayerId) {
            myData = p;
            myCities = p.cities;
            mySkills = p.skills || [];
            if (citiesEl) citiesEl.textContent = p.cities;
            if (cardsEl) cardsEl.textContent = p.skills_count || 0;
        }
        // 观战者不显示在玩家网格中
        if (p.is_spectator) {
            spectators.push(p);
            return;
        }
        const div = document.createElement('div');
        div.className = 'p-card' + (p.id === myPlayerId ? ' self' : '') + (!p.is_alive ? ' dead' : '');
        div.dataset.pid = p.id;
        div.innerHTML = `
            <div class="p-card-name">${esc(p.name)} ${p.id === myPlayerId ? '<span class="badge badge-blue">我</span>' : ''}</div>
            <div class="p-card-cities">${p.cities}<small>城</small></div>
        `;
        grid.appendChild(div);
    });

    // 更新观战席
    const specArea = document.getElementById('spectatorArea');
    const specList = document.getElementById('spectatorList');
    if (specArea && specList) {
        if (spectators.length > 0) {
            specArea.style.display = 'block';
            specList.innerHTML = spectators.map(p => {
                const tag = p.id === myPlayerId ? ' <span class="badge badge-blue" style="font-size:10px">我</span>' : '';
                return '<span style="margin-right:10px">' + esc(p.name) + tag + '</span>';
            }).join('');
            const specRoomId = document.getElementById('specRoomId');
            if (specRoomId) specRoomId.textContent = myRoomId;
        } else {
            specArea.style.display = 'none';
        }
    }

    // 更新技能卡区域
    updateSkillCards(mySkills);

    // 后期操作
    const lateActions = document.getElementById('lateActions');
    if (lateActions) lateActions.style.display = (data.round >= 6) ? 'block' : 'none';

    // 更新结盟/解盟按钮
    updateAllianceButton(myData, arr);

    // 观战者隐藏操作面板，显示上帝视角
    const isSpectator = myData && (myData.is_spectator || !myData.is_alive);
    amSpectator = !!isSpectator;
    const actionPanel = document.getElementById('actionPanel');
    if (actionPanel) {
        if (amSpectator) {
            actionPanel.style.display = 'none';
        } else {
            actionPanel.style.display = 'block';
        }
    }

    // 上帝视角面板
    renderGodView(arr);

    if (amSpectator) {
        updateSpectatorSkillCards(arr);
    } else {
        // 保存当前行动状态，防止同一回合内的状态更新（如技能卡使用）重置已提交的行动
        const savedSubmitted = actionSubmitted;
        const savedAction = selectedAction;
        showActionPanel();
        // 同一回合内，如果玩家已提交行动，恢复提交状态
        if (!isNewRound && savedSubmitted) {
            actionSubmitted = savedSubmitted;
            selectedAction = savedAction;
            if (savedAction) {
                document.querySelectorAll('.act-btn[data-action]').forEach(b => b.classList.remove('active'));
                const btn = document.querySelector(`.act-btn[data-action="${savedAction}"]`);
                if (btn) btn.classList.add('active');
            }
        }
    }
}

function updatePlayerPublicState(players) {
    const grid = document.getElementById('playerGrid');
    if (!grid) return;
    const arr = Array.isArray(players) ? players : Object.values(players);
    arr.forEach(p => {
        const card = grid.querySelector(`.p-card[data-pid="${p.id}"]`);
        if (card) {
            // 更新城池数
            const citiesEl = card.querySelector('.p-card-cities');
            if (citiesEl) citiesEl.innerHTML = p.cities + '<small>城</small>';
            // 更新死亡状态
            if (!p.is_alive) card.classList.add('dead');
            else card.classList.remove('dead');
        }
        // 更新自己的城池数和技能卡数量
        if (p.id === myPlayerId) {
            const citiesEl = document.getElementById('statCities');
            if (citiesEl) citiesEl.textContent = p.cities;
            myCities = p.cities;
            const cardsEl = document.getElementById('statCards');
            if (cardsEl && p.skills_count !== undefined) cardsEl.textContent = p.skills_count;
        }
    });
}

function updateSkillCards(skills) {
    const area = document.getElementById('skillCardArea');
    const container = document.getElementById('skillCards');
    if (!area || !container) return;

    // 保存技能列表供后续使用
    area._skills = skills || [];

    if (skills && skills.length > 0) {
        area.style.display = 'block';
        container.innerHTML = '';
        const typeLabels = { attack: '攻击', defense: '防御', resource: '资源', special: '特殊' };
        skills.forEach((card, idx) => {
            const t = card.type || 'special';
            const div = document.createElement('div');
            div.className = 'skill-card type-' + t;
            div.innerHTML = `
                <div class="skill-card-header">
                    <span class="skill-card-name">${esc(card.name || '技能卡')}</span>
                    <span class="skill-card-type type-${t}">${typeLabels[t] || t}</span>
                </div>
                <div class="skill-card-desc">${esc(card.description || '')}</div>
                <div class="skill-card-actions">
                    <button class="btn btn-primary" onclick="useSkillCard(${idx})">使用</button>
                    <button class="btn btn-secondary" onclick="cancelSkillCard()">取消</button>
                </div>
            `;
            container.appendChild(div);
        });
    } else {
        area.style.display = 'none';
    }
}

// 观战者上帝视角：显示所有存活玩家的技能卡
function updateSpectatorSkillCards(players) {
    const area = document.getElementById('skillCardArea');
    const container = document.getElementById('skillCards');
    if (!area || !container) return;

    const alivePlayers = players.filter(p => p.is_alive && !p.is_spectator && p.skills && p.skills.length > 0);
    if (alivePlayers.length > 0) {
        area.style.display = 'block';
        container.innerHTML = '';
        const typeLabels = { attack: '攻击', defense: '防御', resource: '资源', special: '特殊' };
        alivePlayers.forEach(p => {
            const header = document.createElement('div');
            header.style.cssText = 'font-size:12px;color:var(--orange);margin-bottom:4px;font-weight:600';
            header.textContent = p.name + ' 的技能卡';
            container.appendChild(header);
            p.skills.forEach(card => {
                const t = card.type || 'special';
                const div = document.createElement('div');
                div.className = 'skill-card type-' + t;
                div.innerHTML = `
                    <div class="skill-card-header">
                        <span class="skill-card-name">${esc(card.name || '技能卡')}</span>
                        <span class="skill-card-type type-${t}">${typeLabels[t] || t}</span>
                    </div>
                    <div class="skill-card-desc">${esc(card.description || '')}</div>
                `;
                container.appendChild(div);
            });
        });
    } else {
        area.style.display = 'none';
    }
}

// ===== 上帝视角面板 =====
let _godViewExpanded = false;
let _godViewHistory = []; // { round, type, text }

function renderGodView(players) {
    const panel = document.getElementById('godViewPanel');
    const content = document.getElementById('godViewContent');
    if (!panel || !content) return;

    if (!amSpectator) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    const round = parseInt(document.getElementById('statRound')?.textContent || '1');
    const actionNames = { 'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟', 'dissolve_alliance': '解盟' };
    const gestureNames = { 'rock': '石头', 'paper': '布', 'scissors': '剪刀' };
    const typeIcons = {
        'action': '&#9654;', 'system': '&#9881;', 'city': '&#9650;',
        'event': '&#9888;', 'duel': '&#9876;', 'duel_system': '&#9733;',
        'skill': '&#9733;', 'alliance': '&#9829;', 'dissolve_alliance': '&#9829;'
    };
    const typeColors = {
        'action': '#94a3b8', 'system': '#60a5fa', 'city': '#f59e0b',
        'event': '#f87171', 'duel': '#a78bfa', 'duel_system': '#c084fc',
        'skill': '#facc15', 'alliance': '#4ade80', 'dissolve_alliance': '#fb923c'
    };

    // 记录当前回合操作到历史（避免重复）
    const alivePlayers = players.filter(p => p.is_alive && !p.is_spectator);
    alivePlayers.forEach(p => {
        if (p.action) {
            let detail = actionNames[p.action.type] || p.action.type || '?';
            if (p.action.target_id) {
                const target = players.find(tp => tp.id === p.action.target_id);
                if (target) detail += ' → ' + target.name;
            }
            if (p.action.bet) detail += '，赌注 ' + p.action.bet + ' 城池';
            const text = p.name + ' 提交行动：' + detail;
            if (!_godViewHistory.some(h => h.round === round && h.text === text)) {
                _godViewHistory.push({ round: round, type: 'action', text: text });
            }
        }
    });

    // 约战系统信息
    if (window._godDuelInfo) {
        const di = window._godDuelInfo;
        const text = '约战系统 | 弹仓 ' + di.chambers + ' 孔 | 实弹在第 ' + (di.bullet_pos + 1) + ' 发 | 已开 ' + di.fired + ' 发 | 剩余 ' + (di.chambers - di.fired) + ' 发 | 轮到 ' + (di.current_turn_name || '?');
        if (!_godViewHistory.some(h => h.round === round && h.type === 'duel_system' && h.text === text)) {
            _godViewHistory.push({ round: round, type: 'duel_system', text: text });
        }
    }

    // ---- 渲染：当前玩家概览 ----
    let overviewHtml = '<div class="god-overview">';
    alivePlayers.forEach(p => {
        const skillList = (p.skills && p.skills.length > 0)
            ? p.skills.map(s => '<span class="god-skill-tag">' + esc(s.name) + '</span>').join('')
            : '<span style="opacity:.4">无</span>';
        let actionStr = '等待中';
        if (p.action) {
            actionStr = actionNames[p.action.type] || p.action.type;
            if (p.action.target_id) {
                const t = players.find(tp => tp.id === p.action.target_id);
                if (t) actionStr += ' → ' + t.name;
            }
            if (p.action.bet) actionStr += '（' + p.action.bet + '城）';
            if (p.action.gesture) actionStr += '（' + (gestureNames[p.action.gesture] || p.action.gesture) + '）';
        }
        const allyName = p.alliance_with ? (players.find(ap => ap.id === p.alliance_with)?.name || '?') : '';
        overviewHtml += `<div class="god-player-row">
            <span class="god-pname">${esc(p.name)}</span>
            <span class="god-pcities">${p.cities}城</span>
            <span class="god-paction">${actionStr}</span>
            ${allyName ? '<span class="god-pally">结盟 ' + esc(allyName) + '</span>' : ''}
            <div class="god-pskills">${skillList}</div>
        </div>`;
    });
    overviewHtml += '</div>';

    // 约战实时信息（含弹仓可视化）
    if (window._godDuelInfo) {
        const di = window._godDuelInfo;
        // 弹仓可视化
        let chambersHtml = '<div class="god-duel-chambers">';
        for (let i = 0; i < di.chambers; i++) {
            let cls = 'god-chamber';
            let label = (i + 1);
            if (i < di.fired) {
                cls += i === di.bullet_pos ? ' hit' : ' fired';
                label = i === di.bullet_pos ? 'X' : '-';
            } else if (i === di.bullet_pos) {
                cls += ' bullet';  // 上帝视角能看到子弹
                label = '!';
            }
            chambersHtml += `<span class="${cls}">${label}</span>`;
        }
        chambersHtml += '</div>';
        overviewHtml += `<div class="god-duel-live">
            <div style="color:#a855f7;font-weight:600;margin-bottom:4px">&#9876; 约战进行中 | 轮到：${esc(di.current_turn_name || '?')}</div>
            <div style="margin-bottom:4px">实弹位置：第 ${di.bullet_pos + 1} 发 | 已开 ${di.fired} 发 | 剩余 ${di.chambers - di.fired} 发</div>
            ${chambersHtml}
        </div>`;
    }

    // ---- 渲染：日志区域 ----
    const latestCount = 5;
    const historyItems = _godViewHistory.slice().reverse();
    const showItems = _godViewExpanded ? historyItems : historyItems.slice(0, latestCount);
    const hasMore = historyItems.length > latestCount;

    let logHtml = '<div class="god-log">';
    if (showItems.length > 0) {
        showItems.forEach(h => {
            const icon = typeIcons[h.type] || '&#8226;';
            const color = typeColors[h.type] || '#7a8baa';
            logHtml += `<div class="god-log-entry">
                <span class="god-log-round">R${h.round}</span>
                <span class="god-log-icon" style="color:${color}">${icon}</span>
                <span class="god-log-text" style="color:${color}">${esc(h.text)}</span>
            </div>`;
        });
        if (hasMore && !_godViewExpanded) {
            logHtml += `<div class="god-log-more">... 还有 ${historyItems.length - latestCount} 条日志</div>`;
        }
    } else {
        logHtml += '<div class="god-log-empty">暂无日志</div>';
    }
    logHtml += '</div>';

    // 展开/收起按钮
    let toggleHtml = '';
    if (hasMore || _godViewExpanded) {
        toggleHtml = `<button class="god-view-toggle" onclick="toggleGodView()">${_godViewExpanded ? '&#9650; 收起日志' : '&#9660; 展开全部日志（' + historyItems.length + '条）'}</button>`;
    }

    content.innerHTML = overviewHtml + logHtml + toggleHtml;
}

function toggleGodView() {
    _godViewExpanded = !_godViewExpanded;
    renderGodView(window._lastPlayers || []);
}

// 技能卡需要目标的类型和卡牌ID
const SKILL_NEEDS_TARGET = ['attack', 'special'];
const SKILL_NO_TARGET_IDS = ['disguise', 'first_aid'];  // 特殊类中不需要目标的卡

function useSkillCard(idx) {
    const area = document.getElementById('skillCardArea');
    if (!area) return;
    const mySkills = area._skills || [];
    if (idx < 0 || idx >= mySkills.length) return;

    const card = mySkills[idx];
    const t = card.type || 'special';
    const skillId = card.skill_type || '';

    // 判断是否需要选择目标
    const needsTarget = SKILL_NEEDS_TARGET.includes(t) && !SKILL_NO_TARGET_IDS.includes(skillId);

    if (needsTarget) {
        // 需要选择目标
        window._pendingSkillIdx = idx;
        window._pendingSkillCard = card;
        showHint('请点击一名玩家作为技能卡目标');
        enableTargetSelection('skill');
    } else {
        // 无需目标，直接使用
        submitSkill(card, null);
    }
}

function cancelSkillCard() {
    window._pendingSkillIdx = null;
    window._pendingSkillCard = null;
    // 清除选中状态
    document.querySelectorAll('.p-card').forEach(c => {
        c.classList.remove('selected');
        c.onclick = null;
    });
    const hint = document.getElementById('actionHint');
    if (hint) hint.style.display = 'none';
    toast('已取消使用技能卡', 'info');
}

function submitSkill(card, targetId) {
    if (!socket) return;
    const data = {
        room_id: myRoomId,
        player_id: myPlayerId,
        skill_id: card.skill_type || card.id
    };
    if (targetId) data.target_id = targetId;
    socket.emit('use_skill', data);
    window._pendingSkillIdx = null;
    window._pendingSkillCard = null;
    const hint = document.getElementById('actionHint');
    if (hint) hint.style.display = 'none';
}

function showActionPanel() {
    const ap = document.getElementById('actionPanel');
    const mp = document.getElementById('meetingPanel');
    const dp = document.getElementById('duelPanel');
    const aup = document.getElementById('auctionPanel');
    if (ap) ap.style.display = 'block';
    if (mp) mp.style.display = 'none';
    if (dp) dp.style.display = 'none';
    if (aup) aup.style.display = 'none';
    // 清除结盟通知卡片
    dismissAllianceCard();
    // 重置操作状态
    selectedAction = null;
    actionSubmitted = false;
    duelTargetId = null;
    window._duelInitiator = null;
    window._duelTarget = null;
    document.querySelectorAll('.act-btn[data-action]').forEach(b => b.classList.remove('active'));
    const ga = document.getElementById('gestureArea');
    if (ga) ga.style.display = 'none';
    const hint = document.getElementById('actionHint');
    if (hint) hint.style.display = 'none';
    document.querySelectorAll('.p-card').forEach(c => {
        c.classList.remove('selected');
        c.onclick = null;
    });
    // 重置继续按钮
    const continueBtn = document.getElementById('continueBtn');
    if (continueBtn) {
        continueBtn.style.display = 'block';
        continueBtn.disabled = false;
        continueBtn.textContent = '继续行动';
    }
}

function showMeetingPanel(data) {
    const ap = document.getElementById('actionPanel');
    const mp = document.getElementById('meetingPanel');
    const dp = document.getElementById('duelPanel');
    const aup = document.getElementById('auctionPanel');
    if (ap) ap.style.display = 'none';
    if (dp) dp.style.display = 'none';
    if (aup) aup.style.display = 'none';
    if (mp) {
        mp.style.display = 'block';
        const msgBox = document.getElementById('meetingMessages');
        if (msgBox) {
            // 结构化显示：每人城池变化 + 行动 + 技能卡流出
            let html = '';
            const players = data.players || {};
            const cityChanges = data.city_changes || {};
            const actions = data.actions || {};
            const arr = Array.isArray(players) ? players : Object.values(players);
            const actionLabels = { 'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟', 'dissolve_alliance': '解盟' };
            const gestureLabels = { 'rock': '石头', 'paper': '布', 'scissors': '剪刀' };

            arr.forEach(p => {
                const change = cityChanges[p.id] || 0;
                let changeStr = '';
                if (change > 0) changeStr = '<span style="color:var(--green)">+' + change + '</span>';
                else if (change < 0) changeStr = '<span style="color:var(--red)">' + change + '</span>';
                else changeStr = '<span style="color:var(--text-dim)">+0</span>';

                const deadMark = !p.is_alive ? ' <span style="color:var(--red)">(阵亡)</span>' : '';
                const selfMark = p.id === myPlayerId ? ' <span class="badge badge-blue" style="font-size:10px">我</span>' : '';

                // 显示该玩家的行动
                const act = actions[p.id];
                let actionStr = '';
                if (act) {
                    if (act.type === 'jungle') {
                        actionStr = '<span style="color:var(--gold);font-size:12px">打野 ' + (gestureLabels[act.gesture] || '?') + ' vs ' + (gestureLabels[act.system_gesture] || '?') + ' → ' + (act.result === 'win' ? '成功' : '失败') + '</span>';
                    } else if (act.type === 'attack') {
                        const target = arr.find(ap2 => ap2.id === act.target);
                        actionStr = '<span style="color:var(--red);font-size:12px">攻城→' + (target ? esc(target.name) : '?') + '</span>';
                    } else if (act.type === 'defend') {
                        actionStr = '<span style="color:var(--primary);font-size:12px">守城</span>';
                    } else if (act.type === 'repair') {
                        actionStr = '<span style="color:var(--orange);font-size:12px">修城</span>';
                    } else if (act.type === 'duel') {
                        const target = arr.find(ap2 => ap2.id === act.target);
                        actionStr = '<span style="color:#a855f7;font-size:12px">约战 ' + (target ? esc(target.name) : '?') + ' (' + (act.bet || '?') + '城)</span>';
                    } else if (act.type === 'alliance') {
                        const partner = arr.find(ap2 => ap2.id === act.partner);
                        actionStr = '<span style="color:var(--green);font-size:12px">结盟 ' + (partner ? esc(partner.name) : '?') + '</span>';
                    } else if (act.type === 'dissolve_alliance') {
                        const partner = arr.find(ap2 => ap2.id === act.partner);
                        actionStr = '<span style="color:var(--orange);font-size:12px">解盟 ' + (partner ? esc(partner.name) : '?') + '</span>';
                    }
                }

                html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
                    <span>${esc(p.name)}${selfMark}${deadMark} ${actionStr}</span>
                    <span>${p.cities}城 ${changeStr}</span>
                </div>`;
            });

            // 技能卡流出
            const cardsDrawn = data.skill_cards_drawn || (data.skill_cards ? data.skill_cards.length : 0);
            if (cardsDrawn > 0) {
                html += `<div style="text-align:center;padding:8px 0;color:var(--gold);font-size:13px">本轮技能卡流出 ${cardsDrawn} 张</div>`;
            }

            // 死亡/游戏结束消息
            const msgs = data.messages || [];
            msgs.forEach(m => {
                html += `<div style="text-align:center;padding:4px 0;color:var(--red);font-size:13px">${esc(m)}</div>`;
            });

            if (!html) html = '<div style="text-align:center;color:var(--text-dim)">无事发生</div>';
            msgBox.innerHTML = html;
        }
    }
    // 重置继续按钮 - 观战者/死亡玩家不显示
    const continueBtn = document.getElementById('continueBtn');
    if (continueBtn) {
        const myPlayer = (data.players || {})[myPlayerId];
        const isSpectator = (myPlayer && (myPlayer.is_spectator || !myPlayer.is_alive));
        if (isSpectator) {
            continueBtn.style.display = 'none';
        } else {
            continueBtn.style.display = 'block';
            continueBtn.disabled = false;
            continueBtn.textContent = '继续行动';
        }
    }
}

function renderRoundResult(data) {
    // 更新玩家状态
    let mySkills = [];
    let myData = null;
    const spectators = [];
    const allPlayers = Array.isArray(data.players) ? data.players : Object.values(data.players || {});
    window._lastPlayers = allPlayers;
    if (data.players) {
        const grid = document.getElementById('playerGrid');
        if (grid && data.players) {
            grid.innerHTML = '';
            allPlayers.forEach(p => {
                if (p.id === myPlayerId) {
                    myData = p;
                    myCities = p.cities;
                    const citiesEl = document.getElementById('statCities');
                    if (citiesEl) citiesEl.textContent = p.cities;
                    const cardsEl = document.getElementById('statCards');
                    if (cardsEl) cardsEl.textContent = p.skills_count || 0;
                    mySkills = p.skills || [];
                }
                if (p.is_spectator) {
                    spectators.push(p);
                    return;
                }
                const div = document.createElement('div');
                div.className = 'p-card' + (p.id === myPlayerId ? ' self' : '') + (!p.is_alive ? ' dead' : '');
                div.dataset.pid = p.id;

                // 上帝视角：显示玩家行动和技能
                let godViewHtml = '';
                if (amSpectator && p.id !== myPlayerId) {
                    if (p.action) {
            const actionNames = { 'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟', 'dissolve_alliance': '解盟' };
                        godViewHtml += `<div style="font-size:11px;color:var(--orange);margin-top:4px">行动：${actionNames[p.action.type] || p.action.type || '?'}</div>`;
                    }
                    if (p.skills && p.skills.length > 0) {
                        godViewHtml += `<div style="font-size:11px;color:var(--gold);margin-top:2px">技能：${p.skills.map(s => esc(s.name)).join('、')}</div>`;
                    }
                }

                div.innerHTML = `
                    <div class="p-card-name">${esc(p.name)} ${p.id === myPlayerId ? '<span class="badge badge-blue">我</span>' : ''}</div>
                    <div class="p-card-cities">${p.cities}<small>城</small></div>
                    ${godViewHtml}
                `;
                grid.appendChild(div);
            });
        }
    }

    // 更新观战席
    const specArea = document.getElementById('spectatorArea');
    const specList = document.getElementById('spectatorList');
    if (specArea && specList) {
        if (spectators.length > 0) {
            specArea.style.display = 'block';
            specList.innerHTML = spectators.map(p => {
                const tag = p.id === myPlayerId ? ' <span class="badge badge-blue" style="font-size:10px">我</span>' : '';
                return '<span style="margin-right:10px">' + esc(p.name) + tag + '</span>';
            }).join('');
            // 显示房间号
            const specRoomId = document.getElementById('specRoomId');
            if (specRoomId) specRoomId.textContent = myRoomId;
        } else {
            specArea.style.display = 'none';
        }
    }

    // 更新观战者标志
    const isSpectator = myData && (myData.is_spectator || !myData.is_alive);
    amSpectator = !!isSpectator;

    // 观战者隐藏操作面板，显示所有人技能卡
    if (amSpectator) {
        const ap = document.getElementById('actionPanel');
        if (ap) ap.style.display = 'none';
        updateSpectatorSkillCards(allPlayers);
    } else {
        updateSkillCards(mySkills);
        updateAllianceButton(myData, allPlayers);
    }

    // 刷新上帝视角
    renderGodView(allPlayers);

    // 将回合小结消息记入上帝视角历史
    (data.messages || []).forEach(m => {
        _godViewHistory.push({ round: data.round, type: 'event', text: m });
    });
    // 城池变化记入历史
    const cityChanges = data.city_changes || {};
    Object.keys(cityChanges).forEach(pid => {
        const change = cityChanges[pid];
        if (change !== 0) {
            const p = allPlayers.find(ap => ap.id === pid);
            if (p) {
                const sign = change > 0 ? '+' : '';
                _godViewHistory.push({ round: data.round, type: 'city', text: p.name + ' 城池变化 ' + sign + change + ' → ' + (p.cities) + '城' });
            }
        }
    });
    // 回合行动细节记入历史（系统随机数等）
    const actions = data.actions || {};
    const gestureNames = { 'rock': '石头', 'paper': '布', 'scissors': '剪刀' };
    Object.keys(actions).forEach(pid => {
        const a = actions[pid];
        const p = allPlayers.find(ap => ap.id === pid);
        if (!p) return;
        let text = '';
        if (a.type === 'jungle') {
            text = p.name + ' [打野] 出手：' + (gestureNames[a.gesture] || a.gesture || '?') + ' | 系统：' + (gestureNames[a.system_gesture] || a.system_gesture || '?') + ' | 结果：' + (a.result === 'win' ? '成功（获得技能卡）' : '失败（+' + (data.round >= 6 ? 20 : 10) + '城池）');
        } else if (a.type === 'attack') {
            const target = allPlayers.find(ap => ap.id === a.target);
            text = p.name + ' [攻城] 目标：' + (target ? target.name : '?') + ' | 伤害：' + (a.damage || 0) + ' | 城池转移：' + (a.damage || 0) + '城';
        } else if (a.type === 'defend') {
            text = p.name + ' [守城] 等待反击 | 若被攻击则反弹伤害';
        } else if (a.type === 'repair') {
            text = p.name + ' [修城] 下轮受伤 x2 | 本轮不获得城池';
        } else if (a.type === 'duel') {
            const target = allPlayers.find(ap => ap.id === a.target);
            text = p.name + ' [约战] 目标：' + (target ? target.name : '?') + ' | 赌注：' + (a.bet || '?') + ' 城池 | 进入俄罗斯轮盘';
        } else if (a.type === 'alliance') {
            const partner = allPlayers.find(ap => ap.id === a.partner);
            text = p.name + ' [结盟] 对象：' + (partner ? partner.name : '?');
        } else if (a.type === 'dissolve_alliance') {
            const partner = allPlayers.find(ap => ap.id === a.partner);
            text = p.name + ' [解盟] 与 ' + (partner ? partner.name : '?') + ' 解除同盟';
        }
        if (text) {
            _godViewHistory.push({ round: data.round, type: 'system', text: text });
        }
    });
    // 技能卡流出记入历史
    (data.skill_cards || []).forEach(sc => {
        const p = allPlayers.find(ap => ap.id === sc.player_id);
        if (p) {
            _godViewHistory.push({ round: data.round, type: 'skill', text: p.name + ' [打野成功] 获得技能卡【' + (sc.card?.name || '?') + '】| 效果：' + (sc.card?.description || '?') });
        }
    });

    // 切换到会议面板
    showMeetingPanel({
        players: data.players || {},
        city_changes: data.city_changes || {},
        skill_cards: data.skill_cards || [],
        skill_cards_drawn: (data.skill_cards || []).length,
        messages: data.messages || [],
        actions: data.actions || {}
    });

    // 在聊天区域记录简要信息
    const box = document.getElementById('chatMessages');
    if (box) {
        const div = document.createElement('div');
        div.className = 'chat-msg';
        div.style.background = 'rgba(59,130,246,0.1)';
        div.style.borderRadius = '6px';
        div.style.padding = '8px';
        div.style.marginBottom = '8px';
        const cardsDrawn = (data.skill_cards || []).length;
        let chatText = '<strong>第' + data.round + '回合小结</strong>';
        // 显示行动摘要
        const chatActions = data.actions || {};
        const chatPlayers = Array.isArray(data.players) ? data.players : Object.values(data.players || {});
        const chatActionLabels = { 'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟', 'dissolve_alliance': '解盟' };
        const chatGestureLabels = { 'rock': '石头', 'paper': '布', 'scissors': '剪刀' };
        const actionLines = [];
        Object.keys(chatActions).forEach(pid => {
            const a = chatActions[pid];
            const p = chatPlayers.find(ap2 => ap2.id === pid);
            if (!p) return;
            let line = esc(p.name) + ' [' + (chatActionLabels[a.type] || a.type) + ']';
            if (a.type === 'attack' && a.target) {
                const t = chatPlayers.find(ap2 => ap2.id === a.target);
                if (t) line += ' → ' + esc(t.name);
            } else if (a.type === 'duel' && a.target) {
                const t = chatPlayers.find(ap2 => ap2.id === a.target);
                if (t) line += ' vs ' + esc(t.name);
            } else if (a.type === 'alliance' && a.partner) {
                const t = chatPlayers.find(ap2 => ap2.id === a.partner);
                if (t) line += ' + ' + esc(t.name);
            } else if (a.type === 'jungle') {
                line += ' ' + (chatGestureLabels[a.gesture] || '?') + ' vs ' + (chatGestureLabels[a.system_gesture] || '?') + ' → ' + (a.result === 'win' ? '成功' : '失败');
            }
            actionLines.push(line);
        });
        if (actionLines.length > 0) {
            chatText += '<br>' + actionLines.map(l => '<span class="chat-msg-text" style="color:var(--text-dim)">' + l + '</span>').join('<br>');
        }
        if (cardsDrawn > 0) chatText += '<br>技能卡流出 ' + cardsDrawn + ' 张';
        const msgs = (data.messages && data.messages.length > 0) ? data.messages : [];
        if (msgs.length > 0) chatText += '<br>' + msgs.map(m => '<span class="chat-msg-text">' + esc(m) + '</span>').join('<br>');
        div.innerHTML = chatText;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }
}

// ===== 约战相关 =====

// ===== 拍卖会 =====
function showAuctionPanel(data) {
    const ap = document.getElementById('actionPanel');
    const mp = document.getElementById('meetingPanel');
    const aup = document.getElementById('auctionPanel');
    if (ap) ap.style.display = 'none';
    if (mp) mp.style.display = 'none';
    if (aup) aup.style.display = 'block';

    const phaseEl = document.getElementById('statPhase');
    if (phaseEl) phaseEl.textContent = '拍卖';

    const nameEl = document.getElementById('auctionSkillName');
    const descEl = document.getElementById('auctionSkillDesc');
    const bidEl = document.getElementById('auctionCurrentBid');
    const bidderEl = document.getElementById('auctionHighestBidder');
    const inp = document.getElementById('auctionBidInput');
    const bidArea = document.getElementById('auctionBidArea');

    if (nameEl) nameEl.textContent = data.skill_card?.name || '技能卡';
    if (descEl) descEl.textContent = data.skill_card?.description || '';
    if (bidEl) bidEl.textContent = data.starting_price;
    if (bidderEl) bidderEl.textContent = '';
    if (inp) {
        inp.min = data.starting_price;
        inp.value = data.starting_price;
        inp.max = myCities;
    }
    // 观战者不能出价，隐藏出价区
    if (bidArea) {
        // 清除上一轮拍卖的跳过状态
        const passMsg = document.getElementById('auctionPassMsg');
        if (passMsg) passMsg.remove();
        const bidBtn = document.getElementById('auctionBidBtn');
        const passBtn = document.getElementById('auctionPassBtn');
        if (inp) inp.style.display = '';
        if (bidBtn) bidBtn.style.display = '';
        if (passBtn) passBtn.style.display = '';

        if (amSpectator) {
            bidArea.style.display = 'none';
        } else {
            bidArea.style.display = 'flex';
        }
    }

    // 倒计时
    let remaining = data.time_limit || 30;
    const countdownEl = document.getElementById('auctionCountdown');
    if (countdownEl) countdownEl.textContent = remaining + 's';
    if (window._auctionTimer) clearInterval(window._auctionTimer);
    window._auctionTimer = setInterval(() => {
        remaining--;
        if (countdownEl) countdownEl.textContent = remaining + 's';
        if (remaining <= 0) {
            clearInterval(window._auctionTimer);
            window._auctionTimer = null;
        }
    }, 1000);
}

function submitAuctionBid() {
    const inp = document.getElementById('auctionBidInput');
    if (!inp) return;
    const bid = parseInt(inp.value);
    if (!bid || bid <= 0) {
        toast('请输入有效出价', 'error');
        return;
    }
    socket.emit('auction_bid', { room_id: myRoomId, player_id: myPlayerId, bid: bid });
}

function onAuctionPass() {
    socket.emit('auction_pass', { room_id: myRoomId, player_id: myPlayerId });
    // 禁用出价区，但不销毁内部 DOM
    const area = document.getElementById('auctionBidArea');
    if (area) {
        const passMsg = document.getElementById('auctionPassMsg') || document.createElement('span');
        passMsg.id = 'auctionPassMsg';
        passMsg.style.cssText = 'color:var(--text-dim);font-size:13px';
        passMsg.textContent = '已跳过，等待拍卖结束...';
        if (!document.getElementById('auctionPassMsg')) area.appendChild(passMsg);
        // 隐藏出价输入
        const inp = document.getElementById('auctionBidInput');
        const bidBtn = document.getElementById('auctionBidBtn');
        const passBtn = document.getElementById('auctionPassBtn');
        if (inp) inp.style.display = 'none';
        if (bidBtn) bidBtn.style.display = 'none';
        if (passBtn) passBtn.style.display = 'none';
    }
}

function hideAuctionPanel() {
    const aup = document.getElementById('auctionPanel');
    if (aup) aup.style.display = 'none';
}

function showDuelPanel(data) {
    const ap = document.getElementById('actionPanel');
    const mp = document.getElementById('meetingPanel');
    const dp = document.getElementById('duelPanel');
    const aup = document.getElementById('auctionPanel');
    if (ap) ap.style.display = 'none';
    if (mp) mp.style.display = 'none';
    if (aup) aup.style.display = 'none';
    if (dp) dp.style.display = 'block';

    // 更新阶段显示
    const phaseEl = document.getElementById('statPhase');
    if (phaseEl) phaseEl.textContent = '约战';

    // 保存约战参与者 ID
    window._duelInitiator = data.initiator;
    window._duelTarget = data.target;

    // 保存约战系统信息供上帝视角使用
    window._godDuelInfo = {
        chambers: data.chambers,
        bullet_pos: data.bullet_pos,
        fired: 0,
        current_turn_name: data.initiator_name
    };

    // 是否为约战参与者
    const isParticipant = (myPlayerId === data.initiator || myPlayerId === data.target);

    // 显示约战信息
    const info = document.getElementById('duelInfo');
    if (info) {
        info.innerHTML = `
            <div style="text-align:center;font-size:15px;margin-bottom:8px">
                <strong style="color:var(--red)">${esc(data.initiator_name)}</strong>
                向
                <strong style="color:var(--orange)">${esc(data.target_name)}</strong>
                发起约战
            </div>
            <div style="text-align:center;font-size:14px;color:var(--gold)">
                赌注：${data.bet} 城池
            </div>
        `;
    }

    // 绘制弹仓
    renderChambers(data.chambers, 0);

    // 重置输入框
    const shotsInput = document.getElementById('duelShotsInput');
    if (shotsInput) {
        shotsInput.value = 1;
        shotsInput.max = data.chambers;
        // 回车提交
        shotsInput.onkeypress = e => { if (e.key === 'Enter') shootDuelFromInput(); };
    }

    // 非参与者始终显示等待，参与者根据回合显示
    if (!isParticipant) {
        showDuelWait();
    } else {
        updateDuelTurn(data.current_turn);
    }
}

function renderChambers(total, fired, hitPos) {
    const container = document.getElementById('duelChambers');
    if (!container) return;
    container.innerHTML = '';
    for (let i = 0; i < total; i++) {
        const dot = document.createElement('div');
        dot.className = 'chamber-dot';
        if (i < fired) {
            dot.classList.add(i === hitPos ? 'hit' : 'fired');
            dot.textContent = i === hitPos ? 'X' : '-';
        } else if (i === fired) {
            dot.classList.add('current');
            dot.textContent = '?';
        } else {
            dot.textContent = (i + 1);
        }
        container.appendChild(dot);
    }
}

function updateDuelTurn(currentTurn) {
    const turnInfo = document.getElementById('duelTurnInfo');
    const buttons = document.getElementById('duelButtons');
    const waitInfo = document.getElementById('duelWaitInfo');
    if (!turnInfo) return;

    const isParticipant = (myPlayerId === window._duelInitiator || myPlayerId === window._duelTarget);
    const isMyTurn = currentTurn === myPlayerId;

    if (isMyTurn) {
        turnInfo.innerHTML = '<span style="color:var(--orange)">轮到你了！</span>';
        if (buttons) buttons.style.display = 'flex';
        if (waitInfo) waitInfo.style.display = 'none';
    } else if (isParticipant) {
        turnInfo.innerHTML = '等待对手开枪...';
        if (buttons) buttons.style.display = 'none';
        if (waitInfo) waitInfo.style.display = 'none';
    } else {
        // 非参与者始终等待
        showDuelWait();
    }
}

function showDuelWait() {
    const turnInfo = document.getElementById('duelTurnInfo');
    const buttons = document.getElementById('duelButtons');
    const waitInfo = document.getElementById('duelWaitInfo');
    if (turnInfo) turnInfo.innerHTML = '';
    if (buttons) buttons.style.display = 'none';
    if (waitInfo) waitInfo.style.display = 'block';
}

function shootDuelFromInput() {
    const inp = document.getElementById('duelShotsInput');
    if (!inp) return;
    const shots = parseInt(inp.value);
    if (!shots || shots < 1) {
        toast('请输入有效的枪数', 'error');
        return;
    }
    shootDuel(shots);
}

function shootDuel(shots) {
    if (!socket) return;
    socket.emit('duel_shot', {
        room_id: myRoomId,
        player_id: myPlayerId,
        shots: shots
    });
    // 禁用按钮等待结果
    const btns = document.getElementById('duelButtons');
    if (btns) btns.style.display = 'none';
    const turnInfo = document.getElementById('duelTurnInfo');
    if (turnInfo) turnInfo.innerHTML = '开枪中...';
}

function onDuelShotResult(data) {
    // 更新弹仓显示
    renderChambers(data.total, data.fired, data.hit ? data.fired - 1 : -1);

    // 更新上帝视角约战信息
    if (window._godDuelInfo) {
        window._godDuelInfo.fired = data.fired;
    }

    // 记录到上帝视角日志
    const round = parseInt(document.getElementById('statRound')?.textContent || '1');
    if (data.hit) {
        _godViewHistory.push({ round: round, type: 'duel', text: '[约战] ' + esc(data.player_name) + ' 第 ' + data.fired + ' 发开枪 → 击中！实弹确认在第 ' + data.fired + ' 发' });
    } else {
        _godViewHistory.push({ round: round, type: 'duel', text: '[约战] ' + esc(data.player_name) + ' 开枪 ' + data.shots + ' 发（第 ' + (data.fired - data.shots + 1) + '-' + data.fired + ' 发）→ 空弹 | 剩余 ' + (data.total - data.fired) + ' 发' });
    }

    if (data.hit) {
        const turnInfo = document.getElementById('duelTurnInfo');
        if (turnInfo) {
            turnInfo.innerHTML = '<span style="color:var(--red);font-size:16px">' +
                esc(data.player_name) + ' 被击中！</span>';
        }
        const buttons = document.getElementById('duelButtons');
        if (buttons) buttons.style.display = 'none';
    }

    // 刷新上帝视角
    if (amSpectator) {
        renderGodView(window._lastPlayers || []);
    }
}

function onDuelNextTurn(data) {
    // 更新弹仓
    renderChambers(data.total || 6, data.fired, -1);

    // 更新回合
    updateDuelTurn(data.current_turn);

    // 更新上帝视角约战信息
    if (window._godDuelInfo) {
        window._godDuelInfo.fired = data.fired;
        window._godDuelInfo.current_turn_name = data.current_turn_name || '';
    }

    // 记录换手日志
    const round = parseInt(document.getElementById('statRound')?.textContent || '1');
    _godViewHistory.push({ round: round, type: 'duel', text: '[约战] 换手 → 轮到 ' + esc(data.current_turn_name || '?') + ' | 已开 ' + data.fired + '/' + (data.total || 6) + ' 发 | 实弹在第 ' + ((window._godDuelInfo?.bullet_pos || 0) + 1) + ' 发' });

    // 更新输入框的 max
    const inp = document.getElementById('duelShotsInput');
    if (inp && data.remaining) {
        inp.max = data.remaining;
        if (parseInt(inp.value) > data.remaining) inp.value = data.remaining;
    }

    // 刷新上帝视角
    if (amSpectator) {
        renderGodView(window._lastPlayers || []);
        renderGodView(window._lastPlayers || []);
    }
}

function onDuelEnded(data) {
    const dp = document.getElementById('duelPanel');
    if (dp) dp.style.display = 'none';
    const waitInfo = document.getElementById('duelWaitInfo');
    if (waitInfo) waitInfo.style.display = 'none';

    // 清理约战状态
    window._duelInitiator = null;
    window._duelTarget = null;
    window._godDuelInfo = null;

    // 更新玩家状态
    let mySkills = [];
    if (data.players) {
        window._lastPlayers = Array.isArray(data.players) ? data.players : Object.values(data.players);
        const grid = document.getElementById('playerGrid');
        if (grid) {
            grid.innerHTML = '';
            const arr = Array.isArray(data.players) ? data.players : Object.values(data.players);
            arr.forEach(p => {
                if (p.id === myPlayerId) {
                    myCities = p.cities;
                    const citiesEl = document.getElementById('statCities');
                    if (citiesEl) citiesEl.textContent = p.cities;
                    const cardsEl = document.getElementById('statCards');
                    if (cardsEl) cardsEl.textContent = p.skills_count || 0;
                    mySkills = p.skills || [];
                }
                const div = document.createElement('div');
                div.className = 'p-card' + (p.id === myPlayerId ? ' self' : '') + (!p.is_alive ? ' dead' : '');
                div.dataset.pid = p.id;
                div.innerHTML = `
                    <div class="p-card-name">${esc(p.name)} ${p.id === myPlayerId ? '<span class="badge badge-blue">我</span>' : ''}</div>
                    <div class="p-card-cities">${p.cities}<small>城</small></div>
                `;
                grid.appendChild(div);
            });
        }
    }

    // 更新技能卡
    updateSkillCards(mySkills);

    // 在聊天区域通知约战结果
    const box = document.getElementById('chatMessages');
    if (box) {
        const div = document.createElement('div');
        div.className = 'chat-msg';
        div.style.background = 'rgba(239,68,68,0.1)';
        div.style.borderRadius = '6px';
        div.style.padding = '8px';
        div.style.marginBottom = '8px';
        div.innerHTML = '<strong style="color:var(--red)">约战结束</strong><br>' +
            '<span class="chat-msg-text">' + esc(data.loser_name) + ' 落败，' +
            esc(data.winner_name) + ' 赢得 ' + data.bet + ' 城池</span>';
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }

    toast(data.winner_name + ' 赢得约战！', 'info');

    // 记录到上帝视角历史
    const duelRound = parseInt(document.getElementById('statRound')?.textContent || '1');
     _godViewHistory.push({ round: duelRound, type: 'duel', text: '[约战结束] ' + data.loser_name + ' 被击中落败 | ' + data.winner_name + ' 赢得 ' + data.bet + ' 城池' });

    // 刷新上帝视角
    if (amSpectator) {
        renderGodView(window._lastPlayers || []);
    }

    // 约战结束后由后端发送 round_result 触发小结显示，不在这里调用 showMeetingPanel
}

function _phaseLabel(phase) {
    const map = {
        'waiting': '等待', 'action': '行动', 'meeting': '会议',
        'auction': '拍卖', 'duel': '约战', 'finished': '结束'
    };
    return map[phase] || phase || '行动';
}

// ===== 工具 =====
function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
