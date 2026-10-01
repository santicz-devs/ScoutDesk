import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Buscador de Jugadores",
    page_icon="⚽",
    layout="wide"
)

# -----------------------------
# CARGA DE DATOS
# -----------------------------
ARCHIVO = "jugadores_primera_nacional_con_posicion.csv"

@st.cache_data
def cargar_datos():
    df = pd.read_csv(ARCHIVO, encoding="utf-8-sig")

    def convertir_valor(valor):
        if pd.isna(valor):
            return None

        valor = str(valor).strip().lower()

        if valor == "-":
            return None

        valor = valor.replace("€", "").strip()
        valor = valor.replace(" ", "")

        try:
            if "mill." in valor:
                numero = valor.replace("mill.", "").replace(",", ".")
                return float(numero) * 1_000_000

            if "mil" in valor:
                numero = valor.replace("mil", "").replace(",", ".")
                return float(numero) * 1_000

            numero = valor.replace(",", ".")
            return float(numero)

        except (ValueError, TypeError):
            return None

    df["Valor_num"] = df["Valor de mercado"].apply(convertir_valor)
    return df


df = cargar_datos()

# -----------------------------
# ESTILOS
# -----------------------------
st.markdown("""
<style>
    .main-title {
        font-size: 2.6rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        color: #666;
        font-size: 1.05rem;
        margin-bottom: 2rem;
    }

    .result-number {
        font-size: 2rem;
        font-weight: 800;
    }

    div[data-testid="stMetric"] {
        border: 1px solid #e5e5e5;
        border-radius: 14px;
        padding: 12px;
        background: #fafafa;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# ENCABEZADO
# -----------------------------
st.markdown('<div class="main-title">⚽ Buscador de Jugadores</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Explorá jugadores de Primera Nacional mediante filtros de equipo, posición, edad y valor de mercado.</div>',
    unsafe_allow_html=True
)

# -----------------------------
# SIDEBAR / FILTROS
# -----------------------------
with st.sidebar:
    st.header("Filtros")

    equipos = sorted(df["Equipo"].dropna().unique().tolist())
    posiciones = sorted(df["Posición"].dropna().unique().tolist())

    equipo = st.selectbox(
        "Equipo",
        ["Todos"] + equipos
    )

    posicion = st.selectbox(
        "Posición",
        ["Todas"] + posiciones
    )

    st.divider()

    st.subheader("Edad")

    edad_min = st.number_input(
        "Edad mínima",
        min_value=0,
        max_value=100,
        value=0,
        step=1
    )

    edad_max = st.number_input(
        "Edad máxima",
        min_value=0,
        max_value=100,
        value=100,
        step=1
    )

    st.subheader("Valor de mercado")

    valor_min = st.number_input(
        "Mínimo (€)",
        min_value=0.0,
        value=0.0,
        step=5000.0,
        format="%.0f"
    )

    valor_max = st.number_input(
        "Máximo (€)",
        min_value=0.0,
        value=10_000_000.0,
        step=5000.0,
        format="%.0f"
    )

    st.divider()

    limpiar = st.button("Restablecer filtros", use_container_width=True)

# -----------------------------
# APLICAR FILTROS
# -----------------------------
if limpiar:
    st.rerun()

resultados = df.copy()

if equipo != "Todos":
    resultados = resultados[
        resultados["Equipo"].str.lower() == equipo.lower()
    ]

if posicion != "Todas":
    resultados = resultados[
        resultados["Posición"].fillna("").str.lower() == posicion.lower()
    ]

if edad_min > edad_max:
    st.error("La edad mínima no puede ser mayor que la edad máxima.")
    st.stop()

resultados = resultados[
    (resultados["Edad"] >= edad_min) &
    (resultados["Edad"] <= edad_max)
]

if valor_min > valor_max:
    st.error("El valor mínimo no puede ser mayor que el valor máximo.")
    st.stop()

resultados = resultados[
    resultados["Valor_num"].notna() &
    (resultados["Valor_num"] >= valor_min) &
    (resultados["Valor_num"] <= valor_max)
]

# -----------------------------
# MÉTRICAS
# -----------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Jugadores encontrados", len(resultados))

with col2:
    st.metric("Equipos", resultados["Equipo"].nunique())

with col3:
    if len(resultados) > 0:
        promedio = resultados["Valor_num"].mean()
        st.metric("Valor promedio", f"€{promedio:,.0f}")
    else:
        st.metric("Valor promedio", "—")

st.divider()

# -----------------------------
# RESULTADOS
# -----------------------------
st.subheader("Resultados")

if resultados.empty:
    st.warning("No se encontraron jugadores con los filtros seleccionados.")
else:
    columnas = [
        "Equipo",
        "Jugador",
        "Posición",
        "Edad",
        "Valor de mercado"
    ]

    tabla = resultados[columnas].copy()

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Equipo": st.column_config.TextColumn("Equipo"),
            "Jugador": st.column_config.TextColumn("Jugador"),
            "Posición": st.column_config.TextColumn("Posición"),
            "Edad": st.column_config.NumberColumn("Edad", format="%d"),
            "Valor de mercado": st.column_config.TextColumn("Valor de mercado")
        }
    )

st.caption(f"Base de datos: {len(df):,} jugadores.")
