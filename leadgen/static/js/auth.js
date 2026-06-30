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
    auth_err_generic: 'Помилка. Спробуйте ще раз.',
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
    auth_err_generic: 'Ошибка. Попробуйте снова.',
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
    auth_err_generic: 'Something went wrong. Try again.',
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

async function apiJson(path, opts) {
  const r = await fetch(path, Object.assign({}, opts, {
    headers: authHeaders((opts && opts.headers) || {}),
  }));
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
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('visible');
}

async function initAuthPage(mode) {
  paintAuthI18n();
  try {
    const st = await fetch('/api/auth/status').then((r) => r.json());
    if (st.authenticated) {
      window.location.href = '/';
      return;
    }
    if (mode === 'login' && !st.auth_required && !st.has_users) {
      window.location.href = '/register';
      return;
    }
  } catch (e) { /* offline */ }

  const form = document.getElementById(mode === 'login' ? 'loginForm' : 'registerForm');
  if (!form) return;

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const err = document.getElementById('authError');
    if (err) err.classList.remove('visible');

    const email = form.email.value.trim();
    const password = form.password.value;

    if (mode === 'register') {
      const password2 = form.password2.value;
      if (password !== password2) {
        showAuthError(authT('auth_err_password_mismatch'));
        return;
      }
      try {
        const data = await apiJson('/api/auth/register', {
          method: 'POST',
          body: JSON.stringify({
            email,
            password,
            name: (form.name && form.name.value.trim()) || '',
          }),
        });
        setSession(data.token, data.user);
        window.location.href = '/';
      } catch (e) {
        showAuthError(e.message || authT('auth_err_generic'));
      }
      return;
    }

    try {
      const data = await apiJson('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setSession(data.token, data.user);
      window.location.href = '/';
    } catch (e) {
      showAuthError(e.message || authT('auth_err_generic'));
    }
  });
}

async function guardDashboard() {
  try {
    const st = await fetch('/api/auth/status', { headers: authHeaders() }).then((r) => r.json());
    if (!st.auth_required) return st;
    if (!st.authenticated) {
      window.location.href = st.has_users ? '/login' : '/register';
      return st;
    }
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
