import pandas as pd
import pyodbc
import re
from datetime import datetime
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Conectar ao banco de dados
conn = pyodbc.connect(
    f"DRIVER={{{os.getenv('DB_DRIVER')}}};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_DATABASE')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
)

# Função para determinar o número máximo de telefones (principais ou não)
def get_max_telefones(cursor, is_principal=True):
    query = f"""
        SELECT MAX(TelefonePosicao) AS MaxTelefonePosicao
        FROM (
            SELECT 
                PesPessoasID AS PessoaID,
                ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
            FROM PessoasContatos
            WHERE 
                ISNULL(PesTelefoneInativo, 0) <> 1
                AND ISNULL(PesTelefonePrincipal, 0) = {1 if is_principal else 0}
                AND PesTelefone <> ''
        ) AS Temp;
    """
    cursor.execute(query)
    result = cursor.fetchone()
    return result.MaxTelefonePosicao if result else 0

# Criar cursor e calcular limites
cursor = conn.cursor()
max_principais = get_max_telefones(cursor, is_principal=True)
max_nao_principais = get_max_telefones(cursor, is_principal=False)

# Colunas dinâmicas
dynamic_columns_principais = ', '.join([
    f"MAX(CASE WHEN T.TelefonePosicao = {i} THEN T.Telefone END) AS telefone_principal{i}"
    for i in range(1, max_principais + 1)
])
dynamic_columns_nao_principais = ', '.join([
    f"MAX(CASE WHEN TN.TelefonePosicao = {i} THEN TN.Telefone END) AS telefone_nao_principal{i}"
    for i in range(1, max_nao_principais + 1)
])

# Query principal (SEM NEGOCIADOR / SEM OUTER APPLY)
query_dynamic = f"""
WITH Inadimplentes AS (
    SELECT DISTINCT
        dbo.RetornaNomeCampanha(MoCampanhasID, 1) AS CAMPANHA,
        dbo.RetornaNomeRazaoSocial(MoClientesID) AS CREDOR,
        dbo.RetornaCPFCNPJ(MoInadimplentesID, 1) AS CPFCNPJ_CLIENTE,
        dbo.RetornaNomeRazaoSocial(MoInadimplentesID) AS NOME_RAZAO_SOCIAL,
        MoInadimplentesID AS PessoaID,
        CASE 
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) <= 90 THEN '1. Até 90 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 91 AND 180 THEN '2. 91 a 180 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 181 AND 360 THEN '3. 181 a 360 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 361 AND 720 THEN '4. 361 a 720 dias'
            ELSE '5. Acima de 720 dias'
        END AS FAIXA_AGING
    FROM Movimentacoes
        INNER JOIN Pessoas ON MoInadimplentesID = Pessoas_ID
    WHERE 
        MoStatusMovimentacao = 0
        AND MoDataVencimento < GETDATE()
        AND MoOrigemMovimentacao IN ('C', 'I')
        AND MoCampanhasID NOT IN (12,16,20,35,38,42,44,47,48,49,64,65)
        -- Exclui quem tiver alguma parcela de acordo aberta
        AND NOT EXISTS (
            SELECT 1
            FROM Movimentacoes m2
            WHERE m2.MoInadimplentesID     = Movimentacoes.MoInadimplentesID
              AND m2.MoOrigemMovimentacao  = 'A'  -- Acordo
              AND m2.MoStatusMovimentacao  = 0    -- Aberto
        )
    GROUP BY 
        dbo.RetornaNomeCampanha(MoCampanhasID, 1),
        dbo.RetornaNomeRazaoSocial(MoClientesID),
        dbo.RetornaCPFCNPJ(MoInadimplentesID, 1),
        dbo.RetornaNomeRazaoSocial(MoInadimplentesID),
        MoInadimplentesID
),
TelefonesPrincipais AS (
    SELECT 
        PesPessoasID AS PessoaID,
        CONCAT(PesDDD, PesTelefone) AS Telefone,
        ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
    FROM PessoasContatos
    WHERE 
        ISNULL(PesTelefoneInativo, 0) <> 1 
        AND ISNULL(PesTelefonePrincipal, 0) = 1 
        AND PesTelefone <> ''
),
TelefonesNaoPrincipais AS (
    SELECT 
        PesPessoasID AS PessoaID,
        CONCAT(PesDDD, PesTelefone) AS Telefone,
        ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
    FROM PessoasContatos
    WHERE 
        ISNULL(PesTelefoneInativo, 0) <> 1 
        AND ISNULL(PesTelefonePrincipal, 0) = 0 
        AND PesTelefone <> ''
)
SELECT 
    I.CAMPANHA,
    I.CREDOR,
    I.CPFCNPJ_CLIENTE,
    I.NOME_RAZAO_SOCIAL,
    {dynamic_columns_principais},
    {dynamic_columns_nao_principais}
FROM Inadimplentes I
LEFT JOIN TelefonesPrincipais T ON I.PessoaID = T.PessoaID
LEFT JOIN TelefonesNaoPrincipais TN ON I.PessoaID = TN.PessoaID
GROUP BY 
    I.CAMPANHA,
    I.CREDOR,
    I.CPFCNPJ_CLIENTE,
    I.NOME_RAZAO_SOCIAL;
"""

# Executar a query principal
df = pd.read_sql_query(query_dynamic, conn)

# Consulta dos CPFs com RO recente
query_ro = """
    SELECT DISTINCT
        REPLACE(REPLACE(REPLACE(CPF_CNPJ_CLIENTE, '.', ''), '-', ''), '/', '') AS CPF_CNPJ_CLIENTE
    FROM [Candiotto_reports].dbo.tabelaacionamento
    WHERE 
        RoId IN (56, 57, 58, 59)
        AND [DATA] >= DATEADD(DAY, -7, GETDATE())
"""
df_ro = pd.read_sql(query_ro, conn)
conn.close()

# Normalizar CPF no mailing e filtrar quem teve RO recente
df['CPF_CNPJ_LIMPO'] = df['CPFCNPJ_CLIENTE'].str.replace(r'\D', '', regex=True)
cpfs_com_ro = set(df_ro['CPF_CNPJ_CLIENTE'])
df = df[~df['CPF_CNPJ_LIMPO'].isin(cpfs_com_ro)].copy()

# Limpeza de telefones
telefone_cols = [c for c in df.columns if c.startswith('telefone_principal') or c.startswith('telefone_nao_principal')]

def limpar_telefone(telefone):
    if pd.isnull(telefone):
        return ""
    telefone = re.sub(r'\D', '', str(telefone))
    return telefone if len(telefone) >= 10 else ""

for col in telefone_cols:
    df[col] = df[col].apply(limpar_telefone)

df['telefones'] = df[telefone_cols].apply(lambda row: [tel for tel in row if tel], axis=1)

# Layout final
mailing_columns = ['COD', 'CPFCNPJ CLIENTE', 'NOME / RAZAO SOCIAL', 'CAMPANHA'] + [f'TELEFONE_{i}' for i in range(1, 21)]

def preencher_telefones(row):
    telefones = row['telefones'][:20]
    return telefones + [""] * (20 - len(telefones))

# Geração dos arquivos (um por CAMPANHA)
data_atual = datetime.now().strftime('%Y-%m-%d')
os.makedirs("mailings", exist_ok=True)

for campanha, grupo in df.groupby('CAMPANHA'):
    mailing = pd.DataFrame(columns=mailing_columns)
    mailing['COD'] = grupo['CPFCNPJ_CLIENTE']
    mailing['CPFCNPJ CLIENTE'] = grupo['CPFCNPJ_CLIENTE']
    mailing['NOME / RAZAO SOCIAL'] = grupo['NOME_RAZAO_SOCIAL']
    mailing['CAMPANHA'] = grupo['CAMPANHA']

    telefones_expandidos = grupo.apply(preencher_telefones, axis=1)
    for i in range(20):
        mailing[f'TELEFONE_{i + 1}'] = telefones_expandidos.apply(lambda x: x[i])

    nome_arquivo = f"Mailing {campanha} - {data_atual}.csv"
    nome_arquivo = nome_arquivo.replace("/", "-").replace("\\", "-").replace(":", "-")
    caminho_arquivo = os.path.join("mailings", nome_arquivo)
    mailing.to_csv(caminho_arquivo, index=False, sep=';', encoding='utf-8-sig')

print("Arquivos de mailing por campanha gerados com sucesso!")
