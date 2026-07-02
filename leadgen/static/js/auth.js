/* LeadGen — authentication (login, register, session) */
const LG_TOKEN_KEY = 'lg_token';
const LG_USER_KEY = 'lg_user';

const AUTH_I18N = {
  uk: {
    auth_login_title: 'Вхід',
    auth_login_sub: 'Увійдіть, щоб продовжити роботу з лідами',
    auth_register_title: 'Реєстрація',
    auth_register_sub: 'Створіть акаунт для доступу до платформи',
    auth_email: 'Email',
    auth_password: 'Пароль',
    auth_password_confirm: 'Підтвердження пароля',
    auth_password_hint: 'Мінімум 8 символів',
    auth_name: "Ім'я",
    auth_sign_in: 'Увійти',
    auth_sign_up: 'Створити акаунт',
    auth_no_account: 'Немає акаунту?',
    auth_register_link: 'Зареєструватися',
    auth_have_account: 'Вже є акаунт?',
    auth_login_link: 'Увійти',
    auth_err_password_mismatch: 'Паролі не збігаються',
    auth_err_email_taken: 'Цей email вже зареєстровано. Увійдіть.',
    auth_err_invalid_credentials: 'Невірний email або пароль. Перевірте пароль або зареєструйтесь знову.',
    auth_err_autofill: 'Safari може підставити старий пароль — введіть пароль вручну або скиньте його.',
    auth_forgot: 'Забули пароль?',
    auth_reset_title: 'Новий пароль',
    auth_reset_sub: 'Встановіть новий пароль для вашого акаунта',
    auth_reset_btn: 'Зберегти пароль',
    auth_err_try_reset: 'Акаунт існує — скиньте пароль або введіть його вручну (не autofill).',
    auth_reset_ok: 'Пароль оновлено',
    auth_err_generic: 'Помилка. Спробуйте ще раз.',
    auth_loading: 'Завантаження…',
    auth_submitting: 'Зачекайте…',
    auth_logout: 'Вийти',
  },
  ru: {
    auth_login_title: 'Вход',
    auth_login_sub: 'Войдите, чтобы продолжить работу с лидами',
    auth_register_title: 'Регистрация',
    auth_register_sub: 'Создайте аккаунт для доступа к платформе',
    auth_email: 'Email',
    auth_password: 'Пароль',
    auth_password_confirm: 'Подтверждение пароля',
    auth_password_hint: 'Минимум 8 символов',
    auth_name: 'Имя',
    auth_sign_in: 'Войти',
    auth_sign_up: 'Создать аккаунт',
    auth_no_account: 'Нет аккаунта?',
    auth_register_link: 'Зарегистрироваться',
    auth_have_account: 'Уже есть аккаунт?',
    auth_login_link: 'Войти',
    auth_err_password_mismatch: 'Пароли не совпадают',
    auth_err_email_taken: 'Этот email уже зарегистрирован. Войдите.',
    auth_err_invalid_credentials: 'Неверный email или пароль. Проверьте пароль или зарегистрируйтесь снова.',
    auth_err_autofill: 'Safari может подставить старый пароль — введите вручную или сбросьте.',
    auth_forgot: 'Забыли пароль?',
    auth_reset_title: 'Новый пароль',
    auth_reset_sub: 'Установите новый пароль для аккаунта',
    auth_reset_btn: 'Сохранить пароль',
    auth_err_try_reset: 'Аккаунт существует — сбросьте пароль или введите вручную (не autofill).',
    auth_reset_ok: 'Пароль обновлён',
    auth_err_generic: 'Ошибка. Попробуйте снова.',
    auth_loading: 'Загрузка…',
    auth_submitting: 'Подождите…',
    auth_logout: 'Выйти',
  },
  en: {
    auth_login_title: 'Sign in',
    auth_login_sub: 'Sign in to continue with your leads',
    auth_register_title: 'Create account',
    auth_register_sub: 'Register to access the platform',
    auth_email: 'Email',
    auth_password: 'Password',
    auth_password_confirm: 'Confirm password',
    auth_password_hint: 'At least 8 characters',
    auth_name: 'Name',
    auth_sign_in: 'Sign in',
    auth_sign_up: 'Create account',
    auth_no_account: "Don't have an account?",
    auth_register_link: 'Register',
    auth_have_account: 'Already have an account?',
    auth_login_link: 'Sign in',
    auth_err_password_mismatch: 'Passwords do not match',
    auth_err_email_taken: 'This email is already registered. Please sign in.',
    auth_err_invalid_credentials: 'Invalid email or password. Check your password or register again.',
    auth_err_autofill: 'Safari may autofill the wrong password — type manually or reset it.',
    auth_forgot: 'Forgot password?',
    auth_reset_title: 'New password',
    auth_reset_sub: 'Set a new password for your account',
    auth_reset_btn: 'Save password',
    auth_err_try_reset: 'Account exists — reset password or type it manually (not autofill).',
    auth_reset_ok: 'Password updated',
    auth_err_generic: 'Something went wrong. Try again.',
    auth_loading: 'Loading…',
    auth_submitting: 'Please wait…',
    auth_logout: 'Log out',
  },
};

function authLang() {
  return localStorage.getItem('lg_lang') || 'uk';
}

function authT(key) {
  const l = AUTH_I18N[authLang()] || AUTH_I18N.uk;
  return l[key] || AUTH_I18N.uk[key] || key;
}

function paintAuthI18n() {
  document.querySelectorAll('[data-i]').forEach((el) => {
    const k = el.getAttribute('data-i');
    if (AUTH_I18N.uk[k]) el.textContent = authT(k);
  });
}

function getToken() {
  return localStorage.getItem(LG_TOKEN_KEY) || '';
}

function setSession(token, user) {
  localStorage.setItem(LG_TOKEN_KEY, token);
  if (user) localStorage.setItem(LG_USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(LG_TOKEN_KEY);
  localStorage.removeItem(LG_USER_KEY);
}

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(LG_USER_KEY) || 'null');
  } catch (e) {
    return null;
  }
}

function authHeaders(extra) {
  const h = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
  const t = getToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

function authFetch(path, opts, cookieOnly) {
  const base = Object.assign({ credentials: 'same-origin' }, opts || {});
  if (cookieOnly) {
    base.headers = Object.assign({}, (opts && opts.headers) || {});
  } else {
    base.headers = authHeaders((opts && opts.headers) || {});
  }
  return fetch(path, base);
}

function finishAuth(data) {
  setSession(data.token, data.user);
  sessionStorage.removeItem('lg_auth_redirect');
  window.location.replace('/auth/callback?token=' + encodeURIComponent(data.token));
}

async function resumeSessionIfPossible() {
  try {
    const stCookie = await fetchAuthStatus(true);
    if (stCookie && stCookie.authenticated) {
      syncSessionFromStatus(stCookie);
      window.location.replace('/');
      return true;
    }
  } catch (e) { /* offline */ }

  const token = getToken();
  if (!token) return false;
  try {
    const st = await fetchAuthStatus();
    if (st && st.authenticated) {
      syncSessionFromStatus(st);
      window.location.replace('/');
      return true;
    }
    clearSession();
  } catch (e) { /* offline */ }
  return false;
}

function syncSessionFromStatus(st) {
  if (st && st.user) {
    localStorage.setItem(LG_USER_KEY, JSON.stringify(st.user));
  }
}

function showToast(msg, type) {
  let el = document.getElementById('lgToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'lgToast';
    el.className = 'lg-toast hidden';
    el.setAttribute('role', 'status');
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'lg-toast visible' + (type === 'error' ? ' lg-toast-error' : '');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove('visible'), 3200);
}

function mapAuthError(msg) {
  if (!msg || typeof msg !== 'string') return authT('auth_err_generic');
  const lower = msg.toLowerCase();
  if (lower.includes('already registered') || lower.includes('email already')) {
    return authT('auth_err_email_taken');
  }
  if (lower.includes('invalid email or password')) {
    return authT('auth_err_invalid_credentials');
  }
  if (lower.startsWith('http ')) return authT('auth_err_generic');
  return msg;
}

async function fetchAuthStatus(cookieOnly) {
  const r = await authFetch('/api/auth/status', null, cookieOnly);
  if (!r.ok) return null;
  return r.json();
}

async function apiJson(path, opts) {
  const timeoutMs = path.includes('/api/auth/') ? 90000 : 60000;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let r;
  try {
    r = await authFetch(path, Object.assign({}, opts, { signal: ctrl.signal }));
  } catch (e) {
    clearTimeout(timer);
    if (e && e.name === 'AbortError') {
      throw new Error(authT('auth_submitting'));
    }
    throw e;
  }
  clearTimeout(timer);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && !path.startsWith('/api/auth/')) {
    clearSession();
    if (!window.location.pathname.match(/^\/(login|register)/)) {
      window.location.href = '/login';
    }
    throw new Error(data.detail || 'Unauthorized');
  }
  if (!r.ok) {
    const msg = data.error || data.detail || `HTTP ${r.status}`;
    throw new Error(mapAuthError(typeof msg === 'string' ? msg : JSON.stringify(msg)));
  }
  return data;
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('visible');
}

function bindPasswordToggles(root) {
  (root || document).querySelectorAll('[data-pw-toggle]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = btn.parentElement && btn.parentElement.querySelector('input');
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? '🙈' : '👁';
    });
  });
}

async function hintRegistered(email) {
  try {
    const r = await fetch('/api/auth/email-hint?email=' + encodeURIComponent(email), { credentials: 'same-origin' });
    if (!r.ok) return false;
    const data = await r.json();
    return !!data.registered;
  } catch (e) {
    return false;
  }
}

async function initAuthPage(mode) {
  const boot = document.getElementById('authBoot');
  if (boot) boot.classList.add('hidden');
  paintAuthI18n();
  bindPasswordToggles(document);

  if (mode !== 'reset' && await resumeSessionIfPossible()) return;

  try {
    const st = await fetchAuthStatus();
    if (st && st.authenticated && mode !== 'reset') {
      syncSessionFromStatus(st);
      window.location.replace('/');
      return;
    }
  } catch (e) { /* offline */ }

  const params = new URLSearchParams(window.location.search);
  if (params.get('session') === 'expired') {
    showAuthError(authT('auth_err_invalid_credentials'));
  }

  const formId = mode === 'login' ? 'loginForm' : mode === 'reset' ? 'resetForm' : 'registerForm';
  const form = document.getElementById(formId);
  if (!form) return;

  const prefillEmail = params.get('email');
  if (prefillEmail && form.email) form.email.value = prefillEmail;

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const err = document.getElementById('authError');
    if (err) err.classList.remove('visible');

    const email = form.email.value.trim();
    const password = form.password.value;
    const submitBtn = form.querySelector('button[type="submit"]');
    const prevLabel = submitBtn ? submitBtn.textContent : '';
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = authT('auth_submitting');
    }

    try {
      if (mode === 'reset') {
        const password2 = form.password2.value;
        if (password !== password2) {
          showAuthError(authT('auth_err_password_mismatch'));
          return;
        }
        const data = await apiJson('/api/auth/reset-password', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        });
        finishAuth(data);
        return;
      }

      if (mode === 'register') {
        const password2 = form.password2.value;
        if (password !== password2) {
          showAuthError(authT('auth_err_password_mismatch'));
          return;
        }
        const data = await apiJson('/api/auth/register', {
          method: 'POST',
          body: JSON.stringify({
            email,
            password,
            name: (form.name && form.name.value.trim()) || '',
          }),
        });
        finishAuth(data);
        return;
      }

      const data = await apiJson('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      finishAuth(data);
    } catch (e) {
      const msg = e.message || authT('auth_err_generic');
      if (mode === 'login' && msg === authT('auth_err_invalid_credentials')) {
        const exists = await hintRegistered(email);
        showAuthError(exists ? authT('auth_err_try_reset') : msg);
        if (exists) {
          showToast(authT('auth_err_autofill'), 'error');
        }
      } else {
        showAuthError(msg);
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        const labelKey = mode === 'login' ? 'auth_sign_in' : mode === 'reset' ? 'auth_reset_btn' : 'auth_sign_up';
        submitBtn.textContent = prevLabel || authT(labelKey);
      }
    }
  });
}

async function guardDashboard() {
  try {
    let st = await fetchAuthStatus(true);
    if (!st || !st.authenticated) {
      st = await fetchAuthStatus();
    }
    if (!st || !st.authenticated) {
      clearSession();
      window.location.replace('/login');
      return st;
    }
    syncSessionFromStatus(st);
    const menu = document.getElementById('userMenu');
    const emailEl = document.getElementById('userEmail');
    const user = st.user || getStoredUser();
    if (menu && user) {
      menu.classList.remove('hidden');
      if (emailEl) emailEl.textContent = user.email || user.name || '';
    }
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
      logoutBtn.textContent = authT('auth_logout');
      logoutBtn.onclick = async () => {
        try {
          await apiJson('/api/auth/logout', { method: 'POST' });
        } catch (e) { /* ignore */ }
        clearSession();
        window.location.href = '/login';
      };
    }
    return st;
  } catch (e) {
    return null;
  }
}
