import os
import re
import html
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import streamlit as st
from rapidfuzz import fuzz


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "Dar Makkah International"
APP_SUBTITLE = "Library Catalog Search System"

DATABASE_FILE = Path("library.db")
LOGO_PATH = Path("a.jpg")
SHELVES_DIR = Path("shelves")

MIN_TITLE_SCORE = 72.0
MIN_AUTHOR_SCORE = 78.0
MIN_PUBLISHER_SCORE = 82.0
MIN_GENERAL_SCORE = 72.0

MAX_RESULTS = 50


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# PROFESSIONAL DARK THEME
# ============================================================

st.html(
    """
    <style>

    /* ========================================================
       PROFESSIONAL COLOUR PALETTE
       ========================================================

       Background: Deep Navy
       Surface:     Slate Navy
       Accent:      Warm Gold
       Secondary:   Soft Blue
       Text:        White / Cool Gray

       Designed for a professional library / institutional
       catalog rather than a gaming or neon interface.
       ======================================================== */


    /* ========================================================
       GLOBAL
       ======================================================== */

    .stApp {
        background-color: #0B1220;
        color: #F8FAFC;
    }

    .main .block-container {
        max-width: 1250px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        background: transparent !important;
    }


    /* ========================================================
       HEADER
       ======================================================== */

    .library-header {
        text-align: center;
        padding: 1.2rem 0 1.8rem 0;
        margin-bottom: 1.8rem;

        border-bottom: 2px solid #C9A227;
    }

    .library-logo {
        width: 190px;
        max-height: 130px;
        object-fit: contain;
        border-radius: 10px;
        margin-bottom: 0.8rem;
    }

    .main-heading {
        color: #F8FAFC;
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: 1px;
        margin: 0;
        line-height: 1.2;
    }

    .sub-heading {
        color: #C9A227;
        font-size: 1.15rem;
        font-weight: 500;
        margin-top: 0.45rem;
    }


    /* ========================================================
       SEARCH
       ======================================================== */

    .search-label {
        color: #F8FAFC;
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 0.35rem;
    }

    .stTextInput > div > div > input {
        background-color: #111C2E !important;
        color: #F8FAFC !important;

        border: 1px solid #334155 !important;
        border-radius: 8px !important;

        padding: 12px !important;
        font-size: 1rem !important;

        transition:
            border-color 0.2s ease,
            box-shadow 0.2s ease;
    }

    .stTextInput > div > div > input:hover {
        border-color: #64748B !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #C9A227 !important;

        box-shadow:
            0 0 0 1px #C9A227,
            0 0 10px rgba(201, 162, 39, 0.18) !important;
    }

    .stTextInput label {
        color: #F8FAFC !important;
        font-weight: 600 !important;
    }


    /* ========================================================
       RESULT CARD
       ======================================================== */

    .book-card {
        background: #111C2E;

        border: 1px solid #26364D;
        border-left: 4px solid #C9A227;

        border-radius: 10px;

        padding: 1.25rem 1.35rem;
        margin: 0.8rem 0 0.25rem 0;

        box-shadow:
            0 5px 18px rgba(0, 0, 0, 0.22);

        transition:
            border-color 0.2s ease,
            box-shadow 0.2s ease;
    }

    .book-card:hover {
        border-color: #3B4F6A;

        box-shadow:
            0 7px 22px rgba(0, 0, 0, 0.30);
    }

    .book-title {
        color: #F1F5F9;

        font-size: 1.35rem;
        font-weight: 750;

        margin-bottom: 0.75rem;

        line-height: 1.35;
    }

    .book-badge {
        display: inline-block;

        background: #1E293B;
        color: #CBD5E1;

        padding: 5px 10px;
        margin: 0 5px 5px 0;

        border: 1px solid #334155;
        border-radius: 6px;

        font-size: 0.82rem;
        font-weight: 600;
    }

    .match-badge {
        display: inline-block;

        color: #FFFFFF;

        padding: 5px 10px;

        border-radius: 6px;

        font-size: 0.82rem;
        font-weight: 600;
    }

    /* Exact match - green */

    .match-exact {
        background: #166534;
    }

    /* Title match - blue */

    .match-title {
        background: #1D4ED8;
    }

    /* Author match - teal */

    .match-author {
        background: #0F766E;
    }

    /* Publisher match - muted gold */

    .match-publisher {
        background: #9A6F00;
    }

    /* General match - slate */

    .match-general {
        background: #475569;
    }


    /* ========================================================
       METADATA
       ======================================================== */

    .metadata-box {
        background: #0E1726;

        border: 1px solid #26364D;
        border-radius: 8px;

        padding: 0.9rem 1rem;
        margin-top: 0.4rem;
    }

    .metadata-label {
        color: #94A3B8;

        font-size: 0.8rem;
        font-weight: 600;

        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .metadata-value {
        color: #F8FAFC;

        font-size: 0.95rem;
        margin-top: 0.2rem;
    }


    /* ========================================================
       DASHBOARD METRICS
       ======================================================== */

    .dashboard-card {
        background: #111C2E;

        border: 1px solid #26364D;
        border-radius: 10px;

        padding: 1.1rem;
        text-align: center;

        min-height: 105px;

        box-shadow:
            0 4px 14px rgba(0, 0, 0, 0.18);
    }

    .dashboard-number {
        color: #C9A227;

        font-size: 2rem;
        font-weight: 800;
    }

    .dashboard-label {
        color: #94A3B8;

        font-size: 0.85rem;
        margin-top: 0.25rem;
    }


    /* ========================================================
       SECTION HEADINGS
       ======================================================== */

    .section-heading {
        color: #F1F5F9;

        font-size: 1.35rem;
        font-weight: 750;

        margin-top: 1.6rem;
        margin-bottom: 0.7rem;

        border-left: 3px solid #C9A227;
        padding-left: 0.7rem;
    }

    .section-description {
        color: #94A3B8;

        font-size: 0.92rem;
        margin-bottom: 1rem;
    }


    /* ========================================================
       SYSTEM INFORMATION
       ======================================================== */

    .system-card {
        background: #111C2E;

        border: 1px solid #26364D;
        border-radius: 10px;

        padding: 1rem 1.2rem;
        margin-top: 1.8rem;

        box-shadow:
            0 4px 14px rgba(0, 0, 0, 0.18);
    }

    .system-title {
        color: #C9A227;

        font-weight: 700;
        font-size: 1rem;

        margin-bottom: 0.6rem;
    }

    .system-row {
        display: flex;
        justify-content: space-between;

        border-bottom: 1px solid #26364D;

        padding: 0.45rem 0;

        font-size: 0.88rem;
    }

    .system-row:last-child {
        border-bottom: none;
    }

    .system-key {
        color: #94A3B8;
    }

    .system-value {
        color: #F8FAFC;
        font-weight: 600;
    }


    /* ========================================================
       EMPTY STATE
       ======================================================== */

    .empty-state {
        background: #111C2E;

        border: 1px solid #26364D;
        border-radius: 10px;

        padding: 2rem;

        text-align: center;

        margin-top: 1rem;
    }

    .empty-icon {
        font-size: 2rem;
    }

    .empty-title {
        color: #F1F5F9;

        font-size: 1.15rem;
        font-weight: 700;

        margin-top: 0.5rem;
    }

    .empty-text {
        color: #94A3B8;
        margin-top: 0.4rem;
    }


    /* ========================================================
       STREAMLIT DIVIDER
       ======================================================== */

    hr {
        border-color: #26364D !important;
    }


    /* ========================================================
       STREAMLIT ALERTS
       ======================================================== */

    [data-testid="stAlert"] {
        background-color: #111C2E !important;
        border: 1px solid #334155 !important;
        color: #CBD5E1 !important;
    }


    /* ========================================================
       EXPANDER
       ======================================================== */

    [data-testid="stExpander"] {
        background-color: #111C2E !important;
        border: 1px solid #26364D !important;
        border-radius: 8px !important;
    }

    [data-testid="stExpander"] summary {
        color: #CBD5E1 !important;
    }


    /* ========================================================
       METRICS / GENERAL STREAMLIT TEXT
       ======================================================== */

    [data-testid="stMetric"] {
        background-color: #111C2E;
        border: 1px solid #26364D;
        border-radius: 10px;
        padding: 1rem;
    }

    [data-testid="stMetricValue"] {
        color: #C9A227 !important;
    }

    [data-testid="stMetricLabel"] {
        color: #94A3B8 !important;
    }


    /* ========================================================
       SCROLLBAR
       ======================================================== */

    ::-webkit-scrollbar {
        width: 8px;
    }

    ::-webkit-scrollbar-track {
        background: #0B1220;
    }

    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #475569;
    }

    </style>
    """
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def check_database():
    if not DATABASE_FILE.exists():
        st.error(
            f"Database file `{DATABASE_FILE}` was not found. "
            "Please make sure `library.db` is in the application folder."
        )
        st.stop()

    try:
        connection = get_connection()

        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'books'
            """
        ).fetchone()

        connection.close()

        if table is None:
            st.error(
                "The database exists, but the `books` table was not found."
            )
            st.stop()

    except sqlite3.Error as exc:
        st.error(f"Unable to open the library database: {exc}")
        st.stop()


check_database()


# ============================================================
# LOAD DATABASE
#
# IMPORTANT:
# Return tuples, not sqlite3.Row objects.
# This keeps Streamlit cache serialization safe.
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def load_books():
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            shelf,
            title,
            author,
            publisher,
            language,
            position,
            image
        FROM books
        """
    ).fetchall()

    connection.close()

    return tuple(
        (
            row["id"],
            row["shelf"],
            row["title"] or "",
            row["author"] or "",
            row["publisher"] or "",
            row["language"] or "",
            row["position"],
            row["image"] or "",
        )
        for row in rows
    )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)

ARABIC_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ـ": "",
        "ﻻ": "لا",
        "ﻷ": "لا",
        "ﻹ": "لا",
        "ﻵ": "لا",
    }
)


def remove_latin_accents(text):
    normalized = unicodedata.normalize("NFKD", str(text))

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_text(text):
    if not text:
        return ""

    text = str(text).strip()

    text = remove_latin_accents(text)

    text = ARABIC_DIACRITICS.sub("", text)

    text = text.translate(ARABIC_TRANSLATION)

    text = text.lower()

    text = (
        text
        .replace("’", "'")
        .replace("‘", "'")
        .replace("–", "-")
        .replace("—", "-")
    )

    text = re.sub(
        r"[^\w\u0600-\u06FF]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    return " ".join(text.split()).strip()


def compact_text(text):
    return re.sub(
        r"[\s\-_]+",
        "",
        normalize_text(text),
    )


def tokenize(text):
    normalized = normalize_text(text)

    return normalized.split() if normalized else []


# ============================================================
# SEARCH HELPERS
# ============================================================

def exact_token_match(query, field):
    """
    Checks whether each search word occurs as a complete word
    in the target field.
    """

    query_tokens = tokenize(query)
    field_tokens = set(tokenize(field))

    if not query_tokens or not field_tokens:
        return False

    return all(token in field_tokens for token in query_tokens)


def phrase_contains(query, field):
    query_normalized = normalize_text(query)
    field_normalized = normalize_text(field)

    if not query_normalized or not field_normalized:
        return False

    return query_normalized in field_normalized


def fuzzy_field_score(query, field):
    if not field:
        return 0.0

    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return 0.0

    if q == f:
        return 100.0

    if phrase_contains(q, f):
        return 98.0

    if compact_text(q) in compact_text(f):
        return 97.0

    return float(
        max(
            fuzz.ratio(q, f),
            fuzz.partial_ratio(q, f),
            fuzz.token_set_ratio(q, f),
            fuzz.WRatio(q, f),
        )
    )


def field_match_type(query, title, author, publisher):
    """
    Determines WHY a book matched.

    This is intentionally strict so a search such as:

        prayer

    does not return unrelated books merely because
    one word happens to have a mediocre fuzzy score.
    """

    q = normalize_text(query)

    title_n = normalize_text(title)
    author_n = normalize_text(author)
    publisher_n = normalize_text(publisher)

    # --------------------------------------------------------
    # Exact title
    # --------------------------------------------------------

    if q and q == title_n:
        return "Exact Title Match", 100.0

    # --------------------------------------------------------
    # Title contains complete search phrase
    # --------------------------------------------------------

    if phrase_contains(q, title):
        return "Title Contains Search", 98.0

    # --------------------------------------------------------
    # Every query word appears in title
    # --------------------------------------------------------

    if exact_token_match(q, title):
        return "Title Keyword Match", 96.0

    # --------------------------------------------------------
    # Strong title fuzzy match
    # --------------------------------------------------------

    title_score = fuzzy_field_score(q, title)

    if title_score >= MIN_TITLE_SCORE:
        return "Strong Title Match", title_score

    # --------------------------------------------------------
    # Author
    # --------------------------------------------------------

    if phrase_contains(q, author):
        return "Author Match", 94.0

    if exact_token_match(q, author):
        return "Author Keyword Match", 92.0

    author_score = fuzzy_field_score(q, author)

    if author_score >= MIN_AUTHOR_SCORE:
        return "Author Match", author_score * 0.96

    # --------------------------------------------------------
    # Publisher
    # --------------------------------------------------------

    if phrase_contains(q, publisher):
        return "Publisher Match", 91.0

    if exact_token_match(q, publisher):
        return "Publisher Keyword Match", 89.0

    publisher_score = fuzzy_field_score(q, publisher)

    if publisher_score >= MIN_PUBLISHER_SCORE:
        return "Publisher Match", publisher_score * 0.94

    # --------------------------------------------------------
    # Multi-word title search
    # --------------------------------------------------------

    query_tokens = tokenize(q)
    title_tokens = tokenize(title)

    if len(query_tokens) >= 2 and title_tokens:

        token_scores = []

        for qt in query_tokens:
            best = max(
                fuzz.ratio(qt, tt)
                for tt in title_tokens
            )

            token_scores.append(best)

        average_score = sum(token_scores) / len(token_scores)

        if average_score >= 82:
            return "Title Keyword Match", average_score

    # --------------------------------------------------------
    # DO NOT RETURN RANDOM 60-70% MATCHES
    # --------------------------------------------------------

    return None, 0.0


# ============================================================
# SEARCH DATABASE
# ============================================================

def search_books(query, rows):
    query = query.strip()

    if not query:
        return []

    results = []

    for row in rows:

        (
            book_id,
            shelf,
            title,
            author,
            publisher,
            language,
            position,
            image,
        ) = row

        match_type, score = field_match_type(
            query,
            title,
            author,
            publisher,
        )

        if not match_type:
            continue

        results.append(
            {
                "id": book_id,
                "shelf": shelf or "",
                "title": title or "",
                "author": author or "",
                "publisher": publisher or "",
                "language": language or "",
                "position": position,
                "image": image or "",
                "score": round(score, 1),
                "reason": match_type,
            }
        )

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    reason_priority = {
        "Exact Title Match": 0,
        "Title Contains Search": 1,
        "Title Keyword Match": 2,
        "Strong Title Match": 3,
        "Author Match": 4,
        "Author Keyword Match": 5,
        "Publisher Match": 6,
        "Publisher Keyword Match": 7,
    }

    results.sort(
        key=lambda item: (
            reason_priority.get(item["reason"], 99),
            -item["score"],
            normalize_text(item["title"]),
        )
    )

    return results[:MAX_RESULTS]


# ============================================================
# HTML SAFETY
# ============================================================

def safe(value):
    return html.escape(str(value or ""))


# ============================================================
# SHELF IMAGE
# ============================================================

def get_shelf_image(image_value):
    if not image_value:
        return None

    image_path = Path(str(image_value))

    if image_path.exists():
        return image_path

    image_path = SHELVES_DIR / str(image_value)

    if image_path.exists():
        return image_path

    return None


# ============================================================
# HEADER
# ============================================================

logo_html = ""

if LOGO_PATH.exists():

    import base64

    try:
        image_bytes = LOGO_PATH.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("utf-8")

        logo_html = (
            '<img class="library-logo" '
            f'src="data:image/jpeg;base64,{encoded}" '
            'alt="Dar Makkah International">'
        )

    except Exception:
        logo_html = ""


st.html(
    f"""
    <div class="library-header">

        {logo_html}

        <div class="main-heading">
            {safe(APP_TITLE)}
        </div>

        <div class="sub-heading">
            {safe(APP_SUBTITLE)}
        </div>

    </div>
    """
)


# ============================================================
# LOAD BOOKS
# ============================================================

rows = load_books()


# ============================================================
# DATABASE STATISTICS
# ============================================================

total_books = len(rows)

total_shelves = len(
    {
        row[1]
        for row in rows
        if row[1]
    }
)


# ============================================================
# SEARCH
# ============================================================

st.markdown(
    "Search by book title, author, publisher, or keyword."
)

search_query = st.text_input(
    "🔎 Search Catalog",
    placeholder="Enter book name, author, publisher or keyword...",
    label_visibility="visible",
)


# ============================================================
# SEARCH RESULTS
# ============================================================

if search_query.strip():

    results = search_books(
        search_query,
        rows,
    )

    if results:

        st.html(
            f"""
            <div class="section-heading">
                Found {len(results)} Matching Record(s)
            </div>

            <div class="section-description">
                Results are ranked by the strongest title,
                author and publisher matches.
            </div>
            """
        )

        for book in results:

            title = safe(book["title"])
            shelf = safe(book["shelf"])
            author = safe(book["author"])
            publisher = safe(book["publisher"])
            language = safe(book["language"])
            position = safe(book["position"])
            score = safe(book["score"])
            reason = safe(book["reason"])

            if book["reason"] == "Exact Title Match":
                badge_class = "match-exact"

            elif "Title" in book["reason"]:
                badge_class = "match-title"

            elif "Author" in book["reason"]:
                badge_class = "match-author"

            elif "Publisher" in book["reason"]:
                badge_class = "match-publisher"

            else:
                badge_class = "match-general"

            position_html = ""

            if book["position"] not in (
                None,
                "",
            ):
                position_html = (
                    f'<span class="book-badge">'
                    f'Position: {position}'
                    f'</span>'
                )

            language_html = ""

            if book["language"]:
                language_html = (
                    f'<span class="book-badge">'
                    f'Lang: {language}'
                    f'</span>'
                )

            st.html(
                f"""
                <div class="book-card">

                    <div class="book-title">
                        {title}
                    </div>

                    <div>

                        <span class="book-badge">
                            📍 Shelf: {shelf}
                        </span>

                        {position_html}

                        {language_html}

                        <span class="match-badge {badge_class}">
                            {reason}
                        </span>

                    </div>

                </div>
                """
            )

            # ------------------------------------------------
            # Metadata
            # ------------------------------------------------

            meta1, meta2, meta3 = st.columns(
                [1, 1, 1]
            )

            with meta1:

                if book["author"]:

                    st.markdown(
                        f"**Author:** {book['author']}"
                    )

            with meta2:

                if book["publisher"]:

                    st.markdown(
                        f"**Publisher:** {book['publisher']}"
                    )

            with meta3:

                st.markdown(
                    f"**Match Relevance:** {book['score']}%"
                )

            # ------------------------------------------------
            # Shelf image
            # ------------------------------------------------

            image_path = get_shelf_image(
                book["image"]
            )

            if image_path:

                with st.expander(
                    "📷 View Shelf Location Image"
                ):
                    st.image(
                        str(image_path),
                        use_container_width=True,
                    )

            st.divider()

    else:

        st.html(
            """
            <div class="empty-state">

                <div class="empty-icon">
                    🔍
                </div>

                <div class="empty-title">
                    No matching books found
                </div>

                <div class="empty-text">
                    Try another title, author, publisher,
                    or a more specific keyword.
                </div>

            </div>
            """
        )


# ============================================================
# DEFAULT DASHBOARD
# ============================================================

else:

    st.info(
        "💡 Start typing in the search box to search "
        "the library catalog."
    )

    st.html(
        """
        <div class="section-heading">
            Library Overview
        </div>
        """
    )

    metric1, metric2 = st.columns(2)

    with metric1:

        st.html(
            f"""
            <div class="dashboard-card">

                <div class="dashboard-number">
                    {total_books}
                </div>

                <div class="dashboard-label">
                    Total Books in Database
                </div>

            </div>
            """
        )

    with metric2:

        st.html(
            f"""
            <div class="dashboard-card">

                <div class="dashboard-number">
                    {total_shelves}
                </div>

                <div class="dashboard-label">
                    Total Shelves Indexed
                </div>

            </div>
            """
        )


# ============================================================
# SYSTEM INFORMATION
# ============================================================

database_status = (
    "Connected"
    if DATABASE_FILE.exists()
    else "Unavailable"
)

logo_status = (
    "Available"
    if LOGO_PATH.exists()
    else "Not found"
)

shelf_status = (
    "Available"
    if SHELVES_DIR.exists()
    else "Not found"
)


st.html(
    f"""
    <div class="system-card">

        <div class="system-title">
            System Information
        </div>

        <div class="system-row">
            <span class="system-key">
                Database
            </span>

            <span class="system-value">
                {safe(database_status)}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Database File
            </span>

            <span class="system-value">
                {safe(DATABASE_FILE.name)}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Books Indexed
            </span>

            <span class="system-value">
                {total_books}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Shelves Indexed
            </span>

            <span class="system-value">
                {total_shelves}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Logo
            </span>

            <span class="system-value">
                {safe(logo_status)}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Shelf Images
            </span>

            <span class="system-value">
                {safe(shelf_status)}
            </span>
        </div>

        <div class="system-row">
            <span class="system-key">
                Search Engine
            </span>

            <span class="system-value">
                Exact + Token + Fuzzy Matching
            </span>
        </div>

    </div>
    """
)
