// ابزارهای سراسری پنل

async function pasteConfig() {
    const ta = document.getElementById('raw_text') || document.querySelector('textarea[name="raw_text"]');
    if (!ta) { jsToast('❌ فیلد متن پیدا نشد'); return; }
    try {
        const text = await navigator.clipboard.readText();
        if (!text) { jsToast('⚠️ کلیپ‌بورد خالی است'); return; }
        ta.value = text;
        ta.focus();
        const lines = text.split('\n').filter(l => l.trim()).length;
        jsToast('📋 جاگذاری شد (' + lines + ' خط)');
    } catch (err) {
        jsToast('❌ مرورگر اجازه کلیپ‌بورد نداد — Ctrl+V بزنید');
    }
}

// ===== منوی سفارشی (جایگزین select بومی) =====
function toggleMenu(btn){
    const menu = btn.closest('.menu');
    const panel = menu.querySelector('.menu-panel');
    const wasHidden = panel.classList.contains('hidden');
    closeAllMenus();
    if (wasHidden) {
        panel.classList.remove('hidden');
        menu.classList.add('menu-open');
    }
}
function closeAllMenus(){
    document.querySelectorAll('.menu').forEach(m => m.classList.remove('menu-open'));
    document.querySelectorAll('.menu-panel').forEach(p => p.classList.add('hidden'));
}
document.addEventListener('click', function(e){
    if (!e.target.closest('.menu')) closeAllMenus();
});

// ===== آکاردئون موبایل (کارت کاربران) =====
function toggleAcc(header){
    const body = header.parentElement.querySelector('.acc-body');
    const arrow = header.querySelector('.acc-arrow');
    const opening = body.classList.contains('hidden');
    body.classList.toggle('hidden');
    if (arrow) arrow.style.transform = opening ? 'rotate(180deg)' : 'rotate(0deg)';
}

// ===== جستجوی زنده (موبایل) =====
let _liveTimer = null;
function _goSearch(val, focusAfter){
    const form = document.getElementById('liveSearchForm');
    if (!form) return;
    if (focusAfter) sessionStorage.setItem('liveFocus', '1');
    const params = new URLSearchParams(new FormData(form));
    params.set('q', val);
    window.location.href = '/admin/users?' + params.toString();
}
function liveSearch(val){
    clearTimeout(_liveTimer);
    _liveTimer = setTimeout(function(){ _goSearch(val, true); }, 450);
}
function clearSearch(){
    clearTimeout(_liveTimer);
    _goSearch('', true);
}
document.addEventListener('DOMContentLoaded', function(){
    if (sessionStorage.getItem('liveFocus') === '1') {
        sessionStorage.removeItem('liveFocus');
        const input = document.querySelector('#liveSearchForm input[name="q"]');
        if (input) {
            input.focus();
            const len = input.value.length;
            input.setSelectionRange(len, len);
        }
    }
});
