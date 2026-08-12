
import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image
from rapidfuzz import fuzz

from google import genai
from google.genai import types


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "📚 Library Book Finder"

DATABASE_FILE = Path("library.db")
SHELVES_DIR = Path("shelves")

SHELVES_DIR.mkdir(parents=True, exist_ok=True)

# Keep the Gemini model configurable.
#
# If you already have a working model, you can set:
#
# set GEMINI_MODEL=your-working-model
#
# Otherwise this is the current default used by this app.

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)

SEMANTIC_MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Library Book Finder",
    page_icon="📚",
    layout="wide",
)

st.title(APP_TITLE)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    connection = get_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelf TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            publisher TEXT,
            language TEXT,
            confidence REAL,
            position INTEGER,
            image TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Upgrade older databases.
    columns = connection.execute(
        "PRAGMA table_info(books)"
    ).fetchall()

    column_names = {
        row["name"]
        for row in columns
    }

    if "publisher" not in column_names:
        connection.execute(
            "ALTER TABLE books ADD COLUMN publisher TEXT"
        )

    # Embeddings are kept inside the SAME database.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            book_id INTEGER PRIMARY KEY,
            source_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            FOREIGN KEY(book_id)
                REFERENCES books(id)
                ON DELETE CASCADE
        )
        """
    )

    connection.commit()
    connection.close()


initialize_database()


# ============================================================
# GENERAL HELPERS
# ============================================================

def current_timestamp():
    return (
        datetime.now()
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )


def clean_string(value):
    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# ARABIC + ENGLISH NORMALIZATION
# ============================================================

ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)

ARABIC_TRANSLATION = str.maketrans(
    {
        # Alef variants
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",

        # Ya variants
        "ى": "ي",
        "ئ": "ي",

        # Waw variant
        "ؤ": "و",

        # Tatweel
        "ـ": "",

        # Lam-alef ligatures
        "ﻻ": "لا",
        "ﻷ": "لا",
        "ﻹ": "لا",
        "ﻵ": "لا",
    }
)


def remove_latin_accents(text):
    """
    Converts:

        Â -> A
        É -> E
        ö -> o

    This helps searches such as:

        AL-MAWÂHIB

    match:

        al mawahib
    """

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_text(text):
    """
    Normalize English and Arabic without translating either.

    Examples:

        AL-MAWÂHIB AR-RABBÂNIYAH
        ->
        al mawahib ar rabbaniyah

        تَارِيخُ الإِسْلَام
        ->
        تاريخ الاسلام
    """

    if not text:
        return ""

    text = str(text).strip()

    # English accents.
    text = remove_latin_accents(text)

    # Arabic diacritics.
    text = ARABIC_DIACRITICS.sub(
        "",
        text,
    )

    # Arabic character variants.
    text = text.translate(
        ARABIC_TRANSLATION
    )

    # Lowercase English.
    text = text.lower()

    # Normalize apostrophes.
    text = text.replace(
        "’",
        "'",
    )

    text = text.replace(
        "‘",
        "'",
    )

    # Normalize dashes.
    text = text.replace(
        "–",
        "-",
    )

    text = text.replace(
        "—",
        "-",
    )

    # Convert punctuation to spaces.
    text = re.sub(
        r"[^\w\u0600-\u06FF]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    # Normalize whitespace.
    text = " ".join(
        text.split()
    )

    return text.strip()


def compact_text(text):
    """
    Removes spaces and dashes after normalization.

    This helps:

        al mawahib rabbaniyah

    match:

        AL-MAWÂHIB AR-RABBÂNIYAH
    """

    normalized = normalize_text(
        text
    )

    return re.sub(
        r"[\s_-]+",
        "",
        normalized,
    )


def tokenize(text):
    normalized = normalize_text(
        text
    )

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# SEARCH SCORING
# ============================================================

def fuzzy_field_score(
    query,
    field,
):
    """
    Calculate a strong lexical score for one field.

    Exact/substrings are intentionally much more important
    than semantic similarity.
    """

    if not field:
        return 0.0

    q = normalize_text(query)
    f = normalize_text(field)

    if not q or not f:
        return 0.0

    # Exact whole field.
    if q == f:
        return 100.0

    # Exact substring.
    if q in f:
        return 98.0

    # Compact substring.
    qc = compact_text(query)
    fc = compact_text(field)

    if qc and qc in fc:
        return 97.0

    # Compare against individual words.
    query_tokens = tokenize(query)
    field_tokens = tokenize(field)

    best_word_score = 0.0

    for query_token in query_tokens:

        for field_token in field_tokens:

            score = fuzz.ratio(
                query_token,
                field_token,
            )

            best_word_score = max(
                best_word_score,
                score,
            )

    # Whole-field fuzzy scores.
    whole_scores = [
        fuzz.ratio(q, f),
        fuzz.partial_ratio(q, f),
        fuzz.token_set_ratio(q, f),
        fuzz.WRatio(q, f),
    ]

    best = max(
        [best_word_score] + whole_scores
    )

    return float(best)


def lexical_scores(
    query,
    title,
    author,
    publisher,
):
    """
    Returns separate title/author/publisher scores.
    """

    title_score = fuzzy_field_score(
        query,
        title,
    )

    author_score = fuzzy_field_score(
        query,
        author,
    )

    publisher_score = fuzzy_field_score(
        query,
        publisher,
    )

    return (
        title_score,
        author_score,
        publisher_score,
    )


def token_field_match(
    query_tokens,
    field,
):
    """
    Determines how strongly individual query tokens
    appear in a field.

    Used for multi-word searches such as:

        world iiph

    where:

        world -> title
        iiph  -> publisher
    """

    if not query_tokens or not field:
        return 0.0

    field_normalized = normalize_text(
        field
    )

    field_tokens = tokenize(
        field_normalized
    )

    if not field_tokens:
        return 0.0

    scores = []

    for query_token in query_tokens:

        best = 0.0

        for field_token in field_tokens:

            if query_token == field_token:
                best = 100.0
                break

            if query_token in field_token:
                best = max(
                    best,
                    96.0,
                )

            score = fuzz.ratio(
                query_token,
                field_token,
            )

            best = max(
                best,
                score,
            )

        scores.append(best)

    if not scores:
        return 0.0

    # Average gives credit when different words match
    # different fields.
    return float(
        sum(scores) / len(scores)
    )


def multi_field_lexical_score(
    query,
    title,
    author,
    publisher,
):
    """
    Search every query token across all fields.

    This is important for:

        world iiph

    where the words can belong to different fields.
    """

    query_tokens = tokenize(
        query
    )

    if not query_tokens:
        return 0.0

    per_token = []

    for token in query_tokens:

        best = max(
            fuzzy_field_score(
                token,
                title,
            ),
            fuzzy_field_score(
                token,
                author,
            ) * 0.92,
            fuzzy_field_score(
                token,
                publisher,
            ) * 0.90,
        )

        per_token.append(
            best
        )

    if not per_token:
        return 0.0

    return float(
        sum(per_token) / len(per_token)
    )


def has_real_textual_match(
    query,
    title,
    author,
    publisher,
):
    """
    Critical anti-noise rule.

    Semantic similarity alone is NOT enough.

    A result needs actual evidence in the stored
    title/author/publisher text.
    """

    q = normalize_text(query)

    if not q:
        return False

    fields = [
        normalize_text(title),
        normalize_text(author),
        normalize_text(publisher),
    ]

    fields = [
        field
        for field in fields
        if field
    ]

    if not fields:
        return False

    # Whole query substring.
    for field in fields:

        if q in field:
            return True

        qc = compact_text(q)
        fc = compact_text(field)

        if qc and qc in fc:
            return True

    # Token-level evidence.
    query_tokens = tokenize(q)

    if not query_tokens:
        return False

    for token in query_tokens:

        for field in fields:

            if token in field:
                return True

            for field_token in tokenize(
                field
            ):

                # Reasonable typo tolerance.
                if fuzz.ratio(
                    token,
                    field_token,
                ) >= 82:
                    return True

    return False


# ============================================================
# SEMANTIC MODEL
# ============================================================

@st.cache_resource(
    show_spinner="Loading multilingual semantic search model..."
)
def load_semantic_model():
    from sentence_transformers import (
        SentenceTransformer,
    )

    return SentenceTransformer(
        SEMANTIC_MODEL_NAME
    )


def get_semantic_model_safe():
    try:
        return load_semantic_model()

    except Exception:
        return None


def book_source_text(
    title,
    author,
    publisher,
):
    """
    Text used to generate a book embedding.
    """

    parts = []

    if title:
        parts.append(
            f"Title: {title}"
        )

    if author:
        parts.append(
            f"Author: {author}"
        )

    if publisher:
        parts.append(
            f"Publisher: {publisher}"
        )

    return " | ".join(
        parts
    )


def encode_text(model, text):
    """
    Generate a normalized embedding.
    """

    vector = model.encode(
        [text],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0]

    return np.asarray(
        vector,
        dtype=np.float32,
    )


def embedding_to_blob(vector):
    return vector.astype(
        np.float32
    ).tobytes()


def blob_to_embedding(blob):
    return np.frombuffer(
        blob,
        dtype=np.float32,
    )


# ============================================================
# EMBEDDINGS DATABASE
# ============================================================

def delete_book_embedding(
    connection,
    book_id,
):
    connection.execute(
        "DELETE FROM embeddings WHERE book_id = ?",
        (book_id,),
    )


def save_book_embedding(
    connection,
    book_id,
    source_text,
    vector,
):
    connection.execute(
        """
        INSERT INTO embeddings (
            book_id,
            source_text,
            embedding
        )
        VALUES (?, ?, ?)
        ON CONFLICT(book_id)
        DO UPDATE SET
            source_text = excluded.source_text,
            embedding = excluded.embedding
        """,
        (
            book_id,
            source_text,
            embedding_to_blob(vector),
        ),
    )


def update_embeddings_for_books(
    book_ids,
):
    """
    Generate embeddings after books are stored.

    If the semantic model cannot load, the normal
    database remains usable.
    """

    if not book_ids:
        return False

    model = get_semantic_model_safe()

    if model is None:
        return False

    connection = get_connection()

    try:

        for book_id in book_ids:

            row = connection.execute(
                """
                SELECT
                    title,
                    author,
                    publisher
                FROM books
                WHERE id = ?
                """,
                (book_id,),
            ).fetchone()

            if row is None:
                continue

            source_text = book_source_text(
                row["title"],
                row["author"],
                row["publisher"],
            )

            if not source_text:
                continue

            existing = connection.execute(
                """
                SELECT source_text
                FROM embeddings
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()

            if (
                existing is not None
                and existing["source_text"]
                == source_text
            ):
                continue

            vector = encode_text(
                model,
                source_text,
            )

            save_book_embedding(
                connection,
                book_id,
                source_text,
                vector,
            )

        connection.commit()

        return True

    except Exception:

        connection.rollback()

        return False

    finally:

        connection.close()


def get_all_embeddings():
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            e.book_id,
            e.embedding
        FROM embeddings e
        INNER JOIN books b
            ON b.id = e.book_id
        """
    ).fetchall()

    connection.close()

    results = []

    for row in rows:

        try:

            vector = blob_to_embedding(
                row["embedding"]
            )

            results.append(
                (
                    row["book_id"],
                    vector,
                )
            )

        except Exception:
            continue

    return results


# ============================================================
# SQLITE BOOK OPERATIONS
# ============================================================

def save_books_to_database(
    shelf,
    books,
    image_filename,
):
    """
    Replace ONLY the selected shelf.
    """

    connection = get_connection()

    inserted_ids = []

    try:

        # Find old records first so their embeddings
        # can also be removed.
        old_rows = connection.execute(
            """
            SELECT id
            FROM books
            WHERE shelf = ?
            """,
            (shelf,),
        ).fetchall()

        old_ids = [
            row["id"]
            for row in old_rows
        ]

        if old_ids:

            placeholders = ",".join(
                "?"
                for _ in old_ids
            )

            connection.execute(
                f"""
                DELETE FROM embeddings
                WHERE book_id IN ({placeholders})
                """,
                old_ids,
            )

        # Delete only this shelf.
        connection.execute(
            """
            DELETE FROM books
            WHERE shelf = ?
            """,
            (shelf,),
        )

        timestamp = current_timestamp()

        for book in books:

            if not isinstance(
                book,
                dict,
            ):
                continue

            title = clean_string(
                book.get(
                    "title"
                )
            )

            if not title:
                continue

            author = clean_string(
                book.get(
                    "author"
                )
            )

            publisher = clean_string(
                book.get(
                    "publisher"
                )
            )

            language = clean_string(
                book.get(
                    "language"
                )
            )

            try:
                confidence = float(
                    book.get(
                        "confidence",
                        0,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = 0.0

            try:
                position = int(
                    book.get(
                        "position"
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                position = None

            cursor = connection.execute(
                """
                INSERT INTO books (
                    shelf,
                    title,
                    author,
                    publisher,
                    language,
                    confidence,
                    position,
                    image,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shelf,
                    title,
                    author,
                    publisher,
                    language,
                    confidence,
                    position,
                    image_filename,
                    timestamp,
                ),
            )

            inserted_ids.append(
                cursor.lastrowid
            )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()

    # Generate embeddings after the transaction.
    update_embeddings_for_books(
        inserted_ids
    )

    return inserted_ids


# ============================================================
# GEMINI
# ============================================================

def analyze_shelf_with_gemini(
    image_path,
    api_key,
):
    """
    Gemini Vision analysis.

    Uses the official google-genai SDK image-byte
    input style.
    """

    client = genai.Client(
        api_key=api_key
    )

    prompt = """
You are reading a photograph of a library shelf.

Identify INDIVIDUAL BOOKS that are visibly present.

Read book spines from LEFT TO RIGHT.

IMPORTANT:

- Read every readable book spine.
- Support Arabic and English.
- Preserve Arabic exactly as visible where possible.
- Preserve English exactly as visible where possible.
- Do not translate Arabic.
- Do not invent titles.
- Do not guess unreadable text.
- Ignore objects that are not books.
- Author only if visibly readable.
- Publisher only if visibly readable.
- NEVER guess a publisher from outside knowledge.
- Confidence must reflect actual visibility.
- Give approximate horizontal position from left to right.
- Do not claim pixel-level position.

Publisher is important.

If a publisher name or logo is visible on the spine,
return it.

If the publisher is not visible, return:

"publisher": ""

If author is not visible, return:

"author": ""

Return ONLY a JSON array.

Required format:

[
{
"title": "Journey of World",
"author": "Example Author",
"publisher": "IIPH",
"language": "English",
"confidence": 0.95,
"position": 5
}
]

Do not include Markdown.
Do not include explanations.
Do not include commentary outside the JSON array.
"""

    suffix = (
        Path(image_path)
        .suffix
        .lower()
    )

    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    mime_type = mime_types.get(
        suffix,
        "image/jpeg",
    )

    with open(
        image_path,
        "rb",
    ) as image_file:

        image_bytes = image_file.read()

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type,
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            image_part,
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    return response.text


# ============================================================
# GEMINI JSON PARSER
# ============================================================

def parse_gemini_json(
    raw_text
):
    text = raw_text.strip()

    # Remove accidental Markdown fences.
    if text.startswith(
        "```"
    ):

        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip()
            == "```"
        ):
            lines = lines[:-1]

        text = "\n".join(
            lines
        ).strip()

        if text.lower().startswith(
            "json"
        ):
            text = text[4:].strip()

    data = json.loads(
        text
    )

    if not isinstance(
        data,
        list,
    ):
        raise ValueError(
            "Gemini returned JSON, but it was not a list."
        )

    return data


def clean_gemini_books(
    books
):
    cleaned = []

    for book in books:

        if not isinstance(
            book,
            dict,
        ):
            continue

        title = clean_string(
            book.get(
                "title"
            )
        )

        if not title:
            continue

        cleaned.append(
            {
                "title": title,

                "author": clean_string(
                    book.get(
                        "author"
                    )
                ),

                "publisher": clean_string(
                    book.get(
                        "publisher"
                    )
                ),

                "language": clean_string(
                    book.get(
                        "language"
                    )
                ),

                "confidence": book.get(
                    "confidence",
                    0,
                ),

                "position": book.get(
                    "position"
                ),
            }
        )

    return cleaned


# ============================================================
# SHELF NAME
# ============================================================

# ============================================================
# ONLY CHANGE:
#
# Previously this accepted only:
#
# SHELF-01.jpg
# SHELF-02.jpg
#
# It now also accepts:
#
# SHELF-H2002.jpg
# SHELF-H2003.jpg
# SHELF-A100.jpg
#
# and other letters/numbers after SHELF-.
# ============================================================

SHELF_FILENAME_PATTERN = re.compile(
    r"^(SHELF-[A-Z0-9_-]+)\.(jpg|jpeg|png)$",
    re.IGNORECASE,
)


def shelf_from_filename(
    filename
):
    match = SHELF_FILENAME_PATTERN.match(
        filename
    )

    if not match:
        return None

    return match.group(
        1
    ).upper()


# ============================================================
# SEARCH
# ============================================================

def cosine_similarity(
    a,
    b,
):
    denominator = (
        np.linalg.norm(a)
        * np.linalg.norm(b)
    )

    if denominator == 0:
        return 0.0

    return float(
        np.dot(a, b)
        / denominator
    )


def calculate_result(
    query,
    row,
    semantic_score,
):
    title = row["title"] or ""
    author = row["author"] or ""
    publisher = row["publisher"] or ""

    title_score, author_score, publisher_score = (
        lexical_scores(
            query,
            title,
            author,
            publisher,
        )
    )

    multi_score = (
        multi_field_lexical_score(
            query,
            title,
            author,
            publisher,
        )
    )

    # Strongest lexical evidence.
    lexical_score = max(
        title_score,
        author_score * 0.94,
        publisher_score * 0.92,
        multi_score,
    )

    query_tokens = tokenize(
        query
    )

    short_query = (
        len(query_tokens) <= 2
    )

    # --------------------------------------------------------
    # FINAL SCORE
    #
    # Lexical search is primary.
    # Semantic search is secondary.
    # --------------------------------------------------------

    if lexical_score >= 98:

        # Exact/substring match.
        final_score = (
            0.85 * lexical_score
            + 0.15 * semantic_score
        )

        reason = "Exact or substring match"

    elif lexical_score >= 88:

        # Strong fuzzy/word match.
        final_score = (
            0.75 * lexical_score
            + 0.25 * semantic_score
        )

        reason = "Strong fuzzy/text match"

    elif lexical_score >= 72:

        # Moderate fuzzy match.
        final_score = (
            0.65 * lexical_score
            + 0.35 * semantic_score
        )

        reason = "Fuzzy match"

    else:

        # Weak lexical evidence.
        # Semantic can NEVER freely promote this
        # for short queries.
        if short_query:
            final_score = lexical_score
            reason = "Weak text match"
        else:
            final_score = (
                0.45 * lexical_score
                + 0.55 * semantic_score
            )

            reason = "Text + semantic match"

    return {
        "title_score": round(
            title_score,
            1,
        ),
        "author_score": round(
            author_score,
            1,
        ),
        "publisher_score": round(
            publisher_score,
            1,
        ),
        "lexical_score": round(
            lexical_score,
            1,
        ),
        "semantic_score": round(
            semantic_score,
            1,
        ),
        "final_score": round(
            min(
                final_score,
                100,
            ),
            1,
        ),
        "reason": reason,
    }


def search_books(
    query
):
    """
    Main search.

    IMPORTANT:
    Semantic similarity is NEVER allowed to create
    arbitrary short-query results.
    """

    query = query.strip()

    if not query:
        return []

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            b.*,
            e.embedding
        FROM books b
        LEFT JOIN embeddings e
            ON e.book_id = b.id
        """
    ).fetchall()

    connection.close()

    if not rows:
        return []

    model = None
    query_vector = None

    # Only attempt semantic search if embeddings exist.
    has_embeddings = any(
        row["embedding"] is not None
        for row in rows
    )

    if has_embeddings:

        model = get_semantic_model_safe()

        if model is not None:

            try:

                query_vector = encode_text(
                    model,
                    normalize_text(query),
                )

            except Exception:

                query_vector = None

    query_tokens = tokenize(
        query
    )

    short_query = (
        len(query_tokens) <= 2
    )

    results = []

    for row in rows:

        semantic_score = 0.0

        if (
            query_vector is not None
            and row["embedding"] is not None
        ):

            try:

                book_vector = (
                    blob_to_embedding(
                        row["embedding"]
                    )
                )

                cosine = cosine_similarity(
                    query_vector,
                    book_vector,
                )

                # Convert cosine similarity to
                # an easier 0-100 scale.
                semantic_score = max(
                    0.0,
                    min(
                        100.0,
                        (
                            cosine + 1.0
                        )
                        * 50.0,
                    ),
                )

            except Exception:

                semantic_score = 0.0

        scores = calculate_result(
            query,
            row,
            semantic_score,
        )

        lexical_score = scores[
            "lexical_score"
        ]

        # ----------------------------------------------------
        # HARD RELEVANCE FILTER
        # ----------------------------------------------------

        real_text_match = (
            has_real_textual_match(
                query,
                row["title"],
                row["author"],
                row["publisher"],
            )
        )

        # SHORT QUERY:
        #
        # Do NOT allow semantic-only results.
        #
        # This is the main fix for:
        #
        # journey
        # world
        # iiph
        # python
        #
        if short_query:

            if not real_text_match:
                continue

            # Strong textual threshold.
            if lexical_score < 72:
                continue

        # LONGER QUERY:
        #
        # Semantic can help, but there must still be
        # some textual evidence.
        else:

            if not real_text_match:
                continue

            if (
                lexical_score < 55
                and semantic_score < 72
            ):
                continue

        # Additional quality gate.
        if (
            scores["final_score"] < 60
        ):
            continue

        results.append(
            {
                "id": row["id"],
                "shelf": row["shelf"],
                "title": row["title"] or "",
                "author": row["author"] or "",
                "publisher": row["publisher"] or "",
                "language": row["language"] or "",
                "confidence": row["confidence"],
                "position": row["position"],
                "image": row["image"],
                "updated_at": row["updated_at"],

                "title_score": scores[
                    "title_score"
                ],

                "author_score": scores[
                    "author_score"
                ],

                "publisher_score": scores[
                    "publisher_score"
                ],

                "lexical_score": scores[
                    "lexical_score"
                ],

                "semantic_score": scores[
                    "semantic_score"
                ],

                "score": scores[
                    "final_score"
                ],

                "reason": scores[
                    "reason"
                ],
            }
        )

    results.sort(
        key=lambda item: (
            item["score"],
            item["title_score"],
            item["publisher_score"],
            item["author_score"],
        ),
        reverse=True,
    )

    return results[:5]


# ============================================================
# DATABASE STATISTICS
# ============================================================

def database_statistics():

    connection = get_connection()

    shelves = connection.execute(
        """
        SELECT COUNT(DISTINCT shelf)
        FROM books
        """
    ).fetchone()[0]

    books = connection.execute(
        """
        SELECT COUNT(*)
        FROM books
        """
    ).fetchone()[0]

    connection.close()

    return shelves, books


# ============================================================
# API KEY
# ============================================================

environment_api_key = os.getenv(
    "GEMINI_API_KEY"
)

if environment_api_key:

    api_key = environment_api_key

    st.success(
        "Gemini API key loaded from environment."
    )

else:

    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help=(
            "Optional if GEMINI_API_KEY "
            "is already configured."
        ),
    )


# ============================================================
# DATABASE STATUS
# ============================================================

shelf_count, book_count = (
    database_statistics()
)

st.header("LIBRARY DATABASE")

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Indexed shelves",
        shelf_count,
    )

with col2:
    st.metric(
        "Detected books",
        book_count,
    )


# ============================================================
# SEARCH UI
# ============================================================

st.header("SEARCH")

search_query = st.text_input(
    "Enter book name, author, publisher or keyword",
    placeholder=(
        "Example: journey, iiph, "
        "world iiph, الإسلام"
    ),
)

search_clicked = st.button(
    "Search",
    type="primary",
)

if search_clicked:

    if not search_query.strip():

        st.warning(
            "Please enter a search term."
        )

    else:

        with st.spinner(
            "Searching the library..."
        ):

            results = search_books(
                search_query
            )

        if not results:

            st.warning(
                "No sufficiently relevant books found."
            )

        else:

            st.success(
                f"{len(results)} relevant result(s) found."
            )

            for result in results:

                st.markdown(
                    f"### 📖 {result['title']}"
                )

                if result["author"]:

                    st.write(
                        f"**Author:** "
                        f"{result['author']}"
                    )

                else:

                    st.write(
                        "**Author:** Not detected"
                    )

                if result["publisher"]:

                    st.write(
                        f"**Publisher:** "
                        f"{result['publisher']}"
                    )

                else:

                    st.write(
                        "**Publisher:** Not detected"
                    )

                st.write(
                    f"**Shelf:** "
                    f"{result['shelf']}"
                )

                if result["position"] is not None:

                    st.write(
                        f"**Approximate position:** "
                        f"{result['position']} "
                        f"from left"
                    )

                st.write(
                    f"**Relevance:** "
                    f"{result['score']}%"
                )

                with st.expander(
                    "Search scoring details"
                ):

                    st.write(
                        f"Title score: "
                        f"{result['title_score']}"
                    )

                    st.write(
                        f"Author score: "
                        f"{result['author_score']}"
                    )

                    st.write(
                        f"Publisher score: "
                        f"{result['publisher_score']}"
                    )

                    st.write(
                        f"Lexical score: "
                        f"{result['lexical_score']}"
                    )

                    st.write(
                        f"Semantic score: "
                        f"{result['semantic_score']}"
                    )

                    st.write(
                        f"Final score: "
                        f"{result['score']}"
                    )

                    st.write(
                        f"Match reason: "
                        f"{result['reason']}"
                    )

                # ------------------------------------------------
                # SHOW IMAGE ONLY AFTER RESULT PASSES FILTER
                # ------------------------------------------------

                image_filename = (
                    result["image"]
                )

                if image_filename:

                    image_path = (
                        SHELVES_DIR
                        / image_filename
                    )

                    if image_path.exists():

                        try:

                            shelf_image = Image.open(
                                image_path
                            )

                            st.image(
                                shelf_image,
                                caption=(
                                    f"Current shelf: "
                                    f"{result['shelf']}"
                                ),
                                use_container_width=True,
                            )

                        except Exception as error:

                            st.warning(
                                "Shelf image could not be opened: "
                                f"{error}"
                            )

                    else:

                        st.warning(
                            f"Shelf image is missing: "
                            f"{image_filename}"
                        )

                st.divider()


# ============================================================
# SCAN ONE SHELF
# ============================================================

st.header("SCAN SHELF")

shelf_input = st.text_input(
    "Shelf number",
    placeholder="SHELF-H2002",
)

uploaded_file = st.file_uploader(
    "Upload shelf image",
    type=[
        "jpg",
        "jpeg",
        "png",
    ],
)


def normalize_shelf_name(
    shelf
):
    shelf = shelf.strip().upper()

    if not shelf:
        return ""

    if shelf.startswith(
        "SHELF-"
    ):
        return shelf

    return f"SHELF-{shelf}"


if (
    uploaded_file is not None
    and shelf_input.strip()
):

    shelf_name = normalize_shelf_name(
        shelf_input
    )

    try:

        uploaded_image = Image.open(
            uploaded_file
        ).convert(
            "RGB"
        )

        display_path = (
            SHELVES_DIR
            / f"{shelf_name}.jpg"
        )

        uploaded_image.save(
            display_path,
            format="JPEG",
            quality=95,
        )

        st.image(
            uploaded_image,
            caption=(
                f"Current image: "
                f"{shelf_name}.jpg"
            ),
            use_container_width=True,
        )

    except Exception as error:

        st.error(
            f"Could not save shelf image: "
            f"{error}"
        )


if st.button(
    "Scan Shelf"
):

    if not api_key:

        st.error(
            "Gemini API key is missing."
        )

    elif uploaded_file is None:

        st.error(
            "Please upload a shelf image."
        )

    elif not shelf_input.strip():

        st.error(
            "Please enter a shelf number."
        )

    else:

        shelf_name = normalize_shelf_name(
            shelf_input
        )

        image_path = (
            SHELVES_DIR
            / f"{shelf_name}.jpg"
        )

        try:

            with st.spinner(
                "Gemini is reading the shelf..."
            ):

                raw_response = (
                    analyze_shelf_with_gemini(
                        image_path,
                        api_key,
                    )
                )

            with st.expander(
                "Raw Gemini response"
            ):

                st.code(
                    raw_response,
                    language="json",
                )

            try:

                raw_books = (
                    parse_gemini_json(
                        raw_response
                    )
                )

                books = (
                    clean_gemini_books(
                        raw_books
                    )
                )

                inserted_ids = (
                    save_books_to_database(
                        shelf=shelf_name,
                        books=books,
                        image_filename=(
                            image_path.name
                        ),
                    )
                )

                st.success(
                    f"{shelf_name} successfully updated. "
                    f"{len(inserted_ids)} book(s) indexed."
                )

                if books:

                    st.dataframe(
                        books,
                        use_container_width=True,
                        hide_index=True,
                    )

                else:

                    st.warning(
                        "Gemini did not detect any readable books."
                    )

            except json.JSONDecodeError as error:

                st.error(
                    f"Gemini returned invalid JSON: "
                    f"{error}"
                )

            except Exception as error:

                st.error(
                    f"Could not save Gemini results: "
                    f"{error}"
                )

        except Exception as error:

            st.error(
                f"Gemini scan failed: "
                f"{error}"
            )


# ============================================================
# BULK RE-INDEX
# ============================================================

st.header("BULK SHELF INDEXING")

st.write(
    "Place shelf photographs inside the "
    "`shelves` folder using names such as "
    "`SHELF-01.jpg`, `SHELF-02.jpg`, etc."
)

if st.button(
    "Re-index All Shelves"
):

    if not api_key:

        st.error(
            "Gemini API key is missing."
        )

    else:

        shelf_files = []

        for path in sorted(
            SHELVES_DIR.iterdir()
        ):

            if not path.is_file():
                continue

            shelf = shelf_from_filename(
                path.name
            )

            if shelf:
                shelf_files.append(
                    (
                        shelf,
                        path,
                    )
                )

        if not shelf_files:

            st.warning(
                "No shelf images found in the shelves folder."
            )

        else:

            progress = st.progress(
                0
            )

            status = st.empty()

            processed = 0
            total_books = 0
            errors = []

            total = len(
                shelf_files
            )

            for index, (
                shelf,
                image_path,
            ) in enumerate(
                shelf_files,
                start=1,
            ):

                status.write(
                    f"Processing {index} of "
                    f"{total}: {shelf}"
                )

                try:

                    raw_response = (
                        analyze_shelf_with_gemini(
                            image_path,
                            api_key,
                        )
                    )

                    raw_books = (
                        parse_gemini_json(
                            raw_response
                        )
                    )

                    books = (
                        clean_gemini_books(
                            raw_books
                        )
                    )

                    inserted_ids = (
                        save_books_to_database(
                            shelf=shelf,
                            books=books,
                            image_filename=(
                                image_path.name
                            ),
                        )
                    )

                    total_books += len(
                        inserted_ids
                    )

                    processed += 1

                except Exception as error:

                    errors.append(
                        {
                            "shelf": shelf,
                            "error": str(error),
                        }
                    )

                progress.progress(
                    index / total
                )

            status.success(
                "Re-indexing complete."
            )

            st.write(
                f"**Shelves processed:** "
                f"{processed}"
            )

            st.write(
                f"**Books detected:** "
                f"{total_books}"
            )

            st.write(
                f"**Errors:** "
                f"{len(errors)}"
            )

            if errors:

                st.error(
                    "Some shelves could not be indexed."
                )

                st.dataframe(
                    errors,
                    use_container_width=True,
                    hide_index=True,
                )

            else:

                st.success(
                    "All shelf images were indexed successfully."
                )


# ============================================================
# MODEL / SEARCH STATUS
# ============================================================

with st.expander(
    "System status"
):

    st.write(
        f"Gemini model: `{GEMINI_MODEL}`"
    )

    st.write(
        "Semantic model: "
        f"`{SEMANTIC_MODEL_NAME}`"
    )

    st.write(
        f"Database: `{DATABASE_FILE}`"
    )

    st.write(
        f"Shelves folder: `{SHELVES_DIR}`"
    )

    st.write(
        "Search order: "
        "exact/substring → fuzzy → semantic"
    )

    st.write(
        "Semantic-only weak matches are rejected."
    )

