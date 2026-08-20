"""Central configuration: environment variables first (.env locally),
Streamlit secrets as a fallback when deployed on Streamlit Community Cloud.

Cloud secrets are usually exported as environment variables too, but reading
st.secrets directly makes deployment work regardless of how the platform
injects them.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:  # only available (and populated) inside a Streamlit app
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default
