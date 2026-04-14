"""
Simple email+password auth with PostgreSQL.
"""
import hashlib
import os

import psycopg2
import streamlit as st

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    os.environ.get("DATABASE_PUBLIC_URL"),
)


def _get_db():
    if not DATABASE_URL:
        return None
    return psycopg2.connect(DATABASE_URL)


def init_auth_tables():
    conn = _get_db()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Add user_id to uploads if not exists
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='uploads' AND column_name='user_id'
            ) THEN
                ALTER TABLE uploads ADD COLUMN user_id INTEGER REFERENCES users(id);
            END IF;
        END $$;
    """)
    conn.commit()
    cur.close()
    conn.close()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(email: str, password: str, name: str = "") -> tuple[bool, str]:
    conn = _get_db()
    if not conn:
        return False, "No database"
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s) RETURNING id",
            (email.lower().strip(), _hash_password(password), name.strip()),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return True, str(user_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return False, "Email já cadastrado"
    except Exception as e:
        conn.close()
        return False, str(e)


def login_user(email: str, password: str) -> dict | None:
    conn = _get_db()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, name, created_at FROM users WHERE email = %s AND password_hash = %s",
        (email.lower().strip(), _hash_password(password)),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"id": row[0], "email": row[1], "name": row[2], "created_at": row[3]}
    return None


def get_current_user() -> dict | None:
    return st.session_state.get("auth_user")


def require_auth() -> dict | None:
    """Show login/register form if not authenticated. Returns user dict or None."""
    if "auth_user" in st.session_state and st.session_state.auth_user:
        return st.session_state.auth_user

    # Init tables on first run
    if "auth_tables_ok" not in st.session_state:
        init_auth_tables()
        st.session_state.auth_tables_ok = True

    st.markdown("""
    <style>
    .auth-container {
        max-width: 400px;
        margin: 60px auto;
        padding: 32px;
        background: #111526;
        border: 1px solid #1f2540;
        border-radius: 16px;
    }
    .auth-title {
        text-align: center;
        font-size: 24px;
        font-weight: 800;
        color: #FFD500;
        margin-bottom: 4px;
    }
    .auth-sub {
        text-align: center;
        font-size: 13px;
        color: #a8b2d1;
        margin-bottom: 24px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="auth-title">LATAMSELLERS</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-sub">Finance Platform</div>', unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["Entrar / Войти", "Cadastrar / Регистрация"])

    with tab_login:
        email = st.text_input("Email", key="login_email", placeholder="seu@email.com")
        password = st.text_input("Senha / Пароль", type="password", key="login_pass")
        if st.button("Entrar / Войти", key="login_btn", type="primary", use_container_width=True):
            if not email or not password:
                st.error("Preencha todos os campos")
            else:
                user = login_user(email, password)
                if user:
                    st.session_state.auth_user = user
                    st.rerun()
                else:
                    st.error("Email ou senha incorretos / Неверный email или пароль")

    with tab_register:
        reg_name = st.text_input("Nome / Имя", key="reg_name", placeholder="Seu nome")
        reg_email = st.text_input("Email", key="reg_email", placeholder="seu@email.com")
        reg_pass = st.text_input("Senha / Пароль", type="password", key="reg_pass")
        reg_pass2 = st.text_input("Confirmar senha / Повторите", type="password", key="reg_pass2")
        if st.button("Cadastrar / Зарегистрироваться", key="reg_btn", type="primary", use_container_width=True):
            if not reg_email or not reg_pass:
                st.error("Preencha todos os campos")
            elif reg_pass != reg_pass2:
                st.error("Senhas não coincidem / Пароли не совпадают")
            elif len(reg_pass) < 4:
                st.error("Senha muito curta (mín. 4 caracteres)")
            else:
                ok, msg = register_user(reg_email, reg_pass, reg_name)
                if ok:
                    st.success("✅ Conta criada! Faça login. / Аккаунт создан!")
                else:
                    st.error(msg)

    return None
