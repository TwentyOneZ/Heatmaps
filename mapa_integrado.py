import os
import json
import pandas as pd
import numpy as np
from unidecode import unidecode
import folium
from folium.plugins import HeatMap
from folium.features import DivIcon
from folium.features import GeoJsonTooltip
import math
from html import escape  # para escapar nomes no HTML

# =========================
# ARQUIVOS DE ENTRADA
# =========================
ARQ_LINHAS        = "transmissao_go.csv"
ARQ_USINAS_SOLAR  = "usinas.solar.csv"
ARQ_USINAS_EOLICA = "usinas.eolica.csv"
GEOJSON_MICRO     = "microrregioes_go.json"

# =========================
# PARÂMETROS
# =========================
COL_CAP = "VAL_CAPACOPERLONGACOMLIMIT"
ESTADO_ALVO = "GO"

# Gradientes
GRADIENT_TRANSMISSAO = {0.0: '#00ff00', 0.5: '#808000', 1.0: '#ffff00'}   # verde -> oliva -> amarelo
GRADIENT_USINAS      = {0.0: '#0000ff', 1.0: '#ff0000'}                   # azul -> vermelho

# Heatmap (usinas) - raio variável por score
N_BINS_USINAS        = 6
MIN_RADIUS_USINAS    = 10
MAX_RADIUS_USINAS    = 40
BLUR_GLOBAL_HEAT     = 15
MAX_ZOOM_GLOBAL_HEAT = 10
GRADIENT_GLOBAL      = GRADIENT_USINAS

# Centro aproximado de Goiás (fallback)
GOIAS_CENTER = (-15.95, -50.1)
ZOOM_INICIAL = 6

EARTH_KM  = 6371.0088
PTS_POR_KM = 0.5

def norm(s):
    return unidecode(str(s)).strip().upper()

def value_to_color(value, vmin, vmax):
    if pd.isna(value):
        return '#808080'
    if vmax == vmin:
        red = blue = 128
    else:
        t = (value - vmin) / (vmax - vmin)
        t = max(0.0, min(1.0, float(t)))
        red = int(t * 255)
        blue = int((1.0 - t) * 255)
    return f'#{red:02x}00{blue:02x}'

# ----------------- HeatMap com raio variável por score -----------------
def _add_usinas_heatmap_variable_radius(parent_group, lat, lon, weights_norm,
                                        n_bins=N_BINS_USINAS,
                                        rmin=MIN_RADIUS_USINAS,
                                        rmax=MAX_RADIUS_USINAS,
                                        blur=BLUR_GLOBAL_HEAT,
                                        max_zoom=MAX_ZOOM_GLOBAL_HEAT,
                                        gradient=GRADIENT_GLOBAL):
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    w   = np.asarray(weights_norm, float)
    if len(w) == 0:
        return
    w = np.clip(w, 0.0, 1.0)

    edges = np.linspace(0.0, 1.0 + 1e-12, n_bins + 1)
    radii = np.linspace(rmin, rmax, n_bins).astype(int)

    for i in range(n_bins):
        lo, hi = edges[i], edges[i+1]
        mask = (w >= lo) & (w < hi)
        if not np.any(mask):
            continue
        data_bin = np.c_[lat[mask], lon[mask], w[mask]].tolist()
        HeatMap(
            data_bin,
            radius=int(radii[i]),
            blur=blur,
            max_zoom=max_zoom,
            gradient=gradient,
            min_opacity=0.1
        ).add_to(parent_group)


# ----------------- Carrega e agrega usinas (por arquivo) -----------------
def carregar_usinas_agrupadas(csv_path):
    """
    Agrega por (latitude, longitude) e calcula:
      - fator_capacidade: média
      - nomeUsina: concat único
      - n: contagem
    Retorna (df_grouped, centro_lat, centro_lon) ou None.
    """
    if not os.path.exists(csv_path):
        print(f"[INFO] Arquivo de usinas não encontrado: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    req = ['nomeUsina', 'latitude', 'longitude', 'fator_capacidade']
    faltando = [c for c in req if c not in df.columns]
    if faltando:
        print(f"[ERRO] Faltam colunas no CSV {csv_path}: {faltando}")
        return None

    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df['fator_capacidade'] = pd.to_numeric(df['fator_capacidade'], errors='coerce')
    df = df.dropna(subset=['latitude','longitude','fator_capacidade'])
    if df.empty:
        print(f"[INFO] {csv_path} sem linhas válidas.")
        return None

    grouped = (
        df.groupby(['latitude','longitude'])
          .agg(
              fator_capacidade=('fator_capacidade','mean'),
              nomeUsina=('nomeUsina', lambda s: ' | '.join(sorted(set(map(str, s))))),
              n=('nomeUsina','size')
          ).reset_index()
    )
    centro_lat = grouped['latitude'].mean()
    centro_lon = grouped['longitude'].mean()
    return grouped, centro_lat, centro_lon

# ----------------- Merge de nomes para tooltip -----------------
def _merge_names(a, b):
    parts = []
    for s in (a, b):
        if isinstance(s, str) and s.strip():
            parts.extend([p.strip() for p in s.split('|') if p.strip()])
    uniq = sorted(set(parts))
    return ' | '.join(uniq) if uniq else '(sem nome)'

# ----------------- Marcadores: separados por tecnologia -----------------
def add_marcadores_usinas_separados(m, df_solar, df_eolica, fc_global_min, fc_global_max):
    """
    Cria duas camadas de marcadores:
      - 'Marcadores (Solares)': cor baseada em fc_solar (global min/max)
      - 'Marcadores (Eólicos)': cor baseada em fc_eolico (global min/max)
    O tooltip de cada marcador mostra ambos os fatores, se existirem na mesma coordenada.
    """
    s_dict = {}
    e_dict = {}
    if df_solar is not None:
        for _, r in df_solar.iterrows():
            s_dict[(float(r['latitude']), float(r['longitude']))] = (r['nomeUsina'], float(r['fator_capacidade']))
    if df_eolica is not None:
        for _, r in df_eolica.iterrows():
            e_dict[(float(r['latitude']), float(r['longitude']))] = (r['nomeUsina'], float(r['fator_capacidade']))

    # -------- Solares --------
    if df_solar is not None and not df_solar.empty:
        group_s = folium.FeatureGroup(name='Marcadores (Solares)', show=False)
        for (lat, lon), (nome_s, fc_s) in s_dict.items():
            nome_e, fc_e = e_dict.get((lat, lon), (None, np.nan))
            nome = _merge_names(nome_s, nome_e)
            fc_s_str = f"{fc_s:.4f}" if pd.notna(fc_s) else '—'
            fc_e_str = f"{fc_e:.4f}" if pd.notna(fc_e) else '—'

            color = value_to_color(fc_s, fc_global_min, fc_global_max)

            tooltip = folium.Tooltip(
                f"<b>Usina(s):</b> {escape(nome)}<br>"
                f"<b>Fator de Capacidade (Solar):</b> {fc_s_str} <i>(cor baseada em Solar)</i><br>"
                f"<b>Fator de Capacidade (Eólico):</b> {fc_e_str}",
                sticky=True
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=tooltip
            ).add_to(group_s)
        group_s.add_to(m)

    # -------- Eólicas --------
    if df_eolica is not None and not df_eolica.empty:
        group_e = folium.FeatureGroup(name='Marcadores (Eólicos)', show=False)
        for (lat, lon), (nome_e, fc_e) in e_dict.items():
            nome_s, fc_s = s_dict.get((lat, lon), (None, np.nan))
            nome = _merge_names(nome_s, nome_e)
            fc_s_str = f"{fc_s:.4f}" if pd.notna(fc_s) else '—'
            fc_e_str = f"{fc_e:.4f}" if pd.notna(fc_e) else '—'

            color = value_to_color(fc_e, fc_global_min, fc_global_max)

            tooltip = folium.Tooltip(
                f"<b>Usina(s):</b> {escape(nome)}<br>"
                f"<b>Fator de Capacidade (Solar):</b> {fc_s_str}<br>"
                f"<b>Fator de Capacidade (Eólico):</b> {fc_e_str} <i>(cor baseada em Eólico)</i>",
                sticky=True
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=tooltip
            ).add_to(group_e)
        group_e.add_to(m)

# ----------------- Nomes (usinas) como texto – camada desmarcada por padrão -----------------
def add_camada_nomes_usinas(m, df_solar, df_eolica):
    """
    Cria uma camada 'Nomes (usinas)' com rótulos de texto (DivIcon) por coordenada,
    combinando nomes de solar + eólico quando presentes no mesmo ponto.
    """
    if (df_solar is None or df_solar.empty) and (df_eolica is None or df_eolica.empty):
        return

    # índice por coordenada -> nome combinado
    names = {}
    if df_solar is not None and not df_solar.empty:
        for _, r in df_solar.iterrows():
            key = (float(r['latitude']), float(r['longitude']))
            names[key] = _merge_names(names.get(key, ''), r['nomeUsina'])
    if df_eolica is not None and not df_eolica.empty:
        for _, r in df_eolica.iterrows():
            key = (float(r['latitude']), float(r['longitude']))
            names[key] = _merge_names(names.get(key, ''), r['nomeUsina'])

    group_names = folium.FeatureGroup(name='Nomes (usinas)', show=False)

    for (lat, lon), nome in names.items():
        # texto com halo branco para contraste
        html_label = (
            f'<div style="font-size:10pt;font-weight:bold;color:black;'
            f'text-shadow: 0 0 2px #fff, 0 0 4px #fff;">{escape(nome)}</div>'
        )
        folium.Marker(
            location=[lat, lon],
            icon=DivIcon(
                icon_size=(250, 24),
                icon_anchor=(0, 0),
                html=html_label,
                class_name='text-marker'
            )
        ).add_to(group_names)

    group_names.add_to(m)

# ----------------- Microrregiões (GeoJSON) BÁSICO -----------------
def add_camada_microrregioes(m, geojson_path, show=True, fill_opacity=0.15):
    if not os.path.exists(geojson_path):
        print(f"[INFO] GeoJSON não encontrado: {geojson_path}")
        return None
    micro_group = folium.FeatureGroup(name="Microrregiões (vetor)", show=show)
    gj = folium.GeoJson(
        geojson_path,
        name="microrregioes",
        style_function=lambda f: {"fillColor": "#f5f5dc","color": "#444","weight": 1,"fillOpacity": fill_opacity},
        highlight_function=lambda f: {"weight": 2,"color": "#000","fillOpacity": min(fill_opacity + 0.1, 0.6)},
        tooltip=GeoJsonTooltip(
            fields=[c for c in ["nome", "geocodigo"] if c in f"{open(geojson_path, 'r').read()}"],
            aliases=["Microrregião", "Código"],
            sticky=True
        ),
    )
    gj.add_to(micro_group)
    micro_group.add_to(m)
    try:
        b = gj.get_bounds()
        return (b[0][0], b[0][1], b[1][0], b[1][1])
    except Exception:
        return None

# ----------------- Ponto-no-polígono (ray casting) -----------------
def _point_in_ring(lon, lat, ring):
    """
    ring: lista de vértices [[lon,lat], ...] (fechado ou não).
    Retorna True se (lon,lat) está dentro do anel (sem considerar furos).
    """
    x, y = lon, lat
    inside = False
    n = len(ring)
    if n < 3:
        return False
    # garanta que não dependa de ponto repetido final
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i+1) % n][0], ring[(i+1) % n][1]
        # checa interseção com semi-raio horizontal
        cond = ((y1 > y) != (y2 > y))
        if cond:
            xinters = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-30) + x1
            if xinters > x:
                inside = not inside
    return inside

def point_in_polygon(lon, lat, polygon_coords):
    """
    polygon_coords: [ring_externo, hole1, hole2, ...], cada ring é [[lon,lat],...]
    """
    if not polygon_coords:
        return False
    outer = polygon_coords[0]
    if not _point_in_ring(lon, lat, outer):
        return False
    # se cair em algum furo, considerar fora
    for hole in polygon_coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True

def point_in_multipolygon(lon, lat, multipoly_coords):
    """
    multipoly_coords: lista de polygons (cada polygon com seus rings)
    """
    for poly in multipoly_coords:
        if point_in_polygon(lon, lat, poly):
            return True
    return False

# ----------------- Utilidades GeoJSON -----------------
def _load_geojson(geojson_path):
    with open(geojson_path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    features = gj.get('features', [])
    parsed = []
    for idx, feat in enumerate(features):
        props = feat.get('properties', {}) or {}
        geom  = feat.get('geometry', {}) or {}
        gtype = geom.get('type')
        coords = geom.get('coordinates', [])
        # normaliza para lista de polígonos (cada polígono = lista de rings)
        if gtype == 'Polygon':
            polys = [coords]
        elif gtype == 'MultiPolygon':
            polys = coords
        else:
            # ignora (LineString etc.)
            polys = []
        parsed.append({
            'idx': idx,
            'nome': props.get('nome', f'feat_{idx}'),
            'geocodigo': str(props.get('geocodigo', '')),
            'polygons': polys,  # lista de polygons (cada polygon = [ring_externo, furos...])
            'raw': feat
        })
    return parsed, gj

def _which_micro_for_point(lon, lat, parsed_features):
    """
    Retorna o índice da microrregião que contém (lon,lat) ou None.
    """
    for f in parsed_features:
        polys = f['polygons']
        if not polys:
            continue
        if point_in_multipolygon(lon, lat, polys):
            return f['idx']
    return None

# ----------------- Estatísticas por microrregião -----------------
def calcular_medias_por_microrregiao(df_solar, df_eolica, geojson_path):
    """
    Para cada microrregião, calcula:
      - média (solar) e contagem
      - média (eólica) e contagem
    Usa ponto-no-polígono com as coordenadas das usinas.
    Retorna:
      stats: dict idx -> {'solar_mean','solar_n','eolica_mean','eolica_n'}
      vmin_s, vmax_s, vmin_e, vmax_e
    """
    if not os.path.exists(geojson_path):
        print(f"[INFO] GeoJSON não encontrado: {geojson_path}")
        return {}, 0.0, 1.0, 0.0, 1.0

    parsed, _ = _load_geojson(geojson_path)
    stats = {f['idx']: {'solar_vals': [], 'eolica_vals': [], 'nome': f['nome'], 'geocodigo': f['geocodigo']} for f in parsed}

    # solar
    if df_solar is not None and not df_solar.empty:
        for _, r in df_solar.iterrows():
            lat = float(r['latitude'])
            lon = float(r['longitude'])
            fc  = float(r['fator_capacidade'])
            idx = _which_micro_for_point(lon, lat, parsed)
            if idx is not None:
                stats[idx]['solar_vals'].append(fc)

    # eólica
    if df_eolica is not None and not df_eolica.empty:
        for _, r in df_eolica.iterrows():
            lat = float(r['latitude'])
            lon = float(r['longitude'])
            fc  = float(r['fator_capacidade'])
            idx = _which_micro_for_point(lon, lat, parsed)
            if idx is not None:
                stats[idx]['eolica_vals'].append(fc)

    # agrega
    vmin_s = +np.inf
    vmax_s = -np.inf
    vmin_e = +np.inf
    vmax_e = -np.inf

    for idx in stats:
        s_vals = stats[idx]['solar_vals']
        e_vals = stats[idx]['eolica_vals']
        s_mean = float(np.mean(s_vals)) if len(s_vals) else np.nan
        e_mean = float(np.mean(e_vals)) if len(e_vals) else np.nan
        stats[idx]['solar_mean'] = s_mean
        stats[idx]['solar_n']    = len(s_vals)
        stats[idx]['eolica_mean'] = e_mean
        stats[idx]['eolica_n']    = len(e_vals)
        if not np.isnan(s_mean):
            vmin_s = min(vmin_s, s_mean)
            vmax_s = max(vmax_s, s_mean)
        if not np.isnan(e_mean):
            vmin_e = min(vmin_e, e_mean)
            vmax_e = max(vmax_e, e_mean)

    # fallback caso todas sejam NaN
    if vmin_s == +np.inf: vmin_s, vmax_s = 0.0, 1.0
    if vmin_e == +np.inf: vmin_e, vmax_e = 0.0, 1.0

    return stats, vmin_s, vmax_s, vmin_e, vmax_e

# ----------------- Camadas coloridas por microrregião -----------------
def add_camada_micro_colorizada(m, geojson_path, stats, tecnologia='eolica', vmin=0.0, vmax=1.0, show=False):
    """
    tecnologia: 'eolica' ou 'solar'
    Pinta cada microrregião pela média da tecnologia escolhida e adiciona
    tooltip + popup via GeoJsonPopup (sem loops).
    """
    if not os.path.exists(geojson_path):
        print(f"[INFO] GeoJSON não encontrado: {geojson_path}")
        return

    import json
    with open(geojson_path, 'r', encoding='utf-8') as f:
        gj = json.load(f)

    # injeta propriedades auxiliares (_valor, _valor_str, _n) em cada feature
    feats = gj.get('features', [])
    layer_name = "Microrregiões — média EÓLICA" if tecnologia == 'eolica' else "Microrregiões — média SOLAR"
    for i, feat in enumerate(feats):
        s = stats.get(i, {})
        if tecnologia == 'eolica':
            val = s.get('eolica_mean', np.nan)
            n   = s.get('eolica_n', 0)
        else:
            val = s.get('solar_mean', np.nan)
            n   = s.get('solar_n', 0)

        if 'properties' not in feat or feat['properties'] is None:
            feat['properties'] = {}
        feat['properties']['_valor'] = float(val) if pd.notna(val) else None
        feat['properties']['_valor_str'] = ("{:.4f}".format(val) if pd.notna(val) else "—")
        feat['properties']['_n'] = int(n)

    fg = folium.FeatureGroup(name=layer_name, show=show)

    def _style_function(feat):
        val = feat['properties'].get('_valor', None)
        color = value_to_color(val, vmin, vmax) if val is not None else '#bdbdbd'
        return {"fillColor": color, "color": "#444", "weight": 1, "fillOpacity": 0.55}

    def _highlight(feat):
        return {"weight": 2, "color": "#000", "fillOpacity": 0.65}

    # Tooltip simples (nome/código)
    tooltip = folium.GeoJsonTooltip(
        fields=[f for f in ["nome", "geocodigo"] if f in (feats[0].get("properties", {}) if feats else {})],
        aliases=["Microrregião", "Código"],
        sticky=True
    )

    # Popup com os campos já preparados (_valor_str e _n)
    # Obs.: GeoJsonPopup precisa de 'fields' válidos que existam nas properties
    popup_fields_all = ["nome", "geocodigo", "_valor_str", "_n"]
    available = set(feats[0].get("properties", {}).keys()) if feats else set()
    popup_fields = [f for f in popup_fields_all if f in available]
    popup_aliases_map = {
        "nome": "Microrregião",
        "geocodigo": "Código",
        "_valor_str": f"Média ({'Eólica' if tecnologia == 'eolica' else 'Solar'})",
        "_n": "N pontos"
    }
    popup_aliases = [popup_aliases_map[f] for f in popup_fields]

    gj_layer = folium.GeoJson(
        gj,
        style_function=_style_function,
        highlight_function=_highlight,
        tooltip=tooltip,
        popup=folium.GeoJsonPopup(fields=popup_fields, aliases=popup_aliases, labels=True)
    )

    gj_layer.add_to(fg)
    fg.add_to(m)
    return layer_name

# ----------------- Linhas de transmissão -----------------
def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _color_blue_red(v, vmin, vmax):
    if pd.isna(v) or vmax == vmin:
        r = b = 128
    else:
        t = max(0.0, min(1.0, (float(v)-vmin)/(vmax-vmin)))
        r = int(255 * t)
        b = int(255 * (1-t))
    return f'#{r:02x}00{b:02x}'

def add_camadas_linhas(m, csv_path):
    if not os.path.exists(csv_path):
        print(f"[INFO] Arquivo de transmissão não encontrado: {csv_path}")
        return None
    df = pd.read_csv(csv_path)
    for c in ["CIDADE_DE","ESTADO_DE","CIDADE_PARA","ESTADO_PARA"]:
        if c in df.columns:
            df[c] = df[c].apply(norm)
    df = df[(df["ESTADO_DE"] == ESTADO_ALVO) | (df["ESTADO_PARA"] == ESTADO_ALVO)].copy()
    for c in ["LAT_SUBESTACAO_DE","LON_SUBESTACAO_DE","LAT_SUBESTACAO_PARA","LON_SUBESTACAO_PARA", COL_CAP]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["LAT_SUBESTACAO_DE","LON_SUBESTACAO_DE","LAT_SUBESTACAO_PARA","LON_SUBESTACAO_PARA", COL_CAP])
    if df.empty:
        print("[INFO] Sem linhas válidas para desenhar polylines.")
        return None

    cap_min, cap_max = df[COL_CAP].min(), df[COL_CAP].max()

    linhas_group = folium.FeatureGroup(name="Linhas de Transmissão (capacidade)", show=True)
    for _, r in df.iterrows():
        lat1, lon1 = float(r["LAT_SUBESTACAO_DE"]), float(r["LON_SUBESTACAO_DE"])
        lat2, lon2 = float(r["LAT_SUBESTACAO_PARA"]), float(r["LON_SUBESTACAO_PARA"])
        cap = float(r[COL_CAP])
        cor = _color_blue_red(cap, cap_min, cap_max)
        weight = 2 if cap_max == cap_min else int(2 + 4 * (cap - cap_min)/(cap_max - cap_min))
        nome_lt = str(r.get("NOM_LINHADETRANSMISSAO", "LT"))
        popup = folium.Popup(f"<b>{nome_lt}</b><br><b>Capacidade:</b> {cap:.1f}", max_width=350)
        folium.PolyLine([(lat1, lon1), (lat2, lon2)], color=cor, weight=weight, opacity=0.8, popup=popup).add_to(linhas_group)
    linhas_group.add_to(m)

    # retorna centro aproximado
    return df[["LAT_SUBESTACAO_DE","LON_SUBESTACAO_DE","LAT_SUBESTACAO_PARA","LON_SUBESTACAO_PARA"]].mean().iloc[0], \
           df[["LAT_SUBESTACAO_DE","LON_SUBESTACAO_DE","LAT_SUBESTACAO_PARA","LON_SUBESTACAO_PARA"]].mean().iloc[1]

# ----------------- MAIN -----------------
def main():
    m = folium.Map(location=GOIAS_CENTER, zoom_start=ZOOM_INICIAL, tiles="CartoDB positron")

    centros = []

    # 1) Microrregiões (vetor base)
    bounds = add_camada_microrregioes(m, GEOJSON_MICRO, show=True, fill_opacity=0.15)
    if bounds:
        m.fit_bounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]])

    # 2) Usinas (carrega/agrupa)
    solar  = carregar_usinas_agrupadas(ARQ_USINAS_SOLAR)
    eolica = carregar_usinas_agrupadas(ARQ_USINAS_EOLICA)

    if solar:  centros.append((solar[1], solar[2]))
    if eolica: centros.append((eolica[1], eolica[2]))

    # DataFrames para reutilizar
    df_s_for = solar[0] if solar else None
    df_e_for = eolica[0] if eolica else None

    # 3) Min/Max GLOBAL (ambos arquivos) para heat/markers
    series = []
    if solar:  series.append(solar[0]['fator_capacidade'])
    if eolica: series.append(eolica[0]['fator_capacidade'])
    if len(series) > 0:
        all_vals = pd.concat(series, ignore_index=True)
        fc_global_min = float(all_vals.min())
        fc_global_max = float(all_vals.max())
    else:
        fc_global_min = 0.0
        fc_global_max = 1.0

    # 4) Heatmaps separados (escala global)
    if solar:
        df_s, _, _ = solar
        w_s = (df_s['fator_capacidade'] - fc_global_min) / (fc_global_max - fc_global_min) if fc_global_max > fc_global_min else pd.Series(0.5, index=df_s.index)
        group_s = folium.FeatureGroup(name="Heatmap Usinas Solares (global min/max)", show=True)
        _add_usinas_heatmap_variable_radius(
            group_s,
            lat=df_s['latitude'].values,
            lon=df_s['longitude'].values,
            weights_norm=w_s.values
        )
        group_s.add_to(m)

    if eolica:
        df_e, _, _ = eolica
        w_e = (df_e['fator_capacidade'] - fc_global_min) / (fc_global_max - fc_global_min) if fc_global_max > fc_global_min else pd.Series(0.5, index=df_e.index)
        group_e = folium.FeatureGroup(name="Heatmap Usinas Eólicas (global min/max)", show=True)
        _add_usinas_heatmap_variable_radius(
            group_e,
            lat=df_e['latitude'].values,
            lon=df_e['longitude'].values,
            weights_norm=w_e.values
        )
        group_e.add_to(m)

    # 5) Marcadores separados (cada um com sua própria coloração)
    add_marcadores_usinas_separados(m, df_s_for, df_e_for, fc_global_min, fc_global_max)

    # 6) Nomes (usinas) como texto – camada desmarcada por padrão
    add_camada_nomes_usinas(m, df_s_for, df_e_for)

    # 7) >>> NOVO: Microrregiões coloridas pela média (Eólica/Solar) <<<
    stats, vmin_s, vmax_s, vmin_e, vmax_e = calcular_medias_por_microrregiao(df_s_for, df_e_for, GEOJSON_MICRO)
    # Por padrão deixo ambas DESMARCADAS (show=False) para não “poluir” a visualização inicial
    add_camada_micro_colorizada(m, GEOJSON_MICRO, stats, tecnologia='eolica', vmin=vmin_e, vmax=vmax_e, show=False)
    add_camada_micro_colorizada(m, GEOJSON_MICRO, stats, tecnologia='solar',  vmin=vmin_s, vmax=vmax_s, show=False)

    # 8) Linhas (polylines)
    c_trans = add_camadas_linhas(m, ARQ_LINHAS)
    if c_trans:
        centros.append(c_trans)

    # Centraliza
    if centros:
        lat = float(np.mean([c[0] for c in centros]))
        lon = float(np.mean([c[1] for c in centros]))
        m.location = [lat, lon]

    folium.LayerControl(collapsed=False).add_to(m)
    saida = "mapa_integrado_go.html"
    m.save(saida)
    print(f"[OK] Mapa integrado salvo em: {saida}")

if __name__ == "__main__":
    main()
