import json
import re
import urllib.error
import urllib.request

apiUrl = "https://api.github.com/repos/dvlinuxx-max/Cleanix/releases/latest"


def parseVersion(text):
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:3])


def check(current, timeout=6):
    """Return one of: ("newer", tag, url), ("latest", tag, url), ("none", "", ""), ("offline", "", "")."""
    req = urllib.request.Request(apiUrl, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cleanix-update-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        return ("none", "", "") if e.code == 404 else ("offline", "", "")
    except (OSError, ValueError):
        return ("offline", "", "")
    tag = data.get("tag_name") or ""
    url = data.get("html_url") or ""
    if data.get("draft") or data.get("prerelease") or not parseVersion(tag):
        return ("none", "", "")
    if parseVersion(tag) > parseVersion(current):
        return ("newer", tag, url)
    return ("latest", tag, url)


def newerRelease(current):
    state, tag, url = check(current)
    return (tag, url) if state == "newer" else None
