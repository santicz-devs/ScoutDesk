"""
ScoutDesk | Scouting del Ascenso argentino (Transfermarkt)

Un solo archivo que reemplaza a los scripts sueltos:

  - Acasusso.py / pruebapos.py  -> extraer un plantel desde un HTML
  - ExtraerTodos.py             -> extraer una carpeta entera de HTML
  - ExtraerEquipos.py           -> lista de equipos de la liga (HTML)
  - Programa.py                 -> buscador con filtros (equipo, posición,
                                   edad, valor de mercado)

Uso:  python ScoutDesk.py
Requiere: pandas, beautifulsoup4  (opcional: matplotlib para los gráficos)
"""

import os
import re
import unicodedata
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import quote_plus, urljoin

import pandas as pd
from bs4 import BeautifulSoup

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ============================================================
# CONFIGURACIÓN
# ============================================================

APP_NAME = "ScoutDesk | Scouting"

BG = "#101820"
PANEL = "#192633"
PANEL_ALT = "#223342"
BORDER = "#35495A"
TEXT = "#EDF2F7"
MUTED = "#A9B7C4"
ACCENT = "#45D6A5"
ENTRY_BG = "#111D28"

VISIBLE_COLUMNS = [
    "Equipo",
    "Jugador",
    "Posición",
    "Edad",
    "Valor de mercado",
    "Nacionalidad",
]

# Campos internos: no se muestran en la tabla.
COLUMNS = VISIBLE_COLUMNS + [
    "URL Transfermarkt",
    "URL Equipo",
]

NUMERIC_COLUMNS = ["Edad"]

TEAM_MAP = {
    "agro": "CA Agropecuario",
    "almagro": "Club Almagro",
    "almirante": "Club Almirante Brown",
    "atlanta": "CA Atlanta",
    "bolivar": "Club Ciudad de Bolívar",
    "centralnorte": "CA Central Norte",
    "chaca": "CA Chacarita Juniors",
    "chaco": "CA Chaco For Ever",
    "chicago": "CA Nueva Chicago",
    "colegiales": "CA Colegiales",
    "colon": "CA Colón",
    "defbelgrano": "CA Defensores de Belgrano",
    "estudiantesba": "CA Estudiantes",
    "ferro": "Club Ferro Carril Oeste",
    "gimj": "CA Gimnasia y Esgrima (Jujuy)",
    "godoycruz": "CD Godoy Cruz Antonio Tomba",
    "guemes": "CA Güemes",
    "losandes": "CA Los Andes",
    "landes": "CA Los Andes",
    "madryn": "CS Deportivo Madryn",
    "maipu": "Club Deportivo Maipú",
    "midland": "CA Ferrocarril Midland",
    "mitre": "CA Mitre",
    "moron": "Club Deportivo Morón",
    "patronato": "CA Patronato",
    "quilmes": "Quilmes AC",
    "racingcordoba": "CA Racing (Córdoba)",
    "rafaela": "AMSD Atlético de Rafaela",
    "sanmartinsj": "CA San Martín (San Juan)",
    "sanmartint": "CA San Martín (Tucumán)",
    "sanmiguel": "CA San Miguel",
    "stelmo": "CA San Telmo",
    "tsuarez": "Club Tristán Suárez",
    "tristansuarez": "Club Tristán Suárez",
    "temperley": "CA Temperley",
    "acassuso": "CA Acassuso",
    "acasusso": "CA Acassuso",
    "allboys": "CA All Boys",
    "gimytiro": "Club de Gimnasia y Tiro",
}


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def clean(value):
    """Normaliza un valor a texto."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return re.sub(r"\s+", " ", str(value)).strip()


def strip_accents(text):
    """Quita tildes: 'Tristán Suárez' -> 'Tristan Suarez'."""
    text = unicodedata.normalize("NFKD", clean(text))
    return "".join(c for c in text if not unicodedata.combining(c))


def team_key(text):
    """Clave para comparar nombres de equipos sin tildes ni símbolos."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(text).lower())


def parse_int(text):
    """Convierte un texto a entero, o None si está vacío o no es válido."""
    text = clean(text)
    return int(text) if text.isdigit() else None


def parse_market_value(value):
    """Convierte valores de mercado a números cuando es posible."""
    text = clean(value).lower()

    if not text or text in {"-", "?", "n/a", "nan", "none"}:
        return None

    text = (
        text.replace("€", "")
        .replace(" ", "")
        .replace(".", "")
    )

    multiplier = 1

    for marker in (
        "millones", "millón", "millon", "mill.", "mill", "mn"
    ):
        if marker in text:
            multiplier = 1_000_000
            text = text.replace(marker, "")
            break
    else:
        for marker in ("mil", "k"):
            if marker in text:
                multiplier = 1_000
                text = text.replace(marker, "")
                break

    text = text.replace(",", ".")

    try:
        return float(text) * multiplier
    except (ValueError, TypeError):
        return None


def team_from_filename(path):
    """Intenta identificar el equipo a partir del nombre del archivo."""
    stem = os.path.splitext(os.path.basename(path))[0]

    stem = re.sub(
        r"[_\s-]*(jugadores|players|plantel|squad)$",
        "",
        stem,
        flags=re.I,
    )

    key = team_key(stem)

    for alias, team in TEAM_MAP.items():
        if alias in key:
            return team

    return stem.replace("_", " ").replace("-", " ").strip() or "Sin equipo"


def read_csv_flexible(path):
    """Intenta leer CSV con distintas codificaciones."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue

    return pd.read_csv(path)


def normalize_data(df, team_override=None):
    """Normaliza columnas, tipos y datos importados."""
    df = df.copy()

    aliases = {
        "equipo": "Equipo",
        "club": "Equipo",
        "team": "Equipo",
        "jugador": "Jugador",
        "nombre": "Jugador",
        "player": "Jugador",
        "name": "Jugador",
        "posición": "Posición",
        "posicion": "Posición",
        "position": "Posición",
        "edad": "Edad",
        "age": "Edad",
        "valor de mercado": "Valor de mercado",
        "valor": "Valor de mercado",
        "market value": "Valor de mercado",
        "market_value": "Valor de mercado",
        "nacionalidad": "Nacionalidad",
        "nationality": "Nacionalidad",
        "country": "Nacionalidad",
        "país": "Nacionalidad",
        "pais": "Nacionalidad",
        "url transfermarkt": "URL Transfermarkt",
        "transfermarkt url": "URL Transfermarkt",
        "profile url": "URL Transfermarkt",
        "url perfil": "URL Transfermarkt",
        "url equipo": "URL Equipo",
        "team url": "URL Equipo",
    }

    rename = {}

    for col in df.columns:
        key = clean(col).lower()

        if key in aliases:
            rename[col] = aliases[key]

    df = df.rename(columns=rename)

    if "Jugador" not in df.columns:
        raise ValueError(
            "El archivo debe incluir una columna Jugador, Player o Name."
        )

    if "Equipo" not in df.columns:
        df["Equipo"] = team_override or "Sin equipo"
    elif team_override:
        df["Equipo"] = team_override

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    text_columns = [
        "Equipo",
        "Jugador",
        "Posición",
        "Valor de mercado",
        "Nacionalidad",
        "URL Transfermarkt",
        "URL Equipo",
    ]

    for col in text_columns:
        df[col] = df[col].map(clean)

    df["Edad"] = pd.to_numeric(
        df["Edad"]
        .astype(str)
        .str.extract(r"(\d{1,2})")[0],
        errors="coerce",
    )

    df = df[df["Jugador"].ne("")]
    df["Equipo"] = df["Equipo"].replace("", "Sin equipo")

    return (
        df[COLUMNS]
        .drop_duplicates(
            subset=["Equipo", "Jugador"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def extract_nationality(row):
    """Busca nacionalidades en atributos HTML habituales."""
    found = []

    for node in row.select(
        "img[alt], img[title], [title], [aria-label]"
    ):
        for attr in ("title", "alt", "aria-label"):
            value = clean(node.get(attr, ""))

            if not value:
                continue

            value = re.sub(
                r"^(nationality|nacionalidad|flag|bandera|country|pa[ií]s)"
                r"\s*[:\-]?\s*",
                "",
                value,
                flags=re.I,
            )

            if (
                value
                and value.lower() not in {
                    "flag", "nationality", "nacionalidad",
                    "bandera", "country",
                }
                and value not in found
            ):
                found.append(value)

    return ", ".join(found[:3])


# ============================================================
# EXTRACCIÓN HTML DE TRANSFERMARKT
# ============================================================

LEAGUE_HEADERS = {"equipo", "club", "team", "verein"}
PLAYER_HEADERS = ("jugador", "player", "spieler")


def read_soup(path):
    """Abre un HTML guardado y devuelve el objeto BeautifulSoup."""
    with open(path, "r", encoding="utf-8", errors="replace") as file:
        return BeautifulSoup(file.read(), "html.parser")


def _headers(table):
    return [
        clean(th.get_text(" ", strip=True)).casefold()
        for th in table.find_all("th")
    ]


def find_league_table(soup):
    """Tabla de equipos de una liga (la que tiene la columna 'Equipo')."""
    for table in soup.find_all("table"):
        headers = _headers(table)

        if any(h in LEAGUE_HEADERS for h in headers) and not any(
            p in h for h in headers for p in PLAYER_HEADERS
        ):
            return table

    return None


def page_kind(soup):
    """
    Distingue el HTML de una liga ('league') del de un plantel ('roster').
    Un plantel tiene una columna 'Jugadores'; la liga, una columna 'Equipo'.
    """
    if find_league_table(soup) is None:
        return "roster"

    has_players_header = any(
        p in h
        for table in soup.find_all("table")
        for h in _headers(table)
        for p in PLAYER_HEADERS
    )

    return "roster" if has_players_header else "league"


def parse_league_soup(soup):
    """Devuelve [{'name': ..., 'url': ...}] con los equipos de la liga."""
    table = find_league_table(soup)

    if table is None:
        raise ValueError(
            "No se encontró la tabla de equipos (columna 'Equipo')."
        )

    teams = []
    seen = set()

    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)

        if len(cells) < 2:
            continue

        link = next(
            (
                a
                for a in cells[1].find_all("a", href=True)
                if clean(a.get_text(" ", strip=True))
            ),
            None,
        )

        if link is None:
            continue

        name = clean(link.get_text(" ", strip=True))
        key = team_key(name)

        if key in seen:
            continue

        seen.add(key)

        teams.append({
            "name": name,
            "url": urljoin(
                "https://www.transfermarkt.com",
                clean(link.get("href", "")),
            ),
        })

    if not teams:
        raise ValueError("La tabla de equipos no tiene filas válidas.")

    return teams


def parse_html_roster(path, soup=None):
    """Extrae jugadores de un HTML guardado de Transfermarkt."""
    if soup is None:
        soup = read_soup(path)

    table = None

    # Preferir las tablas de planteles de Transfermarkt.
    for candidate in soup.select("table.items"):
        rows = candidate.select("tbody tr")

        if any(
            len(row.find_all("td", recursive=False)) >= 5
            and row.select_one("td a[href]")
            for row in rows[:10]
        ):
            table = candidate
            break

    # Alternativa para HTML con encabezados reconocibles.
    if table is None:
        for candidate in soup.find_all("table"):
            headers = [
                clean(th.get_text(" ", strip=True)).lower()
                for th in candidate.find_all("th")
            ]

            has_player = any(
                "jugador" in h or "nombre" in h or "player" in h
                for h in headers
            )

            if has_player:
                table = candidate
                break

    if table is None:
        raise ValueError(
            "No se encontró una tabla de jugadores. "
            "Guardá el HTML de la plantilla del club."
        )

    h1 = soup.find("h1")
    team = clean(h1.get_text(" ", strip=True)) if h1 else ""

    if not team or "transfermarkt" in team.lower():
        team = team_from_filename(path)

    # Intentar localizar el enlace de la página del equipo.
    team_url = ""

    for link in soup.select("a[href]"):
        href = clean(link.get("href", ""))

        if (
            href
            and team
            and clean(link.get_text(" ", strip=True)).casefold()
            == team.casefold()
        ):
            team_url = urljoin(
                "https://www.transfermarkt.com",
                href,
            )
            break

    rows_out = []

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)

        if len(cells) < 5:
            continue

        # En Transfermarkt, el enlace del jugador suele estar en la segunda celda.
        link = (
            cells[1].select_one("td.hauptlink a[href]")
            or cells[1].select_one("a[href]")
        )

        if not link:
            continue

        name = clean(link.get_text(" ", strip=True))

        if not name:
            continue

        age_text = clean(cells[2].get_text(" ", strip=True))
        age_match = re.search(r"\((\d{1,2})\)", age_text)

        if not age_match:
            age_match = re.search(
                r"(?:^|\s)(1[5-9]|[2-5]\d)\s*$",
                age_text,
            )

        age = age_match.group(1) if age_match else ""

        pos_node = cells[1].select_one("tr:nth-child(2) td")
        position = (
            clean(pos_node.get_text(" ", strip=True))
            if pos_node
            else ""
        )

        nationality = (
            extract_nationality(cells[3])
            if len(cells) > 3
            else ""
        )

        profile_url = urljoin(
            "https://www.transfermarkt.com",
            clean(link.get("href", "")),
        )

        rows_out.append({
            "Equipo": team,
            "Jugador": name,
            "Posición": position,
            "Edad": age,
            "Valor de mercado": clean(
                cells[4].get_text(" ", strip=True)
            ),
            "Nacionalidad": nationality,
            "URL Transfermarkt": profile_url,
            "URL Equipo": team_url,
        })

    if not rows_out:
        raise ValueError(
            "Se encontró una tabla, pero no se pudieron reconocer "
            "sus filas de jugadores."
        )

    return normalize_data(
        pd.DataFrame(rows_out),
        team_override=team,
    )


# ============================================================
# APLICACIÓN
# ============================================================

class ScoutDesk(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1360x850")
        self.minsize(1080, 700)
        self.configure(bg=BG)

        self.df = pd.DataFrame(columns=COLUMNS)
        self.current_file = None

        # Equipos de la liga (para saber cuáles faltan importar).
        self.league = []

        # Orden de la tabla de jugadores y última búsqueda (para exportar).
        self.sort_col = None
        self.sort_desc = False
        self._filtered = pd.DataFrame(columns=COLUMNS)

        self._style()
        self._build_ui()
        self.refresh_all()

    # --------------------------------------------------------
    # ESTILO
    # --------------------------------------------------------

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("PanelAlt.TFrame", background=PANEL_ALT)

        style.configure(
            "TLabel",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 10),
        )

        style.configure(
            "Muted.TLabel",
            background=BG,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )

        style.configure(
            "PanelTitle.TLabel",
            background=PANEL,
            foreground=TEXT,
            font=("Segoe UI", 12, "bold"),
        )

        style.configure(
            "TButton",
            background=PANEL_ALT,
            foreground=TEXT,
            padding=(10, 8),
            font=("Segoe UI", 9, "bold"),
        )

        style.map(
            "TButton",
            background=[("active", "#30485A")],
        )

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#10251E",
            padding=(12, 9),
            font=("Segoe UI", 9, "bold"),
        )

        style.map(
            "Accent.TButton",
            background=[("active", "#7CE8C2")],
        )

        style.configure(
            "TEntry",
            fieldbackground=ENTRY_BG,
            foreground=TEXT,
            insertcolor=TEXT,
            padding=7,
        )

        style.configure(
            "TCombobox",
            fieldbackground=ENTRY_BG,
            background=ENTRY_BG,
            foreground=TEXT,
            padding=7,
        )

        style.map(
            "TCombobox",
            fieldbackground=[("readonly", ENTRY_BG)],
            foreground=[("readonly", TEXT)],
        )

        style.configure(
            "Treeview",
            background=ENTRY_BG,
            fieldbackground=ENTRY_BG,
            foreground=TEXT,
            rowheight=30,
            font=("Segoe UI", 9),
            borderwidth=0,
        )

        style.configure(
            "Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            padding=(8, 10),
            font=("Segoe UI", 9, "bold"),
        )

        style.map(
            "Treeview",
            background=[("selected", "#226B59")],
            foreground=[("selected", "white")],
        )

        style.configure(
            "TNotebook",
            background=BG,
            borderwidth=0,
        )

        style.configure(
            "TNotebook.Tab",
            background=PANEL_ALT,
            foreground=TEXT,
            padding=(15, 10),
            font=("Segoe UI", 10, "bold"),
        )

        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#10251E")],
        )

    def panel(self, parent, padding=14):
        return ttk.Frame(
            parent,
            style="Panel.TFrame",
            padding=padding,
        )

    # --------------------------------------------------------
    # INTERFAZ PRINCIPAL
    # --------------------------------------------------------

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 14))

        ttk.Label(
            header,
            text="SCOUTDESK  /  SCOUTING LOCAL",
            foreground=ACCENT,
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Gestión de planteles y análisis de equipos",
            font=("Segoe UI", 21, "bold"),
        ).pack(anchor="w", pady=(3, 2))

        ttk.Label(
            header,
            text="Importá datos, analizá planteles y detectá perfiles interesantes.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0, 13))

        self.total_players = self._stat_card(
            cards, "JUGADORES", "0", 0
        )
        self.total_teams = self._stat_card(
            cards, "EQUIPOS", "0", 1
        )
        self.source_label = self._stat_card(
            cards, "FUENTE", "Sin datos", 2
        )

        for i in range(3):
            cards.columnconfigure(i, weight=1, uniform="stats")

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)

        self.tab_dashboard = ttk.Frame(self.tabs, padding=12)
        self.tab_teams = ttk.Frame(self.tabs, padding=12)
        self.tab_players = ttk.Frame(self.tabs, padding=12)
        self.tab_import = ttk.Frame(self.tabs, padding=12)

        self.tabs.add(
            self.tab_dashboard,
            text="  Dashboard de equipos  ",
        )
        self.tabs.add(
            self.tab_teams,
            text="  Equipos y planteles  ",
        )
        self.tabs.add(
            self.tab_players,
            text="  Buscar jugadores  ",
        )
        self.tabs.add(
            self.tab_import,
            text="  Importar / guardar  ",
        )

        self._build_dashboard()
        self._build_teams()
        self._build_players()
        self._build_import()

        footer = tk.Frame(
            root,
            bg=PANEL_ALT,
            padx=10,
            pady=7,
        )
        footer.pack(fill="x", pady=(10, 0))

        self.status = tk.StringVar(
            value="Listo. Importá un CSV para comenzar."
        )

        tk.Label(
            footer,
            textvariable=self.status,
            bg=PANEL_ALT,
            fg=MUTED,
            anchor="w",
        ).pack(fill="x")

    def _stat_card(self, parent, caption, value, col):
        card = ttk.Frame(
            parent,
            style="PanelAlt.TFrame",
            padding=(14, 10),
        )

        card.grid(
            row=0,
            column=col,
            sticky="ew",
            padx=(0 if col == 0 else 6, 0 if col == 2 else 6),
        )

        tk.Label(
            card,
            text=caption,
            bg=PANEL_ALT,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        label = tk.Label(
            card,
            text=value,
            bg=PANEL_ALT,
            fg=TEXT,
            font=("Segoe UI", 16, "bold"),
        )
        label.pack(anchor="w", pady=(3, 0))

        return label

    # --------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------

    def _build_dashboard(self):
        top = self.panel(self.tab_dashboard)
        top.pack(fill="x", pady=(0, 10))

        ttk.Label(
            top,
            text="Dashboard del equipo",
            style="PanelTitle.TLabel",
        ).pack(side="left")

        ttk.Label(
            top,
            text="Equipo:",
            background=PANEL,
            foreground=MUTED,
        ).pack(side="left", padx=(24, 8))

        self.dashboard_team = tk.StringVar(
            value="Seleccioná un equipo"
        )

        self.dashboard_combo = ttk.Combobox(
            top,
            textvariable=self.dashboard_team,
            state="readonly",
            width=34,
            values=[],
        )
        self.dashboard_combo.pack(side="left")
        self.dashboard_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.update_dashboard(),
        )

        ttk.Button(
            top,
            text="Actualizar",
            command=self.update_dashboard,
        ).pack(side="left", padx=8)

        metrics = ttk.Frame(self.tab_dashboard)
        metrics.pack(fill="x", pady=(0, 10))

        self.metric_labels = {}

        metric_defs = [
            ("players", "JUGADORES"),
            ("age", "EDAD PROMEDIO"),
            ("value", "VALOR PROMEDIO"),
            ("nationality", "NACIONALIDAD PRINCIPAL"),
        ]

        for i, (key, caption) in enumerate(metric_defs):
            card = ttk.Frame(
                metrics,
                style="PanelAlt.TFrame",
                padding=(12, 10),
            )

            card.grid(
                row=i // 2,
                column=i % 2,
                sticky="nsew",
                padx=4,
                pady=4,
            )

            tk.Label(
                card,
                text=caption,
                bg=PANEL_ALT,
                fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w")

            value_label = tk.Label(
                card,
                text="—",
                bg=PANEL_ALT,
                fg=TEXT,
                font=("Segoe UI", 14, "bold"),
                wraplength=300,
            )
            value_label.pack(anchor="w", pady=(5, 0))

            self.metric_labels[key] = value_label

        for i in range(2):
            metrics.columnconfigure(i, weight=1, uniform="metric")
            metrics.rowconfigure(i, weight=1)

        chart_area = ttk.Frame(self.tab_dashboard)
        chart_area.pack(fill="both", expand=True)

        self.chart_host = ttk.Frame(
            chart_area,
            style="Panel.TFrame",
            padding=8,
        )
        self.chart_host.pack(fill="both", expand=True)

        if not HAS_MPL:
            ttk.Label(
                self.chart_host,
                text="Para ver gráficos instalá matplotlib: pip install matplotlib",
                background=PANEL,
                foreground=MUTED,
            ).pack(padx=20, pady=20)

        ttk.Label(
            self.tab_dashboard,
            text="Las métricas se calculan a partir de los datos disponibles.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    # --------------------------------------------------------
    # EQUIPOS
    # --------------------------------------------------------

    def _build_teams(self):
        top = self.panel(self.tab_teams)
        top.pack(fill="x", pady=(0, 10))

        ttk.Label(
            top,
            text="Equipos importados",
            style="PanelTitle.TLabel",
        ).pack(side="left")

        ttk.Button(
            top,
            text="Eliminar equipo",
            command=self.delete_team,
        ).pack(side="right")

        ttk.Button(
            top,
            text="Agregar jugador",
            command=self.add_player_dialog,
            style="Accent.TButton",
        ).pack(side="right", padx=8)

        ttk.Button(
            top,
            text="Cargar liga (HTML)",
            command=self.import_league_html,
        ).pack(side="right")

        body = self.panel(self.tab_teams, 8)
        body.pack(fill="both", expand=True)

        cols = (
            "Equipo",
            "Estado",
            "Jugadores",
            "Edad media",
            "Con nacionalidad",
            "Con valor",
        )

        self.team_tree = ttk.Treeview(
            body,
            columns=cols,
            show="headings",
        )

        widths = {
            "Equipo": 330,
            "Estado": 110,
            "Jugadores": 110,
            "Edad media": 120,
            "Con nacionalidad": 150,
            "Con valor": 120,
        }

        for col in cols:
            self.team_tree.heading(col, text=col)
            self.team_tree.column(
                col,
                width=widths[col],
                anchor="w" if col == "Equipo" else "center",
            )

        self.team_tree.pack(fill="both", expand=True)
        self.team_tree.bind(
            "<Double-1>",
            self.open_selected_team,
        )

        self.team_tree.tag_configure("pending", foreground=MUTED)

        ttk.Label(
            self.tab_teams,
            text=(
                "Doble clic: equipo importado -> dashboard · "
                "equipo pendiente -> abre su página en Transfermarkt."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    # --------------------------------------------------------
    # BUSCADOR DE JUGADORES
    # --------------------------------------------------------

    def _build_players(self):
        filters = self.panel(self.tab_players)
        filters.pack(fill="x", pady=(0, 10))

        ttk.Label(
            filters,
            text="Buscar jugadores",
            style="PanelTitle.TLabel",
        ).pack(anchor="w")

        row = ttk.Frame(filters, style="Panel.TFrame")
        row.pack(fill="x", pady=(9, 0))

        self.search_name = tk.StringVar()
        self.search_team = tk.StringVar(value="Todos")
        self.search_position = tk.StringVar(value="Todas")

        for label, var, values in [
            ("Nombre", self.search_name, None),
            ("Equipo", self.search_team, ["Todos"]),
            ("Posición", self.search_position, ["Todas"]),
        ]:
            block = ttk.Frame(row, style="Panel.TFrame")
            block.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 10),
            )

            ttk.Label(
                block,
                text=label,
                background=PANEL,
                foreground=MUTED,
            ).pack(anchor="w")

            if values is None:
                widget = ttk.Entry(block, textvariable=var)
                widget.bind(
                    "<KeyRelease>",
                    lambda _event: self.apply_player_filters(),
                )
            else:
                widget = ttk.Combobox(
                    block,
                    textvariable=var,
                    state="readonly",
                    values=values,
                )

                if label == "Equipo":
                    self.player_team_combo = widget
                else:
                    self.player_position_combo = widget

                widget.bind(
                    "<<ComboboxSelected>>",
                    lambda _event: self.apply_player_filters(),
                )

            widget.pack(fill="x", pady=(4, 0))

        row2 = ttk.Frame(filters, style="Panel.TFrame")
        row2.pack(fill="x", pady=(9, 0))

        self.search_age_min = tk.StringVar()
        self.search_age_max = tk.StringVar()
        self.search_value_min = tk.StringVar()
        self.search_value_max = tk.StringVar()

        for label, var in [
            ("Edad mínima", self.search_age_min),
            ("Edad máxima", self.search_age_max),
            ("Valor mínimo (€)", self.search_value_min),
            ("Valor máximo (€)", self.search_value_max),
        ]:
            block = ttk.Frame(row2, style="Panel.TFrame")
            block.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 10),
            )

            ttk.Label(
                block,
                text=label,
                background=PANEL,
                foreground=MUTED,
            ).pack(anchor="w")

            entry = ttk.Entry(block, textvariable=var)
            entry.pack(fill="x", pady=(4, 0))
            entry.bind(
                "<KeyRelease>",
                lambda _event: self.apply_player_filters(),
            )

        ttk.Label(
            filters,
            text="Valor: 100000 · 100 mil · 1,5 mill.  (se excluyen los jugadores sin valor)",
            background=PANEL,
            foreground=MUTED,
        ).pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(filters, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(
            actions,
            text="Limpiar filtros",
            command=self.clear_player_filters,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="Eliminar jugador",
            command=self.delete_player,
        ).pack(side="left", padx=8)

        ttk.Button(
            actions,
            text="Exportar resultados",
            command=self.export_results,
        ).pack(side="left")

        self.results_label = ttk.Label(
            actions,
            text="0 resultados",
            background=PANEL,
            foreground=ACCENT,
        )
        self.results_label.pack(side="right")

        ttk.Label(
            actions,
            text="Doble clic en un jugador para abrir Transfermarkt",
            background=PANEL,
            foreground=MUTED,
        ).pack(side="right", padx=12)

        body = self.panel(self.tab_players, 8)
        body.pack(fill="both", expand=True)

        self.player_tree = ttk.Treeview(
            body,
            columns=VISIBLE_COLUMNS,
            show="headings",
        )

        widths = {
            "Equipo": 190,
            "Jugador": 210,
            "Posición": 140,
            "Edad": 65,
            "Valor de mercado": 140,
            "Nacionalidad": 160,
        }

        for col in VISIBLE_COLUMNS:
            self.player_tree.heading(
                col,
                text=col,
                command=lambda c=col: self.sort_players_by(c),
            )
            self.player_tree.column(
                col,
                width=widths[col],
                anchor=(
                    "w"
                    if col in (
                        "Equipo",
                        "Jugador",
                        "Posición",
                        "Nacionalidad",
                    )
                    else "center"
                ),
            )

        yscroll = ttk.Scrollbar(
            body,
            orient="vertical",
            command=self.player_tree.yview,
        )

        self.player_tree.configure(
            yscrollcommand=yscroll.set
        )

        self.player_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        yscroll.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.player_tree.bind(
            "<Double-1>",
            self.open_selected_player,
        )

    # --------------------------------------------------------
    # IMPORTACIÓN Y REGISTRO
    # --------------------------------------------------------

    def _build_import(self):
        panel = self.panel(self.tab_import)
        panel.pack(fill="x", pady=(0, 10))

        ttk.Label(
            panel,
            text="Importar planteles y unir bases",
            style="PanelTitle.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            panel,
            text=(
                "Extraé planteles desde los HTML guardados de Transfermarkt "
                "(uno, varios o una carpeta entera). Si entre ellos está la "
                "página de equipos de la liga, se reconoce sola y se usa para "
                "marcar qué planteles faltan. También podés importar o unir "
                "CSV. Se conservan posición, edad, valor, nacionalidad y enlaces."
            ),
            background=PANEL,
            foreground=MUTED,
            wraplength=1000,
        ).pack(anchor="w", pady=(5, 10))

        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill="x")

        ttk.Button(
            row,
            text="Extraer HTML",
            command=self.import_html,
            style="Accent.TButton",
        ).pack(side="left")

        ttk.Button(
            row,
            text="Extraer carpeta HTML",
            command=self.import_html_folder,
            style="Accent.TButton",
        ).pack(side="left", padx=6)

        ttk.Button(
            row,
            text="Importar CSV(s)",
            command=self.import_csv,
        ).pack(side="left", padx=6)

        ttk.Button(
            row,
            text="Juntar carpeta CSV",
            command=self.join_csv_folder,
        ).pack(side="left", padx=6)

        ttk.Button(
            row,
            text="Cargar base",
            command=self.load_csv,
        ).pack(side="left", padx=6)

        ttk.Button(
            row,
            text="Guardar base",
            command=self.save_csv,
        ).pack(side="left", padx=6)

        logpanel = self.panel(self.tab_import)
        logpanel.pack(fill="both", expand=True)

        ttk.Label(
            logpanel,
            text="Información de la base",
            style="PanelTitle.TLabel",
        ).pack(anchor="w")

        self.log = tk.Text(
            logpanel,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            height=12,
            padx=10,
            pady=10,
        )

        self.log.pack(
            fill="both",
            expand=True,
            pady=(8, 0),
        )

        self.log.insert(
            "1.0",
            "ScoutDesk listo.\n\n"
            "Podés extraer planteles HTML, importar CSV o unir "
            "archivos de una carpeta. La aplicación conserva una "
            "base y permite guardarla.",
        )

    def _log(self, title, messages):
        self.log.insert(
            "end",
            "\n\n" + title + "\n" + "\n".join(messages),
        )
        self.log.see("end")

    # --------------------------------------------------------
    # DUPLICADOS E IMPORTACIÓN
    # --------------------------------------------------------

    def _append_imported(self, frames):
        """
        Incorpora datos y pregunta antes de sobrescribir jugadores
        que ya existan en la base.
        """
        if not frames:
            return 0

        incoming = normalize_data(
            pd.concat(frames, ignore_index=True)
        )

        incoming = incoming.drop_duplicates(
            subset=["Equipo", "Jugador"],
            keep="last",
        ).reset_index(drop=True)

        if self.df.empty:
            self.df = incoming
            self.refresh_all()
            return len(incoming)

        existing_keys = set(
            zip(
                self.df["Equipo"].astype(str).str.casefold(),
                self.df["Jugador"].astype(str).str.casefold(),
            )
        )

        incoming_keys = [
            (
                clean(row["Equipo"]).casefold(),
                clean(row["Jugador"]).casefold(),
            )
            for _, row in incoming.iterrows()
        ]

        duplicate_mask = [
            key in existing_keys
            for key in incoming_keys
        ]

        duplicate_count = sum(duplicate_mask)

        if duplicate_count:
            overwrite = messagebox.askyesno(
                "Jugadores duplicados",
                f"Se encontraron {duplicate_count} jugadores "
                "que ya existen en la base.\n\n"
                "¿Querés actualizar sus datos con los nuevos registros?\n\n"
                "Sí: actualizar los duplicados.\n"
                "No: conservar los datos existentes.",
                parent=self,
            )

            if overwrite:
                # Evita perder una URL previa si el nuevo archivo no la trae.
                old_lookup = {}

                for _, row in self.df.iterrows():
                    key = (
                        clean(row["Equipo"]).casefold(),
                        clean(row["Jugador"]).casefold(),
                    )
                    old_lookup[key] = row

                for idx, key in enumerate(incoming_keys):
                    if key not in old_lookup:
                        continue

                    old_row = old_lookup[key]

                    for field in ("URL Transfermarkt", "URL Equipo"):
                        if (
                            not clean(incoming.at[idx, field])
                            and clean(old_row.get(field, ""))
                        ):
                            incoming.at[idx, field] = old_row[field]

                self.df = self.df[
                    ~self.df.apply(
                        lambda row: (
                            clean(row["Equipo"]).casefold(),
                            clean(row["Jugador"]).casefold(),
                        ) in {
                            incoming_keys[i]
                            for i, duplicated in enumerate(duplicate_mask)
                            if duplicated
                        },
                        axis=1,
                    )
                ].copy()

            else:
                incoming = incoming.loc[
                    [not duplicated for duplicated in duplicate_mask]
                ].copy()

        if incoming.empty:
            self.status.set(
                "No se incorporaron jugadores nuevos."
            )
            return 0

        added = len(incoming)

        self.df = pd.concat(
            [self.df, incoming],
            ignore_index=True,
        )

        self.df = self.df.drop_duplicates(
            subset=["Equipo", "Jugador"],
            keep="last",
        ).reset_index(drop=True)

        self.refresh_all()
        return added

    def _pending_teams(self):
        """Equipos de la liga cuyo plantel todavía no se importó."""
        loaded = {
            team_key(team)
            for team in self.df["Equipo"].dropna().map(clean)
            if team
        }

        return [
            team
            for team in self.league
            if team_key(team["name"]) not in loaded
        ]

    def _process_html_paths(
        self,
        paths,
        title="EXTRACCIÓN HTML",
        force_league=False,
    ):
        """
        Procesa una lista de HTML. Cada archivo se reconoce solo:
        plantel de un club o lista de equipos de la liga.
        """
        frames = []
        messages = []
        failed = []
        league_count = 0

        for path in paths:
            filename = os.path.basename(path)

            try:
                soup = read_soup(path)

                if force_league or page_kind(soup) == "league":
                    teams = parse_league_soup(soup)
                    self.league = teams
                    league_count = len(teams)

                    messages.append(
                        f"OK · {filename}: lista de la liga, "
                        f"{len(teams)} equipos"
                    )
                    continue

                data = parse_html_roster(path, soup=soup)
                frames.append(data)

                messages.append(
                    f"OK · {filename}: {len(data)} jugadores · "
                    f"{clean(data['Equipo'].iloc[0])}"
                )

            except Exception as exc:
                failed.append(filename)
                messages.append(f"ERROR · {filename}: {exc}")

        added = self._append_imported(frames)

        if league_count:
            self.refresh_all()

        summary = [
            "",
            f"Planteles procesados: {len(frames)}",
            f"Jugadores incorporados: {added}",
        ]

        if league_count:
            summary.append(
                f"Equipos de la liga: {league_count} "
                f"({len(self._pending_teams())} sin plantel importado)"
            )

        if failed:
            summary.append(
                f"Archivos con problemas ({len(failed)}): "
                + ", ".join(failed)
            )

        self._log(title, messages + summary)

        ok = len(frames) + (1 if league_count else 0)

        self.status.set(
            f"HTML procesados: {ok} de {len(paths)} archivos."
        )

        if ok == 0:
            messagebox.showwarning(
                "Sin datos",
                "No se pudo extraer nada. Revisá el registro "
                "en la pestaña Importar / guardar.",
            )
        elif failed:
            messagebox.showwarning(
                "Archivos con problemas",
                f"{len(failed)} archivos no se pudieron procesar:\n\n"
                + "\n".join(failed[:15])
                + "\n\nEl detalle está en el registro.",
            )

    def import_html(self):
        paths = filedialog.askopenfilenames(
            title="Seleccionar HTML (planteles y/o liga)",
            filetypes=[("Páginas HTML", "*.html *.htm")],
        )

        if paths:
            self._process_html_paths(paths)

    def import_html_folder(self):
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta con los HTML"
        )

        if not folder:
            return

        paths = sorted(
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith((".html", ".htm"))
        )

        if not paths:
            messagebox.showinfo(
                "Carpeta vacía",
                "No se encontraron archivos HTML en esa carpeta.",
            )
            return

        self._process_html_paths(
            paths,
            title="EXTRACCIÓN HTML (CARPETA)",
        )

    def import_league_html(self):
        path = filedialog.askopenfilename(
            title="Seleccionar HTML de la liga (lista de equipos)",
            filetypes=[("Páginas HTML", "*.html *.htm")],
        )

        if path:
            self._process_html_paths(
                [path],
                title="LISTA DE EQUIPOS DE LA LIGA",
                force_league=True,
            )

    def join_csv_folder(self):
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta con CSV por equipo"
        )

        if not folder:
            return

        paths = sorted(
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith(".csv")
        )

        if not paths:
            messagebox.showinfo(
                "Carpeta vacía",
                "No se encontraron archivos CSV en esa carpeta.",
            )
            return

        frames = []
        messages = []

        for path in paths:
            filename = os.path.basename(path)

            if filename.lower() in {
                "equipos_primera_nacional_2026.csv",
                "jugadores_primera_nacional.csv",
                "scoutdesk_base.csv",
            }:
                continue

            try:
                raw = read_csv_flexible(path)

                has_team_col = any(
                    clean(col).lower() in {"equipo", "club", "team"}
                    for col in raw.columns
                )

                team = None if has_team_col else team_from_filename(path)
                data = normalize_data(raw, team_override=team)

                if data.empty:
                    messages.append(
                        f"OMITIDO · {filename}: no hay jugadores reconocibles"
                    )
                    continue

                frames.append(data)

                messages.append(
                    f"OK · {filename}: {len(data)} jugadores · "
                    f"{data['Equipo'].iloc[0]}"
                )

            except Exception as exc:
                messages.append(
                    f"ERROR · {filename}: {exc}"
                )

        added = self._append_imported(frames)

        self._log(
            "JUNTADOR DE CSV",
            messages + [
                f"Total incorporado: {added} jugadores de {len(frames)} archivos."
            ],
        )

        self.status.set(
            f"Juntador: {len(frames)} archivos procesados."
        )

        if frames:
            messagebox.showinfo(
                "Unificación terminada",
                f"Se incorporaron {added} jugadores de "
                f"{len(frames)} archivos.\n\n"
                "Usá Guardar base para conservar el resultado.",
            )
        else:
            messagebox.showwarning(
                "Sin jugadores",
                "No se pudo incorporar ningún CSV. Revisá el registro.",
            )

    def import_csv(self):
        paths = filedialog.askopenfilenames(
            title="Importar CSV",
            filetypes=[("Archivos CSV", "*.csv")],
        )

        if not paths:
            return

        frames = []
        messages = []

        for path in paths:
            try:
                raw = read_csv_flexible(path)

                has_team_col = any(
                    clean(col).lower() in {"equipo", "club", "team"}
                    for col in raw.columns
                )

                team = None if has_team_col else team_from_filename(path)
                data = normalize_data(raw, team_override=team)

                frames.append(data)

                messages.append(
                    f"OK · {os.path.basename(path)}: {len(data)} jugadores"
                )

            except Exception as exc:
                messages.append(
                    f"ERROR · {os.path.basename(path)}: {exc}"
                )

        added = self._append_imported(frames)

        self._log(
            "IMPORTACIÓN CSV",
            messages + [f"Total incorporado: {added} jugadores."],
        )

        self.status.set(
            f"Importación terminada: {added} jugadores incorporados."
        )

        if not frames:
            messagebox.showwarning(
                "Sin datos",
                "No se pudo importar ningún CSV. Revisá el registro.",
            )

    # --------------------------------------------------------
    # CARGAR Y GUARDAR
    # --------------------------------------------------------

    def load_csv(self):
        path = filedialog.askopenfilename(
            title="Cargar base ScoutDesk",
            filetypes=[("Archivos CSV", "*.csv")],
        )

        if not path:
            return

        try:
            raw = read_csv_flexible(path)
            self.df = normalize_data(raw)
            self.current_file = path

            self.refresh_all()

            self.status.set(
                f"Base cargada: {len(self.df)} jugadores."
            )

        except Exception as exc:
            messagebox.showerror(
                "Error al cargar",
                str(exc),
            )

    def save_csv(self):
        if self.df.empty:
            messagebox.showwarning(
                "Base vacía",
                "Importá jugadores antes de guardar.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Guardar base ScoutDesk",
            defaultextension=".csv",
            initialfile="scoutdesk_base.csv",
            filetypes=[("Archivos CSV", "*.csv")],
        )

        if not path:
            return

        try:
            self.df[COLUMNS].to_csv(
                path,
                index=False,
                encoding="utf-8-sig",
            )

            self.current_file = path

            self.source_label.configure(
                text=os.path.basename(path)[:24]
            )

            self.status.set(
                f"Base guardada: {os.path.basename(path)}"
            )

            messagebox.showinfo(
                "Base guardada",
                f"Se guardaron {len(self.df)} jugadores.",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error al guardar",
                str(exc),
            )

    # --------------------------------------------------------
    # ACTUALIZACIÓN DE LA INTERFAZ
    # --------------------------------------------------------

    def refresh_all(self):
        self.df = self.df.reindex(columns=COLUMNS)

        teams = sorted(
            team
            for team in self.df["Equipo"].dropna().map(clean).unique()
            if team
        )

        self.total_players.configure(
            text=f"{len(self.df):,}"
        )

        pending = self._pending_teams()

        self.total_teams.configure(
            text=(
                f"{len(self.league) - len(pending)} de {len(self.league)}"
                if self.league
                else str(len(teams))
            )
        )

        self.source_label.configure(
            text=(
                os.path.basename(self.current_file)[:24]
                if self.current_file
                else ("Datos en sesión" if len(self.df) else "Sin datos")
            )
        )

        self.dashboard_combo.configure(values=teams)

        if teams:
            if self.dashboard_team.get() not in teams:
                self.dashboard_team.set(teams[0])
        else:
            self.dashboard_team.set("Seleccioná un equipo")

        self.player_team_combo.configure(
            values=["Todos"] + teams
        )

        positions = sorted(
            position
            for position in self.df["Posición"].dropna().map(clean).unique()
            if position
        )

        self.player_position_combo.configure(
            values=["Todas"] + positions
        )

        for item in self.team_tree.get_children():
            self.team_tree.delete(item)

        for team, group in self.df.groupby("Equipo", dropna=False):
            team = clean(team) or "Sin equipo"
            age = group["Edad"].mean()

            self.team_tree.insert(
                "",
                "end",
                values=(
                    team,
                    "Importado",
                    len(group),
                    f"{age:.1f}" if pd.notna(age) else "—",
                    int(group["Nacionalidad"].map(clean).ne("").sum()),
                    int(group["Valor de mercado"].map(clean).ne("").sum()),
                ),
            )

        for item in pending:
            self.team_tree.insert(
                "",
                "end",
                values=(item["name"], "Pendiente", 0, "—", 0, 0),
                tags=("pending",),
            )

        self.apply_player_filters()
        self.update_dashboard()

    def update_dashboard(self):
        team = self.dashboard_team.get()

        if (
            not team
            or team == "Seleccioná un equipo"
            or self.df.empty
        ):
            for label in self.metric_labels.values():
                label.configure(text="—")

            self.draw_charts(pd.DataFrame(columns=COLUMNS))
            return

        group = self.df[
            self.df["Equipo"].astype(str) == team
        ].copy()

        count = len(group)
        age = group["Edad"].mean()

        values = group["Valor de mercado"].map(parse_market_value)
        valid_values = values.dropna()

        nationality = group["Nacionalidad"].map(clean)
        nationality = nationality[nationality.ne("")]
        top_nat = nationality.value_counts()

        nat_text = (
            f"{top_nat.index[0]} ({top_nat.iloc[0]})"
            if not top_nat.empty
            else "Sin datos"
        )

        self.metric_labels["players"].configure(
            text=str(count)
        )

        self.metric_labels["age"].configure(
            text=f"{age:.1f} años" if pd.notna(age) else "Sin datos"
        )

        self.metric_labels["value"].configure(
            text=(
                f"€{valid_values.mean():,.0f} promedio"
                if not valid_values.empty
                else "Sin datos"
            )
        )

        self.metric_labels["nationality"].configure(
            text=nat_text
        )

        self.draw_charts(group)

    def draw_charts(self, group):
        if not HAS_MPL:
            return

        for child in self.chart_host.winfo_children():
            child.destroy()

        fig = Figure(
            figsize=(12, 4.2),
            dpi=100,
            facecolor=PANEL,
        )

        ax1 = fig.add_subplot(131)
        ax2 = fig.add_subplot(132)
        ax3 = fig.add_subplot(133)

        for ax in (ax1, ax2, ax3):
            ax.set_facecolor(PANEL)
            ax.tick_params(colors=TEXT, labelsize=8)

            for spine in ax.spines.values():
                spine.set_color(BORDER)

            ax.title.set_color(TEXT)

        if group.empty:
            ax1.text(
                0.5, 0.5, "Importá datos para ver gráficos",
                color=MUTED, ha="center", va="center",
                transform=ax1.transAxes,
            )

            ax2.text(
                0.5, 0.5, "La distribución de edades aparecerá aquí",
                color=MUTED, ha="center", va="center",
                transform=ax2.transAxes,
            )

            ax3.text(
                0.5, 0.5, "Las nacionalidades aparecerán aquí",
                color=MUTED, ha="center", va="center",
                transform=ax3.transAxes,
            )

        else:
            positions = group["Posición"].map(clean)
            positions = positions[positions.ne("")].value_counts().head(8)

            if positions.empty:
                ax1.text(
                    0.5, 0.5, "Sin datos de posición",
                    color=MUTED, ha="center", va="center",
                    transform=ax1.transAxes,
                )
            else:
                ax1.barh(
                    list(positions.index)[::-1],
                    list(positions.values)[::-1],
                    color=ACCENT,
                )
                ax1.set_title("Jugadores por posición", fontsize=11, pad=10)
                ax1.set_xlabel("Cantidad", color=MUTED, fontsize=8)

            ages = group["Edad"].dropna()

            if ages.empty:
                ax2.text(
                    0.5, 0.5, "Sin datos de edad",
                    color=MUTED, ha="center", va="center",
                    transform=ax2.transAxes,
                )
            else:
                lower = max(14, int(ages.min()) - 1)
                upper = min(61, int(ages.max()) + 3)
                bins = list(range(lower, upper, 3))

                if len(bins) < 2:
                    bins = [int(ages.min()) - 1, int(ages.max()) + 2]

                ax2.hist(
                    ages,
                    bins=bins,
                    color=ACCENT,
                    edgecolor=PANEL,
                    rwidth=0.9,
                )

                ax2.set_title("Distribución de edades", fontsize=11, pad=10)
                ax2.set_xlabel("Edad", color=MUTED, fontsize=8)
                ax2.set_ylabel("Jugadores", color=MUTED, fontsize=8)

            nationalities = group["Nacionalidad"].map(clean)
            nationalities = (
                nationalities[nationalities.ne("")]
                .value_counts()
                .head(6)
            )

            if nationalities.empty:
                ax3.text(
                    0.5, 0.5, "Sin datos de nacionalidad",
                    color=MUTED, ha="center", va="center",
                    transform=ax3.transAxes,
                )
            else:
                ax3.barh(
                    list(nationalities.index)[::-1],
                    list(nationalities.values)[::-1],
                    color=ACCENT,
                )

                ax3.set_title("Nacionalidades principales", fontsize=11, pad=10)
                ax3.set_xlabel("Jugadores", color=MUTED, fontsize=8)

        fig.tight_layout(pad=2)

        canvas = FigureCanvasTkAgg(
            fig,
            master=self.chart_host,
        )

        canvas.draw()
        canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

    # --------------------------------------------------------
    # FILTROS DE JUGADORES
    # --------------------------------------------------------

    def apply_player_filters(self):
        result = self.df.copy()

        # Búsqueda por nombre sin distinguir mayúsculas ni tildes.
        query = strip_accents(self.search_name.get()).strip().casefold()

        if query:
            result = result[
                result["Jugador"]
                .astype(str)
                .map(strip_accents)
                .str.casefold()
                .str.contains(re.escape(query), na=False)
            ]

        if self.search_team.get() != "Todos":
            result = result[
                result["Equipo"].astype(str)
                == self.search_team.get()
            ]

        if self.search_position.get() != "Todas":
            result = result[
                result["Posición"].astype(str)
                == self.search_position.get()
            ]

        # Edad (mínima y máxima)
        age_min = parse_int(self.search_age_min.get())
        age_max = parse_int(self.search_age_max.get())

        if age_min is not None:
            result = result[result["Edad"] >= age_min]

        if age_max is not None:
            result = result[result["Edad"] <= age_max]

        # Valor de mercado (mínimo y máximo, en euros)
        value_min = parse_market_value(self.search_value_min.get())
        value_max = parse_market_value(self.search_value_max.get())

        if value_min is not None or value_max is not None:
            values = pd.to_numeric(
                result["Valor de mercado"].map(parse_market_value),
                errors="coerce",
            )

            mask = values.notna()

            if value_min is not None:
                mask &= values >= value_min

            if value_max is not None:
                mask &= values <= value_max

            result = result[mask]

        # Orden por columna
        if self.sort_col:
            if self.sort_col == "Valor de mercado":
                key = pd.to_numeric(
                    result["Valor de mercado"].map(parse_market_value),
                    errors="coerce",
                )
            elif self.sort_col == "Edad":
                key = pd.to_numeric(result["Edad"], errors="coerce")
            else:
                key = (
                    result[self.sort_col]
                    .astype(str)
                    .map(strip_accents)
                    .str.casefold()
                )

            result = (
                result.assign(_orden=key)
                .sort_values(
                    "_orden",
                    ascending=not self.sort_desc,
                    na_position="last",
                    kind="stable",
                )
                .drop(columns="_orden")
            )

        self._filtered = result

        # Flecha de orden en los encabezados
        for col in VISIBLE_COLUMNS:
            arrow = ""

            if col == self.sort_col:
                arrow = "  ▼" if self.sort_desc else "  ▲"

            self.player_tree.heading(col, text=col + arrow)

        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

        for _, row in result.iterrows():
            values = []

            for col in VISIBLE_COLUMNS:
                value = row[col]

                if col in NUMERIC_COLUMNS:
                    value = "" if pd.isna(value) else int(value)
                else:
                    value = clean(value)

                values.append(value)

            self.player_tree.insert(
                "",
                "end",
                values=values,
            )

        self.results_label.configure(
            text=f"{len(result):,} resultados"
        )

    def sort_players_by(self, col):
        """Ordena la tabla al hacer clic en un encabezado."""
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = col
            # Valor: de mayor a menor. El resto: ascendente.
            self.sort_desc = col == "Valor de mercado"

        self.apply_player_filters()

    def clear_player_filters(self):
        self.search_name.set("")
        self.search_team.set("Todos")
        self.search_position.set("Todas")
        self.search_age_min.set("")
        self.search_age_max.set("")
        self.search_value_min.set("")
        self.search_value_max.set("")
        self.sort_col = None
        self.sort_desc = False
        self.apply_player_filters()

    def export_results(self):
        """Guarda en CSV los jugadores que muestra la tabla."""
        if self._filtered is None or self._filtered.empty:
            messagebox.showinfo(
                "Sin resultados",
                "No hay jugadores en la tabla para exportar.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Exportar resultados",
            defaultextension=".csv",
            initialfile="resultados_scouting.csv",
            filetypes=[("Archivos CSV", "*.csv")],
        )

        if not path:
            return

        try:
            self._filtered[
                VISIBLE_COLUMNS + ["URL Transfermarkt"]
            ].to_csv(path, index=False, encoding="utf-8-sig")

            self.status.set(
                f"Resultados exportados: {len(self._filtered)} jugadores "
                f"en {os.path.basename(path)}"
            )

        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc))

    # --------------------------------------------------------
    # ABRIR PERFIL DE TRANSFERMARKT
    # --------------------------------------------------------

    def open_selected_player(self, event=None):
        if event:
            item = self.player_tree.identify_row(event.y)

            if not item:
                return

            self.player_tree.selection_set(item)

        selection = self.player_tree.selection()

        if not selection:
            return

        values = self.player_tree.item(
            selection[0],
            "values",
        )

        if not values:
            return

        team, player = values[0], values[1]

        matches = self.df[
            (self.df["Equipo"].astype(str) == str(team))
            & (self.df["Jugador"].astype(str) == str(player))
        ]

        if matches.empty:
            return

        row = matches.iloc[0]

        profile_url = clean(
            row.get("URL Transfermarkt", "")
        )

        team_url = clean(
            row.get("URL Equipo", "")
        )

        if profile_url.startswith(("https://", "http://")):
            webbrowser.open(profile_url)
            self.status.set(
                f"Abriendo perfil de {player}."
            )
            return

        if team_url.startswith(("https://", "http://")):
            webbrowser.open(team_url)
            self.status.set(
                f"No hay perfil guardado. Abriendo equipo de {player}."
            )
            return

        search_url = (
            "https://www.transfermarkt.com/schnellsuche/"
            "ergebnis/schnellsuche"
            f"?query={quote_plus(player)}"
        )

        webbrowser.open(search_url)

        self.status.set(
            f"No hay perfil guardado. Buscando a {player} en Transfermarkt."
        )

    # --------------------------------------------------------
    # ALTA Y ELIMINACIÓN DE JUGADORES
    # --------------------------------------------------------

    def add_player_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Agregar jugador")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()

        fields = VISIBLE_COLUMNS + [
            "URL Transfermarkt",
            "URL Equipo",
        ]

        variables = {}

        for i, field in enumerate(fields):
            tk.Label(
                dialog,
                text=field,
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 10),
            ).grid(
                row=i,
                column=0,
                sticky="w",
                padx=14,
                pady=5,
            )

            var = tk.StringVar()

            ttk.Entry(
                dialog,
                textvariable=var,
                width=34,
            ).grid(
                row=i,
                column=1,
                padx=14,
                pady=5,
            )

            variables[field] = var

        def save():
            if (
                not variables["Equipo"].get().strip()
                or not variables["Jugador"].get().strip()
            ):
                messagebox.showwarning(
                    "Faltan datos",
                    "Equipo y jugador son obligatorios.",
                    parent=dialog,
                )
                return

            data = pd.DataFrame(
                [[variables[col].get().strip() for col in fields]],
                columns=fields,
            )

            try:
                normalized = normalize_data(data)

                key_team = clean(normalized.iloc[0]["Equipo"]).casefold()
                key_player = clean(normalized.iloc[0]["Jugador"]).casefold()

                existing = self.df[
                    self.df.apply(
                        lambda row: (
                            clean(row["Equipo"]).casefold() == key_team
                            and clean(row["Jugador"]).casefold() == key_player
                        ),
                        axis=1,
                    )
                ]

                if not existing.empty:
                    overwrite = messagebox.askyesno(
                        "Jugador duplicado",
                        f"{key_player.title()} ya existe en {key_team.title()}.\n\n"
                        "¿Querés actualizar sus datos?",
                        parent=dialog,
                    )

                    if not overwrite:
                        return

                    old_row = existing.iloc[0]

                    for field in ("URL Transfermarkt", "URL Equipo"):
                        if (
                            not clean(normalized.iloc[0][field])
                            and clean(old_row.get(field, ""))
                        ):
                            normalized.at[0, field] = old_row[field]

                    self.df = self.df[
                        ~self.df.apply(
                            lambda row: (
                                clean(row["Equipo"]).casefold() == key_team
                                and clean(row["Jugador"]).casefold() == key_player
                            ),
                            axis=1,
                        )
                    ]

                self.df = pd.concat(
                    [self.df, normalized],
                    ignore_index=True,
                )

                self.df = self.df.drop_duplicates(
                    subset=["Equipo", "Jugador"],
                    keep="last",
                ).reset_index(drop=True)

                self.refresh_all()
                dialog.destroy()
                self.status.set("Jugador guardado.")

            except Exception as exc:
                messagebox.showerror(
                    "Error",
                    str(exc),
                    parent=dialog,
                )

        ttk.Button(
            dialog,
            text="Cancelar",
            command=dialog.destroy,
        ).grid(
            row=len(fields),
            column=0,
            padx=14,
            pady=12,
        )

        ttk.Button(
            dialog,
            text="Guardar jugador",
            command=save,
            style="Accent.TButton",
        ).grid(
            row=len(fields),
            column=1,
            padx=14,
            pady=12,
        )

    def delete_team(self):
        selection = self.team_tree.selection()

        if not selection:
            messagebox.showinfo(
                "Seleccioná un equipo",
                "Elegí un equipo de la lista.",
            )
            return

        team = self.team_tree.item(
            selection[0],
            "values",
        )[0]

        count = int(
            (self.df["Equipo"].astype(str) == team).sum()
        )

        if count == 0:
            messagebox.showinfo(
                "Equipo pendiente",
                "Ese equipo todavía no tiene jugadores importados.",
            )
            return

        if messagebox.askyesno(
            "Eliminar equipo",
            f"¿Eliminar {team} y sus {count} jugadores de la base actual?",
        ):
            self.df = self.df[
                self.df["Equipo"].astype(str) != team
            ].reset_index(drop=True)

            self.refresh_all()

            self.status.set(
                f"Equipo eliminado de la sesión: {team}. "
                "Guardá la base para conservar el cambio."
            )

    def delete_player(self):
        selection = self.player_tree.selection()

        if not selection:
            messagebox.showinfo(
                "Seleccioná un jugador",
                "Elegí un jugador de la tabla.",
            )
            return

        values = self.player_tree.item(
            selection[0],
            "values",
        )

        team, player = values[0], values[1]

        if messagebox.askyesno(
            "Eliminar jugador",
            f"¿Eliminar a {player} de {team}?",
        ):
            self.df = self.df[
                ~(
                    (self.df["Equipo"].astype(str) == team)
                    & (self.df["Jugador"].astype(str) == player)
                )
            ].reset_index(drop=True)

            self.refresh_all()

            self.status.set(
                f"Jugador eliminado: {player}. Guardá la base para conservar el cambio."
            )

    # --------------------------------------------------------
    # NAVEGACIÓN ENTRE EQUIPOS
    # --------------------------------------------------------

    def open_selected_team(self, event=None):
        selection = self.team_tree.selection()

        if not selection:
            return

        team = self.team_tree.item(
            selection[0],
            "values",
        )[0]

        # Equipo de la liga sin plantel: abrir su página en Transfermarkt.
        if "pending" in self.team_tree.item(selection[0], "tags"):
            url = next(
                (
                    item["url"]
                    for item in self.league
                    if item["name"] == team
                ),
                "",
            )

            if url.startswith(("https://", "http://")):
                webbrowser.open(url)

                self.status.set(
                    f"Abriendo {team} en Transfermarkt. Guardá la página "
                    "del plantel como HTML y extraela."
                )
            else:
                self.status.set(
                    f"{team} no tiene enlace guardado. Extraé su HTML."
                )

            return

        self.dashboard_team.set(team)
        self.update_dashboard()
        self.tabs.select(self.tab_dashboard)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    app = ScoutDesk()
    app.mainloop()