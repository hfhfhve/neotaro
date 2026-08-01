/* ============================================================
   NEOTARO — service worker.
   Главная задача: принимать веб-пуши. Кэш здесь минимальный и
   намеренно осторожный: приложение живое, кэшировать его целиком
   опасно — люди застрянут на старой версии.
   ============================================================ */

const SW_VERSION = 'neotaro-v1';
const SHELL_CACHE = 'neotaro-shell-v1';

/* Что держим на случай обрыва связи. Только оболочка и иконки,
   никаких данных пользователя. */
const SHELL = [
  '/app/',
  '/site.webmanifest',
  '/android-chrome-192x192.png',
  '/android-chrome-512x512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(cache => cache.addAll(SHELL).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL_CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

/* Страница просит уступить место новой версии */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

/* ---------- сеть ----------
   Только переходы по страницам, и только сначала сеть.
   API живёт на другом домене (api.neotaro.ru) и сюда не попадает —
   ответы с раскладами и профилем кэшировать нельзя. */
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  if (req.mode !== 'navigate') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(req)
      .then(res => {
        const copy = res.clone();
        caches.open(SHELL_CACHE).then(c => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() =>
        caches.match(req).then(hit => hit || caches.match('/app/'))
      )
  );
});

/* ---------- пуши ----------
   Сервер шлёт JSON вида:
   { title, body, url, tag, icon }
   Если пришёл мусор или пустое тело — показываем нейтральный текст,
   молча ронять уведомление нельзя: браузер накажет за это подписку. */
self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    try { data = { body: event.data.text() }; } catch (e2) { data = {}; }
  }

  const title = data.title || 'NEOTARO';
  const options = {
    body: data.body || 'Карта дня ждёт вас',
    icon: data.icon || '/android-chrome-192x192.png',
    badge: '/android-chrome-192x192.png',
    tag: data.tag || 'neotaro-daily',
    renotify: true,
    requireInteraction: false,
    data: { url: data.url || '/app/?src=push' }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

/* Нажатие на уведомление: если вкладка уже открыта — поднимаем её,
   а не плодим новые окна. */
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/app/?src=push';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if (client.url.indexOf('/app/') !== -1 && 'focus' in client) {
          client.navigate(target).catch(() => {});
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});

/* Браузер иногда сам меняет подписку. Без этого обработчика человек
   тихо перестанет получать уведомления, и никто не заметит. */
self.addEventListener('pushsubscriptionchange', event => {
  const oldEndpoint = (event.oldSubscription && event.oldSubscription.endpoint) || '';

  event.waitUntil(
    self.registration.pushManager.getSubscription()
      .then(sub => {
        if (sub) return sub;
        // браузер мог отозвать подписку совсем — пробуем оформить заново
        const key = event.newSubscription ? null : (event.oldSubscription && event.oldSubscription.options && event.oldSubscription.options.applicationServerKey);
        if (!key) return null;
        return self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: key
        }).catch(() => null);
      })
      .then(sub => {
        if (!sub || !oldEndpoint) return null;
        return fetch('https://api.neotaro.ru/api/push/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ old_endpoint: oldEndpoint, subscription: sub.toJSON() })
        }).catch(() => null);
      })
  );
});
