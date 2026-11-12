import streamlit as st

from config.settings import get_settings
from core.security.rbac import is_admin
from ui.components.auth import require_auth

st.set_page_config(page_title="Law by AI")

# Read the auth settings first, so a bad value fails at startup.
_settings = get_settings()
_ = (_settings.auth_cookie_key, _settings.auth_cookie_name, _settings.auth_cookie_expiry_days)


def _home() -> None:
    st.title("Law by AI")
    st.write(
        "AI-powered platform for legal document ingestion, processing, retrieval, and analysis."
    )


user = require_auth()
pages = [st.Page(_home, title="Home", default=True)]
if is_admin(user["role"]):
    pages.append(st.Page("pages/fetch.py", title="Fetch a document"))
st.navigation(pages).run()
