/*
 * 城池战争 Service Worker
 * 仅用于 PWA 可安装性（添加到主屏幕），不缓存任何内容：
 * 游戏是实时联机状态，缓存旧页面/接口会导致数据错乱，因此全部请求直接放行网络
 */
const CACHE_NAME = 'citywar-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(keys.map((k) => caches.delete(k)));
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    // 全部放行网络，不做缓存
    event.respondWith(fetch(event.request));
});
