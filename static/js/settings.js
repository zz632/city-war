/* UI 设置 */
(function() {
    var STORAGE_KEY = 'citywar_ui_settings';
    var DEFAULTS = {
        bgColor: '#F5F5F7',
        bgImage: ''
    };

    var PRESETS = [
        { name: '白', color: '#FFFFFF' },
        { name: '浅灰', color: '#E8E8ED' },
        { name: '黑', color: '#000000' },
        { name: '天蓝', color: '#32ADE6' },
        { name: '靛蓝', color: '#5856D6' },
        { name: '薄荷', color: '#00C7BE' },
        { name: '珊瑚', color: '#FF6482' },
        { name: '琥珀', color: '#FF9F0A' },
    ];

    function load() {
        try {
            var s = localStorage.getItem(STORAGE_KEY);
            if (s) return JSON.parse(s);
        } catch(e) {}
        return Object.assign({}, DEFAULTS);
    }

    function save(settings) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(settings)); } catch(e) {}
    }

    function hexToRgb(hex) {
        if (!hex || hex.length < 7) return { r: 0, g: 0, b: 0 };
        return {
            r: parseInt(hex.slice(1, 3), 16),
            g: parseInt(hex.slice(3, 5), 16),
            b: parseInt(hex.slice(5, 7), 16)
        };
    }

    function rgbToHsl(r, g, b) {
        r /= 255; g /= 255; b /= 255;
        var max = Math.max(r, g, b), min = Math.min(r, g, b);
        var h, s, l = (max + min) / 2;
        if (max === min) {
            h = s = 0;
        } else {
            var d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
            else if (max === g) h = ((b - r) / d + 2) / 6;
            else h = ((r - g) / d + 4) / 6;
        }
        return { h: h, s: s, l: l };
    }

    function hslToRgb(h, s, l) {
        if (s === 0) { var v = Math.round(l * 255); return { r: v, g: v, b: v }; }
        function hue2rgb(p, q, t) {
            if (t < 0) t += 1; if (t > 1) t -= 1;
            if (t < 1/6) return p + (q - p) * 6 * t;
            if (t < 1/2) return q;
            if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
            return p;
        }
        var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        var p = 2 * l - q;
        return {
            r: Math.round(hue2rgb(p, q, h + 1/3) * 255),
            g: Math.round(hue2rgb(p, q, h) * 255),
            b: Math.round(hue2rgb(p, q, h - 1/3) * 255)
        };
    }

    // 色相距离（0~0.5）
    function hueDist(h1, h2) {
        var d = Math.abs(h1 - h2);
        return Math.min(d, 1 - d);
    }

    function hslHex(h, s, l) {
        var rgb = hslToRgb(((h % 1) + 1) % 1, Math.max(0, Math.min(1, s)), Math.max(0, Math.min(1, l)));
        return '#' + [rgb.r, rgb.g, rgb.b].map(function(v) {
            return Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0');
        }).join('');
    }

    // Material Design 3 动态配色
    // 核心原则：
    // 1. 彩色背景(高饱和度) → 始终用浅色方案(白卡片+深文字)，背景作为hero色
    // 2. 中性背景(低饱和度灰/白/黑) → 按亮度决定light/dark
    // 3. surface/border/text 是近中性色(极低饱和度)，accent才高饱和
    function applyTheme(bgHex) {
        var rgb = hexToRgb(bgHex);
        var hsl = rgbToHsl(rgb.r, rgb.g, rgb.b);
        var h = hsl.h; // 种子色相
        var s = hsl.s;
        var l = hsl.l;
        var root = document.documentElement;

        // 彩色且浅色(s>0.25 且 l>0.30) → light scheme（大部分彩色背景都用浅色方案）
        // 深色彩色(s>0.25 且 l<=0.30) → dark scheme（只有很深的彩色才用深色方案）
        // 中性灰(s<=0.25) → 按亮度
        var isLight = (s > 0.25 && l > 0.30) || (s <= 0.25 && l > 0.55);

        // ---- 中性色色阶 (Neutral Tonal Palette) ----
        var nS = 0.03; // 极低饱和度

        if (isLight) {
            root.style.setProperty('--surface',      hslHex(h, nS, 0.985));
            root.style.setProperty('--surface-hover', hslHex(h, nS, 0.955));
            root.style.setProperty('--surface-active',hslHex(h, nS, 0.92));
            root.style.setProperty('--border',        hslHex(h, nS, 0.87));
            root.style.setProperty('--border-strong', hslHex(h, nS, 0.76));
            // --text: 对比白色卡片（卡片内文字）
            root.style.setProperty('--text',          hslHex(h, nS, 0.10));
            root.style.setProperty('--text-secondary',hslHex(h, nS, 0.32));
            root.style.setProperty('--text-tertiary', hslHex(h, nS, 0.54));
            // --text-on-bg: 对比背景色（直接在背景上的文字如房间号、标题）
            // 彩色背景(s>0.25)用白色，灰色背景用深色
            if (s > 0.25) {
                root.style.setProperty('--text-on-bg',          hslHex(h, 0.08, 0.97));
                root.style.setProperty('--text-on-bg-secondary',hslHex(h, 0.06, 0.78));
                root.style.setProperty('--text-on-bg-tertiary', hslHex(h, 0.04, 0.60));
            } else {
                root.style.setProperty('--text-on-bg',          hslHex(h, nS, 0.10));
                root.style.setProperty('--text-on-bg-secondary',hslHex(h, nS, 0.32));
                root.style.setProperty('--text-on-bg-tertiary', hslHex(h, nS, 0.54));
            }
        } else {
            var sT = Math.max(0.12, Math.min(0.22, l + 0.06));
            root.style.setProperty('--surface',      hslHex(h, nS, sT));
            root.style.setProperty('--surface-hover', hslHex(h, nS, Math.min(0.30, sT + 0.03)));
            root.style.setProperty('--surface-active',hslHex(h, nS, Math.min(0.35, sT + 0.06)));
            root.style.setProperty('--border',        hslHex(h, nS, Math.min(0.40, sT + 0.12)));
            root.style.setProperty('--border-strong', hslHex(h, nS, Math.min(0.50, sT + 0.22)));
            root.style.setProperty('--text',          hslHex(h, nS, 0.92));
            root.style.setProperty('--text-secondary',hslHex(h, nS, 0.70));
            root.style.setProperty('--text-tertiary', hslHex(h, nS, 0.50));
            // 深色背景：背景上也是浅色文字
            root.style.setProperty('--text-on-bg',          hslHex(h, nS, 0.92));
            root.style.setProperty('--text-on-bg-secondary',hslHex(h, nS, 0.70));
            root.style.setProperty('--text-on-bg-tertiary', hslHex(h, nS, 0.50));
        }

        // ---- Accent色：高饱和度 + 色相避让 ----
        function adaptHue(accentH) {
            if (hueDist(h, accentH) < 0.10) {
                var diff = accentH - h;
                if (diff >= 0 && diff <= 0.5) return (accentH + 0.15) % 1;
                return ((accentH - 0.15) % 1 + 1) % 1;
            }
            return accentH;
        }

        var pH  = adaptHue(0.58);
        var gH  = adaptHue(0.37);
        var rH  = adaptHue(0.01);
        var oH  = adaptHue(0.08);
        var pUH = adaptHue(0.77);

        var aS = 0.78;
        if (isLight) {
            root.style.setProperty('--primary',       hslHex(pH,  aS, 0.46));
            root.style.setProperty('--primary-hover',  hslHex(pH,  aS, 0.38));
            root.style.setProperty('--green',          hslHex(gH,  aS, 0.40));
            root.style.setProperty('--red',            hslHex(rH,  aS, 0.46));
            root.style.setProperty('--orange',         hslHex(oH,  aS, 0.48));
            root.style.setProperty('--purple',         hslHex(pUH, aS, 0.46));
            root.style.setProperty('--primary-bg', hslHex(pH,  0.30, 0.93));
            root.style.setProperty('--green-bg',   hslHex(gH,  0.30, 0.93));
            root.style.setProperty('--red-bg',     hslHex(rH,  0.30, 0.93));
            root.style.setProperty('--orange-bg',  hslHex(oH,  0.30, 0.93));
            root.style.setProperty('--purple-bg',  hslHex(pUH, 0.30, 0.93));
        } else {
            root.style.setProperty('--primary',       hslHex(pH,  aS, 0.68));
            root.style.setProperty('--primary-hover',  hslHex(pH,  aS, 0.74));
            root.style.setProperty('--green',          hslHex(gH,  aS, 0.64));
            root.style.setProperty('--red',            hslHex(rH,  aS, 0.66));
            root.style.setProperty('--orange',         hslHex(oH,  aS, 0.68));
            root.style.setProperty('--purple',         hslHex(pUH, aS, 0.68));
            root.style.setProperty('--primary-bg', hslHex(pH,  0.30, Math.max(0.18, l + 0.04)));
            root.style.setProperty('--green-bg',   hslHex(gH,  0.30, Math.max(0.18, l + 0.04)));
            root.style.setProperty('--red-bg',     hslHex(rH,  0.30, Math.max(0.18, l + 0.04)));
            root.style.setProperty('--orange-bg',  hslHex(oH,  0.30, Math.max(0.18, l + 0.04)));
            root.style.setProperty('--purple-bg',  hslHex(pUH, 0.30, Math.max(0.18, l + 0.04)));
        }
    }

    function rgbToHex(r, g, b) {
        return '#' + [r, g, b].map(function(v) {
            return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
        }).join('');
    }

    // 从图片dataURL提取主色（简化量化：采样+聚类）
    function extractDominantColor(dataUrl, callback) {
        var img = new Image();
        img.onload = function() {
            var canvas = document.createElement('canvas');
            var size = 64; // 缩小采样
            canvas.width = size; canvas.height = size;
            var ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, size, size);
            var data = ctx.getImageData(0, 0, size, size).data;
            // 简单聚类：按H分组取平均
            var buckets = {};
            for (var i = 0; i < data.length; i += 4) {
                var r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
                if (a < 128) continue;
                var hsl = rgbToHsl(r, g, b);
                // 跳过太暗/太亮的像素
                if (hsl.l < 0.08 || hsl.l > 0.95) continue;
                var key = Math.round(hsl.h * 12); // 12个色相桶
                if (!buckets[key]) buckets[key] = { h: 0, s: 0, l: 0, count: 0 };
                var bk = buckets[key];
                bk.h += hsl.h; bk.s += hsl.s; bk.l += hsl.l; bk.count++;
            }
            // 找最大桶
            var maxKey = null, maxCount = 0;
            for (var k in buckets) {
                if (buckets[k].count > maxCount) { maxCount = buckets[k].count; maxKey = k; }
            }
            if (!maxKey) { callback('#808080'); return; }
            var dominant = buckets[maxKey];
            var h = dominant.h / dominant.count;
            var s = dominant.s / dominant.count;
            var l = dominant.l / dominant.count;
            // 用中等明度和饱和度，作为主题种子色
            callback(hslHex(h, Math.max(0.3, s), Math.max(0.3, Math.min(0.65, l))));
        };
        img.onerror = function() { callback('#808080'); };
        img.src = dataUrl;
    }

    function applySettings(settings) {
        if (settings.bgImage) {
            document.body.style.backgroundImage = 'url(' + settings.bgImage + ')';
            document.body.style.backgroundColor = settings.bgColor;
            // 从图片提取主色来派生主题
            extractDominantColor(settings.bgImage, function(dominantHex) {
                applyTheme(dominantHex);
            });
        } else {
            document.body.style.backgroundImage = 'none';
            document.body.style.backgroundColor = settings.bgColor;
            applyTheme(settings.bgColor || '#F5F5F7');
        }
    }

    function renderSettingsPanel() {
        var settings = load();
        var rgb = hexToRgb(settings.bgColor);

        var overlay = document.createElement('div');
        overlay.className = 'settings-overlay';
        overlay.id = 'settingsOverlay';
        overlay.onclick = closeSettings;

        var sheet = document.createElement('div');
        sheet.className = 'settings-sheet';
        sheet.onclick = function(e) { e.stopPropagation(); };

        var html =
            '<div class="settings-handle"></div>' +
            '<div class="settings-title">外观设置</div>' +

            '<div class="settings-group">' +
                '<div class="settings-group-label">预设颜色</div>' +
                '<div class="settings-group-row" style="justify-content:center;gap:8px;flex-wrap:wrap;padding:12px 14px">' +
                    PRESETS.map(function(p) {
                        var active = settings.bgColor.toUpperCase() === p.color.toUpperCase() && !settings.bgImage ? ' active' : '';
                        return '<div class="color-dot' + active + '" data-color="' + p.color + '" title="' + p.name + '" style="background:' + p.color + '"></div>';
                    }).join('') +
                '</div>' +
            '</div>' +

            '<div class="settings-group">' +
                '<div class="settings-group-label">自定义颜色</div>' +
                '<div class="settings-group-row" style="flex-direction:column;align-items:stretch;gap:10px;padding:14px">' +
                    '<div style="display:flex;align-items:center;gap:10px">' +
                        '<div id="customColorPreview" style="width:36px;height:36px;border-radius:10px;background:' + settings.bgColor + ';border:1px solid var(--border-strong);flex-shrink:0"></div>' +
                        '<span id="customColorHex" style="font-size:14px;font-weight:600;color:var(--text);font-variant-numeric:tabular-nums">' + settings.bgColor.toUpperCase() + '</span>' +
                    '</div>' +
                    '<div style="display:flex;align-items:center;gap:8px">' +
                        '<span style="font-size:12px;font-weight:700;color:#FF3B30;width:14px;text-align:center">R</span>' +
                        '<input type="range" class="ui-slider rgb-slider" id="rgbR" min="0" max="255" value="' + rgb.r + '" style="flex:1">' +
                        '<span id="rgbRVal" style="font-size:12px;color:var(--text-secondary);min-width:28px;text-align:right">' + rgb.r + '</span>' +
                    '</div>' +
                    '<div style="display:flex;align-items:center;gap:8px">' +
                        '<span style="font-size:12px;font-weight:700;color:#34C759;width:14px;text-align:center">G</span>' +
                        '<input type="range" class="ui-slider rgb-slider" id="rgbG" min="0" max="255" value="' + rgb.g + '" style="flex:1">' +
                        '<span id="rgbGVal" style="font-size:12px;color:var(--text-secondary);min-width:28px;text-align:right">' + rgb.g + '</span>' +
                    '</div>' +
                    '<div style="display:flex;align-items:center;gap:8px">' +
                        '<span style="font-size:12px;font-weight:700;color:#007AFF;width:14px;text-align:center">B</span>' +
                        '<input type="range" class="ui-slider rgb-slider" id="rgbB" min="0" max="255" value="' + rgb.b + '" style="flex:1">' +
                        '<span id="rgbBVal" style="font-size:12px;color:var(--text-secondary);min-width:28px;text-align:right">' + rgb.b + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +

            '<div class="settings-group">' +
                '<div class="settings-group-label">背景图片</div>' +
                '<div class="settings-group-row">' +
                    '<span class="settings-row-label">自定义图片</span>' +
                    '<span class="settings-row-value">' +
                        (settings.bgImage ? '<button class="upload-btn" id="clearBgImg">清除</button> ' : '') +
                        '<button class="upload-btn" id="uploadBgImg">选择图片</button>' +
                        '<input type="file" id="bgImgInput" accept="image/*" style="display:none">' +
                    '</span>' +
                '</div>' +
            '</div>';

        sheet.innerHTML = html;
        document.body.appendChild(overlay);
        document.body.appendChild(sheet);

        sheet.querySelectorAll('.color-dot').forEach(function(dot) {
            dot.onclick = function() {
                settings.bgColor = this.dataset.color;
                settings.bgImage = '';
                save(settings);
                applySettings(settings);
                sheet.querySelectorAll('.color-dot').forEach(function(d) { d.classList.remove('active'); });
                this.classList.add('active');
                var c = hexToRgb(settings.bgColor);
                sheet.querySelector('#rgbR').value = c.r;
                sheet.querySelector('#rgbG').value = c.g;
                sheet.querySelector('#rgbB').value = c.b;
                sheet.querySelector('#rgbRVal').textContent = c.r;
                sheet.querySelector('#rgbGVal').textContent = c.g;
                sheet.querySelector('#rgbBVal').textContent = c.b;
                sheet.querySelector('#customColorPreview').style.background = settings.bgColor;
                sheet.querySelector('#customColorHex').textContent = settings.bgColor.toUpperCase();
            };
        });

        function updateRgb() {
            var r = parseInt(sheet.querySelector('#rgbR').value);
            var g = parseInt(sheet.querySelector('#rgbG').value);
            var b = parseInt(sheet.querySelector('#rgbB').value);
            sheet.querySelector('#rgbRVal').textContent = r;
            sheet.querySelector('#rgbGVal').textContent = g;
            sheet.querySelector('#rgbBVal').textContent = b;
            var hex = rgbToHex(r, g, b);
            sheet.querySelector('#customColorPreview').style.background = hex;
            sheet.querySelector('#customColorHex').textContent = hex.toUpperCase();
            settings.bgColor = hex;
            settings.bgImage = '';
            save(settings);
            applySettings(settings);
            sheet.querySelectorAll('.color-dot').forEach(function(d) { d.classList.remove('active'); });
            PRESETS.forEach(function(p, i) {
                if (p.color.toUpperCase() === hex.toUpperCase()) {
                    sheet.querySelectorAll('.color-dot')[i].classList.add('active');
                }
            });
        }
        sheet.querySelector('#rgbR').oninput = updateRgb;
        sheet.querySelector('#rgbG').oninput = updateRgb;
        sheet.querySelector('#rgbB').oninput = updateRgb;

        var fileInput = sheet.querySelector('#bgImgInput');
        sheet.querySelector('#uploadBgImg').onclick = function() { fileInput.click(); };
        fileInput.onchange = function() {
            var file = this.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function(e) {
                var img = new Image();
                img.onload = function() {
                    var canvas = document.createElement('canvas');
                    var maxW = 1200;
                    var scale = Math.min(1, maxW / img.width);
                    canvas.width = img.width * scale;
                    canvas.height = img.height * scale;
                    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                    var dataUrl = canvas.toDataURL('image/jpeg', 0.7);
                    settings.bgImage = dataUrl;
                    save(settings);
                    applySettings(settings);
                    closeSettings();
                    setTimeout(function() { openSettings(); }, 100);
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        };

        var clearBtn = sheet.querySelector('#clearBgImg');
        if (clearBtn) {
            clearBtn.onclick = function() {
                settings.bgImage = '';
                save(settings);
                applySettings(settings);
                closeSettings();
                setTimeout(function() { openSettings(); }, 100);
            };
        }
    }

    function openSettings() {
        closeSettings();
        renderSettingsPanel();
    }

    function closeSettings() {
        var overlay = document.getElementById('settingsOverlay');
        var sheet = document.querySelector('.settings-sheet');
        if (overlay) overlay.remove();
        if (sheet) sheet.remove();
    }

    window.openSettings = openSettings;
    window.closeSettings = closeSettings;

    function addSettingsButton() {
        if (document.getElementById('settingsBtn')) return;
        var btn = document.createElement('button');
        btn.id = 'settingsBtn';
        btn.className = 'settings-btn';
        btn.title = '外观设置';
        btn.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
        btn.onclick = openSettings;
        document.body.appendChild(btn);
    }

    function init() {
        var settings = load();
        applySettings(settings);
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', addSettingsButton);
        } else {
            addSettingsButton();
        }
    }

    init();
})();
