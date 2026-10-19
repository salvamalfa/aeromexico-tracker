"""Disconnected publication dates never become an expanded evidence window."""
import pytest
from src.conversational_analytics.news_query import resolve_news_query

BOUNDS=[(None,None),("2026-06-01",None),(None,"2026-09-30"),("2026-06-01","2026-09-30")]
@pytest.mark.parametrize("bounds",BOUNDS)
@pytest.mark.parametrize("question",[
 "noticias de junio y septiembre de 2026",
 "noticias de junio o septiembre de 2026",
 "noticias de junio, agosto y septiembre de 2026",
 "noticias de 2026-06 y 2026-09",
 "noticias de 2026-06 o 2026-09",
 "noticias del 1 de junio de 2026 y el 30 de septiembre de 2026",
 "noticias de 2026-06-01 o 2026-09-30",
 "noticias de 2024 y 2026",
])
def test_discrete_lists_require_an_explicit_supported_interval(question,bounds):
 with pytest.raises(ValueError,match="intervalo explícito"):
  resolve_news_query(question,*bounds)

@pytest.mark.parametrize("question",[
 "noticias entre junio y septiembre de 2026",
 "noticias entre los meses de junio y septiembre de 2026",
 "noticias de junio a septiembre de 2026",
 "noticias desde junio hasta septiembre de 2026",
 "noticias de junio-septiembre de 2026",
 "noticias de 2026-06 a 2026-09",
 "noticias entre 2026-06 y 2026-09",
 "noticias entre el 1 de junio de 2026 y el 30 de septiembre de 2026",
 "noticias del 1 de junio de 2026 al 30 de septiembre de 2026",
 "noticias entre 2026-06-01 y 2026-09-30",
])
def test_explicit_continuous_intervals_keep_both_stated_endpoints(question):
 result=resolve_news_query(question)
 assert (result['start_date'],result['end_date'])==('2026-06-01','2026-09-30')
