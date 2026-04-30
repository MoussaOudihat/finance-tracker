"""
utils_pdf.py — Génération de rapports PDF mensuels
"""
import os
import tempfile
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from config import C, MONTHS_FR


def generate_monthly_report(db, year: int, month: int, output_path: str) -> str:
    """
    Génère un rapport PDF mensuel complet.

    Args:
        db: Instance de Database
        year: Année du rapport
        month: Mois du rapport (1-12)
        output_path: Chemin de destination du PDF

    Returns:
        Le chemin du fichier créé
    """
    # Créer le répertoire de destination s'il n'existe pas
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Récupérer les données
    rev_data = db.get_revenues(year, month)
    exp_data = db.get_expenses(year, month)
    sav_data = db.get_savings(year, month)
    exp_by_cat = db.get_expenses_by_category(year, month)
    assets = db.get_assets(year, month)

    total_rev = sum(r["amount"] for r in rev_data)
    total_exp = sum(e["amount"] for e in exp_data)
    total_sav = sum(s["amount"] for s in sav_data)

    # Créer le document PDF
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=0.8*cm,
        leftMargin=0.8*cm,
        topMargin=1*cm,
        bottomMargin=1*cm,
    )

    story = []
    styles = getSampleStyleSheet()

    # Style personnalisé pour le titre
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=colors.HexColor(C["primary"]),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    # Style pour les en-têtes de section
    section_style = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.whitesmoke,
        spaceAfter=12,
        spaceBefore=12,
        fontName="Helvetica-Bold",
        backColor=colors.HexColor(C["primary"]),
        leftIndent=8,
        rightIndent=8,
        topPadding=6,
        bottomPadding=6,
    )

    # ──────────────────────────────────
    # 1. EN-TÊTE
    # ──────────────────────────────────
    month_name = MONTHS_FR[month - 1]
    title = Paragraph(f"Rapport Financier — {month_name} {year}", title_style)
    story.append(title)

    # Date de génération
    gen_date = datetime.now().strftime("%d/%m/%Y à %H:%M")
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor(C["muted"]),
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    story.append(Paragraph(f"Généré le {gen_date}", subtitle_style))

    # ──────────────────────────────────
    # 2. KPI RÉSUMÉ (4 blocs côte à côte)
    # ──────────────────────────────────
    kpi_data = [
        ("Revenus", f"{total_rev:,.0f} €", C["green"]),
        ("Dépenses", f"{total_exp:,.0f} €", C["red"]),
        ("Épargne", f"{total_sav:,.0f} €", C["blue"]),
        ("Bilan", f"{(total_rev - total_exp):+,.0f} €",
         C["green"] if (total_rev - total_exp) >= 0 else C["red"]),
    ]

    kpi_rows = []
    for label, value, color in kpi_data:
        cell = [
            Paragraph(label, ParagraphStyle(
                "KPILabel", parent=styles["Normal"],
                fontSize=10, textColor=colors.whitesmoke, alignment=TA_CENTER,
                fontName="Helvetica-Bold"
            )),
            Paragraph(value, ParagraphStyle(
                "KPIValue", parent=styles["Normal"],
                fontSize=18, textColor=colors.whitesmoke, alignment=TA_CENTER,
                fontName="Helvetica-Bold"
            )),
        ]
        kpi_rows.append(cell)

    kpi_table = Table(
        list(zip(*kpi_rows)),
        colWidths=[4.5*cm, 4.5*cm, 4.5*cm, 4.5*cm],
        hAlign="CENTER",
    )
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 1), colors.HexColor(C["green"])),
        ("BACKGROUND", (1, 0), (1, 1), colors.HexColor(C["red"])),
        ("BACKGROUND", (2, 0), (2, 1), colors.HexColor(C["blue"])),
        ("BACKGROUND", (3, 0), (3, 1), colors.HexColor(C["primary"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.8*cm))

    # ──────────────────────────────────
    # 3. GRAPHIQUE CAMEMBERT (dépenses par catégorie)
    # ──────────────────────────────────
    if exp_by_cat:
        story.append(Paragraph("Dépenses par catégorie", section_style))

        # Créer graphique camembert temporaire
        fig, ax = plt.subplots(figsize=(5, 3.5), facecolor="white")
        labels = [c["name"] for c in exp_by_cat]
        sizes = [c["total"] for c in exp_by_cat]

        # Palette de couleurs
        palette = [
            "#3B6FE8", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6",
            "#06B6D4", "#EC4899", "#14B8A6", "#F97316", "#6366F1",
        ]
        colors_pie = (palette * ((len(labels) // len(palette)) + 1))[:len(labels)]

        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90,
               colors=colors_pie, textprops={"fontsize": 9})
        ax.set_title(f"Total : {total_exp:,.0f} €", fontsize=11, fontweight="bold")

        # Sauvegarder en image temporaire
        pie_img_buffer = BytesIO()
        fig.savefig(pie_img_buffer, format="png", dpi=100, bbox_inches="tight")
        pie_img_buffer.seek(0)
        plt.close(fig)

        # Insérer l'image dans le PDF
        pie_image = Image(pie_img_buffer, width=10*cm, height=7*cm)
        story.append(pie_image)
        story.append(Spacer(1, 0.4*cm))

    # ──────────────────────────────────
    # 4. TABLEAU DÉPENSES PAR CATÉGORIE
    # ──────────────────────────────────
    if exp_by_cat:
        story.append(Paragraph("Détail par catégorie", section_style))

        exp_rows = [["Catégorie", "Montant", "% des dépenses"]]
        for cat in exp_by_cat:
            pct = (cat["total"] / total_exp * 100) if total_exp > 0 else 0
            exp_rows.append([
                cat["name"],
                f"{cat['total']:,.2f} €",
                f"{pct:.1f}%",
            ])

        exp_table = Table(exp_rows, colWidths=[7*cm, 3.5*cm, 3*cm])
        exp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C["primary"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(C["light"])),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C["light"])]),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor(C["border"])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(exp_table)
        story.append(Spacer(1, 0.6*cm))

    # ──────────────────────────────────
    # 5. DÉTAIL DES REVENUS
    # ──────────────────────────────────
    if rev_data:
        story.append(Paragraph("Revenus détaillés", section_style))

        rev_rows = [["Source", "Montant"]]
        for rev in rev_data:
            rev_rows.append([
                rev["source"],
                f"{rev['amount']:,.2f} €",
            ])
        rev_rows.append([
            Paragraph("<b>TOTAL</b>", styles["Normal"]),
            Paragraph(f"<b>{total_rev:,.2f} €</b>", styles["Normal"]),
        ])

        rev_table = Table(rev_rows, colWidths=[8.5*cm, 3.5*cm])
        rev_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C["green"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor(C["light"])),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor(C["light"])]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor(C["border"])),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(C["light"])),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, -1), (-1, -1), 10),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ]))
        story.append(rev_table)
        story.append(Spacer(1, 0.6*cm))

    # ──────────────────────────────────
    # 6. DÉTAIL DE L'ÉPARGNE
    # ──────────────────────────────────
    if sav_data:
        story.append(Paragraph("Épargne détaillée", section_style))

        sav_rows = [["Compte", "Montant"]]
        for sav in sav_data:
            sav_rows.append([
                sav["account"] or "(Sans nom)",
                f"{sav['amount']:,.2f} €",
            ])
        sav_rows.append([
            Paragraph("<b>TOTAL</b>", styles["Normal"]),
            Paragraph(f"<b>{total_sav:,.2f} €</b>", styles["Normal"]),
        ])

        sav_table = Table(sav_rows, colWidths=[8.5*cm, 3.5*cm])
        sav_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C["blue"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor(C["light"])),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor(C["light"])]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor(C["border"])),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(C["light"])),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, -1), (-1, -1), 10),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ]))
        story.append(sav_table)
        story.append(Spacer(1, 0.6*cm))

    # ──────────────────────────────────
    # 7. RÉSUMÉ PATRIMOINE
    # ──────────────────────────────────
    if assets:
        story.append(Paragraph("Patrimoine — Actifs courants", section_style))

        pat_rows = [["Type d'actif", "Actif", "Valeur", "Coût d'acquisition"]]
        total_asset_value = 0
        total_asset_basis = 0
        for ast in assets:
            cost_basis = ast["cost_basis"] if ast["cost_basis"] is not None else 0
            pat_rows.append([
                ast["asset_type"],
                ast["asset_name"],
                f"{ast['value']:,.2f} €",
                f"{cost_basis:,.2f} €",
            ])
            total_asset_value += ast["value"]
            total_asset_basis += cost_basis

        pat_rows.append([
            "", "",
            Paragraph(f"<b>{total_asset_value:,.2f} €</b>", styles["Normal"]),
            Paragraph(f"<b>{total_asset_basis:,.2f} €</b>", styles["Normal"]),
        ])

        pat_table = Table(
            pat_rows,
            colWidths=[3*cm, 4*cm, 3.5*cm, 4*cm],
        )
        pat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C["primary"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor(C["light"])),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor(C["light"])]),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor(C["border"])),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(C["light"])),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, -1), (-1, -1), 10),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ]))
        story.append(pat_table)
        story.append(Spacer(1, 1*cm))

    # ──────────────────────────────────
    # 8. PIED DE PAGE
    # ──────────────────────────────────
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor(C["muted"]),
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        f"Généré par Finance Tracker — {gen_date}",
        footer_style
    ))

    # ──────────────────────────────────
    # Construire le PDF
    # ──────────────────────────────────
    doc.build(story)

    return output_path
