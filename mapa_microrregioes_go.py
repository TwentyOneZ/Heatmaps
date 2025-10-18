import pandas as pd
import numpy as np
from unidecode import unidecode
import folium
from folium.plugins import HeatMap

# ==== ARQUIVOS ====
ARQ_LINHAS = "transmissao_go.csv"

# ==== PARÂMETROS ====
COL_CAP = "VAL_CAPACOPERLONGACOMLIMIT"  # escolha da métrica de capacidade
ESTADO_ALVO = "GO"

# ==== 1) Carrega dados ====
df = pd.read_csv(ARQ_LINHAS)

# Padroniza cidades e estados (tira acentos e espaços)
def norm(s):
    return unidecode(str(s)).strip().upper()

for c in ["CIDADE_DE","ESTADO_DE","CIDADE_PARA","ESTADO_PARA"]:
    df[c] = df[c].apply(norm)

# Foca em linhas com pelo menos uma ponta em GO
df = df[(df["ESTADO_DE"] == ESTADO_ALVO) | (df["ESTADO_PARA"] == ESTADO_ALVO)].copy()

# Garante numérico
df[COL_CAP] = pd.to_numeric(df[COL_CAP], errors="coerce").fillna(0.0)
df["LAT_SUBESTACAO_DE"] = pd.to_numeric(df["LAT_SUBESTACAO_DE"], errors="coerce")
df["LON_SUBESTACAO_DE"] = pd.to_numeric(df["LON_SUBESTACAO_DE"], errors="coerce")
df["LAT_SUBESTACAO_PARA"] = pd.to_numeric(df["LAT_SUBESTACAO_PARA"], errors="coerce")
df["LON_SUBESTACAO_PARA"] = pd.to_numeric(df["LON_SUBESTACAO_PARA"], errors="coerce")

# ==== 2) Constrói dataset cidade (DE e PARA), dividindo 50/50 a capacidade ====
a_de_cid = df[["CIDADE_DE","LAT_SUBESTACAO_DE","LON_SUBESTACAO_DE",COL_CAP]].copy()
a_de_cid.columns = ["CHAVE","LAT","LON","CAP"]
a_de_cid["CAP"] = a_de_cid["CAP"] * 0.5

a_para_cid = df[["CIDADE_PARA","LAT_SUBESTACAO_PARA","LON_SUBESTACAO_PARA",COL_CAP]].copy()
a_para_cid.columns = ["CHAVE","LAT","LON","CAP"]
a_para_cid["CAP"] = a_para_cid["CAP"] * 0.5

ac_cid = pd.concat([a_de_cid, a_para_cid], ignore_index=True)

# Remove registros sem coordenadas
ac_cid = ac_cid.dropna(subset=["LAT","LON"]).copy()

# ==== 3) Agrega por cidade: soma da capacidade e média ponderada de LAT/LON ====
# Primeiro somamos capacidade por cidade
cap_por_cidade = ac_cid.groupby("CHAVE", as_index=False)["CAP"].sum().rename(columns={"CAP":"CAP_TOTAL"})

# Depois calculamos a média ponderada das coordenadas
def media_ponderada_coords(g):
    cap_sum = g["CAP"].sum()
    if cap_sum <= 0:
        return pd.Series({"LAT": g["LAT"].mean(), "LON": g["LON"].mean(), "N_PONTOS": len(g)})
    return pd.Series({
        "LAT": np.average(g["LAT"], weights=g["CAP"]),
        "LON": np.average(g["LON"], weights=g["CAP"]),
        "N_PONTOS": len(g)
    })

coords_pond = ac_cid.groupby("CHAVE").apply(media_ponderada_coords).reset_index()

# Junta tudo
grp = cap_por_cidade.merge(coords_pond, on="CHAVE", how="left")

# ==== 4) Normaliza a CAP_TOTAL para virar PESO (0–1) do HeatMap ====
cap_min, cap_max = grp["CAP_TOTAL"].min(), grp["CAP_TOTAL"].max()
if cap_max > cap_min:
    grp["PESO"] = (grp["CAP_TOTAL"] - cap_min) / (cap_max - cap_min)
else:
    grp["PESO"] = 1.0  # todas as cidades com a mesma capacidade

# ==== 5) Cria o mapa Folium ====
# centro aproximado de Goiás
m = folium.Map(location=[-15.95, -50.1], zoom_start=6, tiles="CartoDB positron")

# Heatmap (intensidade = PESO)
heat_data = grp[["LAT","LON","PESO"]].values.tolist()
heat_layer = folium.FeatureGroup(name="Heatmap Capacidade (cidade)", show=True)
HeatMap(heat_data, radius=25, blur=15, max_zoom=10, gradient={0.0: '#00ff00', 0.5: '#808000', 1.0: '#ffff00'}).add_to(heat_layer)
heat_layer.add_to(m)

# Camada de marcadores com popup (opcional para inspeção)
mk_layer = folium.FeatureGroup(name="Marcadores (cidade)", show=False)
for _, r in grp.iterrows():
    popup = folium.Popup(
        f"<b>Cidade:</b> {str(r['CHAVE']).title()}<br>"
        f"<b>Capacidade total (proxy):</b> {r['CAP_TOTAL']:.1f} (unid.)<br>"
        f"<b>Pontos ponderados:</b> {int(r['N_PONTOS'])}",
        max_width=350
    )
    folium.CircleMarker(
        location=[r["LAT"], r["LON"]],
        radius=6,
        fill=True,
        fill_opacity=0.9,
        popup=popup
    ).add_to(mk_layer)
mk_layer.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# ==== 6) Exporta ====
m.save("heatmap_capacidade_cidades_GO.html")
grp.sort_values("CAP_TOTAL", ascending=False).to_csv("ranking_capacidade_cidades_GO.csv", index=False)

print("Mapa salvo em: heatmap_capacidade_cidades_GO.html")
print("Ranking salvo em: ranking_capacidade_cidades_GO.csv")

# ==== 7) (Opcional) Top 10 no console ====
top10 = grp.sort_values("CAP_TOTAL", ascending=False).head(10)
print("\nTop 10 cidades por capacidade (proxy):")
print(top10[["CHAVE","CAP_TOTAL"]])
