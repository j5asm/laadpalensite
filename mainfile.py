
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

st.set_page_config(page_title="EV & Laadpalen Dashboard NL",
                   layout="wide", page_icon=":electric_plug:")

# --- Data Loading & Caching ---
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

@st.cache_data
def load_cars():
    return pd.read_pickle('cars.pkl')

laadpalen = load_laadpaal_data()
cars = load_cars()

# --- Sidebar Filters & Stats ---
st.sidebar.header("🔍 Filters & Statistiek")
provincies = laadpalen["AddressInfo.Title"].dropna().str.extract(r',\s*(.*?)$')[0].unique()
selected_provincie = st.sidebar.selectbox("Provincie (kaart)", options=['Alle'] + [p for p in provincies if isinstance(p, str)])

# Statistiek-overzicht widgets
st.sidebar.metric("🚗 Totaal laadpunten", int(laadpalen.shape[0]))
st.sidebar.metric("📈 Totaal EVs", int(cars.shape[0]))
max_date = cars['datum_eerste_toelating'].max()
min_date = cars['datum_eerste_toelating'].min()
st.sidebar.caption(f"Peildata: {min_date:%Y-%m} t/m {max_date:%Y-%m}")

st.sidebar.download_button("📥 Download laaddata", data=laadpalen.to_csv(), file_name='laadpalen.csv', mime='text/csv')

# --- Tabs Layout ---
tab1, tab2, tab3 = st.tabs(["📊 EV Trends", "🗺️ Laadpalen Map", "🏆 Top 10 Regio's"])

with tab1:
    st.subheader("Cumulatief aantal auto's per brandstofsoort")
    # Brandstof detectie
    def bepaal_brandstof(naam):
        naam = naam.lower()
        if any(x in naam for x in ['ev', 'electric', 'id', 'e-tron']):
            return 'elektrisch'
        elif any(x in naam for x in ['hybrid', 'phev', 'plugin']):
            return 'hybride'
        elif 'diesel' in naam:
            return 'diesel'
        elif 'waterstof' in naam:
            return 'waterstof'
        else:
            return 'benzine'

    cars['brandstof'] = cars['handelsbenaming'].apply(bepaal_brandstof)
    cars['datum_eerste_toelating'] = pd.to_datetime(cars['datum_eerste_toelating'], format='%Y%m%d', errors='coerce')
    groep = cars.groupby([cars['datum_eerste_toelating'].dt.to_period('M'), 'brandstof']).size().unstack().fillna(0).cumsum()
    groep.index = groep.index.astype(str)
    fig1 = px.line(groep.reset_index(), x='datum_eerste_toelating', y=['elektrisch','benzine'],
                   labels={'value':'Aantal voertuigen','datum_eerste_toelating':'Maand'},
                   color_discrete_map={'benzine':'blue','elektrisch':'red'},
                   title="EV vs Benzine — Groeitrend")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Brandstof verdeling historgram")
    histo = cars['brandstof'].value_counts()
    fig2 = px.bar(x=histo.index, y=histo.values, labels={'x':'Brandstof','y':'Aantal'},
                  color=histo.index, color_discrete_map={'benzine':'blue','elektrisch':'red','hybride':'orange'})
    st.plotly_chart(fig2, use_container_width=True)

with tab2:
    st.subheader("Laadpalen in Nederland")
    if selected_provincie != "Alle":
        filter_mask = laadpalen["AddressInfo.Title"].fillna("").str.contains(selected_provincie, na=False)
        laadpalen_to_map = laadpalen[filter_mask]
    else:
        laadpalen_to_map = laadpalen

    m = folium.Map(location=[52.1, 5.3], zoom_start=8)
    marker_cluster = MarkerCluster().add_to(m)
    for _, row in laadpalen_to_map.iterrows():
        folium.Marker(
            location=[row["AddressInfo.Latitude"], row["AddressInfo.Longitude"]],
            popup=f"{row.get('AddressInfo.Title','')}<br>Type: {row.get('ConnectionType.Title','Onbekend')}",
            icon=folium.Icon(color='green', icon='bolt')
        ).add_to(marker_cluster)
    st_folium(m, width=1100, height=650)

with tab3:
    st.subheader("Top 10 regio's met meeste laadpalen")
    laadpalen['Gemeente'] = laadpalen["AddressInfo.Title"].str.split(", ").str[-1]
    top10 = laadpalen['Gemeente'].value_counts().head(10)
    st.table(top10.reset_index().rename(columns={"index":"Gemeente", "Gemeente":"Aantal laadpalen"}))
    st.bar_chart(top10)

    st.subheader("Heatmap snelladers vs gewone laadpalen per regio (extra)")
    laadpalen['is_snel'] = laadpalen['LevelID'] == 3 # Level 3 in OpenChargeMap = snellader
    regio_snel = laadpalen.groupby('Gemeente')['is_snel'].mean().sort_values(ascending=False).head(10)
    st.table(regio_snel.reset_index().rename(columns={'is_snel':'% Snelladers'}))
