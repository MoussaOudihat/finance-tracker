"""
ui/components.py — Widgets et helpers UI réutilisables
"""
import re
import tkinter as tk
import customtkinter as ctk
from config import C, PALETTE


# ──────────────────────────────────────────────────────────
#  Tooltip
# ──────────────────────────────────────────────────────────
class Tooltip:
    """Bulle d'aide placée sur la fenêtre racine — apparaît après 400 ms de survol."""

    def __init__(self, widget, text: str, delay_ms: int = 400):
        self._widget    = widget
        self._text      = text
        self._delay     = delay_ms
        self._tip_frame = None
        self._after_id  = None
        widget.bind("<Enter>",       self._on_enter, add="+")
        widget.bind("<Leave>",       self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _=None):
        self._cancel()
        self._after_id = self._widget.after(self._delay, self._show)

    def _on_leave(self, _=None):
        self._cancel()
        self._destroy()

    def _cancel(self):
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tip_frame or not self._text:
            return
        try:
            root = self._widget.winfo_toplevel()
            x = (self._widget.winfo_rootx() - root.winfo_rootx()
                 + self._widget.winfo_width() + 10)
            y = (self._widget.winfo_rooty() - root.winfo_rooty()
                 + self._widget.winfo_height() // 2 - 14)
        except Exception:
            return
        tip = tk.Frame(root, bg=C["card"], bd=1, relief="solid",
                       highlightbackground=C["border"], highlightthickness=1)
        tk.Label(tip, text=self._text, bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 10), padx=10, pady=5).pack()
        tip.place(x=x, y=y)
        tip.lift()
        self._tip_frame = tip

    def _destroy(self):
        if self._tip_frame:
            try:
                self._tip_frame.destroy()
            except Exception:
                pass
            self._tip_frame = None


# ──────────────────────────────────────────────────────────
#  Cartes
# ──────────────────────────────────────────────────────────
def make_card(parent, **kwargs) -> ctk.CTkFrame:
    defaults = dict(fg_color=C["card"], corner_radius=14,
                    border_width=1, border_color=C["border"])
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def kpi_card(parent, title: str, value: str, color: str, icon: str = "") -> ctk.CTkFrame:
    card  = make_card(parent)
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=18, pady=14)
    ctk.CTkLabel(inner, text=f"{icon}  {title}", font=ctk.CTkFont(size=11),
                 text_color=C["muted"]).pack(anchor="w")
    ctk.CTkLabel(inner, text=value, font=ctk.CTkFont(size=24, weight="bold"),
                 text_color=color).pack(anchor="w", pady=(2, 0))
    return card


# ──────────────────────────────────────────────────────────
#  Navigation
# ──────────────────────────────────────────────────────────
def nav_button(parent, text: str, command, tooltip: str = "") -> ctk.CTkButton:
    btn = ctk.CTkButton(
        parent, text=text, anchor="w", height=36,
        font=ctk.CTkFont(size=12), fg_color="transparent",
        hover_color=C["sidebar2"], text_color="#CBD5E1",
        corner_radius=8, command=command,
    )
    if tooltip:
        Tooltip(btn, tooltip)
    return btn


def month_selector(parent, months_fr, sel_year, sel_month, on_change) -> ctk.CTkFrame:
    """Renvoie un widget sélecteur mois/année avec callback."""
    sel   = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                         border_width=1, border_color=C["border"])
    m_var = ctk.StringVar(value=months_fr[sel_month - 1])
    y_var = ctk.StringVar(value=str(sel_year))

    def _cb(*_):
        on_change(months_fr.index(m_var.get()) + 1, int(y_var.get()))

    ctk.CTkOptionMenu(sel, values=months_fr, variable=m_var, command=_cb,
                      width=135, height=34).pack(side="left", padx=6, pady=6)
    ctk.CTkOptionMenu(sel, values=[str(y) for y in range(2022, 2030)],
                      variable=y_var, command=_cb,
                      width=90, height=34).pack(side="left", padx=(0, 6), pady=6)
    return sel


# ──────────────────────────────────────────────────────────
#  Tableaux
# ──────────────────────────────────────────────────────────
def table_header(parent, columns: list[tuple[int, str]]):
    """
    Configure les colonnes du parent (grille PARTAGÉE par toutes les lignes)
    et affiche l'en-tête directement dans parent.

    Principe : header et lignes sont dans la MÊME grille du parent.
    tkinter calcule donc les largeurs de colonnes en prenant le maximum
    sur TOUS les widgets → alignement parfait indépendamment du contenu.
    """
    n = len(columns)
    # Configure les colonnes du parent UNE SEULE FOIS pour toutes les lignes
    for i, (weight, _) in enumerate(columns):
        parent.grid_columnconfigure(i, weight=weight)
    parent.grid_columnconfigure(n,     weight=0)   # colonne bouton ✏
    parent.grid_columnconfigure(n + 1, weight=0)   # colonne bouton ✕

    # Fond de l'en-tête (placé derrière via lower)
    # width=1, height=1 : évite la taille par défaut 200×200 de CTkFrame
    hdr_bg = ctk.CTkFrame(parent, fg_color=C["light"], corner_radius=6,
                          width=1, height=1)
    hdr_bg.grid(row=0, column=0, columnspan=n + 2,
                sticky="nsew", padx=2, pady=(0, 4))

    for i, (_, label) in enumerate(columns):
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C["muted"],
            fg_color=C["light"],
        ).grid(row=0, column=i, padx=10, pady=6, sticky="w")

    hdr_bg.lower()   # fond derrière les labels


def table_row(parent, row_idx: int, cols: list,
              on_edit=None, on_delete=None) -> None:
    """
    Insère une ligne de données DIRECTEMENT dans parent (même grille que l'en-tête).
    Les largeurs de colonnes sont partagées → alignement parfait garanti.
    """
    n  = len(cols)
    r  = row_idx + 1                                      # ligne 0 = en-tête
    bg = C["light"] if row_idx % 2 == 0 else C["card"]

    # Fond de la ligne (passé derrière les cellules via lower)
    # width=1, height=1 : évite la taille par défaut 200×200 de CTkFrame
    row_bg = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6,
                          width=1, height=1)
    row_bg.grid(row=r, column=0, columnspan=n + 2,
                sticky="nsew", padx=2, pady=1)

    for i, col in enumerate(cols):
        _, text, color = col[0], col[1], col[2]
        ctk.CTkLabel(
            parent, text=text, text_color=color or C["text"],
            font=ctk.CTkFont(size=12),
            fg_color=bg,
        ).grid(row=r, column=i, padx=10, pady=7, sticky="w")

    if on_edit:
        edit_btn = ctk.CTkButton(
            parent, text="✏", width=30, height=26,
            fg_color="#EFF6FF", text_color=C["primary"],
            hover_color="#DBEAFE", command=on_edit,
        )
        edit_btn.grid(row=r, column=n, padx=(4, 2), pady=4)
        Tooltip(edit_btn, "Modifier cette ligne")

    if on_delete:
        del_btn = ctk.CTkButton(
            parent, text="✕", width=30, height=26,
            fg_color="#FEE2E2", text_color=C["red"],
            hover_color="#FECACA", command=on_delete,
        )
        del_btn.grid(row=r, column=n + 1, padx=(2, 8), pady=4)
        Tooltip(del_btn, "Supprimer cette ligne")

    row_bg.lower()   # fond derrière les cellules


# ──────────────────────────────────────────────────────────
#  Barre de filtres
# ──────────────────────────────────────────────────────────
def filter_dropdown(parent, label: str, values: list[str],
                    variable: ctk.StringVar, command):
    ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11),
                 text_color=C["muted"]).pack(side="left", padx=(0, 4))
    ctk.CTkOptionMenu(parent, values=values, variable=variable,
                      command=command, width=165, height=30,
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 16))


# ──────────────────────────────────────────────────────────
#  Barres de total
# ──────────────────────────────────────────────────────────
def total_bar(parent, text: str, color: str, bg: str, border: str,
              use_pack: bool = True):
    f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8,
                     border_width=1, border_color=border)
    if use_pack:
        f.pack(fill="x", padx=2, pady=(6, 4))
    ctk.CTkLabel(f, text=text, font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=color).pack(side="right", padx=16, pady=9)
    return f


# ──────────────────────────────────────────────────────────
#  Renderer Markdown léger pour les réponses IA
# ──────────────────────────────────────────────────────────
def render_ai_text(parent, text: str, bg_color: str = None) -> tk.Text:
    """
    Affiche une réponse IA (Markdown-like) dans un tk.Text avec mise en forme :
      ### Titre   → header gras coloré
      **gras**    → texte en gras (inline)
      * item      → puce •
      ligne vide  → séparateur
    Retourne le widget (déjà pack/grid selon le parent voulu).
    """
    bg = bg_color or C["light"]

    widget = tk.Text(
        parent,
        wrap="word",
        relief="flat",
        borderwidth=0,
        bg=bg,
        fg=C["text"],
        font=("Segoe UI", 11),
        cursor="arrow",
        state="normal",
        padx=10,
        pady=6,
        spacing1=1,
        spacing2=2,
        spacing3=6,
        exportselection=False,
    )

    # ── Tags ────────────────────────────────────────────────
    widget.tag_configure(
        "h3",
        font=("Segoe UI", 13, "bold"),
        foreground=C["primary"],
        spacing1=12,
        spacing3=4,
    )
    widget.tag_configure("bold",   font=("Segoe UI", 11, "bold"))
    widget.tag_configure("normal", font=("Segoe UI", 11))
    widget.tag_configure(
        "bullet",
        lmargin1=4,
        lmargin2=22,
        spacing1=2,
        spacing3=2,
    )
    widget.tag_configure(
        "bullet_marker",
        font=("Segoe UI", 11, "bold"),
        foreground=C["primary"],
        lmargin1=4,
    )
    widget.tag_configure(
        "action",
        font=("Segoe UI", 11),
        foreground=C.get("primary_hover", C["primary"]),
        lmargin1=4,
        lmargin2=22,
    )

    _BOLD_RE = re.compile(r'\*\*(.+?)\*\*')

    def _insert_inline(line_text: str, base_tag: str = "normal"):
        """Insère du texte en gérant le **gras** inline."""
        pos = 0
        for m in _BOLD_RE.finditer(line_text):
            before = line_text[pos:m.start()]
            if before:
                widget.insert("end", before, base_tag)
            widget.insert("end", m.group(1), "bold")
            pos = m.end()
        remainder = line_text[pos:]
        if remainder:
            widget.insert("end", remainder, base_tag)

    # ── Parser ligne par ligne ───────────────────────────────
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()

        if line.startswith("### ") or line.startswith("## "):
            title = line.lstrip("# ").strip()
            widget.insert("end", title + "\n", "h3")

        elif line.startswith("* ") or line.startswith("- "):
            content = line[2:].strip()
            widget.insert("end", "  •  ", "bullet_marker")
            _insert_inline(content, "bullet")
            widget.insert("end", "\n", "bullet")

        elif line.startswith("→ ") or line.startswith("-> "):
            content = line[2:].strip()
            widget.insert("end", "  → ", "action")
            _insert_inline(content, "action")
            widget.insert("end", "\n", "action")

        elif line == "":
            widget.insert("end", "\n")

        else:
            _insert_inline(line, "normal")
            widget.insert("end", "\n", "normal")

    widget.configure(state="disabled")

    # Hauteur automatique (min 4, max 35 lignes)
    n_lines = int(widget.index("end-1c").split(".")[0])
    widget.configure(height=min(max(n_lines, 4), 35))

    return widget


# ──────────────────────────────────────────────────────────
#  Toast notification
# ──────────────────────────────────────────────────────────
def show_toast(root, message: str, duration_ms: int = 2800):
    x = root.winfo_x() + root.winfo_width()  // 2 - 160
    y = root.winfo_y() + root.winfo_height() - 90
    t = ctk.CTkToplevel(root)
    t.geometry(f"320x54+{x}+{y}")
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    ctk.CTkLabel(
        t, text=message,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=C["sidebar"], text_color="white", corner_radius=10,
    ).pack(fill="both", expand=True, padx=4, pady=4)
    t.after(duration_ms, t.destroy)
