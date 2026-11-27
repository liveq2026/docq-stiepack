import time

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY
from app.schemas import DocumentAnalysis


# ---------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ---------------------------------------------------------
# Models
# ---------------------------------------------------------

PRIMARY_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL = "gemini-3.8-flash"
# PRIMARY_MODEL = "gemini-3.8-flash"
# FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]


# ---------------------------------------------------------
# Retryable Gemini errors
# ---------------------------------------------------------

def _is_retryable_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)

    return status_code in (
        429,  # Rate limit
        500,  # Internal server error
        502,  # Bad gateway
        503,  # Service unavailable
        504   # Gateway timeout
    )


# ---------------------------------------------------------
# Generic Gemini request with retry
# ---------------------------------------------------------

def _generate_with_retry(
    model: str,
    prompt: str,
    max_retries: int = 2
):
    for attempt in range(max_retries + 1):

        try:

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            return response

        except Exception as error:

            if not _is_retryable_error(error):
                raise

            if attempt >= max_retries:
                raise

            delay = 2 ** attempt

            print(
                f"Gemini temporary error "
                f"({getattr(error, 'status_code', 'unknown')}). "
                f"Retrying in {delay} seconds..."
            )

            time.sleep(delay)


# ---------------------------------------------------------
# Structured Document Analysis
# ---------------------------------------------------------

def _analyze_with_retry(
    model: str,
    prompt: str,
    max_retries: int = 1
) -> DocumentAnalysis:

    for attempt in range(max_retries + 1):
        start = time.perf_counter()

        try:
            print(
                f"[DocQ] Calling Gemini: {model} | "
                f"Attempt: {attempt + 1} | "
                f"Prompt: {len(prompt):,} characters"
            )

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DocumentAnalysis,
                    temperature=0.2,
                    automatic_function_calling=(
                        types.AutomaticFunctionCallingConfig(disable=True)
                    ),
                    thinking_config=types.ThinkingConfig(
                        thinking_level="LOW"
                    )
                )
            )

            print(
                f"[DocQ] Gemini response received in "
                f"{time.perf_counter() - start:.2f}s"
            )

            if response.parsed is not None:
                return _filter_paragraph_like_fields(response.parsed)

            if response.text:
                parsed = DocumentAnalysis.model_validate_json(response.text)
                return _filter_paragraph_like_fields(parsed)

            raise ValueError("Gemini returned an empty response")

        except Exception as error:
            elapsed = time.perf_counter() - start

            print(
                f"[DocQ] Gemini error after {elapsed:.2f}s: "
                f"{error}"
            )

            if not _is_retryable_error(error):
                raise

            if attempt >= max_retries:
                raise

            delay = 2 ** attempt
            print(f"[DocQ] Retrying in {delay}s")
            time.sleep(delay)


# ---------------------------------------------------------
# Main DocQ Document Analysis
# ---------------------------------------------------------

# ---------------------------------------------------------
# Conservative field-name validation (reject paragraph-like fields)
# ---------------------------------------------------------

def _is_form_field_label(field) -> bool:
    """Keep short label-like names; reject sentence/paragraph-like names."""
    import re
    name = str(getattr(field, "name", "") or "").strip()
    if not name or len(name) > 120:
        return False
    words = re.findall(r"\b[\wÄÖÜäöüß-]+\b", name, flags=re.UNICODE)
    if len(words) > 10:
        return False
    # Field labels may end with colon or abbreviations, but not sentence punctuation.
    if name.endswith((".", "!", "?")):
        return False
    # Sentence-like names often contain a verb and multiple clause separators.
    if len(words) >= 7 and (name.count(",") >= 2 or name.count(";") >= 1):
        return False
    return True


def _filter_paragraph_like_fields(analysis: DocumentAnalysis) -> DocumentAnalysis:
    """Apply a cautious second-pass filter to Gemini's field list."""
    fields = list(getattr(analysis, "fields", []) or [])
    kept = [field for field in fields if _is_form_field_label(field)]
    removed = len(fields) - len(kept)
    if removed:
        print(f"[DocQ] Filtered {removed} paragraph-like field name(s)")
    analysis.fields = kept
    return analysis



def analyze_document(
    document_text: str
) -> DocumentAnalysis:

    prompt = f"""
You are DocQ, an intelligent document automation
and document analysis engine.

Analyze the document carefully.

Your FIRST responsibility is to classify the document
into one of these three modes:

STATIC
-------
The document is essentially fixed content and does not
require runtime data mapping.

Examples:
- Company policy
- Instruction document
- Fixed notice
- Informational document
- Static reference document

DYNAMIC
--------
The document contains information that can change between
generated documents.

Examples:
- Quotation
- Invoice
- Purchase Order
- Offer Letter
- Salary Slip
- Certificate
- Contract
- Application Form
- Business Report

A document should normally be considered DYNAMIC when it
contains customer information, dates, numbers, variable
business information, repeating items, tables containing
business data, placeholders, or other content that could
benefit from runtime JSON mapping.

REVIEW
------
Use REVIEW when you cannot confidently determine whether
the document is STATIC or DYNAMIC.

IMPORTANT RULES
---------------

1. Do not invent information.

2. Extract only information that actually exists in
   the document.

3. Extract fields ONLY when the text is a clearly identifiable field label
   paired with a value, or a form placeholder/blank intended for user input.
   Examples of valid labels: Name, Customer Number, Date, Liefertermin ca.,
   Belegnr., Kundennr., Email, Address, Signature, Amount.

4. Do NOT turn ordinary paragraph text, explanatory sentences, legal clauses,
   terms and conditions, descriptions, narrative prose, or arbitrary sentence
   fragments into fields. A paragraph is not a field merely because it contains
   useful information or a number/date.

5. For a field, the field name must be a short label/title (not a sentence).
   Keep the label as it appears in the document. If no clear label exists,
   omit it from fields rather than guessing.

6. Identify repeating items and table data where possible, but keep table rows
   and descriptive item text in items—not as standalone editable fields unless
   they are clearly labeled fields.

7. For DYNAMIC documents, provide mapping suggestions.

8. Mapping suggestions are suggestions only.
   They are NOT final mappings.

9. For STATIC documents, mapping_suggestions should
   normally be empty.

10. If classification confidence is low, use REVIEW.

11. Confidence must be between 0.0 and 1.0.

12. Preserve the actual values found in the document.

13. Identify the document type, for example:
    quotation, invoice, purchase_order, contract,
    policy, certificate, receipt, report, etc.

14. For dynamic fields, suggest sensible JSON paths.

Example:

Document field:
Customer Name

Suggested path:
customer.name

Another example:

Document field:
Quotation Number

Suggested path:
quotation.number

Another example:

Document field:
Product

Suggested path:
items[].description

Another example:

Document field:
Quantity

Suggested path:
items[].quantity

DOCUMENT TO ANALYZE
-------------------

{document_text}
"""

    # -----------------------------------------------------
    # Try primary model
    # -----------------------------------------------------

    try:

        return _analyze_with_retry(
            model=PRIMARY_MODEL,
            prompt=prompt
        )

    except Exception as primary_error:

        print(
            f"Primary Gemini model failed: {primary_error}"
        )

        print(
            f"Trying fallback model: {FALLBACK_MODEL}"
        )

    # -----------------------------------------------------
    # Try fallback model
    # -----------------------------------------------------

    return _analyze_with_retry(
        model=FALLBACK_MODEL,
        prompt=prompt
    )


# ---------------------------------------------------------
# Gemini Health / Connection Test
# ---------------------------------------------------------

def test_gemini():

    response = _generate_with_retry(
        model=PRIMARY_MODEL,
        prompt=(
            "Say exactly: "
            "Bismillah ❤️ DocQ Gemini is alive!"
        )
    )

    return response.text