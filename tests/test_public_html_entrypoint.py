from pathlib import Path

from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_public_html_has_the_approved_three_view_contract() -> None:
    page = (ROOT / "static" / "aeromexico_tracker.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(page, "html.parser")

    assert [tab.get_text(strip=True) for tab in soup.select('.reader-tabs [role="tab"]')] == [
        "Lectura ejecutiva",
        "Economía unitaria",
        "Vuelos",
    ]
    assert not soup.select("#panel-reading .kpi-card")
    assert len(soup.select("#panel-economy .kpi-card")) == 4
    assert len(soup.select("#panel-flights .flight-kpi")) == 4
    ids = [node["id"] for node in soup.select("[id]")]
    assert len(ids) == len(set(ids))


def test_public_streamlit_entrypoint_starts_without_exceptions() -> None:
    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert '"app/static/aeromexico_tracker.html"' in entrypoint
    assert '"/app/static/aeromexico_tracker.html"' not in entrypoint
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
    assert not app.exception
