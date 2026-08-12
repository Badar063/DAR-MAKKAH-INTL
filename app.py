
import os
import re
import sqlite3
import html
import unicodedata
from pathlib import Path

import streamlit as st
from rapidfuzz import fuzz


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_TITLE = "Dar Makkah International"
APP_SUBTITLE = "Library Catalog Search System"

DATABASE_FILE = Path("library.db")
LOGO_PATH = Path("a.jpg")

# Search configuration
MIN_RESULT_SCORE = 70.0
MAX_RESULTS = 20

# For very short searches such as "prayer", we want high precision.
SHORT_QUERY_MIN_SCORE = 78.0

# Fuzzy spelling tolerance.
# This is deliberately conservative.
FUZZY_WORD_THRESHOLD = 84.0


# ============================================================
# STREAMLIT PAGE CONFIGURATION
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

st.markdown(
    """
    <style>

    /* ========================================================
       GLOBAL
       ======================================================== */

    .stApp {
        background:
            radial-gradient(
                circle at top center,
                #17131f 0%,
                #0e0e10 45%,
                #09090b 100%
            ) !important;

        color: #ffffff !important;
    }

    .block-container {
        max-width: 1200px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }


    /* ========================================================
       HEADER
       ======================================================== */

    .header-container {
        text-align: center;
        padding: 1rem 0 1.8rem 0;
        margin-bottom: 2rem;

        border-bottom:
            1px solid rgba(255, 102, 0, 0.45);

        background:
            linear-gradient(
                180deg,
                rgba(168, 85, 247, 0.06),
                transparent
            );
    }

    .main-heading {
        color: #a855f7 !important;

        font-size: 2.45rem !important;
        font-weight: 800 !important;

        margin: 0.4rem 0 0.3rem 0 !important;

        letter-spacing: 0.8px;
    }

    .sub-heading {
        color: #ff7a18 !important;

        font-size: 1.05rem !important;
        font-weight: 500 !important;

        letter-spacing: 0.5px;
    }


    /* ========================================================
       SEARCH AREA
       ======================================================== */

    .search-description {
        color: #a1a1aa !important;

        font-size: 0.92rem;

        margin-bottom: 0.5rem;
    }

    .stTextInput > div > div > input {
        background-color: #18181b !important;
        color: #ffffff !important;

        border:
            1px solid #ff6600 !important;

        border-radius: 10px !important;

        padding: 13px 15px !important;

        font-size: 1rem !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #a855f7 !important;

        box-shadow:
            0 0 0 1px #a855f7,
            0 0 14px rgba(168, 85, 247, 0.25) !important;
    }


    /* ========================================================
       BOOK CARD
       ======================================================== */

    .book-card {
        background:
            linear-gradient(
                145deg,
                #1b1b20,
                #151519
            );

        border:
            1px solid #303038;

        border-left:
            4px solid #ff6600;

        border-radius:
            12px;

        padding:
            1.25rem 1.35rem;

        margin:
            0.8rem 0 0.4rem 0;

        box-shadow:
            0 8px 24px rgba(0, 0, 0, 0.28);
    }

    .book-title {
        color: #c084fc !important;

        font-size: 1.35rem;

        font-weight: 750;

        line-height: 1.35;

        margin-bottom: 0.75rem;
    }

    .book-badge {
        display: inline-block;

        background:
            rgba(255, 102, 0, 0.13);

        color: #ff9a55 !important;

        border:
            1px solid rgba(255, 102, 0, 0.28);

        padding:
            4px 9px;

        margin:
            2px 5px 2px 0;

        border-radius:
            6px;

        font-size:
            0.78rem;

        font-weight:
            600;
    }


    /* ========================================================
       SCORE
       ======================================================== */

    .score-good {
        color: #4ade80 !important;
        font-weight: 700;
    }

    .score-medium {
        color: #facc15 !important;
        font-weight: 700;
    }


    /* ========================================================
       DASHBOARD
       ======================================================== */

    .dashboard-card {
        background:
            #151519;

        border:
            1px solid #2f2f36;

        border-radius:
            10px;

        padding:
            1rem;

        text-align:
            center;
    }


    /* ========================================================
       GENERAL TEXT
       ======================================================== */

    label {
        color: #ffffff !important;
    }

    p {
        color: #e4e4e7;
    }

    .muted {
        color: #a1a1aa !important;
    }


    /* ========================================================
       STREAMLIT CLEANUP
       ======================================================== */

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        background: transparent !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATABASE
# ============================================================

@st.cache_resource
def get_connection():
    """
    Create one reusable SQLite connection.

    check_same_thread=False is used because Streamlit can
    execute application code in different execution contexts.
    """
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    return connection


def check_database():
    """Verify that library.db and the books table exist."""

    if not DATABASE_FILE.exists():
        st.error(
            f"Database file '{DATABASE_FILE}' was not found."
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

        if table is None:
            st.error(
                "The database exists, but the 'books' table was not found."
            )
            st.stop()

    except sqlite3.Error as error:
        st.error(f"Database error: {error}")
        st.stop()


check_database()


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
    """Remove Latin accent marks while preserving Arabic."""

    normalized = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_text(text):
    """
    Normalize English and Arabic text.

    Examples:

        KHUSHŪ'
        khushu

    become comparable.

        Imām
        Imam

    become comparable.
    """

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

    # Keep letters/numbers/Arabic characters.
    text = re.sub(
        r"[^\w\u0600-\u06FF]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    return " ".join(text.split()).strip()


def tokenize(text):
    normalized = normalize_text(text)

    return normalized.split() if normalized else []


# ============================================================
# SEARCH HELPERS
# ============================================================

def exact_word_exists(word, field):
    """
    True only when the word actually exists as a complete token.

    This is extremely important for short searches.

    Searching "prayer" should not match an unrelated title merely
    because some fuzzy algorithm thinks two strings look similar.
    """

    word = normalize_text(word)

    if not word:
        return False

    field_tokens = tokenize(field)

    return word in field_tokens


def count_exact_query_words(query, field):
    """Count how many query words occur exactly in a field."""

    query_tokens = set(tokenize(query))
    field_tokens = set(tokenize(field))

    if not query_tokens:
        return 0

    return len(query_tokens.intersection(field_tokens))


def all_query_words_exist(query, field):
    """Check whether every query word exists in the field."""

    query_tokens = set(tokenize(query))

    if not query_tokens:
        return False

    field_tokens = set(tokenize(field))

    return query_tokens.issubset(field_tokens)


def phrase_exists(query, field):
    """
    Check whether the complete normalized query occurs
    as a phrase in the field.
    """

    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return False

    return q in f


def best_fuzzy_word_score(query_word, field):
    """
    Conservative fuzzy matching.

    This is used only to tolerate OCR/spelling mistakes.

    Example:

        prayer
        praver

    can still match.

    But completely unrelated words are rejected.
    """

    field_tokens = tokenize(field)

    if not field_tokens:
        return 0.0

    best = 0.0

    for field_word in field_tokens:

        # Exact word already handled elsewhere.
        if query_word == field_word:
            return 100.0

        score = fuzz.ratio(
            query_word,
            field_word,
        )

        if score > best:
            best = score

    return float(best)


# ============================================================
# PROFESSIONAL SEARCH SCORING
# ============================================================

def title_score(query, title):
    """
    Calculate a precision-first title score.

    Title matches are much more important than author/publisher
    matches.
    """

    q = normalize_text(query)
    t = normalize_text(title)

    if not q or not t:
        return 0.0

    # --------------------------------------------------------
    # 1. Exact title
    # --------------------------------------------------------

    if q == t:
        return 100.0

    # --------------------------------------------------------
    # 2. Complete query phrase inside title
    # --------------------------------------------------------

    if phrase_exists(q, t):
        return 96.0

    query_tokens = tokenize(q)
    title_tokens = tokenize(t)

    if not query_tokens or not title_tokens:
        return 0.0

    # --------------------------------------------------------
    # 3. Exact token matching
    # --------------------------------------------------------

    exact_count = count_exact_query_words(q, t)

    coverage = exact_count / len(set(query_tokens))

    # Every query word exists in title.
    if coverage == 1.0:

        if len(query_tokens) == 1:
            return 94.0

        return 92.0 + min(
            3.0,
            len(query_tokens) * 0.5
        )

    # Partial exact token coverage.
    if exact_count > 0:

        base = 70.0 + (coverage * 18.0)

        # Bonus when query starts the title.
        if t.startswith(q):
            base += 5.0

        return min(base, 91.0)

    # --------------------------------------------------------
    # 4. Conservative fuzzy word matching
    # --------------------------------------------------------

    fuzzy_scores = []

    for query_word in set(query_tokens):

        score = best_fuzzy_word_score(
            query_word,
            t,
        )

        if score >= FUZZY_WORD_THRESHOLD:
            fuzzy_scores.append(score)

    if not fuzzy_scores:
        return 0.0

    fuzzy_coverage = len(fuzzy_scores) / len(set(query_tokens))

    if fuzzy_coverage == 1.0:
        return min(
            88.0,
            sum(fuzzy_scores) / len(fuzzy_scores)
        )

    # A single fuzzy word should not make an unrelated title
    # appear as a strong result.
    if len(query_tokens) == 1:
        return 82.0 if fuzzy_scores[0] >= 90 else 0.0

    return 0.0


def author_score(query, author):
    """
    Author matching is intentionally weaker than title matching.
    """

    q = normalize_text(query)
    a = normalize_text(author)

    if not q or not a:
        return 0.0

    if q == a:
        return 90.0

    if phrase_exists(q, a):
        return 86.0

    exact_count = count_exact_query_words(q, a)
    query_count = len(set(tokenize(q)))

    if query_count == 0:
        return 0.0

    coverage = exact_count / query_count

    if coverage == 1.0:
        return 82.0

    if exact_count > 0:
        return 65.0 + coverage * 15.0

    return 0.0


def publisher_score(query, publisher):
    """
    Publisher matching is useful, but should never dominate
    a title match.
    """

    q = normalize_text(query)
    p = normalize_text(publisher)

    if not q or not p:
        return 0.0

    if q == p:
        return 85.0

    if phrase_exists(q, p):
        return 80.0

    exact_count = count_exact_query_words(q, p)

    if exact_count > 0:
        return 60.0

    return 0.0


def calculate_book_score(query, row):
    """
    Final relevance score.

    Priority:

        TITLE
        ↓
        AUTHOR
        ↓
        PUBLISHER

    This prevents common author/publisher words from polluting
    title searches.
    """

    title = row["title"] or ""
    author = row["author"] or ""
    publisher = row["publisher"] or ""

    t_score = title_score(query, title)
    a_score = author_score(query, author)
    p_score = publisher_score(query, publisher)

    # --------------------------------------------------------
    # TITLE HAS STRONG PRIORITY
    # --------------------------------------------------------

    if t_score >= 90:
        final_score = t_score

    elif t_score >= 70:
        final_score = t_score

        # Small author bonus only.
        if a_score >= 80:
            final_score += 2.0

    elif a_score >= 80:
        final_score = a_score * 0.92

    elif p_score >= 80:
        final_score = p_score * 0.88

    else:
        final_score = max(
            t_score,
            a_score * 0.88,
            p_score * 0.82,
        )

    return round(
        min(final_score, 100.0),
        1,
    )


# ============================================================
# SEARCH DATABASE
# ============================================================

@st.cache_data(ttl=300)
def load_books():
    """Load all books once and cache them."""

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

    return rows


def search_books(query):
    """
    High precision catalog search.

    Important:
    We do NOT return every fuzzy match.

    A book must have a meaningful relationship to the query.
    """

    query = query.strip()

    if not query:
        return []

    normalized_query = normalize_text(query)

    if not normalized_query:
        return []

    query_tokens = tokenize(normalized_query)

    rows = load_books()

    if not rows:
        return []

    results = []

    for row in rows:

        title = row["title"] or ""
        author = row["author"] or ""
        publisher = row["publisher"] or ""

        t_normalized = normalize_text(title)
        a_normalized = normalize_text(author)
        p_normalized = normalize_text(publisher)

        # ====================================================
        # STRICT RELEVANCE FILTER
        # ====================================================

        title_exact = (
            normalized_query == t_normalized
        )

        title_phrase = (
            normalized_query in t_normalized
        )

        title_exact_words = count_exact_query_words(
            normalized_query,
            title,
        )

        author_exact_words = count_exact_query_words(
            normalized_query,
            author,
        )

        publisher_exact_words = count_exact_query_words(
            normalized_query,
            publisher,
        )

        # ----------------------------------------------------
        # Calculate score
        # ----------------------------------------------------

        score = calculate_book_score(
            normalized_query,
            row,
        )

        # ----------------------------------------------------
        # Determine whether this book is genuinely relevant
        # ----------------------------------------------------

        relevant = False

        # Exact title.
        if title_exact:
            relevant = True

        # Query phrase occurs in title.
        elif title_phrase:
            relevant = True

        # Exact query word exists in title.
        elif title_exact_words > 0:
            relevant = True

        # Exact query word exists in author.
        elif author_exact_words > 0:
            relevant = True

        # Exact query word exists in publisher.
        elif publisher_exact_words > 0:
            relevant = True

        # Conservative fuzzy spelling correction.
        elif score >= MIN_RESULT_SCORE:
            relevant = True

        if not relevant:
            continue

        # ----------------------------------------------------
        # Extra protection for one-word searches.
        # ----------------------------------------------------

        if len(query_tokens) == 1:

            q_word = query_tokens[0]

            actual_word_match = (
                exact_word_exists(q_word, title)
                or exact_word_exists(q_word, author)
                or exact_word_exists(q_word, publisher)
            )

            # If there is no actual word match, require a
            # genuinely strong fuzzy match.
            if not actual_word_match and score < SHORT_QUERY_MIN_SCORE:
                continue

        results.append(
            {
                "id": row["id"],
                "shelf": row["shelf"] or "",
                "title": title,
                "author": author,
                "publisher": publisher,
                "language": row["language"] or "",
                "position": row["position"],
                "image": row["image"] or "",
                "score": score,
            }
        )

    # ========================================================
    # SORTING
    # ========================================================

    results.sort(
        key=lambda book: (
            -book["score"],
            book["title"].lower(),
        )
    )

    return results[:MAX_RESULTS]


# ============================================================
# SAFE HTML
# ============================================================

def safe(value):
    """Escape text before placing it inside HTML."""

    return html.escape(
        str(value or "")
    )


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
            width=190,
        )

    st.markdown(
        f"""
        <div class="header-container">

            <div class="main-heading">
                {safe(APP_TITLE)}
            </div>

            <div class="sub-heading">
                {safe(APP_SUBTITLE)}
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SEARCH
# ============================================================

st.markdown(
    '<div class="search-description">'
    'Search by book title, author, publisher, or keyword.'
    '</div>',
    unsafe_allow_html=True,
)

search_query = st.text_input(
    "🔎 Search Catalog",
    placeholder="Example: Prayer, Ibn Qayyim, Dar as-Sunnah...",
    label_visibility="visible",
)


# ============================================================
# SEARCH RESULTS
# ============================================================

if search_query:

    results = search_books(search_query)

    if results:

        st.markdown(
            f"""
            <h3 style="
                color:#a855f7;
                margin-top:1.5rem;
                margin-bottom:1rem;
            ">
                {len(results)} Matching Book(s)
            </h3>
            """,
            unsafe_allow_html=True,
        )

        for book in results:

            title = safe(book["title"])
            shelf = safe(book["shelf"])
            author = safe(book["author"])
            publisher = safe(book["publisher"])
            language = safe(book["language"])

            position = (
                safe(book["position"])
                if book["position"] is not None
                else ""
            )

            score = book["score"]

            if score >= 90:
                score_class = "score-good"
            else:
                score_class = "score-medium"

            # ------------------------------------------------
            # BOOK CARD
            # ------------------------------------------------

            st.markdown(
                f"""
                <div class="book-card">

                    <div class="book-title">
                        📖 {title}
                    </div>

                    <div>

                        <span class="book-badge">
                            📍 Shelf: {shelf}
                        </span>

                        {
                            f'''
                            <span class="book-badge">
                                Position: {position}
                            </span>
                            '''
                            if position
                            else ""
                        }

                        {
                            f'''
                            <span class="book-badge">
                                Language: {language}
                            </span>
                            '''
                            if language
                            else ""
                        }

                    </div>

                </div>
                """,
                unsafe_allow_html=True,
            )

            # ------------------------------------------------
            # METADATA
            # ------------------------------------------------

            meta_col1, meta_col2, meta_col3 = st.columns(
                [1.2, 1.2, 0.7]
            )

            with meta_col1:

                if author:

                    st.markdown(
                        f"""
                        **Author:** {author}
                        """
                    )

            with meta_col2:

                if publisher:

                    st.markdown(
                        f"""
                        **Publisher:** {publisher}
                        """
                    )

            with meta_col3:

                st.markdown(
                    f"""
                    **Match:**
                    <span class="{score_class}">
                    {score}%
                    </span>
                    """,
                    unsafe_allow_html=True,
                )

            # ------------------------------------------------
            # SHELF IMAGE
            # ------------------------------------------------

            if book["image"]:

                image_name = Path(
                    str(book["image"])
                ).name

                possible_paths = [
                    Path(image_name),
                    Path("shelves") / image_name,
                ]

                image_path = None

                for candidate in possible_paths:

                    if candidate.exists():

                        image_path = candidate

                        break

                if image_path:

                    with st.expander(
                        "📷 View Shelf Location"
                    ):

                        st.image(
                            str(image_path),
                            use_container_width=True,
                        )

            st.divider()

    else:

        st.warning(
            f"No relevant books found for "
            f"'{search_query}'. "
            "Try another title, author, or keyword."
        )


# ============================================================
# DEFAULT DASHBOARD
# ============================================================

else:

    st.info(
        "💡 Start typing in the search box to search the library catalog."
    )

    rows = load_books()

    total_books = len(rows)

    total_shelves = len(
        {
            row["shelf"]
            for row in rows
            if row["shelf"]
        }
    )

    # --------------------------------------------------------
    # DASHBOARD METRICS
    # --------------------------------------------------------

    metric1, metric2 = st.columns(2)

    with metric1:

        st.metric(
            "📚 Total Books",
            total_books,
        )

    with metric2:

        st.metric(
            "🗄️ Indexed Shelves",
            total_shelves,
        )

    # --------------------------------------------------------
    # SYSTEM INFORMATION
    # --------------------------------------------------------

    st.markdown(
        """
        <div class="dashboard-card" style="margin-top:1.5rem;">

            <div style="
                color:#a855f7;
                font-size:1.1rem;
                font-weight:700;
            ">
                Library Search System
            </div>

            <div class="muted" style="margin-top:0.4rem;">
                Precision-first catalog search with
                Arabic/English text normalization and
                conservative fuzzy matching.
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

