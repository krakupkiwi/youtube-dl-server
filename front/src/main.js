import { createApp } from 'vue';
import App from './App.vue';
import VueCookies from 'vue-cookies';
import { createRouter, createWebHashHistory } from 'vue-router';

import 'bootstrap/dist/css/bootstrap.css';

import './assets/style.css';
import Logs from './components/Logs.vue';
import Home from './components/Home.vue';
import Finished from './components/Finished.vue';
import { saveConfig, getApiKey } from './utils';

// Optional API-key protection (see ydl_server.middleware.APIKeyMiddleware):
// pick up ?api_key=... from the URL once, persist it, and strip it from the
// visible address bar. Every same-origin fetch() then carries it as a header.
const urlParams = new URLSearchParams(window.location.search);
const apiKeyParam = urlParams.get('api_key');
if (apiKeyParam) {
	saveConfig('apiKey', apiKeyParam);
	urlParams.delete('api_key');
	const newSearch = urlParams.toString();
	const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : '') + window.location.hash;
	window.history.replaceState({}, '', newUrl);
}

const originalFetch = window.fetch.bind(window);
window.fetch = (input, init) => {
	const apiKey = getApiKey();
	if (!apiKey) return originalFetch(input, init);
	const headers = new Headers((init && init.headers) || (input instanceof Request ? input.headers : undefined));
	headers.set('X-API-Key', apiKey);
	return originalFetch(input, { ...init, headers });
};

const routes = [
	{ path: '/', component: Home },
	{ path: '/home', component: Home },
	{ path: '/logs', component: Logs },
	{ path: '/finished', component: Finished },
];

const router = createRouter({
	history: createWebHashHistory(),
	routes,
});
const app = createApp(App);
app.use(router);
app.use(VueCookies);

app.mount('#app');
