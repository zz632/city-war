/**
 * 城池战争 - 主应用逻辑
 * 现代简洁版 UI
 */

// 全局状态
const AppState = {
    socket: null,
    roomId: null,
    playerId: null,
    playerName: '',
    isHost: false,
    gameState: null,
    players: [],
    currentTab: 'action',
    selectedAction: null,
    selectedTarget: null,
    selectedSkill: null,
    messages: [],
    unreadCount: 0
};

// Socket.IO 连接
function initSocket() {
    AppState.socket = io();
    
    AppState.socket.on('connect', () => {
        console.log('Connected to server');
        AppState.playerId = AppState.socket.id;
    });
    
    AppState.socket.on('room_joined', (data) => {
        AppState.roomId = data.room_id;
        AppState.isHost = data.is_host;
        AppState.players = data.players;
        showScreen('lobby');
        updateLobby();
    });
    
    AppState.socket.on('player_joined', (data) => {
        AppState.players = data.players;
        updateLobby();
        showToast(`${data.player_name} 加入了房间`);
    });
    
    AppState.socket.on('player_left', (data) => {
        AppState.players = data.players;
        AppState.isHost = data.is_host;
        updateLobby();
        showToast(`${data.player_name} 离开了房间`);
    });
    
    AppState.socket.on('game_started', (data) => {
        AppState.gameState = data.game_state;
        showScreen('game');
        initGame();
        showToast('游戏开始！');
    });
    
    AppState.socket.on('game_state_updated', (data) => {
        AppState.gameState = data;
        updateGameUI();
    });
    
    AppState.socket.on('action_result', (data) => {
        showActionResult(data);
    });
    
    AppState.socket.on('chat_message', (data) => {
        addChatMessage(data);
    });
    
    AppState.socket.on('error', (data) => {
        showToast(data.message, 'error');
    });
}

// 创建房间
function createRoom() {
    const name = document.getElementById('playerName').value.trim();
    if (!name) {
        showToast('请输入玩家名称', 'error');
        return;
    }
    
    AppState.playerName = name;
    AppState.socket.emit('create_room', { player_name: name });
}

// 加入房间
function joinRoom() {
    const name = document.getElementById('playerName').value.trim();
    const roomId = document.getElementById('roomCode').value.trim().toUpperCase();
    
    if (!name) {
        showToast('请输入玩家名称', 'error');
        return;
    }
    if (!roomId) {
        showToast('请输入房间代码', 'error');
        return;
    }
    
    AppState.playerName = name;
    AppState.socket.emit('join_room', { 
        room_id: roomId, 
        player_name: name 
    });
}

// 开始游戏
function startGame() {
    if (!AppState.isHost) return;
    AppState.socket.emit('start_game', { room_id: AppState.roomId });
}

// 提交行动
function submitAction() {
    if (!AppState.selectedAction) {
        showToast('请选择行动', 'error');
        return;
    }
    
    const actionData = {
        room_id: AppState.roomId,
        action_type: AppState.selectedAction,
        target_id: AppState.selectedTarget,
        skill_id: AppState.selectedSkill
    };
    
    AppState.socket.emit('submit_action', actionData);
    
    // 重置选择
    AppState.selectedAction = null;
    AppState.selectedTarget = null;
    AppState.selectedSkill = null;
    
    // 更新 UI
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    document.querySelectorAll('.player-target').forEach(p => {
        p.classList.remove('selected');
    });
    document.querySelectorAll('.skill-card').forEach(c => {
        c.classList.remove('selected');
    });
    
    showToast('行动已提交');
}

// 选择行动
function selectAction(action) {
    AppState.selectedAction = action;
    
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    document.querySelector(`[data-action="${action}"]`).classList.add('selected');
    
    // 显示/隐藏目标选择
    const targetSection = document.getElementById('targetSection');
    if (action === 'attack' || action === 'duel' || action === 'alliance') {
        targetSection.classList.remove('hidden');
    } else {
        targetSection.classList.add('hidden');
        AppState.selectedTarget = null;
    }
}

// 选择目标
function selectTarget(playerId) {
    AppState.selectedTarget = playerId;
    
    document.querySelectorAll('.player-target').forEach(p => {
        p.classList.remove('selected');
    });
    document.querySelector(`[data-player-id="${playerId}"]`).classList.add('selected');
}

// 选择技能卡
function selectSkill(skillId) {
    AppState.selectedSkill = skillId;
    
    document.querySelectorAll('.skill-card').forEach(c => {
        c.classList.remove('selected');
    });
    document.querySelector(`[data-skill-id="${skillId}"]`).classList.add('selected');
}

// 使用技能卡
function useSkill() {
    if (!AppState.selectedSkill) {
        showToast('请选择技能卡', 'error');
        return;
    }
    
    AppState.socket.emit('use_skill', {
        room_id: AppState.roomId,
        skill_id: AppState.selectedSkill,
        target_id: AppState.selectedTarget
    });
}

// 发送聊天消息
function sendChat() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    AppState.socket.emit('chat_message', {
        room_id: AppState.roomId,
        message: message
    });
    
    input.value = '';
}

// 更新大厅 UI
function updateLobby() {
    document.getElementById('roomCodeDisplay').textContent = AppState.roomId;
    document.getElementById('playerCount').textContent = AppState.players.length;
    
    const playerList = document.getElementById('playerList');
    playerList.innerHTML = AppState.players.map(p => `
        <div class="player-item ${p.is_host ? 'host' : ''}">
            <span class="player-name">${p.name}</span>
            ${p.is_host ? '<span class="host-badge">房主</span>' : ''}
        </div>
    `).join('');
    
    // 显示/隐藏开始按钮
    const startBtn = document.getElementById('startBtn');
    if (AppState.isHost) {
        startBtn.classList.remove('hidden');
        startBtn.disabled = AppState.players.length < 2;
    } else {
        startBtn.classList.add('hidden');
    }
}

// 初始化游戏界面
function initGame() {
    updateGameUI();
    updatePlayersList();
    updateSkillsList();
}

// 更新游戏 UI
function updateGameUI() {
    if (!AppState.gameState) return;
    
    // 更新回合信息
    document.getElementById('roundNumber').textContent = AppState.gameState.round;
    document.getElementById('phaseName').textContent = getPhaseName(AppState.gameState.phase);
    
    // 更新我的信息
    const me = AppState.gameState.players.find(p => p.id === AppState.playerId);
    if (me) {
        document.getElementById('myCities').textContent = me.cities;
        document.getElementById('mySkillCount').textContent = me.skills_count || 0;
    }
    
    // 更新玩家列表
    updatePlayersList();
    
    // 更新技能卡
    updateSkillsList();
}

// 更新玩家列表
function updatePlayersList() {
    if (!AppState.gameState) return;
    
    const container = document.getElementById('playersList');
    const alivePlayers = AppState.gameState.players.filter(p => p.is_alive && p.id !== AppState.playerId);
    
    container.innerHTML = alivePlayers.map(p => `
        <div class="player-target" data-player-id="${p.id}" onclick="selectTarget('${p.id}')">
            <div class="player-avatar">${p.name[0]}</div>
            <div class="player-info">
                <div class="player-name">${p.name}</div>
                <div class="player-cities">${p.cities} 城池</div>
            </div>
        </div>
    `).join('');
}

// 更新技能卡列表
function updateSkillsList() {
    if (!AppState.gameState) return;
    
    const me = AppState.gameState.players.find(p => p.id === AppState.playerId);
    if (!me || !me.skills) return;
    
    const container = document.getElementById('skillsList');
    container.innerHTML = me.skills.map(s => `
        <div class="skill-card" data-skill-id="${s.id}" onclick="selectSkill('${s.id}')">
            <div class="skill-name">${s.name}</div>
            <div class="skill-type">${getSkillTypeName(s.type)}</div>
            <div class="skill-desc">${s.description}</div>
        </div>
    `).join('');
}

// 添加聊天消息
function addChatMessage(data) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${data.player_id === AppState.playerId ? 'self' : ''}`;
    messageDiv.innerHTML = `
        <span class="chat-author">${data.player_name}</span>
        <span class="chat-text">${data.message}</span>
    `;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
    
    // 如果在其他标签页，增加未读计数
    if (AppState.currentTab !== 'chat') {
        AppState.unreadCount++;
        updateUnreadBadge();
    }
}

// 显示行动结果
function showActionResult(data) {
    const modal = document.getElementById('resultModal');
    const content = document.getElementById('resultContent');
    
    content.innerHTML = `
        <h3>${data.title}</h3>
        <p>${data.message}</p>
        ${data.city_change ? `<div class="city-change ${data.city_change > 0 ? 'positive' : 'negative'}">${data.city_change > 0 ? '+' : ''}${data.city_change}</div>` : ''}
    `;
    
    modal.classList.remove('hidden');
    
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 3000);
}

// 切换标签页
function switchTab(tab) {
    AppState.currentTab = tab;
    
    // 更新标签按钮
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    
    // 更新内容区域
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tab}Tab`);
    });
    
    // 清除未读标记
    if (tab === 'chat') {
        AppState.unreadCount = 0;
        updateUnreadBadge();
    }
}

// 更新未读标记
function updateUnreadBadge() {
    const badge = document.getElementById('chatBadge');
    if (AppState.unreadCount > 0) {
        badge.textContent = AppState.unreadCount;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// 显示/隐藏屏幕
function showScreen(screen) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(`${screen}Screen`).classList.add('active');
}

// 显示提示
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 获取阶段名称
function getPhaseName(phase) {
    const names = {
        'action': '行动阶段',
        'meeting': '会议阶段',
        'auction': '拍卖阶段',
        'duel': '约战阶段',
        'finished': '游戏结束'
    };
    return names[phase] || phase;
}

// 获取技能类型名称
function getSkillTypeName(type) {
    const names = {
        'attack': '攻击',
        'defense': '防御',
        'resource': '资源',
        'special': '特殊'
    };
    return names[type] || type;
}

// 键盘事件
function handleKeyPress(e) {
    if (e.key === 'Enter') {
        if (document.activeElement.id === 'chatInput') {
            sendChat();
        }
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    
    // 绑定键盘事件
    document.addEventListener('keypress', handleKeyPress);
    
    // 绑定标签切换
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
});
