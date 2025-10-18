import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# ---------- Parâmetros ----------
ARQ_EOLICA = "usinas.eolica.csv"
ARQ_SOLAR  = "usinas.solar.csv"
def fmt_br(x, casas=3):
    return f"{x:.{casas}f}".replace(".", ",")

# ---------- Leitura ----------
eolica = pd.read_csv(ARQ_EOLICA)
solar  = pd.read_csv(ARQ_SOLAR)

eolica["ano"] = eolica["ano"].astype(int)
eolica["mes"] = eolica["mes"].astype(int)
solar["ano"]  = solar["ano"].astype(int)
solar["mes"]  = solar["mes"].astype(int)

# ---------- Agregação (mediana mensal do fator_capacidade) ----------
fc_eolica = (
    eolica.groupby(["mes"], as_index=False)["fator_capacidade"]
    .median()
    .rename(columns={"fator_capacidade": "fc_eolica"})
)
fc_solar = (
    solar.groupby(["mes"], as_index=False)["fator_capacidade"]
    .median()
    .rename(columns={"fator_capacidade": "fc_solar"})
)

# Merge e tratamento de tipos
mensal = pd.merge(fc_solar, fc_eolica, on="mes", how="outer").copy()
mensal[["fc_solar", "fc_eolica"]] = mensal[["fc_solar", "fc_eolica"]].fillna(0.0)
mensal["mes"] = mensal["mes"].round(0).astype(int)
mensal = mensal.sort_values("mes").reset_index(drop=True)

# Descobre se existe um único ano nas duas bases; se sim, usa no rótulo
anos = sorted(set(eolica["ano"].unique()).union(set(solar["ano"].unique())))
if len(anos) == 1:
    ano_rotulo = str(anos[0])
    mensal["rotulo"] = mensal["mes"].apply(lambda m: f"{int(m):02d}/{ano_rotulo}")
else:
    # Se houver mais de um ano nas bases, mostre só o mês
    mensal["rotulo"] = mensal["mes"].apply(lambda m: f"{int(m):02d}")

# ---------- Plot ----------
x = np.arange(len(mensal))
larg = 0.65

fig, ax = plt.subplots(figsize=(12, 6))

bars_solar  = ax.bar(x, mensal["fc_solar"], width=larg, color="#d62728", label="Solar")
bars_eolica = ax.bar(x, mensal["fc_eolica"], width=larg, bottom=mensal["fc_solar"],
                     color="#2ca02c", label="Eólica")

ax.set_title("Mediana Mensal do Fator de Capacidade (Solar + Eólica)", fontsize=28)
ax.set_xlabel("Mês de Referência", fontsize=24)
ax.set_ylabel("Fator de Capacidade Médio", fontsize=24)
ax.set_xticks(x)
ax.set_xticklabels(mensal["rotulo"], rotation=35, fontsize=18)
ax.legend(loc="upper left")

# Anotações por segmento
for rect, val in zip(bars_solar, mensal["fc_solar"]):
    if val > 0:
        ax.text(rect.get_x() + rect.get_width()/2,
                rect.get_y() + rect.get_height()/2,
                fmt_br(val),
                ha="center", va="center", fontsize=9, color="white", weight="bold")

for rect, val, base in zip(bars_eolica, mensal["fc_eolica"], mensal["fc_solar"]):
    if val > 0:
        ax.text(rect.get_x() + rect.get_width()/2,
                base + val/2,
                fmt_br(val),
                ha="center", va="center", fontsize=9, color="white", weight="bold")

ax.margins(y=0.1)
ax.grid(axis="y", linestyle="--", alpha=0.3)
plt.tight_layout()
plt.show()
