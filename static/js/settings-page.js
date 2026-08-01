/* 设置页面逻辑 */
(function () {
    var ui = window._uiSettings;
    if (!ui) return;

    var PRESETS = ui.PRESETS;
    var settings = ui.load();

    var currentSection = 'account'; // 当前选中 section
    var isNarrow = window.innerWidth < 768;
    var narrowView = 'list'; // 'list' | 'detail'
    var profileData = null;
    var isLocalMode = !localStorage.getItem('auth_token');

    // ===== 导航 =====
    function selectSection(section) {
        currentSection = section;
        if (isNarrow) {
            narrowView = 'detail';
            renderNarrowDetail();
        } else {
            updateSidebarActive();
            renderWideContent();
        }
    }

    function goBack() {
        if (isNarrow && narrowView === 'detail') {
            narrowView = 'list';
            renderNarrowList();
        } else {
            window.history.back();
        }
    }

    // ===== 侧边栏 =====
    function updateSidebarActive() {
        document.querySelectorAll('.sp-sidebar-item').forEach(function (item) {
            item.classList.toggle('active', item.dataset.section === currentSection);
        });
    }

    // ===== 账号 Section =====
    function renderAccountSection(container) {
        if (isLocalMode) {
            container.innerHTML =
                '<div class="sp-section-header">' +
                    '<svg class="sp-section-icon" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
                    '<span>账号</span>' +
                '</div>' +
                '<div class="sp-local-msg">' +
                    '<svg viewBox="0 0 24 24" width="32" height="32" style="stroke:var(--text-tertiary);fill:none;stroke-width:1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>' +
                    '<p>本地模式 - 无需登录</p>' +
                '</div>';
            return;
        }

        container.innerHTML =
            '<div class="sp-section-header">' +
                '<svg class="sp-section-icon" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
                '<span>账号</span>' +
            '</div>' +
            '<div id="profileInfo" class="sp-profile-info"></div>' +
            '<div class="field">' +
                '<label class="field-label"><span>昵称</span></label>' +
                '<input type="text" id="profileDisplayName" class="field-input" placeholder="新昵称" maxlength="12" autocomplete="off">' +
            '</div>' +
            '<div id="profilePasswordSection">' +
                '<div class="field">' +
                    '<label class="field-label"><span>旧密码</span></label>' +
                    '<div class="field-input-wrap">' +
                        '<input type="password" id="profileOldPassword" class="field-input field-input-pw" placeholder="输入旧密码" autocomplete="off">' +
                        '<button class="pw-toggle" onclick="togglePw(\'profileOldPassword\', this)" title="显示/隐藏密码">' +
                            '<svg class="pw-eye-open" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
                            '<svg class="pw-eye-closed" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' +
                        '</button>' +
                    '</div>' +
                '</div>' +
                '<div class="field">' +
                    '<label class="field-label"><span>新密码</span></label>' +
                    '<div class="field-input-wrap">' +
                        '<input type="password" id="profileNewPassword" class="field-input field-input-pw" placeholder="输入新密码（留空不改）" autocomplete="off">' +
                        '<button class="pw-toggle" onclick="togglePw(\'profileNewPassword\', this)" title="显示/隐藏密码">' +
                            '<svg class="pw-eye-open" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
                            '<svg class="pw-eye-closed" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' +
                        '</button>' +
                    '</div>' +
                '</div>' +
                '<div class="field">' +
                    '<label class="field-label"><span>确认新密码</span></label>' +
                    '<div class="field-input-wrap">' +
                        '<input type="password" id="profileNewPasswordConfirm" class="field-input field-input-pw" placeholder="再输入一次新密码" autocomplete="off">' +
                        '<button class="pw-toggle" onclick="togglePw(\'profileNewPasswordConfirm\', this)" title="显示/隐藏密码">' +
                            '<svg class="pw-eye-open" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
                            '<svg class="pw-eye-closed" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' +
                        '</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<button class="btn btn-primary sp-save-btn" onclick="settingsPageSaveProfile()">保存</button>';

        loadProfile();
    }

    function loadProfile() {
        var authToken = localStorage.getItem('auth_token') || '';
        fetch('/api/auth/profile', { headers: { 'Authorization': 'Bearer ' + authToken } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    profileData = data;
                    var dnInput = document.getElementById('profileDisplayName');
                    if (dnInput) dnInput.value = data.display_name || '';
                    var info = document.getElementById('profileInfo');
                    if (info) {
                        info.innerHTML =
                            '<div class="sp-profile-row"><span class="sp-profile-label">用户名</span><span>' + escHtml(data.username) + '</span></div>' +
                            (data.email ? '<div class="sp-profile-row"><span class="sp-profile-label">邮箱</span><span>' + escHtml(data.email) + '</span></div>' : '') +
                            (data.oauth_provider ? '<div class="sp-profile-row"><span class="sp-profile-label">登录方式</span><span>' + escHtml(data.oauth_provider.toUpperCase()) + '</span></div>' : '') +
                            (data.is_guest ? '<div class="sp-profile-row"><span class="sp-profile-label">账号类型</span><span class="badge badge-gray">游客</span></div>' : '');
                    }
                    var pwSection = document.getElementById('profilePasswordSection');
                    if (pwSection) {
                        pwSection.style.display = (data.is_guest || data.oauth_provider) ? 'none' : 'block';
                    }
                }
            })
            .catch(function () {});
    }

    window.settingsPageSaveProfile = function () {
        var authToken = localStorage.getItem('auth_token') || '';
        var display_name = (document.getElementById('profileDisplayName').value || '').trim();
        var old_password = document.getElementById('profileOldPassword') ? document.getElementById('profileOldPassword').value : '';
        var new_password = document.getElementById('profileNewPassword') ? document.getElementById('profileNewPassword').value : '';
        var new_password_confirm = document.getElementById('profileNewPasswordConfirm') ? document.getElementById('profileNewPasswordConfirm').value : '';

        if (new_password && new_password !== new_password_confirm) {
            toast('两次输入的新密码不一致', 'error');
            return;
        }

        var body = { display_name: display_name };
        if (new_password) {
            body.old_password = old_password;
            body.new_password = new_password;
        }

        fetch('/api/auth/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
            body: JSON.stringify(body)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    toast('修改成功', 'success');
                } else {
                    toast(data.message || '修改失败', 'error');
                }
            })
            .catch(function () { toast('网络错误', 'error'); });
    };

    // ===== AI 配置 Section =====
    var AI_CONFIG_KEY = 'citywar_ai_config';
    var AI_DEFAULTS = { base_url: 'https://api.openai.com/v1', api_key: '', model: 'gpt-4o-mini' };

    function getAuthToken() {
        return localStorage.getItem('auth_token') || '';
    }

    function renderAIConfigSection(container) {
        // 先渲染骨架
        container.innerHTML =
            '<div class="sp-section-header">' +
                '<svg class="sp-section-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>' +
                '<span>AI 配置</span>' +
            '</div>' +
            (isLocalMode ? '<div class="sp-settings-group-label" style="color:var(--text-tertiary);font-size:12px;margin-bottom:8px">本地模式：配置保存在浏览器本地</div>' : '') +
            '<div class="sp-settings-group">' +
                '<div class="sp-settings-group-label" style="color:var(--text-tertiary);font-size:13px;margin-bottom:12px">使用 OpenAI 兼容格式（支持 OpenAI、DeepSeek、通义千问等兼容服务）</div>' +
                '<div class="field">' +
                    '<label class="field-label"><span>API Base URL</span></label>' +
                    '<input type="text" id="aiBaseUrl" class="field-input" placeholder="https://api.openai.com/v1" autocomplete="off">' +
                '</div>' +
                '<div class="field">' +
                    '<label class="field-label"><span>API Key</span></label>' +
                    '<div class="field-input-wrap">' +
                        '<input type="password" id="aiApiKey" class="field-input field-input-pw" placeholder="sk-..." autocomplete="off">' +
                        '<button class="pw-toggle" onclick="togglePw(\'aiApiKey\', this)" title="显示/隐藏密码">' +
                            '<svg class="pw-eye-open" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
                            '<svg class="pw-eye-closed" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' +
                        '</button>' +
                    '</div>' +
                '</div>' +
                '<div class="field">' +
                    '<label class="field-label"><span>模型名称</span></label>' +
                    '<input type="text" id="aiModel" class="field-input" placeholder="gpt-4o-mini" autocomplete="off">' +
                '</div>' +
            '</div>' +
            '<button class="btn btn-primary sp-save-btn" onclick="settingsPageSaveAIConfig()">保存</button>';

        // 加载配置：登录用户从服务器，本地模式从localStorage
        if (isLocalMode) {
            try {
                var raw = localStorage.getItem(AI_CONFIG_KEY);
                if (raw) {
                    var c = JSON.parse(raw);
                    var el;
                    el = document.getElementById('aiBaseUrl');
                    if (el) el.value = c.base_url || AI_DEFAULTS.base_url;
                    el = document.getElementById('aiApiKey');
                    if (el) el.value = c.api_key || '';
                    el = document.getElementById('aiModel');
                    if (el) el.value = c.model || AI_DEFAULTS.model;
                }
            } catch (e) {}
        } else {
            fetch('/api/ai/config', { headers: { 'Authorization': 'Bearer ' + getAuthToken() } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success && data.config) {
                        var c = data.config;
                        var el;
                        el = document.getElementById('aiBaseUrl');
                        if (el) el.value = c.base_url || AI_DEFAULTS.base_url;
                        el = document.getElementById('aiApiKey');
                        if (el) el.value = c.api_key || '';
                        el = document.getElementById('aiModel');
                        if (el) el.value = c.model || AI_DEFAULTS.model;
                        // 同步写回localStorage作fallback
                        localStorage.setItem(AI_CONFIG_KEY, JSON.stringify({
                            base_url: c.base_url || AI_DEFAULTS.base_url,
                            api_key: c.api_key || '',
                            model: c.model || AI_DEFAULTS.model
                        }));
                    }
                })
                .catch(function () {});
        }
    }

    window.settingsPageSaveAIConfig = function () {
        var base_url = (document.getElementById('aiBaseUrl').value || '').trim();
        var api_key = (document.getElementById('aiApiKey').value || '').trim();
        var model = (document.getElementById('aiModel').value || '').trim();

        if (!base_url) {
            toast('请填写 API Base URL', 'error');
            return;
        }
        if (!api_key) {
            toast('请填写 API Key', 'error');
            return;
        }
        if (!model) {
            toast('请填写模型名称', 'error');
            return;
        }

        // 同时写入localStorage作fallback，服务器端也保存（登录模式）
        localStorage.setItem(AI_CONFIG_KEY, JSON.stringify({ base_url: base_url, api_key: api_key, model: model }));
        if (isLocalMode) {
            toast('AI 配置已保存', 'success');
        } else {
            fetch('/api/ai/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + getAuthToken() },
                body: JSON.stringify({ base_url: base_url, api_key: api_key, model: model })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        toast('AI 配置已保存', 'success');
                    } else {
                        toast(data.message || '保存失败', 'error');
                    }
                })
                .catch(function () { toast('网络错误', 'error'); });
        }
    };

    // ===== 外观 Section =====
    function renderAppearanceSection(container) {
        settings = ui.load();
        var rgb = ui.hexToRgb(settings.bgColor);

        container.innerHTML =
            '<div class="sp-section-header">' +
                '<svg class="sp-section-icon" viewBox="0 0 24 24"><circle cx="13.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="10.5" r="2.5"/><circle cx="8.5" cy="7.5" r="2.5"/><circle cx="6.5" cy="12.5" r="2.5"/><path d="M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z"/></svg>' +
                '<span>外观</span>' +
            '</div>' +

            // 预设颜色
            '<div class="sp-settings-group">' +
                '<div class="sp-settings-group-label">预设颜色</div>' +
                '<div class="sp-preset-row">' +
                    PRESETS.map(function (p) {
                        var active = settings.bgColor.toUpperCase() === p.color.toUpperCase() && !settings.bgImage ? ' active' : '';
                        return '<div class="color-dot' + active + '" data-color="' + p.color + '" title="' + p.name + '" style="background:' + p.color + '"></div>';
                    }).join('') +
                '</div>' +
            '</div>' +

            // 自定义颜色
            '<div class="sp-settings-group">' +
                '<div class="sp-settings-group-label">自定义颜色</div>' +
                '<div class="sp-rgb-area">' +
                    '<div class="sp-rgb-preview-row">' +
                        '<div id="customColorPreview" class="sp-color-preview" style="background:' + settings.bgColor + '"></div>' +
                        '<span id="customColorHex" class="sp-color-hex">' + settings.bgColor.toUpperCase() + '</span>' +
                    '</div>' +
                    '<div class="sp-slider-row">' +
                        '<span class="sp-slider-label" style="color:#FF3B30">R</span>' +
                        '<input type="range" class="ui-slider" id="rgbR" min="0" max="255" value="' + rgb.r + '">' +
                        '<span id="rgbRVal" class="sp-slider-val">' + rgb.r + '</span>' +
                    '</div>' +
                    '<div class="sp-slider-row">' +
                        '<span class="sp-slider-label" style="color:#34C759">G</span>' +
                        '<input type="range" class="ui-slider" id="rgbG" min="0" max="255" value="' + rgb.g + '">' +
                        '<span id="rgbGVal" class="sp-slider-val">' + rgb.g + '</span>' +
                    '</div>' +
                    '<div class="sp-slider-row">' +
                        '<span class="sp-slider-label" style="color:#007AFF">B</span>' +
                        '<input type="range" class="ui-slider" id="rgbB" min="0" max="255" value="' + rgb.b + '">' +
                        '<span id="rgbBVal" class="sp-slider-val">' + rgb.b + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +

            // 背景图片
            '<div class="sp-settings-group">' +
                '<div class="sp-settings-group-label">背景图片</div>' +
                '<div class="sp-bg-row">' +
                    (settings.bgImage ? '<button class="upload-btn" id="clearBgImg">清除</button> ' : '') +
                    '<button class="upload-btn" id="uploadBgImg">选择图片</button>' +
                    '<input type="file" id="bgImgInput" accept="image/*" style="display:none">' +
                '</div>' +
            '</div>';

        // 绑定事件
        bindAppearanceEvents(container);
    }

    function bindAppearanceEvents(container) {
        // 预设颜色点击
        container.querySelectorAll('.color-dot').forEach(function (dot) {
            dot.onclick = function () {
                settings.bgColor = this.dataset.color;
                settings.bgImage = '';
                ui.save(settings);
                ui.applySettings(settings);
                // 更新 UI
                container.querySelectorAll('.color-dot').forEach(function (d) { d.classList.remove('active'); });
                this.classList.add('active');
                var c = ui.hexToRgb(settings.bgColor);
                container.querySelector('#rgbR').value = c.r;
                container.querySelector('#rgbG').value = c.g;
                container.querySelector('#rgbB').value = c.b;
                container.querySelector('#rgbRVal').textContent = c.r;
                container.querySelector('#rgbGVal').textContent = c.g;
                container.querySelector('#rgbBVal').textContent = c.b;
                container.querySelector('#customColorPreview').style.background = settings.bgColor;
                container.querySelector('#customColorHex').textContent = settings.bgColor.toUpperCase();
            };
        });

        // RGB 滑块
        function updateRgb() {
            var r = parseInt(container.querySelector('#rgbR').value);
            var g = parseInt(container.querySelector('#rgbG').value);
            var b = parseInt(container.querySelector('#rgbB').value);
            container.querySelector('#rgbRVal').textContent = r;
            container.querySelector('#rgbGVal').textContent = g;
            container.querySelector('#rgbBVal').textContent = b;
            var hex = ui.rgbToHex(r, g, b);
            container.querySelector('#customColorPreview').style.background = hex;
            container.querySelector('#customColorHex').textContent = hex.toUpperCase();
            settings.bgColor = hex;
            settings.bgImage = '';
            ui.save(settings);
            ui.applySettings(settings);
            container.querySelectorAll('.color-dot').forEach(function (d) { d.classList.remove('active'); });
            PRESETS.forEach(function (p, i) {
                if (p.color.toUpperCase() === hex.toUpperCase()) {
                    container.querySelectorAll('.color-dot')[i].classList.add('active');
                }
            });
        }
        container.querySelector('#rgbR').oninput = updateRgb;
        container.querySelector('#rgbG').oninput = updateRgb;
        container.querySelector('#rgbB').oninput = updateRgb;

        // 背景图片
        var fileInput = container.querySelector('#bgImgInput');
        container.querySelector('#uploadBgImg').onclick = function () { fileInput.click(); };
        fileInput.onchange = function () {
            var file = this.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function (e) {
                var img = new Image();
                img.onload = function () {
                    var canvas = document.createElement('canvas');
                    var maxW = 1200;
                    var scale = Math.min(1, maxW / img.width);
                    canvas.width = img.width * scale;
                    canvas.height = img.height * scale;
                    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                    var dataUrl = canvas.toDataURL('image/jpeg', 0.7);
                    settings.bgImage = dataUrl;
                    ui.save(settings);
                    ui.applySettings(settings);
                    renderAppearanceSection(container);
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        };

        var clearBtn = container.querySelector('#clearBgImg');
        if (clearBtn) {
            clearBtn.onclick = function () {
                settings.bgImage = '';
                ui.save(settings);
                ui.applySettings(settings);
                renderAppearanceSection(container);
            };
        }
    }

    // ===== 宽屏布局 (≥768px) =====
    function renderWideLayout() {
        var main = document.getElementById('spMain');
        main.innerHTML =
            '<div class="sp-sidebar" id="spSidebar">' +
                '<div class="sp-sidebar-item active" data-section="account">' +
                    '<svg class="sp-sidebar-icon" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
                    '<span>账号</span>' +
                '</div>' +
                '<div class="sp-sidebar-item" data-section="appearance">' +
                    '<svg class="sp-sidebar-icon" viewBox="0 0 24 24"><circle cx="13.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="10.5" r="2.5"/><circle cx="8.5" cy="7.5" r="2.5"/><circle cx="6.5" cy="12.5" r="2.5"/><path d="M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z"/></svg>' +
                    '<span>外观</span>' +
                '</div>' +
                '<div class="sp-sidebar-item" data-section="ai">' +
                    '<svg class="sp-sidebar-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>' +
                    '<span>AI 配置</span>' +
                '</div>' +
            '</div>' +
            '<div class="sp-content" id="spContent"></div>';

        // 绑定侧边栏点击
        main.querySelectorAll('.sp-sidebar-item').forEach(function (item) {
            item.onclick = function () {
                selectSection(this.dataset.section);
            };
        });

        renderWideContent();
    }

    function renderWideContent() {
        var content = document.getElementById('spContent');
        if (!content) return;
        if (currentSection === 'account') {
            renderAccountSection(content);
        } else if (currentSection === 'appearance') {
            renderAppearanceSection(content);
        } else if (currentSection === 'ai') {
            renderAIConfigSection(content);
        }
    }

    // ===== 窄屏布局 (<768px) =====
    function renderNarrowLayout() {
        if (narrowView === 'list') {
            renderNarrowList();
        } else {
            renderNarrowDetail();
        }
    }

    function renderNarrowList() {
        var main = document.getElementById('spMain');
        main.innerHTML =
            '<div class="sp-narrow-list">' +
                '<div class="sp-narrow-item" data-section="account">' +
                    '<svg class="sp-narrow-icon" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
                    '<span class="sp-narrow-label">账号</span>' +
                    '<svg class="sp-narrow-chevron" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>' +
                '</div>' +
                '<div class="sp-narrow-item" data-section="appearance">' +
                    '<svg class="sp-narrow-icon" viewBox="0 0 24 24"><circle cx="13.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="10.5" r="2.5"/><circle cx="8.5" cy="7.5" r="2.5"/><circle cx="6.5" cy="12.5" r="2.5"/><path d="M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z"/></svg>' +
                    '<span class="sp-narrow-label">外观</span>' +
                    '<svg class="sp-narrow-chevron" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>' +
                '</div>' +
                '<div class="sp-narrow-item" data-section="ai">' +
                    '<svg class="sp-narrow-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>' +
                    '<span class="sp-narrow-label">AI 配置</span>' +
                    '<svg class="sp-narrow-chevron" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>' +
                '</div>' +
            '</div>';

        main.querySelectorAll('.sp-narrow-item').forEach(function (item) {
            item.onclick = function () {
                selectSection(this.dataset.section);
            };
        });
    }

    function renderNarrowDetail() {
        var main = document.getElementById('spMain');
        main.innerHTML = '<div class="sp-content" id="spContent"></div>';
        if (currentSection === 'account') {
            renderAccountSection(document.getElementById('spContent'));
        } else if (currentSection === 'appearance') {
            renderAppearanceSection(document.getElementById('spContent'));
        } else if (currentSection === 'ai') {
            renderAIConfigSection(document.getElementById('spContent'));
        }
    }

    // ===== 工具 =====
    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // ===== Toast 复用 =====
    function toast(msg, type) {
        if (window.toast) {
            window.toast(msg, type || 'info');
        }
    }

    // ===== 初始化 =====
    function init() {
        // 返回按钮
        document.getElementById('spBack').onclick = goBack;

        // 应用主题
        settings = ui.load();
        ui.applySettings(settings);

        // 渲染布局
        renderLayout();

        // 监听窗口大小变化
        window.addEventListener('resize', function () {
            var newNarrow = window.innerWidth < 768;
            if (newNarrow !== isNarrow) {
                isNarrow = newNarrow;
                renderLayout();
            }
        });
    }

    function renderLayout() {
        var main = document.getElementById('spMain');
        main.className = 'sp-main' + (isNarrow ? ' sp-narrow' : ' sp-wide');
        if (isNarrow) {
            renderNarrowLayout();
        } else {
            renderWideLayout();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
