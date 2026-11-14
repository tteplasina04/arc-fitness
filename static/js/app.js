(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const page = document.body.dataset.page || 'home';
  const daysRu = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
  const escapeHtml = (value = '') => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
    let payload = {};
    try { payload = await response.json(); } catch { /* 204 or non-JSON response */ }
    if (!response.ok) {
      const error = new Error(payload.detail || payload.message || `Ошибка запроса (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function setStatus(element, message, kind = '') {
    if (!element) return;
    element.textContent = message || '';
    element.classList.remove('success', 'error');
    if (kind) element.classList.add(kind);
  }

  function formDataObject(form) {
    return Object.fromEntries(new FormData(form).entries());
  }

  function renderShell() {
    const header = $('#site-header');
    if (header) {
      const navItems = [
        ['/about', 'О клубе', 'about'], ['/trainers', 'Тренеры', 'trainers'],
        ['/schedule', 'Расписание', 'schedule'], ['/memberships', 'Абонементы', 'memberships'],
        ['/promotions', 'Акции', 'promotions'], ['/news', 'Новости', 'news']
      ];
      const links = navItems.map(([href, label, key]) => `<a href="${href}"${page === key ? ' class="active" aria-current="page"' : ''}>${label}</a>`).join('');
      header.innerHTML = `
        <header class="site-header"><div class="container header-inner">
          <a class="brand" href="/" aria-label="ARC.FITNESS — главная"><span class="brand-symbol"><span>A</span></span><span class="brand-name">ARC<span>.</span>FITNESS</span></a>
          <nav class="site-nav" aria-label="Основная навигация">${links}</nav>
          <div class="header-actions"><button class="theme-toggle" type="button" data-theme-toggle aria-label="Переключить тему">◐</button><a href="/account" class="header-cta">Кабинет ↗</a><button class="menu-toggle" type="button" data-menu-toggle aria-label="Открыть меню" aria-expanded="false">☰</button></div>
        </div></header>`;
    }
    const footer = $('#site-footer');
    if (footer) {
      footer.innerHTML = `
        <footer class="site-footer"><div class="container"><div class="footer-top">
          <div class="footer-brand"><a class="brand" href="/"><span class="brand-symbol"><span>A</span></span><span class="brand-name">ARC<span>.</span>FITNESS</span></a><p>Пространство для движения, силы и последовательного прогресса.</p></div>
          <div class="footer-col"><h3>Навигация</h3><a href="/about">О клубе</a><a href="/trainers">Тренеры</a><a href="/schedule">Расписание</a><a href="/memberships">Абонементы</a></div>
          <div class="footer-col"><h3>Обновления</h3><a href="/promotions">Акции</a><a href="/news">Новости</a><a href="/#callback-form">Обратный звонок</a><a href="/account">Личный кабинет</a><a href="/privacy">Обработка данных</a></div>
          <div class="footer-col"><h3>Контакты</h3><p>Воронеж, Ленинский проспект, 172Д</p><p>Оставьте заявку, и мы свяжемся с вами</p></div>
        </div><div class="footer-bottom"><span>© <span data-current-year></span> ARC.FITNESS. </span><span>Движение начинается с первого шага</span></div></div></footer>`;
    }
    $$('[data-current-year]').forEach(node => node.textContent = new Date().getFullYear());
    const accountLink = $('.header-cta');
    if (accountLink) {
      api('/api/auth/me').then(({ user }) => {
        accountLink.href = user.role === 'admin' ? '/admin' : '/account';
        accountLink.textContent = user.role === 'admin' ? 'Администратор ↗' : 'Кабинет ↗';
      }).catch(() => {
        accountLink.href = '/login';
        accountLink.textContent = 'Войти ↗';
      });
    }
    ensureNewsModal();
  }

  function ensureNewsModal() {
    if (!$('[data-news-modal]')) {
      document.body.insertAdjacentHTML('beforeend', '<dialog class="news-modal" data-news-modal><button type="button" class="modal-close" data-modal-close aria-label="Закрыть">×</button><div class="modal-image image-slot"></div><div class="modal-body"><p class="eyebrow" data-modal-category></p><h2 data-modal-title></h2><p data-modal-body></p></div></dialog>');
    }
    const modal = $('[data-news-modal]');
    $('[data-modal-close]', modal)?.addEventListener('click', () => modal.close());
    modal?.addEventListener('click', event => { if (event.target === modal) modal.close(); });
  }

  function setupThemeAndMenu() {
    const savedTheme = localStorage.getItem('arc-theme');
    if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
    $('[data-theme-toggle]')?.addEventListener('click', () => {
      const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      if (nextTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      else delete document.documentElement.dataset.theme;
      localStorage.setItem('arc-theme', nextTheme);
    });
    const menuToggle = $('[data-menu-toggle]');
    const nav = $('.site-nav');
    menuToggle?.addEventListener('click', () => {
      const opened = nav?.classList.toggle('open') || false;
      menuToggle.setAttribute('aria-expanded', String(opened));
      menuToggle.textContent = opened ? '×' : '☰';
    });
    $$('.site-nav a').forEach(link => link.addEventListener('click', () => {
      nav?.classList.remove('open');
      menuToggle?.setAttribute('aria-expanded', 'false');
      if (menuToggle) menuToggle.textContent = '☰';
    }));
  }

  async function setupCallbackForm() {
    const form = $('#callback-form');
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const status = $('.form-status', form);
      const submit = $('button[type="submit"]', form);
      setStatus(status, 'Отправляем заявку…');
      if (submit) submit.disabled = true;
      try {
        const payload = await api('/api/callback', { method: 'POST', body: JSON.stringify(formDataObject(form)) });
        setStatus(status, payload.message || 'Заявка отправлена.', 'success');
        form.reset();
      } catch (error) {
        setStatus(status, 'Не удалось отправить заявку. Попробуйте ещё раз позднее.', 'error');
      } finally { if (submit) submit.disabled = false; }
    });
  }

  async function setupHome() {
    const scheduleContainer = $('[data-schedule-preview]');
    if (scheduleContainer) {
      try {
        const data = await api('/api/weekly-schedule');
        const today = (new Date().getDay() + 6) % 7;
        const items = (data.items || []).slice().sort((a, b) => ((a.day_of_week - today + 7) % 7) - ((b.day_of_week - today + 7) % 7) || a.starts_at.localeCompare(b.starts_at)).slice(0, 3);
        scheduleContainer.innerHTML = items.length ? items.map(item => `<a class="preview-slot" href="/schedule"><span class="preview-time">${escapeHtml(item.starts_at)}</span><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.day_label)} · ${escapeHtml(item.trainer_name)}</p></div><span class="mini-arrow">↗</span></a>`).join('') : '<div class="empty-state">На этой неделе занятий пока нет. Обратитесь к администратору клуба.</div>';
      } catch {
        scheduleContainer.innerHTML = '<div class="empty-state">Расписание временно недоступно. Попробуйте позже.</div>';
      }
    }
    const newsContainer = $('[data-news-preview]');
    if (newsContainer) {
      try {
        const data = await api('/api/news');
        newsContainer.innerHTML = (data.items || []).slice(0, 3).map((item, index) => `<article class="news-preview-card"><img src="${escapeHtml(item.image_path || '/static/images/news-placeholder.jpg')}" alt="${escapeHtml(item.title)}" class="news-card-image" loading="lazy"><div class="news-card-content"><p class="eyebrow">${escapeHtml(item.category)}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.excerpt)}</p><button type="button" data-open-news="${item.id}">Читать новость ↗</button></div></article>`).join('') || '<div class="empty-state">Пока нет опубликованных новостей.</div>';
        const lookup = new Map((data.items || []).map(item => [String(item.id), item]));
        $$('[data-open-news]').forEach(btn => btn.addEventListener('click', () => openNewsModal(lookup.get(btn.dataset.openNews))));
      } catch {
        newsContainer.innerHTML = '<div class="empty-state">Новости временно недоступны. Попробуйте позже.</div>';
      }
    }
    const track = $('[data-gallery-track]');
    $('[data-gallery-next]')?.addEventListener('click', () => track?.scrollBy({ left: 300, behavior: 'smooth' }));
    $('[data-gallery-prev]')?.addEventListener('click', () => track?.scrollBy({ left: -300, behavior: 'smooth' }));
  }

  let scheduleItems = [];
  let selectedDay = (new Date().getDay() + 6) % 7;
  let selectedCategory = 'Все';
  async function loadSchedule() {
    const container = $('[data-schedule-list]');
    if (!container) return;
    container.innerHTML = '<div class="empty-state">Загружаем расписание…</div>';
    try {
      const data = await api('/api/weekly-schedule');
      scheduleItems = data.items || [];
      renderSchedule();
    } catch (error) {
      container.innerHTML = '<div class="empty-state">Расписание временно недоступно. Попробуйте позже.</div>';
    }
  }
  function renderSchedule() {
    const container = $('[data-schedule-list]');
    if (!container) return;
    const filtered = scheduleItems.filter(item => item.day_of_week === selectedDay && (selectedCategory === 'Все' || item.category === selectedCategory));
    const dayBtns = $$('[data-schedule-days] [data-day]');
    dayBtns.forEach(btn => btn.classList.toggle('active', Number(btn.dataset.day) === selectedDay));
    $$('[data-category-filters] [data-category]').forEach(btn => btn.classList.toggle('active', btn.dataset.category === selectedCategory));
    if (!filtered.length) {
      container.innerHTML = `<div class="empty-state">На ${daysRu[selectedDay].toLowerCase()} нет занятий в выбранной категории.</div>`;
      return;
    }
    container.innerHTML = filtered.map(item => `<article class="schedule-item">
      <div class="schedule-time">${escapeHtml(item.starts_at)}</div>
      <div class="schedule-main"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.day_label)} · ${escapeHtml(item.duration_minutes)} минут</p></div>
      <div class="schedule-person"><p>${escapeHtml(item.trainer_name)}</p><p>${escapeHtml(item.room)}</p></div>
      <div class="schedule-tag"><span class="category-tag" data-category="${escapeHtml(item.category)}">${escapeHtml(item.category)}</span></div>
      <div><p class="schedule-capacity">Свободно: ${item.available} из ${item.capacity}</p>${item.is_group ? `<button type="button" class="button ${item.available ? 'button-lime' : 'button-outline'}" data-book-class="${item.id}" ${item.available <= 0 ? 'disabled' : ''}>${item.available > 0 ? 'Записаться ↗' : 'Мест нет'}</button>` : '<a class="text-link" href="/#callback-form">Уточнить у клуба ↗</a>'}</div>
      </article>`).join('');
    $$('[data-book-class]', container).forEach(button => button.addEventListener('click', () => bookClass(Number(button.dataset.bookClass), button)));
  }
  async function bookClass(classId, button) {
    try {
      button.disabled = true;
      const result = await api('/api/bookings', { method: 'POST', body: JSON.stringify({ class_id: classId }) });
      alert(`${result.message}\nНомер записи: ${result.booking.booking_code}`);
      await loadSchedule();
    } catch (error) {
      if (error.status === 401) {
        sessionStorage.setItem('arc_pending_booking', String(classId));
        location.href = '/login';
        return;
      }
      alert(error.message);
      button.disabled = false;
      if (error.status === 409) await loadSchedule();
    }
  }
  function setupScheduleFilters() {
    $$('[data-schedule-days] [data-day]').forEach(btn => btn.addEventListener('click', () => { selectedDay = Number(btn.dataset.day); renderSchedule(); }));
    $$('[data-category-filters] [data-category]').forEach(btn => btn.addEventListener('click', () => { selectedCategory = btn.dataset.category; renderSchedule(); }));
  }

  async function setupTrainersPage() {
    const container = $('[data-trainers-grid]');
    if (!container) return;
    try {
      const data = await api('/api/trainers');
      if (!data.items?.length) return;
      container.innerHTML = data.items.map((item) => `<article class="trainer-card"><img src="${escapeHtml(item.photo_path || '/static/images/trainer-placeholder.jpg')}" alt="${escapeHtml(item.name)}" class="trainer-photo" loading="lazy"><div class="trainer-meta"><span class="eyebrow">${escapeHtml(item.speciality)}</span><span class="experience">${item.experience_years} ЛЕТ ОПЫТА</span></div><h2>${escapeHtml(item.name)}</h2><p class="muted">${escapeHtml(item.bio)}</p><a class="text-link" href="/schedule">Посмотреть расписание ↗</a></article>`).join('');
    } catch { /* keep static placeholders visible when API is not connected */ }
  }

  async function setupMemberships() {
    const container = $('[data-membership-grid]');
    if (!container) return;
    try {
      const data = await api('/api/memberships');
      if (!data.items?.length) return;
      container.innerHTML = data.items.map((plan, index) => `<article class="membership-card ${plan.plan_key === 'plus' ? 'membership-featured' : ''}">${plan.plan_key === 'plus' ? '<span class="plan-badge">ПОПУЛЯРНЫЙ</span>' : ''}<span class="plan-mark">ARC / 0${index + 1}</span><h2>${escapeHtml(plan.title)}</h2><p class="muted">${escapeHtml(plan.description)}</p><div class="plan-price">${Number(plan.price).toLocaleString('ru-RU')} <small>₽ / ${plan.duration_days} дней</small></div><ul>${String(plan.features).split(/[,;\n]/).map(s => s.trim()).filter(Boolean).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul><button class="button ${plan.plan_key === 'plus' ? 'button-lime' : 'button-outline'} button-full" data-plan="${escapeHtml(plan.plan_key)}">Оставить заявку ↗</button></article>`).join('');
    } catch { /* initial local markup is a graceful fallback */ }
    $$('[data-plan]').forEach(button => button.addEventListener('click', () => requestPlan(button.dataset.plan, button)));
  }
  async function requestPlan(planKey, button) {
    try {
      button.disabled = true;
      const result = await api('/api/membership-requests', { method: 'POST', body: JSON.stringify({ plan_key: planKey }) });
      setStatus($('.membership-status'), result.message, 'success');
      button.textContent = 'Заявка отправлена ✓';
    } catch (error) {
      if (error.status === 401) {
        sessionStorage.setItem('arc_pending_plan', planKey);
        location.href = '/login';
        return;
      }
      setStatus($('.membership-status'), error.message, 'error');
      button.disabled = false;
    }
  }

  function startCountdowns() {
    const update = () => $$('[data-countdown]').forEach(node => {
      const target = new Date(node.dataset.countdown).getTime();
      const diff = Math.max(0, target - Date.now());
      const values = {
        days: Math.floor(diff / 86400000), hours: Math.floor((diff % 86400000) / 3600000),
        minutes: Math.floor((diff % 3600000) / 60000), seconds: Math.floor((diff % 60000) / 1000)
      };
      Object.entries(values).forEach(([key, value]) => { const targetEl = $(`[data-${key}]`, node); if (targetEl) targetEl.textContent = String(value).padStart(2, '0'); });
    });
    update();
    if ($('[data-countdown]')) window.setInterval(update, 1000);
  }
  async function setupPromotions() {
    const container = $('[data-promotions-grid]');
    if (!container) { startCountdowns(); return; }
    try {
      const data = await api('/api/promotions');
      if (data.items?.length) {
        container.innerHTML = data.items.map((item, index) => `<article class="promotion-card"><div class="promo-visual ${index % 2 ? 'promo-visual-two' : ''}"><span class="promo-discount">−${item.discount_percent}%</span><span class="promo-side">ARC / OFFER ${String(index + 1).padStart(2, '0')}</span></div><div class="promo-content"><p class="eyebrow">${escapeHtml(item.subtitle)}</p><h2>${escapeHtml(item.title)}</h2><p>${escapeHtml(item.description)}</p><div class="countdown" data-countdown="${escapeHtml(item.ends_at)}"><span><b data-days>--</b><small>дней</small></span><span><b data-hours>--</b><small>часов</small></span><span><b data-minutes>--</b><small>минут</small></span><span><b data-seconds>--</b><small>секунд</small></span></div><a class="text-link" href="/memberships">Выбрать тариф ↗</a></div></article>`).join('');
      }
    } catch { /* keep sample card placeholders */ }
    startCountdowns();
  }

  function openNewsModal(item) {
    if (!item) return;
    const modal = $('[data-news-modal]');
    if (!modal) return;
    $('[data-modal-category]', modal).textContent = item.category || 'ARC.FITNESS';
    $('[data-modal-title]', modal).textContent = item.title || '';
    $('[data-modal-body]', modal).textContent = item.body || item.excerpt || '';
    const image = $('.modal-image', modal);
    if (image) image.innerHTML = '';
    if (typeof modal.showModal === 'function') modal.showModal();
    else modal.setAttribute('open', '');
  }
  async function setupNews() {
    const container = $('[data-news-grid]');
    if (!container) return;
    let items = [];
    const render = () => {
      const activeButton = $('[data-news-filters] .filter-chip.active');
      const category = activeButton?.dataset.newsCategory || 'Все';
      const filtered = category === 'Все' ? items : items.filter(item => item.category === category);
      container.innerHTML = filtered.length ? filtered.map((item, index) => `<article class="news-card"><img src="${escapeHtml(item.image_path || '/static/images/news-placeholder.jpg')}" alt="${escapeHtml(item.title)}" class="news-card-image" loading="lazy"><div class="news-card-content"><p class="eyebrow">${escapeHtml(item.category)} · ${item.published_at ? new Date(item.published_at).toLocaleDateString('ru-RU') : ''}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.excerpt)}</p><button type="button" data-open-news="${item.id}">Читать новость ↗</button></div></article>`).join('') : '<div class="empty-state">В этой категории пока нет опубликованных новостей.</div>';
      const lookup = new Map(items.map(item => [String(item.id), item]));
      $$('[data-open-news]', container).forEach(btn => btn.addEventListener('click', () => openNewsModal(lookup.get(btn.dataset.openNews))));
    };
    try {
      const data = await api('/api/news');
      items = data.items || [];
      render();
    } catch (error) {
      container.innerHTML = '<div class="empty-state">Новости временно недоступны. Попробуйте позже.</div>';
    }
    $$('[data-news-category]').forEach(btn => btn.addEventListener('click', () => {
      $$('[data-news-category]').forEach(other => other.classList.toggle('active', other === btn));
      render();
    }));
  }

  async function setupRegister() {
    const form = $('#register-form');
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const statusEl = $('.form-status', form);
      const button = $('button[type="submit"]', form);
      setStatus(statusEl, 'Создаём аккаунт…');
      if (button) button.disabled = true;
      const data = formDataObject(form);
      if (!data.phone) data.phone = null;
      try {
        const result = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(data) });
        sessionStorage.setItem('arc_register_email', result.email || data.email);
        location.href = '/verify';
      } catch (error) {
        setStatus(statusEl, error.message, 'error');
        if (button) button.disabled = false;
      }
    });
  }

  async function setupVerify() {
    const form = $('#verify-form');
    if (!form) return;
    const emailInput = $('[name="email"]', form);
    if (emailInput && sessionStorage.getItem('arc_register_email')) emailInput.value = sessionStorage.getItem('arc_register_email');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const statusEl = $('.form-status', form);
      const button = $('button[type="submit"]', form);
      setStatus(statusEl, 'Проверяем код…');
      if (button) button.disabled = true;
      try {
        const data = await api('/api/auth/verify', { method: 'POST', body: JSON.stringify(formDataObject(form)) });
        setStatus(statusEl, data.message, 'success');
        sessionStorage.removeItem('arc_register_email');
        await afterLoginActions();
      } catch (error) {
        setStatus(statusEl, error.message, 'error');
        if (button) button.disabled = false;
      }
    });
  }

  async function afterLoginActions() {
    const pendingBooking = sessionStorage.getItem('arc_pending_booking');
    if (pendingBooking) {
      sessionStorage.removeItem('arc_pending_booking');
      try { await api('/api/bookings', { method: 'POST', body: JSON.stringify({ class_id: Number(pendingBooking) }) }); }
      catch (error) { alert(`Не удалось оформить запись: ${error.message}`); }
      location.href = '/account';
      return true;
    }
    const pendingPlan = sessionStorage.getItem('arc_pending_plan');
    if (pendingPlan) {
      sessionStorage.removeItem('arc_pending_plan');
      try {
        const result = await api('/api/membership-requests', { method: 'POST', body: JSON.stringify({ plan_key: pendingPlan }) });
        sessionStorage.setItem('arc_plan_notice', result.message);
      } catch (error) { sessionStorage.setItem('arc_plan_notice', error.message); }
      location.href = '/account';
      return true;
    }
    const next = new URLSearchParams(location.search).get('next');
    if (next && next.startsWith('/') && !next.startsWith('//')) location.href = next;
    else {
      try {
        const { user } = await api('/api/auth/me');
        location.href = user.role === 'admin' ? '/admin' : '/account';
      } catch { location.href = '/account'; }
    }
    return true;
  }
  async function setupLogin() {
    const form = $('#login-form');
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const statusEl = $('.form-status', form);
      const button = $('button[type="submit"]', form);
      setStatus(statusEl, 'Проверяем данные…');
      if (button) button.disabled = true;
      try {
        await api('/api/auth/login', { method: 'POST', body: JSON.stringify(formDataObject(form)) });
        await afterLoginActions();
      } catch (error) {
        setStatus(statusEl, error.message, 'error');
        if (button) button.disabled = false;
      }
    });
  }

  async function setupAccount() {
    if (page !== 'account') return;
    const statusEl = $('[data-account-status]');
    let user;
    try {
      const data = await api('/api/auth/me');
      user = data.user;
    } catch {
      location.href = '/login?next=/account';
      return;
    }
    if (user.role === 'admin') { location.replace('/admin'); return; }
    const name = $('[data-profile-name]');
    const email = $('[data-profile-email]');
    const avatar = $('[data-avatar]');
    const greeting = $('[data-account-greeting]');
    if (name) name.textContent = user.full_name;
    if (email) email.textContent = user.email;
    if (avatar) avatar.textContent = user.full_name.split(/\s+/).slice(0, 2).map(v => v[0]).join('').toUpperCase();
    if (greeting) greeting.textContent = `Привет, ${user.full_name.split(' ')[0]}! Здесь можно управлять профилем и следить за своими записями.`;
    const profile = $('#profile-form');
    if (profile) {
      $('[name="full_name"]', profile).value = user.full_name || '';
      $('[name="email"]', profile).value = user.email || '';
      $('[name="phone"]', profile).value = user.phone || '';
      profile.addEventListener('submit', async event => {
        event.preventDefault();
        const formStatus = $('.form-status', profile);
        const data = formDataObject(profile);
        if (!data.phone) data.phone = null;
        if (!data.current_password) delete data.current_password;
        if (!data.new_password) delete data.new_password;
        setStatus(formStatus, 'Сохраняем профиль…');
        try {
          const result = await api('/api/profile', { method: 'PATCH', body: JSON.stringify(data) });
          setStatus(formStatus, result.message, 'success');
          if (name) name.textContent = result.user.full_name;
          if (avatar) avatar.textContent = result.user.full_name.split(/\s+/).slice(0, 2).map(v => v[0]).join('').toUpperCase();
          $('[name="current_password"]', profile).value = '';
          $('[name="new_password"]', profile).value = '';
        } catch (error) { setStatus(formStatus, error.message, 'error'); }
      });
    }
    const membershipList = $('[data-my-memberships]');
    if (membershipList) {
      try {
        const membershipData = await api('/api/membership-requests/mine');
        const statusLabels = { new: 'Ожидает обработки', processed: 'Обработана администратором', cancelled: 'Отменена' };
        const active = membershipData.active_membership;
        const activeHtml = active ? `<article class="booking-row current-membership"><div><p class="eyebrow">АКТИВНЫЙ АБОНЕМЕНТ</p><h3>${escapeHtml(active.plan_title)}</h3><p>${Number(active.price).toLocaleString('ru-RU')} ₽ · ${active.duration_days} дней</p><p>Действует до ${new Date(active.ends_at).toLocaleDateString('ru-RU')}</p></div><span class="status-pill">Активен</span></article>` : '<div class="empty-state">Сейчас у вас нет активного абонемента. После звонка администратор сможет привязать выбранный тариф к вашему профилю.</div>';
        const requestsHtml = membershipData.items?.length ? `<h3 class="membership-history-title">История заявок</h3>${membershipData.items.map(item => `<article class="booking-row"><div><h3>${escapeHtml(item.plan_title)}</h3><p>${Number(item.price).toLocaleString('ru-RU')} ₽ · ${item.duration_days} дней</p><p>${item.created_at ? new Date(item.created_at).toLocaleDateString('ru-RU') : ''}</p></div><span class="status-pill">${escapeHtml(statusLabels[item.status] || item.status)}</span></article>`).join('')}` : '';
        membershipList.innerHTML = activeHtml + requestsHtml;
      } catch (error) { membershipList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
    }
    const bookingList = $('[data-my-bookings]');
    async function loadMyBookings() {
      if (!bookingList) return;
      try {
        const data = await api('/api/bookings');
        const items = data.items || [];
        bookingList.innerHTML = items.length ? items.map(item => `<article class="booking-row"><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(daysRu[item.day_of_week] || '')} · ${escapeHtml(String(item.starts_at).slice(0, 5))} · ${escapeHtml(item.trainer_name || 'Тренер клуба')}</p><p>${escapeHtml(item.status === 'active' ? 'Активная запись' : 'Запись отменена')} · ${escapeHtml(item.room)}</p></div><div class="booking-code">${escapeHtml(item.booking_code)}</div>${item.status === 'active' ? `<button class="button button-outline" type="button" data-cancel-booking="${item.id}">Отменить</button>` : '<span class="muted small">Завершено</span>'}</article>`).join('') : '<div class="empty-state">У вас пока нет записей. Выберите тренировку в расписании.</div>';
        $$('[data-cancel-booking]', bookingList).forEach(button => button.addEventListener('click', async () => {
          if (!confirm('Отменить запись на тренировку?')) return;
          button.disabled = true;
          try { const result = await api(`/api/bookings/${button.dataset.cancelBooking}`, { method: 'DELETE' }); setStatus(statusEl, result.message, 'success'); await loadMyBookings(); }
          catch (error) { setStatus(statusEl, error.message, 'error'); button.disabled = false; }
        }));
      } catch (error) { bookingList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
    }
    await loadMyBookings();
    const planNotice = sessionStorage.getItem('arc_plan_notice');
    if (planNotice) { setStatus(statusEl, planNotice, planNotice.includes('не удалось') ? 'error' : 'success'); sessionStorage.removeItem('arc_plan_notice'); }
    $('[data-logout]')?.addEventListener('click', async () => {
      try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* the cookie is removed on logout endpoint */ }
      location.href = '/';
    });
    setupBjuCalculator();
  }

  function setupBjuCalculator() {
    const form = $('#bju-form');
    const results = $('[data-bju-results]');
    if (!form || !results) return;
    form.addEventListener('submit', event => {
      event.preventDefault();
      const data = formDataObject(form);
      const age = Number(data.age), height = Number(data.height), weight = Number(data.weight), activity = Number(data.activity);
      if (age < 18) {
        setStatus(results, 'Калькулятор предназначен только для взрослых. Для подростков нормы питания лучше обсуждать с врачом или диетологом. ', 'error');
        results.hidden = false;
        return;
      }
      if (!(height > 0 && weight > 0 && activity > 0)) return;
      const bmr = 10 * weight + 6.25 * height - 5 * age + (data.sex === 'male' ? 5 : -161);
      let calories = bmr * activity;
      if (data.goal === 'gentle_loss') calories *= 0.92;
      if (data.goal === 'gentle_gain') calories *= 1.08;
      calories = Math.round(calories / 10) * 10;
      const protein = Math.round(weight * 1.6);
      const fat = Math.round(weight * 0.8);
      const carbs = Math.max(0, Math.round((calories - protein * 4 - fat * 9) / 4));
      results.hidden = false;
      results.innerHTML = `<div class="bju-result"><span>Энергия / день</span><strong>${calories}</strong><small>ккал · ориентир</small></div><div class="bju-result"><span>Белки</span><strong>${protein}</strong><small>г / день</small></div><div class="bju-result"><span>Жиры</span><strong>${fat}</strong><small>г / день</small></div><div class="bju-result"><span>Углеводы</span><strong>${carbs}</strong><small>г / день</small></div>`;
    });
  }

  async function setupAdmin() {
    if (page !== 'admin') return;
    const statusEl = $('[data-admin-status]');
    const statsEl = $('[data-admin-stats]');
    const requestsTable = $('[data-admin-requests]');
    const clientsTable = $('[data-admin-clients]');
    const bookingsTable = $('[data-admin-bookings]');
    const classesTable = $('[data-admin-classes]');
    const requestFilter = $('[data-request-filter]');
    const clientSearch = $('[data-client-search]');
    const clientDialog = $('[data-client-dialog]');
    const clientDetail = $('[data-client-detail]');
    const classForm = $('[data-admin-class-form]');
    const classFormStatus = $('[data-class-form-status]');
    const classTrainerSelect = $('[data-class-trainer]');
    const classSubmit = $('[data-class-submit]');
    const classCancel = $('[data-class-cancel]');
    let requestItems = [];
    let clientItems = [];
    let bookingItems = [];
    let classItems = [];
    let trainerItems = [];

    const statusLabels = { new: 'Новая', processed: 'Обработана', cancelled: 'Отменена', closed: 'Закрыта', active: 'Активна', revoked: 'Отвязана', expired: 'Истекла' };
    const formatDate = value => value ? new Date(value).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '—';
    const statusTag = status => `<span class="admin-status-tag admin-status-${escapeHtml(status || 'new')}">${escapeHtml(statusLabels[status] || status || '—')}</span>`;
    const classLabel = item => `${daysRu[item.day_of_week] || 'День не указан'} · ${String(item.starts_at || '').slice(0, 5)} — ${item.title}${item.room ? ` · ${item.room}` : ''}`;

    function renderRequests() {
      if (!requestsTable) return;
      const filter = requestFilter?.value || 'all';
      const items = requestItems.filter(item => {
        if (filter === 'new') return item.status === 'new';
        if (filter !== 'all') return item.type === filter;
        return true;
      });
      if (!items.length) {
        requestsTable.innerHTML = '<tr><td colspan="5"><div class="admin-empty">Заявок по выбранному фильтру пока нет.</div></td></tr>';
        return;
      }
      requestsTable.innerHTML = items.map(item => {
        const contact = [item.phone, item.email].filter(Boolean).join(' · ') || 'Контакты не указаны';
        let action = '—';
        if (item.type === 'callback' && item.status === 'new') action = `<button type="button" data-request-process="callback:${item.id}">Отметить обработанной</button>`;
        if (item.type === 'membership' && item.status === 'new') action = `<button type="button" data-request-process="membership:${item.id}">Отметить обработанной</button>`;
        if (item.type === 'booking') action = `<button type="button" data-jump-booking="${item.id}">Управлять записью ↘</button>`;
        return `<tr>
          <td><strong>${escapeHtml(item.type_label)}</strong><span class="admin-contact-line">${escapeHtml(formatDate(item.created_at))}</span><span class="admin-contact-line">№ ${escapeHtml(item.id)}</span></td>
          <td><span class="admin-contact-name">${escapeHtml(item.client_name || 'Посетитель')}</span><span class="admin-contact-line">${escapeHtml(contact)}</span></td>
          <td><strong>${escapeHtml(item.title || 'Обращение')}</strong><details class="admin-details"><summary>Подробнее</summary><p>${escapeHtml(item.details || 'Подробности не указаны')}</p>${item.comment ? `<p>Комментарий: ${escapeHtml(item.comment)}</p>` : ''}${item.booking_code ? `<p>Код записи: ${escapeHtml(item.booking_code)}</p>` : ''}${item.user_id ? `<p><button type="button" data-open-client="${item.user_id}">Открыть карточку клиента</button></p>` : ''}</details></td>
          <td>${statusTag(item.status)}</td><td><div class="admin-row-actions">${action}</div></td>
        </tr>`;
      }).join('');
      $$('[data-request-process]', requestsTable).forEach(button => button.addEventListener('click', async () => {
        const [type, id] = button.dataset.requestProcess.split(':');
        button.disabled = true;
        try {
          const result = await api(`/api/admin/requests/${type}/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'processed' }) });
          setStatus(statusEl, result.message || 'Заявка обработана.', 'success');
          await loadAdminData();
        } catch (error) { setStatus(statusEl, error.message, 'error'); button.disabled = false; }
      }));
      $$('[data-jump-booking]', requestsTable).forEach(button => button.addEventListener('click', () => {
        const row = $$('[data-admin-bookings] tr').find(tr => tr.dataset.bookingId === button.dataset.jumpBooking);
        row?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        row?.classList.add('admin-row-highlight');
        window.setTimeout(() => row?.classList.remove('admin-row-highlight'), 1800);
      }));
      $$('[data-open-client]', requestsTable).forEach(button => button.addEventListener('click', () => openClient(Number(button.dataset.openClient))));
    }

    function renderClients() {
      if (!clientsTable) return;
      const query = (clientSearch?.value || '').trim().toLocaleLowerCase('ru-RU');
      const items = clientItems.filter(item => !query || [item.full_name, item.email, item.phone].some(value => String(value || '').toLocaleLowerCase('ru-RU').includes(query)));
      clientsTable.innerHTML = items.length ? items.map(item => `<tr>
        <td><span class="admin-contact-name">${escapeHtml(item.full_name)}</span><span class="admin-contact-line">Клиент №${item.id} · регистрация ${escapeHtml(new Date(item.created_at).toLocaleDateString('ru-RU'))}</span></td>
        <td>${escapeHtml(item.email)}<span class="admin-contact-line">${escapeHtml(item.phone || 'Телефон не указан')}</span></td>
        <td>${statusTag(item.is_verified ? 'active' : 'new')}<span class="admin-contact-line">${item.is_verified ? 'Email подтверждён' : 'Email не подтверждён'}</span></td>
        <td>${item.membership_title ? `<strong>${escapeHtml(item.membership_title)}</strong><span class="admin-contact-line">До ${escapeHtml(new Date(item.membership_ends_at).toLocaleDateString('ru-RU'))}</span>` : '<span class="muted">Нет активного абонемента</span>'}</td>
        <td><button type="button" data-open-client="${item.id}">Открыть карточку</button></td>
      </tr>`).join('') : '<tr><td colspan="5"><div class="admin-empty">Клиенты не найдены.</div></td></tr>';
      $$('[data-open-client]', clientsTable).forEach(button => button.addEventListener('click', () => openClient(Number(button.dataset.openClient))));
    }

    function renderBookings() {
      if (!bookingsTable) return;
      if (!bookingItems.length) {
        bookingsTable.innerHTML = '<tr><td colspan="5"><div class="admin-empty">Записей пока нет.</div></td></tr>';
        return;
      }
      bookingsTable.innerHTML = bookingItems.map(item => {
        const active = item.status === 'active';
        const classOptions = classItems.map(slot => `<option value="${slot.id}" ${slot.id !== item.class_id && slot.available <= 0 ? 'disabled' : ''}>${escapeHtml(classLabel(slot))} · свободно ${slot.available}/${slot.capacity}</option>`).join('');
        return `<tr data-booking-id="${item.id}">
          <td><strong>${escapeHtml(item.booking_code)}</strong><span class="admin-contact-line">${escapeHtml(formatDate(item.created_at))}</span></td>
          <td><span class="admin-contact-name">${escapeHtml(item.full_name)}</span><span class="admin-contact-line">${escapeHtml(item.email)}</span><span class="admin-contact-line">${escapeHtml(item.phone || 'Телефон не указан')}</span><button type="button" data-open-client="${item.user_id}">Карточка клиента</button></td>
          <td><strong>${escapeHtml(item.class_title)}</strong><span class="admin-contact-line">${escapeHtml(daysRu[item.day_of_week] || '')} · ${escapeHtml(String(item.starts_at).slice(0,5))} · ${escapeHtml(item.room || '')}</span></td>
          <td>${active ? `<select class="admin-class-select" aria-label="Новая тренировка для записи ${escapeHtml(item.booking_code)}" data-booking-target="${item.id}"><option value="">Выберите занятие</option>${classOptions}</select>` : '<span class="muted">Перенос недоступен для отменённой записи</span>'}</td>
          <td>${statusTag(item.status)}${active ? `<div class="admin-row-actions booking-actions"><button type="button" data-move-booking="${item.id}">Перенести</button><button type="button" class="danger-action" data-cancel-admin-booking="${item.id}">Отменить</button></div>` : ''}</td>
        </tr>`;
      }).join('');
      $$('[data-booking-target]', bookingsTable).forEach(select => {
        select.value = String(bookingItems.find(item => String(item.id) === select.dataset.bookingTarget)?.class_id || '');
      });
      $$('[data-move-booking]', bookingsTable).forEach(button => button.addEventListener('click', async () => {
        const id = Number(button.dataset.moveBooking);
        const select = $(`[data-booking-target="${id}"]`, bookingsTable);
        const classId = Number(select?.value || 0);
        if (!classId) { setStatus(statusEl, 'Выберите занятие для переноса.', 'error'); return; }
        if (classId === Number(bookingItems.find(item => item.id === id)?.class_id)) { setStatus(statusEl, 'Выбрано текущее занятие.', 'error'); return; }
        button.disabled = true;
        try {
          const result = await api(`/api/admin/bookings/${id}`, { method: 'PATCH', body: JSON.stringify({ class_id: classId }) });
          setStatus(statusEl, result.message, 'success'); await loadAdminData();
        } catch (error) { setStatus(statusEl, error.message, 'error'); button.disabled = false; }
      }));
      $$('[data-cancel-admin-booking]', bookingsTable).forEach(button => button.addEventListener('click', async () => {
        if (!confirm('Отменить запись и освободить место в группе?')) return;
        button.disabled = true;
        try {
          const result = await api(`/api/admin/bookings/${button.dataset.cancelAdminBooking}`, { method: 'PATCH', body: JSON.stringify({ status: 'cancelled' }) });
          setStatus(statusEl, result.message, 'success'); await loadAdminData();
        } catch (error) { setStatus(statusEl, error.message, 'error'); button.disabled = false; }
      }));
      $$('[data-open-client]', bookingsTable).forEach(button => button.addEventListener('click', () => openClient(Number(button.dataset.openClient))));
    }

    function fillTrainerSelect() {
      if (!classTrainerSelect) return;
      const selected = classTrainerSelect.value;
      classTrainerSelect.innerHTML = '<option value="">Без выбранного тренера</option>' + trainerItems.map(trainer => `<option value="${trainer.id}">${escapeHtml(trainer.name)} · ${escapeHtml(trainer.speciality)}</option>`).join('');
      if (selected) classTrainerSelect.value = selected;
    }

    function resetClassForm() {
      classForm?.reset();
      const idInput = $('[name="class_id"]', classForm);
      if (idInput) idInput.value = '';
      if (classSubmit) classSubmit.textContent = 'Добавить занятие';
      if (classCancel) classCancel.hidden = true;
      setStatus(classFormStatus, '');
    }

    function renderClasses() {
      if (!classesTable) return;
      if (!classItems.length) {
        classesTable.innerHTML = '<tr><td colspan="5"><div class="admin-empty">Групповых занятий пока нет.</div></td></tr>';
        return;
      }
      classesTable.innerHTML = classItems.map(item => `<tr>
        <td><strong>${escapeHtml(daysRu[item.day_of_week] || '')}</strong><span class="admin-contact-line">${escapeHtml(String(item.starts_at).slice(0,5))} · ${item.duration_minutes} мин.</span></td>
        <td><span class="admin-contact-name">${escapeHtml(item.title)}</span><span class="admin-contact-line">${escapeHtml(item.category)}</span></td>
        <td>${escapeHtml(item.trainer_name || 'Тренер не назначен')}<span class="admin-contact-line">${escapeHtml(item.room)}</span></td>
        <td><strong>${item.available} / ${item.capacity}</strong><span class="admin-contact-line">Свободно / всего</span><span class="admin-contact-line">Записано: ${item.booked_count}</span></td>
        <td><div class="admin-row-actions"><button type="button" data-edit-class="${item.id}">Изменить</button><button type="button" class="danger-action" data-hide-class="${item.id}">Скрыть</button></div></td>
      </tr>`).join('');
      $$('[data-edit-class]', classesTable).forEach(button => button.addEventListener('click', () => {
        const item = classItems.find(row => Number(row.id) === Number(button.dataset.editClass));
        if (!item || !classForm) return;
        $('[name="class_id"]', classForm).value = item.id;
        $('[name="title"]', classForm).value = item.title;
        $('[name="category"]', classForm).value = item.category;
        $('[name="day_of_week"]', classForm).value = String(item.day_of_week);
        $('[name="starts_at"]', classForm).value = String(item.starts_at).slice(0,5);
        $('[name="duration_minutes"]', classForm).value = item.duration_minutes;
        $('[name="room"]', classForm).value = item.room;
        $('[name="trainer_id"]', classForm).value = item.trainer_id || '';
        $('[name="capacity"]', classForm).value = item.capacity;
        if (classSubmit) classSubmit.textContent = 'Сохранить изменения';
        if (classCancel) classCancel.hidden = false;
        setStatus(classFormStatus, `Редактирование: ${item.title}`);
        classForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }));
      $$('[data-hide-class]', classesTable).forEach(button => button.addEventListener('click', async () => {
        if (!confirm('Скрыть занятие из расписания?')) return;
        button.disabled = true;
        try {
          const result = await api(`/api/admin/classes/${button.dataset.hideClass}`, { method: 'DELETE' });
          setStatus(statusEl, result.message, 'success');
          await loadAdminData();
        } catch (error) { setStatus(statusEl, error.message, 'error'); button.disabled = false; }
      }));
    }

    async function loadAdminData() {
      setStatus(statusEl, 'Загружаем данные…');
      try {
        const [requests, clients, bookings, classes, trainers] = await Promise.all([
          api('/api/admin/requests'), api('/api/admin/clients'), api('/api/admin/bookings'), api('/api/admin/classes'), api('/api/trainers')
        ]);
        requestItems = requests.items || [];
        clientItems = clients.items || [];
        bookingItems = bookings.items || [];
        classItems = classes.items || [];
        trainerItems = trainers.items || [];
        fillTrainerSelect();
        const newRequests = requestItems.filter(item => item.status === 'new').length;
        const activeBookings = bookingItems.filter(item => item.status === 'active').length;
        if (statsEl) statsEl.innerHTML = `<div class="admin-stat"><span>Клиенты</span><strong>${clientItems.length}</strong></div><div class="admin-stat"><span>Новые заявки</span><strong>${newRequests}</strong></div><div class="admin-stat"><span>Активные записи</span><strong>${activeBookings}</strong></div>`;
        renderRequests(); renderClients(); renderBookings(); renderClasses();
        setStatus(statusEl, 'Данные обновлены.', 'success');
      } catch (error) {
        setStatus(statusEl, error.status === 401 ? 'Войдите в аккаунт администратора.' : error.status === 403 ? 'Доступ разрешён только администратору.' : 'Не удалось загрузить данные. Попробуйте обновить страницу.', 'error');
        if (error.status === 401) setTimeout(() => { location.href = '/login?next=/admin'; }, 700);
        if (error.status === 403) setTimeout(() => { location.href = '/account'; }, 900);
      }
    }

    async function openClient(userId) {
      if (!clientDialog || !clientDetail) return;
      clientDetail.innerHTML = '<p class="loading-line">Загрузка информации…</p>';
      if (!clientDialog.open && typeof clientDialog.showModal === 'function') clientDialog.showModal();
      else if (!clientDialog.open) clientDialog.setAttribute('open', '');
      try {
        const data = await api(`/api/admin/clients/${userId}`);
        const user = data.user;
        const now = Date.now();
        const active = (data.memberships || []).find(item => item.status === 'active' && new Date(item.ends_at).getTime() > now);
        const plans = (data.plans || []).map(plan => `<option value="${escapeHtml(plan.plan_key)}">${escapeHtml(plan.title)} · ${Number(plan.price).toLocaleString('ru-RU')} ₽ / ${plan.duration_days} дней</option>`).join('');
        const membershipsHtml = (data.memberships || []).length ? data.memberships.map(item => `<div class="client-history-item"><div><strong>${escapeHtml(item.plan_title)}</strong><p>${escapeHtml(formatDate(item.starts_at))} — ${escapeHtml(formatDate(item.ends_at))}</p></div>${statusTag(item.status)}</div>`).join('') : '<p class="muted">Истории абонементов пока нет.</p>';
        const requestsHtml = (data.membership_requests || []).length ? data.membership_requests.map(item => `<div class="client-history-item"><div><strong>${escapeHtml(item.plan_title)}</strong><p>${Number(item.price).toLocaleString('ru-RU')} ₽ · ${escapeHtml(formatDate(item.created_at))}</p></div>${statusTag(item.status)}</div>`).join('') : '<p class="muted">Заявок на абонемент нет.</p>';
        const bookingsHtml = (data.bookings || []).length ? data.bookings.map(item => `<div class="client-booking-line"><strong>${escapeHtml(item.booking_code)}</strong> · ${escapeHtml(item.class_title)} · ${escapeHtml(daysRu[item.day_of_week] || '')} ${escapeHtml(String(item.starts_at).slice(0,5))} · ${escapeHtml(statusLabels[item.status] || item.status)}</div>`).join('') : '<p class="muted">Записей на тренировки пока нет.</p>';
        clientDetail.innerHTML = `
          <div class="client-info-grid"><div class="client-info-item"><span>Имя</span><strong>${escapeHtml(user.full_name)}</strong></div><div class="client-info-item"><span>Клиент №</span><strong>${user.id}</strong></div><div class="client-info-item"><span>Email</span><strong>${escapeHtml(user.email)}</strong></div><div class="client-info-item"><span>Телефон</span><strong>${escapeHtml(user.phone || 'Не указан')}</strong></div><div class="client-info-item"><span>Регистрация</span><strong>${escapeHtml(formatDate(user.created_at))}</strong></div><div class="client-info-item"><span>Подтверждение email</span><strong>${user.is_verified ? 'Подтверждён' : 'Не подтверждён'}</strong></div></div>
          <section class="client-dialog-section"><h3>Абонемент клиента</h3>${active ? `<div class="client-history-item"><div><strong>${escapeHtml(active.plan_title)}</strong><p>${Number(active.price).toLocaleString('ru-RU')} ₽ · действует до ${escapeHtml(new Date(active.ends_at).toLocaleDateString('ru-RU'))}</p></div>${statusTag('active')}</div><button class="button button-outline danger-action" type="button" data-revoke-membership="${user.id}">Удалить абонемент</button>` : `<p class="muted">Активного абонемента нет.</p><form class="client-membership-form" data-assign-membership="${user.id}"><label>Абонемент<select name="plan_key" required><option value="">Выберите тариф</option>${plans}</select></label><button class="button button-lime" type="submit">Привязать абонемент</button></form>`}<div class="client-history-list top-gap">${membershipsHtml}</div></section>
          <section class="client-dialog-section"><h3>Заявки на абонементы</h3><div class="client-history-list">${requestsHtml}</div></section>
          <section class="client-dialog-section"><h3>Записи на тренировки</h3>${bookingsHtml}</section>
          <p class="form-status" data-client-status aria-live="polite"></p>`;
        const assignForm = $('[data-assign-membership]', clientDetail);
        assignForm?.addEventListener('submit', async event => {
          event.preventDefault();
          const form = event.currentTarget;
          const button = $('button[type="submit"]', form);
          button.disabled = true;
          try {
            const result = await api(`/api/admin/clients/${user.id}/membership`, { method: 'POST', body: JSON.stringify(formDataObject(form)) });
            setStatus($('[data-client-status]', clientDetail), result.message, 'success');
            await loadAdminData(); await openClient(user.id);
          } catch (error) { setStatus($('[data-client-status]', clientDetail), error.message, 'error'); button.disabled = false; }
        });
        $('[data-revoke-membership]', clientDetail)?.addEventListener('click', async event => {
          if (!confirm('Удалить активный абонемент у клиента?')) return;
          const button = event.currentTarget; button.disabled = true;
          try {
            const result = await api(`/api/admin/clients/${user.id}/membership`, { method: 'DELETE' });
            setStatus($('[data-client-status]', clientDetail), result.message, 'success');
            await loadAdminData(); await openClient(user.id);
          } catch (error) { setStatus($('[data-client-status]', clientDetail), error.message, 'error'); button.disabled = false; }
        });
      } catch (error) {
        clientDetail.innerHTML = `<p class="form-status error">${escapeHtml(error.message)}</p>`;
      }
    }

    classForm?.addEventListener('submit', async event => {
      event.preventDefault();
      const submitButton = $('button[type="submit"]', classForm);
      const raw = formDataObject(classForm);
      const classId = raw.class_id;
      const payload = {
        title: raw.title,
        category: raw.category,
        day_of_week: Number(raw.day_of_week),
        starts_at: raw.starts_at,
        duration_minutes: Number(raw.duration_minutes),
        room: raw.room,
        trainer_id: raw.trainer_id ? Number(raw.trainer_id) : null,
        capacity: Number(raw.capacity)
      };
      if (submitButton) submitButton.disabled = true;
      setStatus(classFormStatus, 'Сохраняем расписание…');
      try {
        const result = classId
          ? await api(`/api/admin/classes/${classId}`, { method: 'PATCH', body: JSON.stringify(payload) })
          : await api('/api/admin/classes', { method: 'POST', body: JSON.stringify(payload) });
        setStatus(classFormStatus, result.message, 'success');
        resetClassForm();
        await loadAdminData();
      } catch (error) { setStatus(classFormStatus, error.message, 'error'); }
      finally { if (submitButton) submitButton.disabled = false; }
    });
    classCancel?.addEventListener('click', resetClassForm);

    $('[data-admin-refresh]')?.addEventListener('click', loadAdminData);
    $('[data-admin-logout]')?.addEventListener('click', async () => {
      try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* logout endpoint clears the session cookie */ }
      location.href = '/';
    });
    requestFilter?.addEventListener('change', renderRequests);
    clientSearch?.addEventListener('input', renderClients);
    $('[data-close-client]')?.addEventListener('click', () => clientDialog?.close());
    clientDialog?.addEventListener('click', event => { if (event.target === clientDialog) clientDialog.close(); });
    await loadAdminData();
  }

  async function bootstrap() {
    renderShell();
    setupThemeAndMenu();
    setupCallbackForm();
    if (page === 'home') setupHome();
    if (page === 'schedule') { setupScheduleFilters(); loadSchedule(); }
    if (page === 'trainers') setupTrainersPage();
    if (page === 'memberships') setupMemberships();
    if (page === 'promotions') setupPromotions();
    if (page === 'news') setupNews();
    if (page === 'register') setupRegister();
    if (page === 'verify') setupVerify();
    if (page === 'login') setupLogin();
    if (page === 'account') setupAccount();
    if (page === 'admin') setupAdmin();
  }

  document.addEventListener('DOMContentLoaded', bootstrap);
})();
