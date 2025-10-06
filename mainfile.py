import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

st.set_page_config(page_title="EV & Laadpalen Dashboard NL",
                   layout="wide", page_icon=":electric_plug:")

# --- DATA LAADPAAL: API ophalen & cachen ---
@st.cache_data
def load_laadpaal_data():
    url = "https://api.openchargemap.io/v3/poi/?output=json&countrycode=NL&maxresults=6000&compact=true&verbose=false&key=2960318e-86ae-49e0-82b1-3c8bc6790b41"
    r = requests.get(url)
    laad_json = r.json()
    df_laad = pd.json_normalize(laad_json)
    df_connections = pd.json_normalize(df_laad.Connections)
    df_con = pd.json_normalize(df_connections[0])
    df = pd.concat([df_laad, df_con], axis=1)
    geometry = [Point(xy) for xy in zip(df["AddressInfo.Longitude"], df["AddressInfo.Latitude"])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    return gdf

laadpalen = load_laadpaal_data()

# --- DATA CARS: Upload-widget, geen fout ---
st.sidebar.header("🔍 Upload je voertuigdataset ('cars.pkl')")
uploaded_file = st.sidebar.file_uploader("Kies het bestand", type="pkl")

if uploaded_file is not None:
    cars = pd.read_pickle(uploaded_file)
    file_loaded = True
else:
    st.warning("⚠️ Upload eerst het 'cars.pkl' bestand in de sidebar om de statistieken en grafieken te zien.")
    file_loaded = False

# --- SIDEBAR: Statistieken/Data ---
st.sidebar.header("📊 Overzicht")
st.sidebar.metric("🚗 Totaal laadpunten", int(laadpalen.shape[0]))
if file_loaded:
    st.sidebar.metric("📈 Totaal voertuigen", int(cars.shape[0]))
    max_date = pd.to_datetime(cars['datum_eerste_toelating'], format='%Y%m%d', errors='coerce').max()
    min_date = pd.to_datetime(cars['datum_eerste_toelating'], format='%Y%m%d', errors='coerce').min()
    st.sidebar.caption(f"Peildata: {min_date:%Y-%m} t/m {max_date:%Y-%m}")

# --- TABS: Layout ---
tab1, tab2, tab3 = st.tabs(["📊 EV Trends", "🗺️ Laadpalen Map", "🏆 Top 10 Regio's"])

# --- TAB 1: EV Trends & Brandstof ---
with tab1:
    st.subheader("Cumulatief aantal auto's per brandstofsoort")
    if file_loaded:
        # Brandstof detectie
        def bepaal_brandstof(naam):
            naam = naam.lower()
            if any(x in naam
