"""Parse U.S. House Periodic Transaction Report (PTR) PDFs into structured
transactions.

House PTR PDFs (e-filed, DocID starting with "200...") carry a real text
layer. The transaction table wraps unpredictably, so this parser is
line-based and PRECISION-FIRST: each transaction's core (type + two dates +
amount range) sits on one physical line together with its asset name; the
stock ticker is either on that line or wraps to the next. When no ticker can
be confidently attached, the transaction is kept but marked private/None
rather than guessing a wrong symbol.
"""

import re

# type + optional (partial) + transaction date + notification date + amount range
_CORE = re.compile(
    r"\b(?P<type>P|S|E)\s*(?P<partial>\(partial\))?\s+"
    r"(?P<td>\d{2}/\d{2}/\d{4})\s+(?P<nd>\d{2}/\d{2}/\d{4})\s+"
    r"\$(?P<lo>[\d,]+)\s*-\s*\$?(?P<hi>[\d,]+)"
)
_TICKER = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)")
_NAME = re.compile(r"Name:\s*(?:Hon\.\s*)?(.+)")
_DIST = re.compile(r"State/District:\s*([A-Z]{2}\d{2})")
_FILING_ID = re.compile(r"Filing ID #(\d+)")

TX_TYPE_LABEL = {"P": "Purchase", "S": "Sale", "E": "Exchange"}


def _join_wrapped_amounts(text):
    """A PTR amount range can wrap: a line ending in '$100,001 -' with the
    upper bound '$250,000' on the next line. Re-join those so the core
    pattern matches on a single line."""
    return re.sub(
        r"(\$[\d,]+\s*-)\s*\n\s*(\$?[\d,]+)",
        r"\1 \2",
        text,
    )


def parse_ptr_text(text):
    """Parse the extracted text of one PTR PDF.

    Returns a dict:
      {filing_id, member_name, state_district, state, district, transactions:[...]}
    Each transaction:
      {ticker, asset, tx_type, tx_type_label, partial, tx_date,
       notification_date, amount_low, amount_high}
    ticker is None for private/unlisted assets.
    """
    text = _join_wrapped_amounts(text)
    lines = text.splitlines()

    fid = _FILING_ID.search(text)
    name = _NAME.search(text)
    dist = _DIST.search(text)
    state = district = None
    if dist:
        sd = dist.group(1)
        state, district = sd[:2], int(sd[2:])

    transactions = []
    for i, line in enumerate(lines):
        m = _CORE.search(line)
        if not m:
            continue
        prefix = line[: m.start()]
        nextline = lines[i + 1] if i + 1 < len(lines) else ""
        tk = _TICKER.search(prefix + " " + nextline)
        ticker = tk.group(1) if tk else None
        # asset name is the text before any "(" on the transaction line
        asset = re.sub(r"\([A-Z].*$", "", prefix).strip(" -\t")
        asset = re.sub(r"\s+", " ", asset)[:80]
        transactions.append({
            "ticker": ticker,
            "asset": asset or None,
            "tx_type": m.group("type"),
            "tx_type_label": TX_TYPE_LABEL.get(m.group("type"), m.group("type")),
            "partial": bool(m.group("partial")),
            "tx_date": m.group("td"),
            "notification_date": m.group("nd"),
            "amount_low": int(m.group("lo").replace(",", "")),
            "amount_high": int(m.group("hi").replace(",", "")),
        })

    return {
        "filing_id": fid.group(1) if fid else None,
        "member_name": name.group(1).strip() if name else None,
        "state_district": dist.group(1) if dist else None,
        "state": state,
        "district": district,
        "transactions": transactions,
    }


def public_transactions(parsed):
    """Only transactions with an identifiable stock ticker."""
    return [t for t in parsed["transactions"] if t["ticker"]]
