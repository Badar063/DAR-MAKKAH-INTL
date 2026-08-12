import os
import re
import sqlite3
import unicodedata
from pathlib import Path

import streamlit as st
from rapidfuzz import fuzz

# ============================================================
# CONFIGURATION & CONSTANTS
# ============================================================

APP_TITLE = "Dar Makkah International"
APP_SUBTITLE = "Library Catalog Search System"
DATABASE_FILE = Path("library.db")
LOGO_PATH = "a.jpg"  # Stored directly in root repository as requested

# ============================================================
# STREAMLIT PAGE CONFIG & CUSTOM ORANGE/WHITE STYLING
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Professional Orange & White Modern Theme CSS
st.markdown(
    """
    <style>
    /* Global Page Background & Fonts */
    .main {
        background-color: #FAFAFA;
        color: #212121;
    }
    
    /* Custom Header Banner */
    .header-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(135deg, #FF6600 0%, #E65100 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(255, 102, 0, 0.2);
    }
    
    .header-text h1 {
        color: white !important;
        font-size: 2.3rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    .header-text p {
        color: #FFE0B2 !important;
        font-size: 1.1rem !important;
        margin-top: 5px !important;
    }

    .header-logo img {
        max-height: 80px;
        border-radius: 8px;
        background-color: white;
        padding: 5px;
    }

    /* Cards & Container Styling */
    .book-card {
        background-color: #FFFFFF;
        border: 1px solid #FFE0B2;
        border-left: 5px solid #FF6600;
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .book-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(255, 102, 0, 0.15);
    }

    .book-title {
        color: #D84315;
        font-size: 1.35rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }

    .book-badge {
        background-color: #FFF3E0;
        color: #E65100;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.5rem;
    }

    /* Input Styling */
    .stTextInput > div > div > input {
        border: 2px solid #FFE0B2;
        border-radius: 8px;
        padding: 10px;
        font-size: 1rem;
    }

    .stTextInput > div > div > input:focus {
        border-color: #FF6600;
        box-shadow: 0 0 5px rgba(255, 102, 0, 0.4);
    }

    /* Hide Streamlit Boilerplate */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_scope=True,
)


# ============================================================
# DATABASE SETUP & CONNECTION
# ============================================================

def get_connection():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def check_database():
    """Verify library.db exists and contains the books table."""
    if not DATABASE_FILE.exists():
        st.error(f"Database file `{DATABASE_FILE}` was not found. Please ensure `library.db` is in the application directory.")
        st.stop()


check_database()

# ============================================================
# TEXT NORMALIZATION HELPERS
# ============================================================

ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
ARABIC_TRANSLATION = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ـ": "",
    "ﻻ": "لا", "ﻷ": "لا", "ﻹ": "لا", "ﻵ": "لا",
})


def remove_latin_accents(text):
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip()
    text = remove_latin_accents(text)
    text = ARABIC_DIACRITICS.sub("", text)
    text = text.translate(ARABIC_TRANSLATION)
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^\w\u0600-\u06FF]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split()).strip()


def compact_text(text):
    normalized = normalize_text(text)
    return re.sub(r"[\s_-]+", "", normalized)


def tokenize(text):
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


# ============================================================
# SEARCH & MATCHING ALGORITHMS
# ============================================================

def fuzzy_field_score(query, field):
    if not field:
        return 0.0
    q = normalize_text(query)
    f = normalize_text(field)
    if not q or not f:
        return 0.0
    if q == f:
        return 100.0
    if q in f:
        return 98.0

    qc, fc = compact_text(query), compact_text(field)
    if qc and qc in fc:
        return 97.0

    query_tokens, field_tokens = tokenize(query), tokenize(field)
    best_word_score = 0.0
    for qt in query_tokens:
        for ft in field_tokens:
            best_word_score = max(best_word_score, fuzz.ratio(qt, ft))

    whole_scores = [
        fuzz.ratio(q, f),
        fuzz.partial_ratio(q, f),
        fuzz.token_set_ratio(q, f),
        fuzz.WRatio(q, f),
    ]
    return float(max([best_word_score] + whole_scores))


def multi_field_lexical_score(query, title, author, publisher):
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    per_token = [
        max(
            fuzzy_field_score(t, title),
            fuzzy_field_score(t, author) * 0.92,
            fuzzy_field_score(t, publisher) * 0.90,
        )
        for t in query_tokens
    ]
    return float(sum(per_token) / len(per_token)) if per_token else 0.0


def search_books(query):
    query = query.strip()
    if not query:
        return []

    connection = get_connection()
    rows = connection.execute("SELECT * FROM books").fetchall()
    connection.close()

    if not rows:
        return []

    normalized_query = normalize_text(query)

    # Priority 1: Exact Match Evaluation
    exact_title_rows = [
        row for row in rows if normalize_text(row["title"] or "") == normalized_query
    ]

    if exact_title_rows:
        exact_results = []
        for row in exact_title_rows:
            exact_results.append({
                "id": row["id"],
                "shelf": row["shelf"],
                "title": row["title"] or "",
                "author": row["author"] or "",
                "publisher": row["publisher"] or "",
                "language": row["language"] or "",
                "position": row["position"],
                "image": row["image"],
                "score": 100.0,
                "reason": "Exact Title Match",
            })
        exact_results.sort(key=lambda x: (x["shelf"], x["position"] if x["position"] is not None else 999999))
        return exact_results

    # Priority 2: Multi-field Fuzzy Search
    results = []
    for row in rows:
        t, a, p = row["title"] or "", row["author"] or "", row["publisher"] or ""
        
        t_score = fuzzy_field_score(query, t)
        a_score = fuzzy_field_score(query, a)
        p_score = fuzzy_field_score(query, p)
        m_score = multi_field_lexical_score(query, t, a, p)

        lexical_score = max(t_score, a_score * 0.94, p_score * 0.92, m_score)

        if lexical_score >= 60.0:  # Match Threshold
            results.append({
                "id": row["id"],
                "shelf": row["shelf"],
                "title": t,
                "author": a,
                "publisher": p,
                "language": row["language"] or "",
                "position": row["position"],
                "image": row["image"],
                "score": round(lexical_score, 1),
                "reason": "Relevance Match",
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ============================================================
# USER INTERFACE LAYOUT
# ============================================================

# Title Banner with Image Logo
col_title, col_logo = st.columns([4, 1])

with col_title:
    st.markdown(
        f"""
        <div class="header-container">
            <div class="header-text">
                <h1>{APP_TITLE}</h1>
                <p>{APP_SUBTITLE}</p>
            </div>
        </div>
        """,
        unsafe_allow_scope=True,
    )

with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, use_container_width=True)

# Search Controls
search_query = st.text_input(
    "🔎 Search Catalog",
    placeholder="Enter book title, author, or publisher (e.g., 'Khushu', 'IIPH')...",
)

if search_query:
    results = search_books(search_query)

    if results:
        st.markdown(f"### Found {len(results)} Matching Record(s)")

        for book in results:
            # Main card layout
            st.markdown(
                f"""
                <div class="book-card">
                    <div class="book-title">{book['title']}</div>
                    <div>
                        <span class="book-badge">📍 Shelf: {book['shelf']}</span>
                        {'<span class="book-badge">Position: ' + str(book['position']) + '</span>' if book['position'] else ''}
                        {'<span class="book-badge">Lang: ' + book['language'] + '</span>' if book['language'] else ''}
                    </div>
                </div>
                """,
                unsafe_allow_scope=True,
            )

            # Metadata details grid
            meta_col1, meta_col2, meta_col3 = st.columns([1, 1, 1])

            with meta_col1:
                if book["author"]:
                    st.markdown(f"**Author:** {book['author']}")

            with meta_col2:
                if book["publisher"]:
                    st.markdown(f"**Publisher:** {book['publisher']}")

            with meta_col3:
                st.markdown(f"**Match Relevance:** {book['score']}%")

            # Image display only if the file exists and is valid
            if book["image"]:
                img_path = Path("shelves") / book["image"] if not Path(book["image"]).exists() else Path(book["image"])
                if img_path.exists():
                    with st.expander("📷 View Shelf Location Image"):
                        st.image(str(img_path), use_container_width=True)

            st.divider()

    else:
        st.warning("No matching books found in the library database. Try refining your search terms.")

else:
    # Default Dashboard View
    st.info("💡 Start typing in the search bar above to query books directly from the database.")
    
    conn = get_connection()
    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    total_shelves = conn.execute("SELECT COUNT(DISTINCT shelf) FROM books").fetchone()[0]
    conn.close()

    m1, m2 = st.columns(2)
    m1.metric("Total Books in Database", total_books)
    m2.metric("Total Shelves Indexed", total_shelves)
