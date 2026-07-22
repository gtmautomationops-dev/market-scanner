"""Committee/legislator roster loading and the committee-jurisdiction overlay.

This is the differentiating layer: it maps a PTR filer to their congressional
committees, then flags a disclosed trade when the traded ticker sits in a
sector that member's committee has jurisdiction over.
"""

import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "congress_roster"

ROSTER_URLS = {
    "legislators": "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml",
    "committees": "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/committees-current.yaml",
    "membership": "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/committee-membership-current.yaml",
}


def _cached_yaml(name, url, user_agent, ttl_hours):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.yaml"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < ttl_hours * 3600
    if not fresh:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
        resp.raise_for_status()
        path.write_text(resp.text, encoding="utf-8")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CongressRoster:
    """Resolves PTR filers to committees and evaluates committee overlap."""

    def __init__(self, cfg):
        self.cfg = cfg
        ua = cfg["scraper"]["user_agent"]
        ttl = cfg["scraper"].get("roster_cache_hours", 24)
        self.legislators = _cached_yaml("legislators", ROSTER_URLS["legislators"], ua, ttl)
        self.committees = _cached_yaml("committees", ROSTER_URLS["committees"], ua, ttl)
        self.membership = _cached_yaml("membership", ROSTER_URLS["membership"], ua, ttl)

        # committee code (incl. subcommittee) -> official name, and
        # base (4-char) code -> top-level committee name
        self.code_name = {}
        self.base_name = {}
        for c in self.committees:
            tid = c.get("thomas_id")
            if tid:
                self.code_name[tid] = c["name"]
                self.base_name[tid[:4]] = c["name"]
            for sub in c.get("subcommittees", []) or []:
                sub_code = tid + sub["thomas_id"] if tid else sub["thomas_id"]
                self.code_name[sub_code] = f"{c['name']} — {sub['name']}"

        # bioguide -> list of {code, base, name, title}
        self.by_bioguide = {}
        for code, members in self.membership.items():
            base = code[:4]
            name = self.code_name.get(code) or self.code_name.get(base) or code
            for m in members:
                bg = m.get("bioguide")
                if not bg:
                    continue
                self.by_bioguide.setdefault(bg, []).append({
                    "code": code, "base": base, "name": name,
                    "title": m.get("title", ""),
                })

        # (last_lower, state, district) -> legislator identity
        self.member_index = {}
        for leg in self.legislators:
            term = leg["terms"][-1]
            last = leg["name"].get("last", "").lower()
            state = term.get("state")
            district = term.get("district")  # int for House, absent for Senate
            key = (last, state, district if district is not None else "S")
            self.member_index[key] = {
                "bioguide": leg["id"]["bioguide"],
                "full_name": leg["name"].get("official_full") or
                             f"{leg['name'].get('first','')} {leg['name'].get('last','')}".strip(),
                "party": term.get("party"),
                "chamber": "house" if term.get("type") == "rep" else "senate",
                "state": state,
                "district": district,
            }

        # ticker -> set(sectors)
        self.ticker_sectors = {}
        for sector, tickers in cfg.get("sector_tickers", {}).items():
            for t in tickers:
                self.ticker_sectors.setdefault(t.upper(), set()).add(sector)

        self.committee_sectors = cfg.get("committee_sectors", {})
        self.critical_substrings = [s.lower() for s in cfg.get("critical_committees", [])]

    # ---------------------------------------------------------------- lookup

    def match_member(self, last_name, state, district):
        """Match a PTR filer to a legislator. district is int (House) or None."""
        last = (last_name or "").lower()
        key = (last, state, district if district is not None else "S")
        if key in self.member_index:
            return self.member_index[key]
        # Fallback: unique last-name + state match (handles at-large/data drift)
        candidates = [
            v for (l, s, _d), v in self.member_index.items()
            if l == last and s == state
        ]
        return candidates[0] if len(candidates) == 1 else None

    def committees_for(self, bioguide):
        return self.by_bioguide.get(bioguide, [])

    def _top_level_committees(self, bioguide):
        """Distinct top-level committees (collapsing subcommittees) for a member,
        as list of (base_code, top_level_name)."""
        seen, out = set(), []
        for c in self.committees_for(bioguide):
            if c["base"] in seen:
                continue
            seen.add(c["base"])
            out.append((c["base"], self.base_name.get(c["base"], c["name"])))
        return out

    def is_critical(self, bioguide):
        """Return the member's top-level committees considered critical."""
        out = []
        for _base, name in self._top_level_committees(bioguide):
            if any(sub in name.lower() for sub in self.critical_substrings):
                out.append(name)
        return out

    def conflicts_for_trade(self, bioguide, ticker):
        """Top-level committees whose jurisdiction overlaps the traded ticker's
        sector. Returns list of {committee, sector} explaining each overlap."""
        if not ticker:
            return []
        sectors = self.ticker_sectors.get(ticker.upper())
        if not sectors:
            return []
        out = []
        for base, name in self._top_level_committees(bioguide):
            overlap = set(self.committee_sectors.get(base, [])) & sectors
            for sector in sorted(overlap):
                out.append({"committee": name, "sector": sector})
        return out
