# Instruções para agentes

## Escopo e fatos do repositório

- Este é um pipeline Python para extrair precipitação diária CHIRPS do Google Earth Engine, processar dados geoespaciais e gerar entradas DSS/HEC-HMS.
- As dependências estão declaradas em `environment.yml` (Conda, Python 3.11) e `requirements.txt` (pip).
- Não há configuração versionada de build, testes, lint ou verificação de tipos. Não presuma que esses comandos ou ferramentas estejam instalados.
- A configuração é carregada de variáveis de ambiente e de `.env` (`python-dotenv`). `.env` e `credentials.json` são ignorados pelo Git. Nunca leia, copie ou registre valores de credenciais em documentação, logs ou commits.
- Não há banco de dados relacional ou migrações neste repositório. O formato persistente de dados de modelagem é DSS, criado pela integração `pydsstools`.

## Arquitetura

O fluxo está dividido em dois workflows orquestrados em `src/main.py`:

1. `gee_workflow`: autentica no Earth Engine (`src/auth.py`), processa geometrias e estatísticas geoespaciais (`src/geoprocessor.py`) e busca precipitação da coleção CHIRPS em blocos de até 30 dias, gravando CSVs (`src/data.py`).
2. `dss_workflow`: lê o CSV, gera ou consulta metadados DSS (`src/dss_generator.py`) e cria arquivos `.gage`, `.met` e `.control` para HEC-HMS (`src/hms_file_generator.py`).

`src/config.py` contém `Config` e `DssConfig`, além dos parâmetros e templates. `src/gui.py` fornece uma interface Tkinter que chama os dois workflows. `src/analysis.ipynb` é um notebook de análise, não um passo da orquestração principal.

## Tecnologias verificadas

- Python 3.11 no ambiente Conda declarado.
- Google Earth Engine: `earthengine-api`, `geemap`, `google-auth`.
- Dados e geoprocessamento: `pandas`, `numpy`, `geopandas`, `shapely`, `rasterio`, `rasterstats`.
- Configuração e templates: `python-dotenv`, `jinja2`.
- HEC-DSS: `pydsstools`.
- GUI: `tkinter` é importado por `src/gui.py`; não aparece como dependência Python separada nos manifests.

## Estrutura

- `src/`: módulos da aplicação, interface gráfica e notebook.
- `assets/`: caminho esperado para raster auxiliar `GCN.tif`; arquivos `assets/*.tif` são ignorados pelo Git.
- `saidas/`: saídas e intermediários gerados, incluindo CSVs, shapefiles, GeoJSON, raster, gráficos e exportações HEC-HMS.
- `environment.yml`, `requirements.txt`: manifests de dependências.
- `README.md`: descrição geral do projeto.

Os dados de entrada e os resultados existentes não necessariamente estão todos versionados. Verifique a disponibilidade dos arquivos exigidos pela configuração antes de executar um workflow.

## Configuração e execução

O código usa variáveis como `FILE_PATH`, `EXIT_PATH`, `PRIVATE_KEY_PATH`, `PROJECT_NAME`, `CSV_FILE`, `HMS_FILE` e `BASIN_NAME`; a lista e os defaults estão em `src/config.py`. A autenticação GEE usa uma chave de conta de serviço. Não documente valores secretos. Não há `.env.example` no repositório.

Ambiente Conda declarado:

```bash
conda env create -f environment.yml
conda activate gee-data-pipeline
```

Entradas executáveis verificadas:

```bash
python src/main.py  # executa GEE e, em seguida, DSS/HEC-HMS
python src/gui.py   # inicia a interface Tkinter
```

Esses comandos dependem das variáveis de ambiente, credenciais, dados geoespaciais e arquivos de projeto necessários. `src/main.py` usa imports sem prefixo `src`; execute-o pelo caminho mostrado a partir da raiz do repositório.

## Testes, lint, build e tipos

- Não há suíte de testes nem comando de teste configurado no repositório.
- Não há ferramenta ou comando de lint configurado.
- Não há build ou empacotamento configurado.
- Não há ferramenta ou comando de verificação de tipos configurado.
- Não apresente comandos de ferramentas externas como comandos já suportados pelo projeto. Se uma tarefa solicitar essas verificações, informe a ausência de configuração; só adicione ferramentas ou configuração quando isso fizer parte do escopo autorizado.

## Convenções de código observadas

- Módulos e funções usam `snake_case`; classes usam `PascalCase`.
- O código existente usa indentação de quatro espaços.
- A implementação é organizada em módulos por responsabilidade, com configuração passada aos componentes por construtor.
- Há mistura de mensagens e comentários em português e inglês; preserve o idioma e o estilo local do arquivo ao modificá-lo.
- Não existe formatter ou padrão de documentação formal configurado. Evite reformatar arquivos inteiros sem necessidade.

## Dados persistentes e arquivos DSS

- Não existem regras de migração de banco relacional neste projeto. Não introduza um banco ou migrações como se já fizessem parte da arquitetura.
- Arquivos DSS são saídas de dados importantes para o HEC-HMS. `DssGenerator.create_dss_file()` chama `remove_old_dss()` antes de criar um novo DSS; trate essa operação como destrutiva para o arquivo anterior. Preserve dados existentes e só regenere/sobrescreva DSS quando a tarefa pedir essa alteração e as entradas relevantes estiverem identificadas.
- CSVs, shapefiles, rasters e arquivos HEC-HMS em `saidas/` são dados/artefatos, não código-fonte. Não os substitua ou remova incidentalmente ao editar a aplicação.

## Dependências

- `environment.yml` e `requirements.txt` são os dois manifests presentes. Ao alterar dependências da aplicação, mantenha os manifests coerentes entre si e não declare como instalada uma dependência que não esteja listada ou verificada.
- O ambiente Conda fixa Python 3.11; respeite essa versão ao propor mudanças de compatibilidade.
- Não adicione dependências sem necessidade para a tarefa. Não inclua credenciais, caminhos pessoais ou configurações secretas nos manifests.

## Git e segurança dos dados

- Respeite `.gitignore`: ele exclui `.env`, `credentials.json`, `env/`, `assets/*.tif`, entre outros arquivos locais.
- Nunca force a inclusão de credenciais, chaves privadas, dados locais ignorados ou artefatos gerados sem solicitação explícita.
- Preserve alterações preexistentes no working tree. Antes de editar ou preparar mudanças, verifique `git status` e não descarte alterações do usuário.
- Mantenha commits focados em código e documentação da tarefa; evite incluir resultados em `saidas/` sem que sejam parte explícita do trabalho.
