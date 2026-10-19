"""Prepare one hash-bound owner decision packet; never write approvals or the index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.dashboard.news import build_news_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    package = build_news_payload(args.candidate)["approval_package"]
    lines = [
        "# Noticias: una decisión sobre la pestaña y las once candidatas",
        "",
        "Estado: propuesta sin aprobar. No cambia el índice, los recibos, las tesis, el runtime ni la publicación.",
        "",
        f"Paquete SHA-256: `{package['proposal_sha256']}`. El hash cubre el objeto canónico excluyendo el propio campo `proposal_sha256`.",
        f"Corte original SHA-256: `{package['candidate_file_sha256']}`.",
        "",
        "El dueño puede aprobar la pestaña y las once fichas normalizadas en una sola decisión referida a este paquete. La implementación posterior generaría los once recibos internos con la misma decisión; no requiere once trámites del dueño. Integración, nueva presentación técnica y publicación conservan sus controles independientes.",
        "",
        "Opciones revisables: pestaña con las tres noticias ya aprobadas; pestaña más este corpus de once; o aplazar ambos. Esta propuesta no ejecuta ninguna opción.",
        "",
        "## Fichas y fuentes",
        "",
        "Las fechas de publicación, hecho y primera captura son distintas. Los resúmenes son originales y breves; no se incluyen artículos ni imágenes.",
        "",
    ]
    hashes = {x["record"]["id"]: x["candidate_content_sha256"] for x in package["proposed_index_records"]}
    for n, row in enumerate(package["records"], 1):
        event = row.get("event_date") or "No documentada"
        if row.get("event_end_date"):
            event += " a " + row["event_end_date"]
        lines += [
            f"### {n}. {row['title']}",
            "",
            f"ID: `{row['id']}` · {', '.join(row['companies'])} · {row['publisher']}",
            "",
            row["description"],
            "",
            f"Publicación: {row['published_at']}. Hecho: {event}. Primera captura: {row['first_captured_at']}.",
            "",
            f"[Abrir fuente]({row['source']['url']}). SHA-256 de la fuente: `{row['source']['sha256']}`.",
            f"Hash del registro normalizado propuesto: `{hashes[row['id']]}`.",
            "",
        ]
    lines += [
        "## Búsqueda y verificación",
        "",
        "Hoy el índice aprobado contiene tres fichas (dos Aeroméxico y una Volaris); ninguna Viva. Las once anteriores solo se consultan en la simulación candidata explícita. El backend de producción no las carga sin índice aprobado y pin externo nuevos.",
        "",
        "El chat resuelve consultas completas a través de su herramienta existente, devuelve filtros de publicación/empresa/tema, referencias y destinos verificados. La navegación comprueba corpus, hash del índice, ID, título, fecha, URL y hash de fuente contra la tarjeta cargada. Hasta cinco resúmenes por llamada y hasta 50 identificadores para abrir el conjunto de fichas, con total explícito. La preview distingue la simulación sin modelo de la búsqueda aprobada.",
        "",
        "Se prueba el recorrido HTTP API → worker → herramienta → historial/SSE → tarjeta con proveedor simulado y consultas completas en español, además de referencias inexistentes e inyección. No se acredita inferencia de un modelo real en esta sesión: la configuración local mantiene proveedor mock y carece del opt-in/modelo/runtime de producción; una clave presente no salta esos controles.",
        "",
        "No se habilita cron ni actualización mensual. Las decisiones técnicas de presentación y del corpus son distintas de reaprobar tesis económicas.",
    ]
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
    args.markdown.write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "candidates": len(package["records"]),
                "proposal_sha256": package["proposal_sha256"],
                "approved": False,
            }
        )
    )


if __name__ == "__main__":
    main()
