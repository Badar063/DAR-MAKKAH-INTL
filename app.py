import os
import re
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

# Search tuning
MIN_SEARCH_LENGTH = 2
TITLE_CONTAINS_BONUS = 25.0
EXACT_TITLE_SCORE = 100.0
EXACT_PHRASE_SCORE = 98.0
WORD_MATCH_THRESHOLD = 82.0
DEFAULT_MIN_SCORE = 70.0
SHORT_QUERY_MIN_SCORE = 82.0

# Maximum results shown
MAX_RESULTS = 50


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# ORIGINAL DARK THEME
# ============================================================

st.markdown(
    """
    <style>

    /* Global Page Background & Fonts */
    .stApp {
        background-color: #0E0E10 !important;
        color: #FFFFFF !important;
    }

    /* Centered Header Section */
    .header-container {
        text-align: center;
        padding: 1rem 0 2rem 0;
        margin-bottom: 2rem;
        border-bottom: 2px solid #FF6600;
    }

    .logo-img {
        max-height: 120px;
        margin-bottom: 1rem;
        border-radius: 8px;
    }

    .main-heading {
        color: #A855F7 !important;
        font-size: 2.5rem !important;
        font-weight: 800 !important;
        margin: 0.5rem 0 0.2rem 0 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .sub-heading {
        color: #FF6600 !important;
        font-size: 1.2rem !important;
        font-weight: 500 !important;
        margin: 0 !important;
    }

    /* Cards */
    .book-card {
        background-color: #18181B;
        border: 1px solid #3F3F46;
        border-left: 5px solid #FF6600;
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    }

    .book-title {
        color: #A855F7 !important;
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }

    .book-badge {
        background-color: #FF6600;
        color: #FFFFFF !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.5rem;
        margin-right: 0.4rem;
    }

    /* Search Input */
    .stTextInput > div > div > input {
        background-color: #18181B !important;
        color: #FFFFFF !important;
        border: 2px solid #FF6600 !important;
        border-radius: 8px !important;
        padding: 12px !important;
        font-size: 1rem !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #A855F7 !important;
        box-shadow: 0 0 8px rgba(168, 85, 247, 0.5) !important;
    }

    /* Labels */
    label {
        color: #FFFFFF !important;
    }

    /* Metrics */
    [data-testid="stMetric"] {
        background-color: #18181B;
        border: 1px solid #3F3F46;
        border-radius: 10px;
        padding: 15px;
    }

    [data-testid="stMetricLabel"] {
        color: #FFFFFF !important;
    }

    [data-testid="stMetricValue"] {
        color: #A855F7 !important;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        background-color: #18181B;
        border: 1px solid #3F3F46;
    }

    /* Hide Streamlit Boilerplate */
    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    """
    Creates a SQLite connection.

    row_factory is deliberately NOT returned from cached functions.
    This avoids Streamlit's UnserializableReturnValueError.
    """
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def check_database():
    """Verify the database exists and contains a books table."""

    if not DATABASE_FILE.exists():
        st.error(
            f"Database file `{DATABASE_FILE}` was not found. "
            "Please make sure `library.db` is in the application directory."
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

    except Exception as exc:
        st.error(f"Unable to open the library database: {exc}")
        st.stop()


check_database()


# ============================================================
# DATABASE LOADING
# ============================================================

@st.cache_data(show_spinner=False)
def load_books(database_mtime: float) -> list[dict[str, Any]]:
    """
    Load books into plain Python dictionaries.

    IMPORTANT:
    We deliberately return list[dict] rather than sqlite3.Row objects.
    sqlite3.Row objects can cause Streamlit's
    UnserializableReturnValueError.
    """

    del database_mtime

    connection = get_connection()

    try:
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

        books: list[dict[str, Any]] = []

        for row in rows:
            books.append(
                {
                    "id": row["id"],
                    "shelf": row["shelf"] or "",
                    "title": row["title"] or "",
                    "author": row["author"] or "",
                    "publisher": row["publisher"] or "",
                    "language": row["language"] or "",
                    "position": row["position"],
                    "image": row["image"] or "",
                }
            )

        return books

    finally:
        connection.close()


def get_books() -> list[dict[str, Any]]:
    """Load books and automatically refresh cache when DB changes."""

    try:
        database_mtime = DATABASE_FILE.stat().st_mtime
    except OSError:
        database_mtime = 0.0

    return load_books(database_mtime)


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


def remove_latin_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_text(text: Any) -> str:
    if text is None:
        return ""

    text = str(text).strip()

    if not text:
        return ""

    text = remove_latin_accents(text)

    text = ARABIC_DIACRITICS.sub("", text)

    text = text.translate(ARABIC_TRANSLATION)

    text = text.lower()

    text = (
        text.replace("’", "'")
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


def compact_text(text: Any) -> str:
    normalized = normalize_text(text)

    return re.sub(
        r"[\s_\-]+",
        "",
        normalized,
    )


def tokenize(text: Any) -> list[str]:
    normalized = normalize_text(text)

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# SEARCH HELPERS
# ============================================================

def exact_word_match(query: str, field: str) -> bool:
    """
    Checks whether query exists as a complete word.

    Example:

    prayer -> prayer = True
    prayer -> prayers = False

    This is important because it prevents random fuzzy matches.
    """

    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return False

    words = set(tokenize(f))

    return q in words


def phrase_exists(query: str, field: str) -> bool:
    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return False

    return q in f


def fuzzy_field_score(query: str, field: str) -> float:
    """
    Calculates fuzzy similarity, but does NOT blindly treat
    partial matches as strong matches.
    """

    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return 0.0

    if q == f:
        return 100.0

    # Exact phrase inside field.
    if phrase_exists(q, f):
        return 97.0

    # Exact complete word.
    if exact_word_match(q, f):
        return 96.0

    qc = compact_text(q)
    fc = compact_text(f)

    if qc and qc == fc:
        return 100.0

    if qc and len(qc) >= 4 and qc in fc:
        return 92.0

    query_tokens = tokenize(q)
    field_tokens = tokenize(f)

    if not query_tokens or not field_tokens:
        return 0.0

    best_word_score = 0.0

    for query_word in query_tokens:
        for field_word in field_tokens:

            # Avoid making tiny words produce huge scores.
            if len(query_word) <= 2:
                if query_word == field_word:
                    best_word_score = max(
                        best_word_score,
                        100.0,
                    )
                continue

            score = fuzz.ratio(
                query_word,
                field_word,
            )

            best_word_score = max(
                best_word_score,
                score,
            )

    whole_scores = [
        fuzz.ratio(q, f),
        fuzz.token_set_ratio(q, f),
        fuzz.WRatio(q, f),
    ]

    return float(
        max(
            [best_word_score] + whole_scores
        )
    )


def title_score(query: str, title: str) -> float:
    """
    Special title scoring.

    Titles receive much stronger preference than author/publisher.
    """

    q = normalize_text(query)
    t = normalize_text(title)

    if not q or not t:
        return 0.0

    # Exact title
    if q == t:
        return 100.0

    # Query is a complete word in title.
    if exact_word_match(q, t):
        return 99.0

    # Query phrase exists in title.
    if phrase_exists(q, t):
        return 98.0

    query_tokens = tokenize(q)
    title_tokens = tokenize(t)

    if not query_tokens or not title_tokens:
        return 0.0

    # Score every query token against title words.
    token_scores = []

    for query_token in query_tokens:

        best = 0.0

        for title_token in title_tokens:

            if query_token == title_token:
                best = 100.0
                break

            if len(query_token) >= 3:

                score = fuzz.ratio(
                    query_token,
                    title_token,
                )

                best = max(best, score)

        token_scores.append(best)

    if not token_scores:
        return 0.0

    average_token_score = sum(token_scores) / len(token_scores)

    whole_score = fuzz.token_set_ratio(
        q,
        t,
    )

    return float(
        max(
            average_token_score,
            whole_score,
        )
    )


def author_score(query: str, author: str) -> float:
    if not author:
        return 0.0

    return fuzzy_field_score(
        query,
        author,
    )


def publisher_score(query: str, publisher: str) -> float:
    if not publisher:
        return 0.0

    return fuzzy_field_score(
        query,
        publisher,
    )


# ============================================================
# PROFESSIONAL SEARCH ENGINE
# ============================================================

def score_book(
    query: str,
    book: dict[str, Any],
) -> tuple[float, str]:
    """
    Calculate relevance.

    The most important rule:

    TITLE > AUTHOR > PUBLISHER

    Therefore searching "prayer" will primarily return books
    whose title actually contains prayer.

    Completely unrelated books will no longer appear merely
    because one word happens to have a fuzzy similarity.
    """

    normalized_query = normalize_text(query)

    title = book.get("title", "")
    author = book.get("author", "")
    publisher = book.get("publisher", "")

    title_normalized = normalize_text(title)

    # --------------------------------------------------------
    # Exact title
    # --------------------------------------------------------

    if normalized_query == title_normalized:
        return EXACT_TITLE_SCORE, "Exact Title Match"

    # --------------------------------------------------------
    # Exact phrase in title
    # --------------------------------------------------------

    if phrase_exists(
        normalized_query,
        title_normalized,
    ):
        return EXACT_PHRASE_SCORE, "Title Contains Search"

    # --------------------------------------------------------
    # Exact complete word in title
    # --------------------------------------------------------

    if exact_word_match(
        normalized_query,
        title_normalized,
    ):
        return 96.0, "Title Word Match"

    # --------------------------------------------------------
    # Individual scores
    # --------------------------------------------------------

    t_score = title_score(
        normalized_query,
        title,
    )

    a_score = author_score(
        normalized_query,
        author,
    )

    p_score = publisher_score(
        normalized_query,
        publisher,
    )

    query_tokens = tokenize(normalized_query)

    # --------------------------------------------------------
    # Strong title token matching
    # --------------------------------------------------------

    title_tokens = tokenize(title)

    matched_title_tokens = 0

    for query_token in query_tokens:

        if len(query_token) < 3:
            continue

        best_token = 0.0

        for title_token in title_tokens:

            best_token = max(
                best_token,
                fuzz.ratio(
                    query_token,
                    title_token,
                ),
            )

        if best_token >= WORD_MATCH_THRESHOLD:
            matched_title_tokens += 1

    title_token_coverage = 0.0

    if query_tokens:
        title_token_coverage = (
            matched_title_tokens
            / len(query_tokens)
        )

    # --------------------------------------------------------
    # Strong scoring hierarchy
    # --------------------------------------------------------

    score = max(
        t_score,
        a_score * 0.72,
        p_score * 0.55,
    )

    # If query words are genuinely represented in title,
    # increase confidence.
    if title_token_coverage > 0:
        score = max(
            score,
            72.0 + (
                title_token_coverage * 25.0
            ),
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # Prevent unrelated author/publisher matches from
    # appearing when title has nothing to do with query.
    # --------------------------------------------------------

    title_has_real_match = (
        phrase_exists(
            normalized_query,
            title_normalized,
        )
        or title_token_coverage >= 0.5
        or t_score >= 82.0
    )

    if not title_has_real_match:

        # Author can still be a valid search.
        if a_score >= 90.0:
            score = max(
                score,
                min(a_score, 92.0),
            )
            reason = "Author Match"

        # Publisher match should be stricter.
        elif p_score >= 92.0:
            score = max(
                score,
                min(p_score, 88.0),
            )
            reason = "Publisher Match"

        else:
            # This is where unrelated books such as
            # "The Art of Trade" get removed.
            score = min(
                score,
                58.0,
            )
            reason = "Weak Match"

    else:
        if t_score >= 95:
            reason = "Strong Title Match"

        elif t_score >= 82:
            reason = "Title Relevance Match"

        else:
            reason = "Relevance Match"

    return round(score, 1), reason


def search_books(
    query: str,
    books: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Main search function.
    """

    query = query.strip()

    if len(query) < MIN_SEARCH_LENGTH:
        return []

    normalized_query = normalize_text(query)

    if not normalized_query:
        return []

    results = []

    for book in books:

        score, reason = score_book(
            normalized_query,
            book,
        )

        # Strong threshold.
        threshold = DEFAULT_MIN_SCORE

        # Short searches require even stronger evidence.
        if len(normalized_query) <= 3:
            threshold = SHORT_QUERY_MIN_SCORE

        if score < threshold:
            continue

        result = {
            **book,
            "score": score,
            "reason": reason,
        }

        results.append(result)

    # --------------------------------------------------------
    # Sort:
    #
    # 1. Highest relevance
    # 2. Title matches
    # 3. Shelf
    # 4. Position
    # --------------------------------------------------------

    def sort_key(book: dict[str, Any]):
        reason = book.get("reason", "")

        title_priority = {
            "Exact Title Match": 5,
            "Title Contains Search": 5,
            "Title Word Match": 4,
            "Strong Title Match": 3,
            "Title Relevance Match": 2,
            "Author Match": 1,
            "Publisher Match": 0,
            "Relevance Match": 0,
        }.get(reason, 0)

        position = book.get("position")

        try:
            position_value = int(position)
        except (TypeError, ValueError):
            position_value = 999999

        return (
            -book["score"],
            -title_priority,
            book.get("shelf", ""),
            position_value,
        )

    results.sort(
        key=sort_key,
    )

    return results[:MAX_RESULTS]


# ============================================================
# SHELF IMAGE RESOLUTION
# ============================================================

def resolve_image_path(image_value: Any) -> Path | None:
    """
    Safely locate shelf image.

    Supports:
        shelves/image.jpg
        image.jpg
        /absolute/path/image.jpg
    """

    if not image_value:
        return None

    image_value = str(image_value).strip()

    if not image_value:
        return None

    direct_path = Path(image_value)

    if direct_path.exists():
        return direct_path

    shelf_path = SHELVES_DIR / image_value

    if shelf_path.exists():
        return shelf_path

    return None


# ============================================================
# HEADER
# ============================================================

col_left, col_center, col_right = st.columns(
    [1, 2, 1]
)

with col_center:

    if LOGO_PATH.exists():
        st.image(
            str(LOGO_PATH),
            width=220,
        )

    st.markdown(
        f"""
        <div class="header-container">
            <div class="main-heading">
                {APP_TITLE}
            </div>

            <div class="sub-heading">
                {APP_SUBTITLE}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# LOAD DATABASE
# ============================================================

books = get_books()


# ============================================================
# SEARCH
# ============================================================

st.markdown(
    "Search by book title, author, publisher, or keyword."
)

search_query = st.text_input(
    "🔎 Search Catalog",
    placeholder="Type title, author, or publisher name...",
)


# ============================================================
# SEARCH RESULTS
# ============================================================

if search_query.strip():

    results = search_books(
        search_query,
        books,
    )

    if results:

        st.markdown(
            f"""
            <h3 style="color:#A855F7;">
                Found {len(results)} Matching Record(s)
            </h3>
            """,
            unsafe_allow_html=True,
        )

        # Search quality notice
        if len(results) == 1:
            st.caption(
                "Showing the strongest matching book."
            )
        else:
            st.caption(
                "Results are ranked by title relevance, "
                "then author and publisher relevance."
            )

        for book in results:

            # ------------------------------------------------
            # Book card
            # ------------------------------------------------

            st.markdown(
                f"""
                <div class="book-card">

                    <div class="book-title">
                        {book["title"] or "Untitled"}
                    </div>

                    <div>

                        <span class="book-badge">
                            📍 Shelf: {book["shelf"] or "Unknown"}
                        </span>

                        {
                            (
                                '<span class="book-badge">'
                                f'Position: {book["position"]}'
                                '</span>'
                            )
                            if book["position"] not in (None, "")
                            else ""
                        }

                        {
                            (
                                '<span class="book-badge">'
                                f'Lang: {book["language"]}'
                                '</span>'
                            )
                            if book["language"]
                            else ""
                        }

                    </div>

                </div>
                """,
                unsafe_allow_html=True,
            )

            # ------------------------------------------------
            # Metadata
            # ------------------------------------------------

            meta_col1, meta_col2, meta_col3 = st.columns(
                [1, 1, 1]
            )

            with meta_col1:

                if book["author"]:

                    st.markdown(
                        f"**Author:** {book['author']}"
                    )

            with meta_col2:

                if book["publisher"]:

                    st.markdown(
                        f"**Publisher:** {book['publisher']}"
                    )

            with meta_col3:

                st.markdown(
                    f"**Match Relevance:** "
                    f"{book['score']}%"
                )

                st.caption(
                    book["reason"]
                )

            # ------------------------------------------------
            # Shelf Image
            # ------------------------------------------------

            image_path = resolve_image_path(
                book.get("image")
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

        st.warning(
            f'No strong matches found for "{search_query}".'
        )

        st.caption(
            "Try a more specific title, author name, "
            "or another keyword."
        )


# ============================================================
# DEFAULT DASHBOARD
# ============================================================

else:

    st.info(
        "💡 Start typing in the search box to search "
        "the library catalog."
    )

    total_books = len(books)

    shelves = {
        book["shelf"]
        for book in books
        if book.get("shelf")
    }

    total_shelves = len(shelves)

    m1, m2 = st.columns(2)

    m1.metric(
        "Total Books in Database",
        total_books,
    )

    m2.metric(
        "Total Shelves Indexed",
        total_shelves,
    )


# ============================================================
# OPTIONAL DEBUG / DATABASE INFORMATION
# ============================================================

with st.expander("System Information"):

    st.write(
        f"**Database:** `{DATABASE_FILE}`"
    )

    st.write(
        f"**Books loaded:** {len(books)}"
    )

    st.write(
        f"**Shelves detected:** {len({b.get('shelf') for b in books if b.get('shelf')})}"
    )

    st.write(
        "**Search engine:** "
        "Title-priority fuzzy search"
    )

    st.write(
        "**Database cache:** "
        "Automatically refreshes when library.db changes"
    )
