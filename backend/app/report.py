"""Génération du rapport d'inventaire (PDF).

Document destiné à l'impression ou à une déclaration d'assurance : totaux de la
collection et liste détaillée des objets, valeurs exprimées dans la devise de
référence. Aucune donnée n'est écrite : le PDF est produit en mémoire.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from xml.sax.saxutils import escape as _esc

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import crud, currency, media, models
from .stats import compute_stats

TYPE_LABEL = {"DIECAST": "Maquette", "PATCH": "Patch", "OTHER": "Autre"}
STATUS_LABEL = {
    "EXHIBITED": "Exposé",
    "STORED_BOX": "En boîte",
    "WANTED": "Recherché",
    "TRANSIT": "En transit",
}
MATERIAL_LABEL = {
    "EMBROIDERED": "Broderie",
    "PVC": "PVC",
    "LEATHER": "Cuir",
    "WOVEN": "Tissé",
}
ATTACHMENT_LABEL = {
    "HOOK_VELCRO": "Velcro crochet",
    "LOOP_VELCRO": "Velcro boucle",
    "SEW_ON": "À coudre",
}
SHAPE_LABEL = {"ROUND": "Rond", "SHIELD": "Écusson", "TAB": "Fanion", "CUT_OUT": "Découpé"}

# Libellés des colonnes et largeurs (en mm) — la somme couvre une A4 paysage
# moins les marges du document (2 × 12 mm).
COLUMNS = ["Objet", "Type", "Statut", "Pays", "Emplacement", "Classe", "Valeur est.", "Achat"]
COLUMN_WIDTHS = [70 * mm, 20 * mm, 20 * mm, 26 * mm, 38 * mm, 45 * mm, 26 * mm, 26 * mm]

_EURO_STYLE = colors.HexColor("#0f172a")
_HEADER_BG = colors.HexColor("#e2e8f0")
_ZEBRA_BG = colors.HexColor("#f8fafc")

# Style de paragraphe des cellules, réutilisé pour toutes les lignes.
_BODY = ParagraphStyle("AviadbCell", fontName="Helvetica", fontSize=7.5, leading=9)


def _money(value: float | None, code: str) -> str:
    """Montant lisible en français (« 1 234,50 € »), ou un tiret si absent.

    Les séparateurs sont des espaces insécables (U+00A0), présentes dans
    l'encodage WinAnsi des polices standard de PDF — contrairement à l'espace
    fine insécable (U+202F), qui n'y figure pas et s'afficherait en carré.
    """
    if value is None:
        return "—"
    text = f"{float(value):,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{text}\u00a0{code}"


def _items(db: Session) -> list[models.Item]:
    return list(
        db.scalars(
            select(models.Item)
            .options(
                selectinload(models.Item.diecast),
                selectinload(models.Item.patch),
                selectinload(models.Item.item_class),
            )
            .order_by(models.Item.name)
        ).all()
    )


def _row(item: models.Item, by_id: dict, base: str) -> list[str]:
    diecast = item.diecast
    patch = item.patch
    detail = ""
    if item.item_type == models.ItemType.DIECAST and diecast is not None:
        detail = " ".join(part for part in (diecast.scale, diecast.manufacturer) if part)
    elif item.item_type == models.ItemType.PATCH and patch is not None:
        detail = " ".join(part for part in (patch.unit_squadron, patch.base) if part)

    name = _esc(item.name)
    if detail:
        name = f"{name} <font size='6'>{_esc(detail)}</font>"
    class_name = " › ".join(crud.class_path(by_id, item.class_id) or []) or "—"

    return [
        Paragraph(name or "—", _BODY),
        TYPE_LABEL.get(item.item_type.value, item.item_type.value),
        STATUS_LABEL.get(item.status.value, item.status.value),
        item.country or "—",
        item.storage_location or "—",
        class_name,
        _money(item.estimated_value, item.currency or base),
        _money(item.purchase_eur_value, "EUR"),
    ]


def build_inventory_pdf(db: Session) -> bytes:
    """Construit le PDF et renvoie son contenu binaire."""
    stats = compute_stats(db)
    base = stats.base_currency

    classes = crud.all_classes(db)
    by_id = {node.id: node for node in classes}

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Inventaire AviaDB",
        author="AviaDB",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AviadbTitle", parent=styles["Title"], fontSize=18, spaceAfter=2, textColor=_EURO_STYLE
    )
    meta_style = ParagraphStyle(
        "AviadbMeta", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )

    generated = datetime.now(UTC).astimezone()
    story = [
        Paragraph("Inventaire de la collection", title_style),
        Paragraph(
            f"Édité le {generated.strftime('%d/%m/%Y à %H:%M')} — "
            f"{stats.total_items} objet(s), {stats.total_photos} photo(s) — "
            f"valeurs en {base}",
            meta_style,
        ),
        Spacer(1, 6 * mm),
    ]

    summary = [
        ["Valeur estimée", "Total des achats", "Objets valorisés", "Taux du"],
        [
            _money(stats.total_estimated_value, base),
            _money(stats.total_purchase_value, base),
            f"{stats.items_with_estimated_value} / {stats.total_items}",
            (stats.rates_updated_at or "—")[:10],
        ],
    ]
    summary_table = Table(summary, colWidths=[60 * mm] * 4)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ]
        )
    )
    story += [summary_table, Spacer(1, 6 * mm)]

    rows = [COLUMNS] + [_row(item, by_id, base) for item in _items(db)]
    table = Table(rows, colWidths=COLUMN_WIDTHS, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), _EURO_STYLE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ZEBRA_BG]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    document.build(story)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Fiche détaillée d'un objet
# --------------------------------------------------------------------------- #
_LABEL_STYLE = ParagraphStyle(
    "AviadbItemLabel", fontName="Helvetica-Bold", fontSize=9, textColor=_EURO_STYLE
)
_VALUE_STYLE = ParagraphStyle("AviadbItemValue", fontName="Helvetica", fontSize=9)
_H2 = ParagraphStyle(
    "AviadbH2", fontName="Helvetica-Bold", fontSize=11, spaceBefore=4, spaceAfter=3
)


def _text(value: object) -> str:
    if value is None or value == "":
        return "—"
    return _esc(str(value))


def _kv_table(rows: list[tuple[str, object]]) -> Table:
    data = [
        [Paragraph(_esc(label), _LABEL_STYLE), Paragraph(_text(value), _VALUE_STYLE)]
        for label, value in rows
    ]
    table = Table(data, colWidths=[45 * mm, 115 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    return table


def _photo_flowable(item: models.Item) -> Image | None:
    """Photo principale (ou première disponible), mise à l'échelle."""
    photos = sorted(item.photos, key=lambda p: (not p.is_primary, p.position, p.id))
    for photo in photos:
        relative = photo.thumb_path or photo.file_path
        if not relative:
            continue
        path = media.UPLOAD_DIR / relative
        if not path.is_file():
            continue
        try:
            width, height = ImageReader(str(path)).getSize()
        except OSError:
            continue
        if not width or not height:
            continue
        scale = min(90 * mm / width, 70 * mm / height, 1.0)
        return Image(str(path), width=width * scale, height=height * scale)
    return None


def build_item_pdf(db: Session, item: models.Item) -> bytes:
    """Fiche d'un objet : photo, caractéristiques, liens et historique de prix."""
    base = currency.get_base_currency(db)
    rates = currency.get_rates(db)
    by_id = {node.id: node for node in crud.all_classes(db)}
    class_name = " › ".join(crud.class_path(by_id, item.class_id) or [])

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Fiche {item.name}",
        author="AviaDB",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AviadbItemTitle", parent=styles["Title"], fontSize=18, spaceAfter=2, textColor=_EURO_STYLE
    )
    meta_style = ParagraphStyle(
        "AviadbItemMeta", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )

    generated = datetime.now(UTC).astimezone()
    subtitle = " · ".join(
        part
        for part in (
            TYPE_LABEL.get(item.item_type.value, item.item_type.value),
            STATUS_LABEL.get(item.status.value, item.status.value),
            class_name or None,
        )
        if part
    )
    story = [
        Paragraph(_esc(item.name), title_style),
        Paragraph(subtitle, meta_style),
        Paragraph(
            f"Fiche éditée le {generated.strftime('%d/%m/%Y')} — valeurs converties en {base}",
            meta_style,
        ),
        Spacer(1, 4 * mm),
    ]

    photo = _photo_flowable(item)
    if photo is not None:
        story += [photo, Spacer(1, 4 * mm)]

    diecast = item.diecast
    patch = item.patch
    details: list[tuple[str, object]] = []
    for label, value in (
        ("Pays", item.country),
        ("Modèle", item.aircraft_model),
        ("Emplacement", item.storage_location),
        ("Échelle", diecast.scale if diecast else None),
        ("Fabricant", diecast.manufacturer if diecast else None),
        ("Référence", diecast.part_number if diecast else None),
        ("Immatriculation", diecast.registration_number if diecast else None),
        ("Configuration", diecast.configuration if diecast else None),
        ("Unité / escadron", patch.unit_squadron if patch else None),
        ("Base", patch.base if patch else None),
        ("Matière", MATERIAL_LABEL.get(patch.material.value) if patch and patch.material else None),
        (
            "Fixation",
            ATTACHMENT_LABEL.get(patch.attachment_type.value)
            if patch and patch.attachment_type
            else None,
        ),
        ("Forme", SHAPE_LABEL.get(patch.shape.value) if patch and patch.shape else None),
        ("Événement / mission", patch.event_or_mission if patch else None),
        ("Date d'achat", item.purchase_date.isoformat() if item.purchase_date else None),
        ("Prix d'achat", _money(item.purchase_price, item.currency or base)),
        ("Équivalent d'achat", _money(item.purchase_eur_value, "EUR")),
        ("Valeur estimée", _money(item.estimated_value, item.currency or base)),
        ("Notes", item.notes),
    ):
        if value not in (None, ""):
            details.append((label, value))

    if details:
        story += [Paragraph("Caractéristiques", _H2), _kv_table(details), Spacer(1, 4 * mm)]

    if item.tags:
        tag_names = ", ".join(_esc(t.name) for t in sorted(item.tags, key=lambda t: t.name))
        story += [
            Paragraph("Tags", _H2),
            Paragraph(tag_names, _VALUE_STYLE),
            Spacer(1, 4 * mm),
        ]

    if item.links:
        story.append(Paragraph("Liens", _H2))
        for link in item.links:
            prefix = f"{_esc(link.label)} — " if link.label else ""
            story.append(Paragraph(f"• {prefix}{_esc(link.url)}", _VALUE_STYLE))
        story.append(Spacer(1, 4 * mm))

    if item.price_points:
        story.append(Paragraph(f"Historique de prix (en {base})", _H2))
        rows: list[list[str]] = [["Date", "Prix relevé", f"Équivalent {base}", "Note"]]
        for point in item.price_points:
            eur_value = point.eur_value
            if eur_value is None:
                eur_value = currency.to_eur(float(point.price), point.currency, rates)
            rows.append(
                [
                    point.recorded_on.isoformat(),
                    _money(point.price, point.currency),
                    _money(currency.to_base(float(eur_value), "EUR", base, rates), base),
                    point.note or "",
                ]
            )
        table = Table(rows, colWidths=[30 * mm, 38 * mm, 38 * mm, 54 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

    document.build(story)
    return buffer.getvalue()
