import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from unidecode import unidecode
import re

# =========================
# ARQUIVOS DE ENTRADA
# =========================
ARQ_USINAS_SOLAR  = "usinas.solar.csv"
ARQ_USINAS_EOLICA = "usinas.eolica.csv"

# =========================
# PARÂMETROS DE SAÍDA
# =========================
PASTA_SAIDA = "histogramas_comparativos_por_cidade"

def carregar_e_processar_dados(arquivos_usinas):
    """
    Lê uma lista de arquivos de usinas, aplica as regras de negócio específicas
    (filtro e score para solar), adiciona uma coluna 'fonte' e retorna um
    único DataFrame consolidado.
    """
    lista_dfs = []
    
    for csv_path in arquivos_usinas:
        if not os.path.exists(csv_path):
            print(f"[AVISO] Arquivo não encontrado, pulando: {csv_path}")
            continue

        print(f"[INFO] Lendo o arquivo: {csv_path}")
        df = pd.read_csv(csv_path)

        # Garante que as colunas necessárias existam antes de processar
        req = ['nomeUsina', 'fator_capacidade']
        if not all(col in df.columns for col in req):
            print(f"[ERRO] Faltam colunas essenciais em {csv_path}. Pulando arquivo.")
            continue

        # Aplica as regras específicas para dados SOLARES
        if 'solar' in csv_path.lower():
            df['fonte'] = 'Solar' # Adiciona a coluna de identificação
            if 'hora' in df.columns:
                print(f"[INFO] Aplicando filtro de horário (6h-18h) para {csv_path}")
                df = df[(df['hora'] >= 6) & (df['hora'] <= 18)].copy()
                
                print(f"[INFO] Fator de capacidade do arquivo solar foi dividido por 2.")
                df['fator_capacidade'] = df['fator_capacidade'] / 2
            else:
                print(f"[AVISO] Coluna 'hora' não encontrada em {csv_path}. Regras não aplicadas.")
        
        # Identifica dados EÓLICOS
        elif 'eolica' in csv_path.lower():
            df['fonte'] = 'Eolica' # Adiciona a coluna de identificação
        
        else:
            df['fonte'] = 'Outra'

        lista_dfs.append(df)

    if not lista_dfs:
        return None

    df_consolidado = pd.concat(lista_dfs, ignore_index=True)
    df_consolidado['fator_capacidade'] = pd.to_numeric(df_consolidado['fator_capacidade'], errors='coerce')
    df_consolidado = df_consolidado.dropna(subset=['nomeUsina', 'fator_capacidade', 'fonte'])
    
    return df_consolidado

def gerar_histogramas_sobrepostos(df):
    """
    Gera histogramas sobrepostos (solar vs. eólico) para cada 'nomeUsina'.
    """
    if df is None or df.empty:
        print("[ERRO] Nenhum dado válido para gerar histogramas.")
        return

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    print(f"[INFO] Histogramas serão salvos na pasta: '{PASTA_SAIDA}/'")

    usinas = df['nomeUsina'].unique()

    for usina in usinas:
        df_usina = df[df['nomeUsina'] == usina]
        
        # Separa os dados por fonte
        dados_solar = df_usina[df_usina['fonte'] == 'Solar']['fator_capacidade']
        dados_eolica = df_usina[df_usina['fonte'] == 'Eolica']['fator_capacidade']

        # Pula se a usina não tiver dados de nenhuma das fontes
        if dados_solar.empty and dados_eolica.empty:
            continue
            
        # Inicia o plot
        plt.figure(figsize=(12, 7))
        
        # Plota o histograma para cada fonte, se houver dados
        if not dados_solar.empty:
            sns.histplot(dados_solar, kde=True, bins=30, color='red', label='Solar (Score)', alpha=0.6)
        
        if not dados_eolica.empty:
            sns.histplot(dados_eolica, kde=True, bins=30, color='blue', label='Eólica', alpha=0.6)

        # Títulos e legendas
        plt.title(f'Distribuição do Fator de Capacidade - {usina}')
        plt.xlabel('Fator de Capacidade')
        plt.ylabel('Frequência (Contagem de Horas)')
        plt.legend() # Adiciona a legenda para identificar as cores
        plt.grid(True, linestyle='--', alpha=0.6)

        # Salva o arquivo
        nome_arquivo_seguro = re.sub(r'[^a-zA-Z0-9_-]', '_', unidecode(usina))
        caminho_saida = os.path.join(PASTA_SAIDA, f"{nome_arquivo_seguro}_comparativo.png")

        try:
            plt.savefig(caminho_saida)
            print(f"  -> Histograma salvo: {caminho_saida}")
        except Exception as e:
            print(f"[ERRO] Falha ao salvar o histograma para {usina}: {e}")
            
        plt.close()

def main():
    """
    Função principal que orquestra a execução do script.
    """
    arquivos = [ARQ_USINAS_SOLAR, ARQ_USINAS_EOLICA]
    df_dados_completos = carregar_e_processar_dados(arquivos)
    gerar_histogramas_sobrepostos(df_dados_completos)
    print("\n[OK] Processo finalizado.")

if __name__ == "__main__":
    main()