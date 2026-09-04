import types

from elk_lead_agent import agent_tools
from elk_lead_agent.config import load_config


def test_parse_html_extracts_text_and_absolute_links():
    html = """<html><body><p>Boarding House Wien</p>
      <a href="/projekt/1">Projekt Eins</a>
      <script>ignore()</script>
      <a href="https://x.at/p2">Projekt Zwei</a></body></html>"""
    text, links = agent_tools._parse_html(html, "https://base.at/")
    assert "Boarding House Wien" in text
    assert "ignore()" not in text
    urls = [u for _t, u in links]
    assert "https://base.at/projekt/1" in urls
    assert "https://x.at/p2" in urls


def test_source_label():
    assert agent_tools._source_label("https://www.derstandard.at/story/1") == "derstandard.at"


class _FakeClient:
    """Drives run_agent deterministically: one fetch tool call, then a final JSON."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "fetch_url",
                            "arguments": '{"url": "https://real.at/projekt-holz-boardinghouse"}',
                        },
                    }
                ],
            }
        return {"content": "fertig"}  # no tool_calls -> loop ends

    def chat_json(self, messages):
        return {
            "projects": [
                {
                    "title": "Boarding House Holzbau",
                    "url": "https://real.at/projekt-holz-boardinghouse",  # was fetched -> kept
                    "location": "Wien",
                    "status": "In Planung",
                    "categories": ["wohnen_auf_zeit"],
                    "volume_eur": None,
                    "investor": None,
                    "timber_or_modular": True,
                    "submission_imminent": False,
                },
                {
                    "title": "Erfundenes Projekt",
                    "url": "https://hallucinated.example/not-seen",  # never fetched -> dropped
                    "categories": ["budget_hotels"],
                    "timber_or_modular": False,
                    "submission_imminent": False,
                },
            ]
        }


def test_run_agent_drops_unseen_urls(monkeypatch):
    # Avoid real network: fetch_url returns a page with the same link.
    def fake_get(url, **kwargs):
        html = '<html><body><a href="https://real.at/projekt-holz-boardinghouse">x</a> Holzbau</body></html>'
        return types.SimpleNamespace(
            url=url, text=html, raise_for_status=lambda: None
        )

    monkeypatch.setattr(agent_tools.httpx, "get", fake_get)

    projects, errors = agent_tools.run_agent(load_config(), _FakeClient())
    urls = [p.finding.url for p in projects]
    assert "https://real.at/projekt-holz-boardinghouse" in urls
    assert "https://hallucinated.example/not-seen" not in urls
