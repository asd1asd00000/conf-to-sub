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
    const panel = btn.parentElement.querySelector('.menu-panel');
    const wasHidden = panel.classList.contains('hidden');
    closeAllMenus();
    if (wasHidden) panel.classList.remove('hidden');
}
function closeAllMenus(){
    document.querySelectorAll('.menu-panel').forEach(p => p.classList.add('hidden'));
}
document.addEventListener('click', function(e){
    if (!e.target.closest('.menu')) closeAllMenus();
});
