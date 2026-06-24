import re
import requests


def find_email_hunter(
    first_name: str,
    last_name: str,
    company_domain: str,
    api_key: str,
) -> str:
    """
    Look up email via Hunter.io Email Finder API.
    Free plan: 25 searches/month. Returns email or empty string.
    """
    if not api_key:
        return ""
    if not company_domain:
        return ""

    try:
        url = "https://api.hunter.io/v2/email-finder"
        params = {
            "first_name": first_name,
            "last_name": last_name,
            "domain": company_domain,
            "api_key": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            email = data.get("data", {}).get("email", "")
            confidence = data.get("data", {}).get("score", 0)
            if email and confidence >= 50:
                return email
    except Exception as e:
        print(f"  Hunter.io error: {e}")
    return ""


def guess_company_domain(company_name: str) -> str:
    """
    Rough domain guess from company name.
    e.g. "Acme Corp" >> "acmecorp.com"
    Not reliable - use Hunter.io domain search for accuracy.
    """
    if not company_name:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9]", "", company_name.lower())
    # Strip common suffixes
    for suffix in ["inc", "llc", "ltd", "corp", "pvt", "technologies", "tech", "solutions"]:
        clean = clean.replace(suffix, "")
    return f"{clean}.com" if clean else ""


def split_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' >> ('First', 'Last')."""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]
