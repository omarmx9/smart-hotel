// Load translations from JSON file, then translate the page.
// Compatible with Cloudflare Rocket Loader (uses data-cfasync="false")
(function () {
    'use strict';

    let KIOSK_TRANSLATIONS = null;

    function translatePage(lang) {
        const strings = (KIOSK_TRANSLATIONS && KIOSK_TRANSLATIONS[lang])
            ? KIOSK_TRANSLATIONS[lang]
            : (KIOSK_TRANSLATIONS && KIOSK_TRANSLATIONS['en'])
                ? KIOSK_TRANSLATIONS['en']
                : {};

        const nodes = document.querySelectorAll('[data-i18n]');
        nodes.forEach(function (el) {
            const key = el.getAttribute('data-i18n');
            let txt = strings[key];
            if (typeof txt === 'undefined' || txt === '') {
                return; // Keep original text if no translation
            }
            // Simple interpolation for {n}, {res}, {name}, {cap}, {rem}
            if (el.dataset.i18nCount) txt = txt.replace('{n}', el.dataset.i18nCount);
            if (el.dataset.i18nRes) txt = txt.replace('{res}', el.dataset.i18nRes);
            if (el.dataset.i18nName) txt = txt.replace('{name}', el.dataset.i18nName);
            if (el.dataset.i18nCap) txt = txt.replace('{cap}', el.dataset.i18nCap);
            if (el.dataset.i18nRem) txt = txt.replace('{rem}', el.dataset.i18nRem);

            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                if (el.type === 'submit' || el.type === 'button') {
                    el.value = txt;
                } else if (el.placeholder !== undefined) {
                    el.placeholder = txt;
                }
            } else {
                el.textContent = txt;
            }
        });
        console.log('[i18n] Translated', nodes.length, 'elements to', lang);
    }

    function getCookie(name) {
        const v = '; ' + document.cookie;
        const parts = v.split('; ' + name + '=');
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    async function loadTranslationsAndInit() {
        // Determine language: cookie takes priority over server-provided value
        let lang = (typeof KIOSK_LANGUAGE !== 'undefined') ? KIOSK_LANGUAGE : 'en';
        const cookieLang = getCookie('kiosk_language');
        if (cookieLang) lang = cookieLang;

        // Fetch translation file with cache-busting for Cloudflare
        const ts = Date.now();
        try {
            const resp = await fetch('/static/i18n/' + lang + '.json?_=' + ts, {
                cache: 'no-store',
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            KIOSK_TRANSLATIONS = {};
            KIOSK_TRANSLATIONS[lang] = data;
        } catch (e) {
            console.warn('[i18n] Failed to load', lang + '.json:', e.message);
            // Fallback to English
            try {
                const resp2 = await fetch('/static/i18n/en.json?_=' + ts, {
                    cache: 'no-store',
                    headers: { 'Accept': 'application/json' }
                });
                if (resp2.ok) {
                    KIOSK_TRANSLATIONS = { en: await resp2.json() };
                    lang = 'en';
                }
            } catch (e2) {
                console.error('[i18n] Failed to load fallback en.json:', e2.message);
                return;
            }
        }

        translatePage(lang);
    }

    // Check if we should skip translation
    if (typeof NO_TRANSLATE !== 'undefined' && NO_TRANSLATE) {
        console.log('[i18n] Translation disabled for this page');
        return;
    }

    // Run translation when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadTranslationsAndInit);
    } else {
        // DOM already loaded, run immediately
        loadTranslationsAndInit();
    }
})();
