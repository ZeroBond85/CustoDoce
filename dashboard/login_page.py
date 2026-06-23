import streamlit as st

from dashboard.components.ui import get_logo_branco_base64
from services.auth import (
    load_config,
    verify_password,
    create_token,
    verify_totp,
    get_totp_uri,
    generate_totp_secret,
    hash_password,
)
from services.rate_limiter import RateLimiter

_limiter = RateLimiter()

_LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

.cd-login-bg {
    background: linear-gradient(135deg, #FFF5EB 0%, #FDE8EF 50%, #EBF2FC 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}
.cd-login-card {
    background: #FFFFFF;
    border-radius: 20px;
    padding: 2.5rem 2rem;
    box-shadow: 0 20px 60px rgba(245,158,66,0.1), 0 8px 24px rgba(232,115,154,0.08);
    border: 1px solid rgba(245,158,66,0.1);
    max-width: 420px;
    width: 100%;
}
.cd-login-tagline {
    text-align: center;
    color: #8B7355;
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0.25rem 0 2rem;
    letter-spacing: 0.01em;
}
.cd-login-divider {
    border: none;
    border-top: 1px solid #F0E6DB;
    margin: 1.5rem 0;
}
.cd-login-error {
    background: #FEF2F2;
    border: 1px solid #FECACA;
    color: #991B1B;
    padding: 0.75rem 1rem;
    border-radius: 10px;
    font-size: 0.85rem;
    margin: 1rem 0;
    font-weight: 600;
}
.cd-login-hint {
    font-size: 0.75rem;
    color: #8B7355;
    margin-top: 0.25rem;
    font-weight: 600;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #F59E42, #E8739A) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-family: 'Nunito', sans-serif !important;
    letter-spacing: 0.02em;
    transition: transform 0.15s, box-shadow 0.15s !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(245,158,66,0.3) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
}
div[data-testid="stTabs"] > div > div > div > div {
    padding-top: 0;
}
</style>
"""


def render_login():
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    _left, _center, _right = st.columns([1, 2.5, 1])

    with _center:
        _logo_b64 = get_logo_branco_base64()
        if _logo_b64:
            st.markdown(
                f'<div style="text-align:center;margin-bottom:0.5rem">'
                f'<img src="data:image/png;base64,{_logo_b64}" '
                f'style="width:200px" alt="CustoDoce"></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<p class="cd-login-tagline">Seu doce com o melhor custo</p>',
            unsafe_allow_html=True,
        )

        config = load_config()

        ip = "login"
        if _limiter.is_limited(ip):
            wait = _limiter.retry_after(ip)
            st.markdown(
                f'<div class="cd-login-error">'
                f"Muitas tentativas. Tente novamente em {wait}s."
                f"</div>",
                unsafe_allow_html=True,
            )
            return False

        username = st.text_input(
            "Usuario",
            placeholder="admin",
            key="login_user",
            label_visibility="collapsed",
        )
        password = st.text_input(
            "Senha",
            type="password",
            placeholder="Sua senha",
            key="login_pass",
            label_visibility="collapsed",
        )

        totp_code = ""
        totp_needed = False
        if config.totp_enabled and config.totp_secret:
            totp_needed = True
            totp_code = st.text_input(
                "Codigo 2FA",
                placeholder="000000",
                max_chars=6,
                key="login_totp",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="cd-login-hint">'
                "Abra seu app autenticador (Google Authenticator, Authy, etc.)"
                "</p>",
                unsafe_allow_html=True,
            )

        c1, c2 = st.columns(2)
        with c1:
            submitted = st.button(
                "Entrar", type="primary", width='stretch'
            )
        with c2:
            if st.button("Limpar", width='stretch'):
                for k in ["login_user", "login_pass", "login_totp"]:
                    st.session_state.pop(k, None)
                st.rerun()

        if submitted:
            if not username or not password:
                st.markdown(
                    '<div class="cd-login-error">'
                    "Preencha usuario e senha."
                    "</div>",
                    unsafe_allow_html=True,
                )
                return False

            import os as _os
            import hmac as _hmac

            pw_plain = _os.environ.get("ADMIN_PASSWORD", "")
            stored_hash = config.admin_password_hash

            valid = _hmac.compare_digest(password, pw_plain) if pw_plain else verify_password(password, stored_hash)

            if not valid:
                _limiter.record_attempt(ip)
                remaining = _limiter.remaining_attempts(ip)
                st.markdown(
                    '<div class="cd-login-error">'
                    f"Senha incorreta. {remaining} tentativa(s) restante(s)."
                    "</div>",
                    unsafe_allow_html=True,
                )
                return False

            if totp_needed and (not totp_code or not verify_totp(config.totp_secret, totp_code)):
                    _limiter.record_attempt(ip)
                    st.markdown(
                        '<div class="cd-login-error">'
                        "Codigo 2FA invalido."
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    return False

            _limiter.clear_attempts(ip)
            token = create_token(username, config.secret_key)
            st.session_state.authenticated = True
            st.session_state.token = token
            st.session_state.user = username
            st.rerun()

    return False


def render_setup_first_user():
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    _left, _center, _right = st.columns([1, 2.5, 1])

    with _center:
        _logo_b64 = get_logo_branco_base64()
        if _logo_b64:
            st.markdown(
                f'<div style="text-align:center;margin-bottom:0.5rem">'
                f'<img src="data:image/png;base64,{_logo_b64}" '
                f'style="width:200px" alt="CustoDoce"></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<p class="cd-login-tagline">Configure sua conta de administrador</p>',
            unsafe_allow_html=True,
        )

        new_pass = st.text_input(
            "Nova senha",
            type="password",
            placeholder="Minimo 8 caracteres",
            key="setup_pass",
            label_visibility="collapsed",
        )
        confirm_pass = st.text_input(
            "Confirmar senha",
            type="password",
            placeholder="Repita a senha",
            key="setup_confirm",
            label_visibility="collapsed",
        )

        enable_totp = st.checkbox(
            "Ativar 2FA (TOTP)", value=False, key="setup_totp"
        )

        totp_secret = ""  # nosec B105 - inicializacao de string, nao senha
        if enable_totp:
            if "setup_totp_secret" not in st.session_state:
                st.session_state.setup_totp_secret = generate_totp_secret()
            totp_secret = st.session_state.setup_totp_secret
            uri = get_totp_uri(totp_secret)
            st.info(
                "Escaneie o QR code abaixo com seu app autenticador "
                "(Google Authenticator, Authy, etc.)"
            )
            st.code(uri, language="text")
            st.markdown(
                f'<p class="cd-login-hint">'
                f"Ou digite manualmente: <strong>{totp_secret}</strong></p>",
                unsafe_allow_html=True,
            )
            totp_test = st.text_input(
                "Digite o codigo do app para confirmar",
                max_chars=6,
                placeholder="000000",
                key="setup_totp_test",
                label_visibility="collapsed",
            )
            if totp_test and len(totp_test) == 6:
                from services.auth import verify_totp as _vt

                if not _vt(totp_secret, totp_test):
                    st.error("Codigo invalido. Verifique o app autenticador.")

        if st.button(
            "Salvar Configuracao", type="primary", width='stretch'
        ):
            if not new_pass or len(new_pass) < 8:
                st.error("A senha deve ter no minimo 8 caracteres.")
                return
            if new_pass != confirm_pass:
                st.error("As senhas nao conferem.")
                return

            pw_hash = hash_password(new_pass)
            st.session_state["_setup_pw_hash"] = pw_hash
            st.session_state["_setup_totp_secret"] = (
                totp_secret if enable_totp else ""
            )
            st.session_state["_setup_totp_enabled"] = (
                "1" if enable_totp else ""
            )

            sug = (
                f"export ADMIN_PASSWORD_HASH='{pw_hash}'\n"
                f"export TOTP_SECRET='{totp_secret}'\n"
                f"export TOTP_ENABLED={'1' if enable_totp else ''}"
            )
            st.success(
                "Configuracao gerada! Adicione ao ambiente ou ao Streamlit Cloud Secrets:"
            )
            st.code(sug, language="bash")
            st.info("Apos configurar as secrets, reinicie o app.")
