// Load translations from JSON file, then translate the page.
let KIOSK_TRANSLATIONS = null;

function translatePage(lang) {
    const strings = (KIOSK_TRANSLATIONS && KIOSK_TRANSLATIONS[lang]) ? KIOSK_TRANSLATIONS[lang] : (KIOSK_TRANSLATIONS && KIOSK_TRANSLATIONS['en']) ? KIOSK_TRANSLATIONS['en'] : {};
    const nodes = Array.from(document.querySelectorAll('[data-i18n]'));
    const summary = {total: nodes.length, applied: 0, missing: []};
    nodes.forEach(el => {
        const key = el.getAttribute('data-i18n');
        let txt = strings[key];
        if (typeof txt === 'undefined') {
            summary.missing.push(key);
            txt = '';
        } else {
            summary.applied += 1;
        }
        // simple interpolation for {n}, {res} and {name}
        if (el.dataset.i18nCount) {
            txt = txt.replace('{n}', el.dataset.i18nCount);
        }
        if (el.dataset.i18nRes) {
            txt = txt.replace('{res}', el.dataset.i18nRes);
        }
        if (el.dataset.i18nName) {
            txt = txt.replace('{name}', el.dataset.i18nName);
        }
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
            el.value = txt;
        } else {
            el.textContent = txt;
        }
    });
}

function getCookie(name) {
    const v = `; ${document.cookie}`;
    const parts = v.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

async function loadTranslationsAndInit() {
    // Determine language first (server-provided or cookie)
    let lang = (typeof KIOSK_LANGUAGE !== 'undefined') ? KIOSK_LANGUAGE : 'en';
    const cookieLang = getCookie('kiosk_language');
    if (cookieLang) lang = cookieLang;

    // try fetch the language file, fall back to English file
    try {
        let resp = await fetch(`/static/i18n/${lang}.json`, {cache: 'no-store'});
        if (!resp.ok) throw new Error('not found');
        const data = await resp.json();
        KIOSK_TRANSLATIONS = {};
        KIOSK_TRANSLATIONS[lang] = data;
    } catch (e) {
        try {
            const resp2 = await fetch('/static/i18n/en.json', {cache: 'no-store'});
            const data2 = await resp2.json();
            KIOSK_TRANSLATIONS = {en: data2};
            lang = 'en';
        } catch (e2) {
            KIOSK_TRANSLATIONS = {en: {}};
            lang = 'en';
        }
    }

    try {
        translatePage(lang);
    } catch (e) {
        // Silent fail for production
    }
}

// ensure translation runs after DOM ready and after translations are loaded
if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', loadTranslationsAndInit);
} else {
    loadTranslationsAndInit();
}
