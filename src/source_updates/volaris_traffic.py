"""Explicitly admitted Volaris issuer traffic original; distinct from SEC financials."""

ENTRY = "https://ir.volaris.com/es/informacion-financiera/reportes-de-trafico/"
PDF = (
    "https://filemanager-cdn.mziq.com/published/ea52c1bb-e8e2-457e-820a-98ca17753a37/"
    "d13b9b6b-4e2e-471f-a6db-60f23a9f2262"
)
PERIOD = "2026M09"
PRODUCT = "volaris_traffic_ir"


def validate_admitted_url(url):
    # Exact strings also reject arbitrary subdomains, documents, ports, query
    # variants and redirects; catalogue allowed_hosts alone does not do that.
    if url not in {ENTRY, PDF}:
        raise ValueError("Volaris IR admits only the reviewed issuer page and exact September PDF")


def selection():
    return dict(
        version=1,
        items=[
            dict(
                id="volaris-ir-index",
                product=PRODUCT,
                source_system="volaris_ir",
                entity="volaris_traffic_catalog",
                period="current",
                purpose="catalog",
                url=ENTRY,
                extension="html",
                mode="get",
            ),
            dict(
                id="volaris-ir-september",
                product=PRODUCT,
                source_system="volaris_ir",
                entity="volaris_traffic_report",
                period=PERIOD,
                purpose="data",
                url=PDF,
                extension="pdf",
                mode="get",
                relative_dir="volaris_ir/traffic",
            ),
        ],
    )
