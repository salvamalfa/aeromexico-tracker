"""Reviewed retained input roles and complete-certifier routing; no acquisition."""

from pathlib import Path

from src.source_updates.catalog import ROOT


def spec(product: str) -> dict:
    from src.source_updates import (
        afac_airports,
        afac_countries,
        afac_margins,
        airport_group_native,
        authorities,
        bts_native,
        context_snapshots,
        financials,
        government_traffic,
        oma_traffic,
        route_documents,
        sec_fiscal,
        series_native,
        slots,
        viva_financials,
        viva_traffic,
        volaris_traffic,
    )

    registry = {
        "afac_airports": {
            "roles": {"workbook": ("afac",)},
            "primary": "workbook",
            "code_files": [Path(afac_airports.__file__)],
            "table": afac_airports.TABLE,
            "grain": afac_airports.BUSINESS_GRAIN,
            "parse": lambda originals, period: afac_airports.parse(
                originals["workbook"][0], period, originals["workbook"][1]
            ),
        }
    }
    for name, module, roles in [
        (
            "afac_margins",
            afac_margins,
            {"routes": ("afac_research", "afac"), "carriers": ("afac_research", "afac")},
        ),
        (
            "afac_countries",
            afac_countries,
            {"pdf": ("afac_research", "afac"), "routes": ("afac_research", "afac")},
        ),
    ]:
        registry[name] = {
            "roles": roles,
            "primary": next(iter(roles)),
            "code_files": [Path(module.__file__), Path(afac_margins.__file__), Path(afac_airports.__file__)],
            "support_all_originals": True,
            "table": module.TABLE,
            "grain": module.GRAIN,
            "parse": module.parse,
        }
    for name, role, aliases in [
        ("iasa", "pdf", ("faa_iasa",)),
        ("dictionary", "csv", ("loughran_mcdonald",)),
    ]:
        registry[name] = {
            "roles": {role: aliases},
            "primary": role,
            "table": context_snapshots.TABLES[name],
            "grain": context_snapshots.GRAINS[name],
            "parse": getattr(context_snapshots, name),
            "code_files": [Path(context_snapshots.__file__)],
        }
    registry["am_financials"] = {
        "roles": {"pdf": ("aeromexico_ir",), "html": ("aeromexico_ir",)},
        "role_sets": [{"pdf"}, {"html"}],
        "primary": "pdf",
        "table": financials.TABLE,
        "grain": financials.GRAIN,
        "parse": financials.parse,
        "revision_values": ["value", "unit", "is_preliminary", "is_unaudited"],
        "code_files": [
            Path(financials.__file__),
            ROOT / "src/source_updates/financials_html.py",
            ROOT / "src/parse/aeromexico_ir_financial.py",
            ROOT / "src/parse/aeromexico_ir.py",
        ],
    }
    registry["ryanair_sec"] = {
        "roles": {role: ("sec",) for role in ("html", "submissions", "index")},
        "primary": "html",
        "table": sec_fiscal.TABLE,
        "grain": sec_fiscal.GRAIN,
        "parse": sec_fiscal.parse,
        "support_all_originals": True,
        "revision_values": ["value", "unit", "source_decimals", "period_start_date", "period_end_date"],
        "code_files": [Path(sec_fiscal.__file__)],
    }
    registry["oma_traffic"] = {
        "roles": {"pdf": ("oma_ir",)},
        "primary": "pdf",
        "table": oma_traffic.TABLE,
        "grain": oma_traffic.GRAIN,
        "parse": oma_traffic.parse,
        "code_files": [
            Path(oma_traffic.__file__),
            Path(authorities.__file__),
            Path(afac_airports.__file__),
            ROOT / "src/transform/international_routes.py",
        ],
    }
    registry["viva_traffic"] = {
        "roles": {"pdf": ("viva_ir",)},
        "primary": "pdf",
        "table": viva_traffic.TABLE,
        "grain": viva_traffic.GRAIN,
        "parse": viva_traffic.parse,
        "revision_values": ["value", "unit", "entity_as_reported"],
        "code_files": [Path(viva_traffic.__file__)],
    }
    registry["volaris_traffic_ir"] = {
        "roles": {"pdf": ("volaris_ir",)},
        "primary": "pdf",
        "table": volaris_traffic.TABLE,
        "grain": volaris_traffic.GRAIN,
        "parse": volaris_traffic.parse,
        "code_files": [Path(volaris_traffic.__file__)],
        "revision_values": [
            "value",
            "unit",
            "scale_multiplier",
            "reported_change",
            "reported_change_unit",
            "flight_scope",
            "passenger_definition",
            "is_preliminary",
            "is_unaudited",
        ],
    }
    registry["aicm_slots"] = {
        "roles": {"pdf": ("aicm",)},
        "primary": "pdf",
        "table": slots.TABLE,
        "grain": slots.GRAIN,
        "parse": slots.parse,
        "code_files": [Path(slots.__file__)],
    }
    for name, aliases in {
        "am_routes": ("aeromexico_press",),
        "oma_routes": ("oma",),
        "colima": ("colima_subsectur_mirror",),
        "aifa_roster": ("expansion",),
    }.items():
        registry[name] = {
            "roles": {"document": aliases},
            "primary": "document",
            "table": route_documents.TABLES[name],
            "grain": route_documents.GRAIN,
            "parse": lambda inputs, period, name=name: route_documents.parse(name, inputs, period),
            "code_files": [Path(route_documents.__file__)],
        }
    for name, roles in {
        "anac": {"json": ("international_routes",)},
        "caa": {"csv": ("route_authority_research", "international_routes")},
        "aena": {
            role: ("aena",)
            for role in ("company_operations", "company_passengers", "market_operations", "market_passengers")
        },
    }.items():
        registry[name] = {
            "roles": roles,
            "primary": next(iter(roles)),
            "code_files": [Path(authorities.__file__), ROOT / "src/transform/international_routes.py"],
            "table": authorities.TABLES[name],
            "grain": authorities.GRAIN,
            "parse": getattr(authorities, name),
        }
    registry["afac_margins"]["revision_values"] = ["value", "unit", "source_cell_estimated", "source_notes"]
    registry["dictionary"]["revision_values"] = [*context_snapshots.FIELDS[1:], "unit"]
    for name, role, alias in [("aicm_traffic", "pdf", "aicm"), ("aifa_traffic", "workbook", "aifa")]:
        registry[name] = {
            "roles": {role: (alias,)},
            "primary": role,
            "certifier": "government",
            "table": "fact_airport_traffic",
            "grain": government_traffic.GRAIN,
            "code_files": [Path(government_traffic.__file__)],
        }
    registry["viva_financials"] = {
        "roles": {"pdf": ("viva_ir",), "prior_quarter": ("viva_ir",)},
        "primary": "pdf",
        "certifier": "viva_financial",
        "table": "fact_viva_retained_financial_source_metrics",
        "grain": viva_financials.GRAIN,
        "code_files": [Path(viva_financials.__file__)],
    }
    registry["bts_segments"] = {
        "roles": {"archive": ("bts_t100",)},
        "primary": "archive",
        "certifier": "bts",
        "table": "fact_route_traffic",
        "grain": bts_native.GRAIN,
        "code_files": [Path(bts_native.__file__)],
    }
    for name in sorted(airport_group_native.PRODUCTS):
        registry[name] = {
            "roles": {"html": ("sec", "sec_edgar", "sec_filing")},
            "primary": "html",
            "certifier": "airport_group",
            "table": "fact_airport_traffic",
            "grain": airport_group_native.GRAIN,
            "code_files": [Path(airport_group_native.__file__)],
        }
        if name == "asur_traffic":
            from src.source_updates import asur_reconstructed, asur_reconstruction_inputs

            definition = registry[name]
            definition["roles"].update(
                {role: (asur_reconstructed.ALIAS,) for role in asur_reconstruction_inputs.FILES}
            )
            definition["role_sets"] = [{"html"}, set(asur_reconstruction_inputs.FILES)]
            definition["code_files"] += [
                Path(asur_reconstructed.__file__),
                Path(asur_reconstruction_inputs.__file__),
            ]
    registry.update(series_native.definitions())
    from src.source_updates.carrier_source_contract import retention_specs

    registry.update(retention_specs())
    if product not in registry:
        raise ValueError("No reviewed retained-product adapter")
    return registry[product]
