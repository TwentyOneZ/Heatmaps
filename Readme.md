# Projeto de Visualização Geoespacial - Microrregiões de Goiás

Este projeto foca na análise e visualização de dados geoespaciais, especificamente criando mapas de calor (heatmaps) e mapas coropléticos interativos para as microrregiões do estado de Goiás.

O projeto utiliza scripts Python para processar dados geoespaciais (Shapefiles), convertê-los e gerar visualizações em HTML interativo. Além disso, inclui uma configuração Docker para servir um mapa web.

## Estrutura do Projeto

O repositório está organizado da seguinte forma:

-   **`/` (Raiz)**: Contém os scripts principais de processamento e geração de mapas, bem como os arquivos de dados.
-   **`/mapa`**: Contém uma aplicação web containerizada (usando Docker) para servir um mapa interativo.

## Componentes Principais

### Scripts Python

-   **`mapa_microrregioes_go.py`**: Script principal para ler os dados geoespaciais e gerar um mapa das microrregiões de Goiás.
-   **`mapa_integrado.py`**: Provavelmente um script que integra dados adicionais (como o "fator de capacidade") ao mapa principal.
-   **`convert_gdf.py`**: Utilitário para converter arquivos de dados, possivelmente convertendo o Shapefile (`.shp`) para o formato GeoJSON (`.json`) usando GeoPandas.
-   **`fatorCapacidade.py`**: Script de análise para calcular ou processar dados relacionados a um "fator de capacidade", que é então usado nas visualizações.
-   **`histo.py`**: Script para gerar histogramas ou outras análises estatísticas dos dados.

### Dados

-   **`52MI2500G.shp` / `.shx` / `.dbf`**: Arquivos Shapefile (padrão Esri) contendo os polígonos e dados das microrregiões de Goiás.
-   **`microrregioes_go.json`**: Arquivo GeoJSON, provavelmente o resultado da conversão do Shapefile, usado pelos scripts para gerar os mapas.

### Saída (Exemplos)

-   **`mapa_integrado_go.html`**: Um exemplo de mapa HTML interativo (provavelmente gerado com Folium ou Plotly) resultante da execução dos scripts.

### Serviço Web (Docker)

O diretório `/mapa` contém uma configuração para servir um mapa web estático ou interativo:

-   **`Dockerfile`**: Define a imagem do contêiner (usando `httpd:latest`, um servidor web Apache).
-   **`docker-compose.yml`**: Facilita a inicialização do serviço web.
-   **`index.html`**: A página web principal que é servida.
-   **`microrregioes_go.json`**: Uma cópia local do GeoJSON para ser usada pelo `index.html`.

## Como Executar

### 1. Instalação (Ambiente Python)

Para executar os scripts Python localmente, primeiro instale as dependências:

```bash
pip install -r requirements.txt
```

### 2. Geração dos Mapas
Execute os scripts Python para processar os dados e gerar os arquivos HTML:

```Bash
# Gerar o mapa integrado
python mapa_integrado.py
```

Isso deve criar (ou atualizar) o arquivo maps/mapa_integrado.html.

### 3. Executando o Serviço Web (Docker)
Para visualizar o mapa servido pelo Docker:

Certifique-se de ter o Docker e o Docker Compose instalados.

Navegue até o diretório /mapa:

```Bash
cd mapa
```
Inicie o serviço:

```Bash
docker-compose up -d
```
Acesse o mapa em seu navegador: http://localhost:8080 (ou a porta definida no docker-compose.yml).


