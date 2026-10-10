"""Lightweight entrypoint: no lexicon, matcher, or full dataset initialization."""
import streamlit as st
from src.outputs.sqlite_ui import render_sqlite_preview

st.set_page_config(page_title="技能明細查核", layout="wide")
render_sqlite_preview()
