"""
utils_email.py — Envoi d'emails avec résumé mensuel
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import MONTHS_FR


def send_monthly_summary(db, year: int, month: int,
                         to_email: str, smtp_host: str, smtp_port: int,
                         smtp_user: str, smtp_password: str,
                         use_tls: bool = True) -> tuple[bool, str]:
    """
    Envoie un résumé mensuel par email.

    Args:
        db: Instance de Database
        year: Année du rapport
        month: Mois du rapport (1-12)
        to_email: Adresse email du destinataire
        smtp_host: Hôte SMTP
        smtp_port: Port SMTP
        smtp_user: Nom d'utilisateur SMTP
        smtp_password: Mot de passe SMTP
        use_tls: Utiliser TLS (défaut: True)

    Returns:
        (succès: bool, message: str)
    """
    try:
        # Récupérer les données
        rev_data = db.get_revenues(year, month)
        exp_data = db.get_expenses(year, month)
        sav_data = db.get_savings(year, month)
        exp_by_cat = db.get_expenses_by_category(year, month)

        total_rev = sum(r["amount"] for r in rev_data)
        total_exp = sum(e["amount"] for e in exp_data)
        total_sav = sum(s["amount"] for s in sav_data)
        bilan = total_rev - total_exp

        # Taux d'épargne
        taux_epargne = (total_sav / total_rev * 100) if total_rev > 0 else 0

        # Top 5 catégories
        top_categories = sorted(
            exp_by_cat,
            key=lambda x: x["total"],
            reverse=True
        )[:5]

        # Construire le HTML
        month_name = MONTHS_FR[month - 1]
        subject = f"Fintrack — Résumé {month_name} {year}"

        html_body = _build_html_summary(
            month_name, year,
            total_rev, total_exp, total_sav, bilan, taux_epargne,
            top_categories
        )

        # Configurer le message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email

        # Ajouter le corps HTML
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Envoyer via SMTP
        if use_tls:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        return True, "Email envoyé avec succès"

    except smtplib.SMTPAuthenticationError:
        return False, "Erreur d'authentification SMTP (vérifiez les identifiants)"
    except smtplib.SMTPException as e:
        return False, f"Erreur SMTP : {str(e)}"
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def _build_html_summary(month_name: str, year: int,
                        total_rev: float, total_exp: float,
                        total_sav: float, bilan: float,
                        taux_epargne: float, top_categories: list) -> str:
    """
    Construit le corps HTML de l'email.
    """
    # Couleurs CSS inline
    primary_color = "#3B6FE8"
    green_color = "#22C55E"
    red_color = "#EF4444"
    blue_color = "#3B82F6"
    light_bg = "#F8FAFC"
    border_color = "#E2E8F0"

    # Bilan couleur
    bilan_color = green_color if bilan >= 0 else red_color
    bilan_sign = "+" if bilan >= 0 else ""

    # En-têtes des catégories
    top_cats_html = ""
    for i, cat in enumerate(top_categories, 1):
        top_cats_html += f"""
            <tr style="background-color: {'white' if i % 2 == 1 else light_bg};">
                <td style="padding: 10px; border-bottom: 1px solid {border_color};">
                    {i}. {cat['name']}
                </td>
                <td style="padding: 10px; border-bottom: 1px solid {border_color}; text-align: right;">
                    {cat['total']:,.2f} €
                </td>
            </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background-color: {light_bg};
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, {primary_color} 0%, #2563eb 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: bold;
            }}
            .content {{
                padding: 30px;
            }}
            .kpi-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr 1fr;
                gap: 15px;
                margin-bottom: 30px;
            }}
            .kpi-card {{
                background-color: {light_bg};
                padding: 15px;
                border-radius: 6px;
                text-align: center;
                border-left: 4px solid {primary_color};
            }}
            .kpi-card.green {{
                border-left-color: {green_color};
            }}
            .kpi-card.red {{
                border-left-color: {red_color};
            }}
            .kpi-card.blue {{
                border-left-color: {blue_color};
            }}
            .kpi-label {{
                font-size: 12px;
                color: #64748B;
                font-weight: 600;
                margin-bottom: 5px;
            }}
            .kpi-value {{
                font-size: 20px;
                font-weight: bold;
                color: #1E293B;
            }}
            .section {{
                margin-bottom: 25px;
            }}
            .section-title {{
                background-color: {primary_color};
                color: white;
                padding: 10px 15px;
                border-radius: 4px;
                font-weight: bold;
                margin-bottom: 15px;
                font-size: 14px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            th {{
                background-color: {light_bg};
                padding: 10px;
                text-align: left;
                font-weight: 600;
                color: #1E293B;
                border-bottom: 1px solid {border_color};
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid {border_color};
            }}
            .stat-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid {border_color};
            }}
            .stat-label {{
                color: #64748B;
                font-weight: 500;
            }}
            .stat-value {{
                font-weight: bold;
                color: #1E293B;
            }}
            .footer {{
                background-color: {light_bg};
                padding: 20px;
                text-align: center;
                font-size: 12px;
                color: #64748B;
                border-top: 1px solid {border_color};
            }}
            .footer p {{
                margin: 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <h1>📊 {month_name} {year}</h1>
            </div>

            <!-- Content -->
            <div class="content">
                <!-- KPI Grid -->
                <div class="kpi-grid">
                    <div class="kpi-card green">
                        <div class="kpi-label">Revenus</div>
                        <div class="kpi-value">{total_rev:,.0f} €</div>
                    </div>
                    <div class="kpi-card red">
                        <div class="kpi-label">Dépenses</div>
                        <div class="kpi-value">{total_exp:,.0f} €</div>
                    </div>
                    <div class="kpi-card blue">
                        <div class="kpi-label">Épargne</div>
                        <div class="kpi-value">{total_sav:,.0f} €</div>
                    </div>
                    <div class="kpi-card" style="border-left-color: {bilan_color};">
                        <div class="kpi-label">Bilan</div>
                        <div class="kpi-value" style="color: {bilan_color};">
                            {bilan_sign}{bilan:,.0f} €
                        </div>
                    </div>
                </div>

                <!-- Taux d'épargne -->
                <div class="section">
                    <div class="section-title">📈 Taux d'épargne</div>
                    <div class="stat-row">
                        <span class="stat-label">Taux d'épargne</span>
                        <span class="stat-value">{taux_epargne:.1f}%</span>
                    </div>
                </div>

                <!-- Top 5 catégories -->
                <div class="section">
                    <div class="section-title">💡 Top 5 catégories de dépenses</div>
                    <table>
                        <tbody>
                            {top_cats_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Footer -->
            <div class="footer">
                <p>
                    <strong>Fintrack</strong> — Application personnelle de suivi financier
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    return html
