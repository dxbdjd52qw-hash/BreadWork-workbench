/* 麺包的工作台 · Service Worker（保守策略，保证应用可安装 + 弱网兜底，绝不缓存 API 数据） */
const CACHE = 'ytwb-v2';
const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-180.png'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // 只处理 GET，且绝不拦截后端 API（/api/*），保证同步与 AI 永远走网络
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        // 仅缓存同源的页面导航与静态资源
        if (url.origin === location.origin &&
            (e.request.mode === 'navigate' || /\.(png|webmanifest|ico)$/.test(url.pathname))) {
          const cp = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, cp));
        }
        return res;
      })
      .catch(() => caches.match(e.request).then(m => m || caches.match('./index.html')))
  );
});
