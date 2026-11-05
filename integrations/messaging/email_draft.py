"""Open a mailto draft. This does not send mail by itself."""

from __future__ import annotations

import urllib.parse
import webbrowser


class EmailDraft:
    def open_draft(self, recipient: str, subject: str, body: str) -> str:
        query = urllib.parse.urlencode({"subject": subject, "body": body})
        url = f"mailto:{urllib.parse.quote(recipient)}?{query}"
        webbrowser.open(url)
        return url
