"""
popular_regras_oficiais.py
--------------------------
Popula a tabela `cnae_regra_oficial` com respostas DETERMINÍSTICAS
para os CNAEs mais comuns. Cada regra tem:
  - obrigatoriedade: 'sim' | 'nao' | 'condicional'
  - condicoes_obrigatorio / condicoes_dispensa: descrição clara
  - base_legal: lei/resolução com nº e data
  - link_lei: URL pro PDF/texto da norma oficial

⚠️ IMPORTANTE: A base começa com poucos CNAEs cuidadosamente
verificados. À medida que a equipe encontra novos casos, deve
adicionar pela página "📚 Base de Regras" no app. Cada regra
nova precisa citar a lei/resolução — sem isso, fica como
"pesquisar manualmente".

Rode 1x (idempotente):
    python redesim_manager/popular_regras_oficiais.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db, upsert_regra_oficial  # noqa: E402

# =====================================================================
# REGRAS-SEED
# =====================================================================
# Cada entrada é a resposta OFICIAL pra "CNAE X precisa de registro
# no órgão Y?" — com base legal citada.
#
# Quando obrigatoriedade='condicional', SEMPRE preencher pelo menos
# uma das condições (condicoes_obrigatorio OU condicoes_dispensa).
# =====================================================================
REGRAS = [
    # =============================================================
    # IMOBILIÁRIO — caso do Eduardo (6822-6/00)
    # =============================================================
    {
        "cnae": "6822-6/00",
        "orgao_sigla": "CRECI",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Exigido SE a empresa INTERMEDIA negócios imobiliários "
            "(procura compradores/inquilinos, agencia venda ou locação "
            "como atividade-meio). Lei 6.530/78 art. 3º define "
            "intermediação como ato privativo do Corretor."
        ),
        "condicoes_dispensa": (
            "DISPENSADO quando a empresa apenas ADMINISTRA imóveis "
            "(cobra aluguel, paga IPTU/condomínio, repassa ao "
            "proprietário, faz manutenção) sem intermediar novos "
            "contratos. Resolução COFECI 327/92, art. 3º (admin. "
            "patrimonial não é ato privativo de Corretor). "
            "Confirmado pela Resolução COFECI 1.422/2018."
        ),
        "observacoes": (
            "Na prática: se a empresa SÓ recebe procuração pra "
            "administrar (síndico de aluguel) → dispensa. Se busca "
            "novos inquilinos / divulga imóveis → exige."
        ),
        "base_legal": (
            "Lei 6.530/78 art. 3º + Decreto 81.871/78 + "
            "Resolução COFECI 327/92 art. 3º + "
            "Resolução COFECI 1.422/2018"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6530.htm",
    },
    {
        "cnae": "6810-2/01",   # Compra e venda de imóveis próprios
        "orgao_sigla": "CRECI",
        "obrigatoriedade": "nao",
        "condicoes_dispensa": (
            "Compra/venda de imóveis PRÓPRIOS (do patrimônio da PJ) "
            "não configura intermediação imobiliária. É ato comercial "
            "comum, dispensa registro no CRECI."
        ),
        "observacoes": (
            "Atenção: se a empresa também intermedia imóveis de "
            "terceiros, aí vira CNAE 6822-6/00 e exige CRECI."
        ),
        "base_legal": (
            "Lei 6.530/78 art. 3º (define intermediação) + "
            "Resolução COFECI 327/92 art. 3º"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6530.htm",
    },
    {
        "cnae": "6810-2/02",   # Aluguel de imóveis próprios
        "orgao_sigla": "CRECI",
        "obrigatoriedade": "nao",
        "condicoes_dispensa": (
            "Aluguel de imóveis do próprio patrimônio da PJ não é "
            "intermediação. Dispensa CRECI."
        ),
        "base_legal": "Resolução COFECI 327/92 art. 3º",
        "link_lei": (
            "https://www.cofeci.gov.br/arquivos/legislacao/2000/"
            "resolucao327.pdf"
        ),
    },
    {
        "cnae": "6821-8/01",   # Corretagem na compra e venda
        "orgao_sigla": "CRECI",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Corretagem de imóveis é ato PRIVATIVO do Corretor de "
            "Imóveis registrado. PJ que exerce a atividade precisa "
            "ter Responsável Técnico inscrito no CRECI + registro PJ."
        ),
        "base_legal": "Lei 6.530/78 art. 3º + Decreto 81.871/78",
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6530.htm",
    },
    {
        "cnae": "6821-8/02",   # Corretagem no aluguel
        "orgao_sigla": "CRECI",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Corretagem/intermediação na locação é privativa do "
            "Corretor. Mesma lógica do CNAE 6821-8/01."
        ),
        "base_legal": "Lei 6.530/78 art. 3º",
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6530.htm",
    },

    # =============================================================
    # CONTABILIDADE — escritório do Eduardo
    # =============================================================
    {
        "cnae": "6920-6/01",   # Atividades de contabilidade
        "orgao_sigla": "CRC",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Escritório de contabilidade (PJ) precisa de Registro "
            "Cadastral no CRC do estado da sede + Responsável Técnico "
            "contador (com diploma e CRC ativo). Decreto-Lei 9.295/46 "
            "art. 15."
        ),
        "base_legal": (
            "Decreto-Lei 9.295/46 art. 15 + Resolução CFC 1.555/2018"
        ),
        "link_lei": (
            "https://www.planalto.gov.br/ccivil_03/decreto-lei/del9295.htm"
        ),
    },
    {
        "cnae": "6920-6/02",   # Atividades de auditoria contábil
        "orgao_sigla": "CRC",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Auditoria contábil é privativa de contador registrado. "
            "PJ precisa de registro CRC + RT contador. Auditor "
            "independente também precisa de cadastro CVM se atuar "
            "em companhias abertas (CVM Instrução 308/99)."
        ),
        "base_legal": (
            "Decreto-Lei 9.295/46 + Lei 12.249/2010 + "
            "Resolução CFC 1.555/2018"
        ),
        "link_lei": (
            "https://www.planalto.gov.br/ccivil_03/decreto-lei/del9295.htm"
        ),
    },

    # =============================================================
    # COMÉRCIO VAREJISTA (sem registros adicionais comuns)
    # =============================================================
    {
        "cnae": "4711-3/02",   # Comércio varejista de mercadorias em geral
        "orgao_sigla": "ANVISA",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Exigido SE a loja vende produtos de saúde controlados "
            "pela ANVISA: medicamentos, correlatos, alimentos pra "
            "fins especiais, cosméticos (em grande escala). Necessita "
            "AFE (Autorização de Funcionamento)."
        ),
        "condicoes_dispensa": (
            "DISPENSADO se vende apenas mercadorias gerais de "
            "consumo (mercearia comum, produtos de limpeza domésticos, "
            "etc.) sem produtos sob regulação sanitária federal."
        ),
        "base_legal": (
            "Lei 6.360/76 + RDC ANVISA 16/2014 (AFE)"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6360.htm",
    },
    {
        "cnae": "4711-3/02",
        "orgao_sigla": "CVS-SP",
        "orgao_uf": "SP",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Em SP, comércio que manipula/vende ALIMENTOS exige "
            "Licença Sanitária (CVS 5/2013). Risco baixo: "
            "Comunicado de Início; Risco médio/alto: Licença + "
            "vistoria."
        ),
        "condicoes_dispensa": (
            "Loja que não trabalha com alimentos, medicamentos, "
            "cosméticos ou saneantes está fora do escopo da CVS-SP."
        ),
        "base_legal": (
            "Portaria CVS 5/2013 + Portaria CVS 4/2011"
        ),
        "link_lei": (
            "http://www.cvs.saude.sp.gov.br/zip/E_PT-CVS-05_090413.pdf"
        ),
    },

    # =============================================================
    # ALIMENTAÇÃO FORA DO LAR
    # =============================================================
    {
        "cnae": "5611-2/01",   # Restaurantes e similares
        "orgao_sigla": "CVS-SP",
        "orgao_uf": "SP",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Restaurantes em SP precisam de Licença Sanitária "
            "estadual. Risco MÉDIO pela Portaria CVS 4/2011 — exige "
            "vistoria sanitária na abertura e renovação anual."
        ),
        "base_legal": (
            "Portaria CVS 4/2011 (classificação de risco) + "
            "Portaria CVS 5/2013 (boas práticas)"
        ),
        "link_lei": (
            "http://www.cvs.saude.sp.gov.br/zip/E_PT-CVS-04_140711.pdf"
        ),
    },
    {
        "cnae": "5611-2/01",
        "orgao_sigla": "CBPMESP",
        "orgao_uf": "SP",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Restaurante exige AVCB SE: área construída > 250m² OU "
            "altura > 12m OU lotação > 100 pessoas. IT-01/2019 "
            "classifica como ocupação F-8 (alimentação)."
        ),
        "condicoes_dispensa": (
            "Restaurante muito pequeno (até 250m², 1 pavimento, "
            "lotação inferior a 100) pode emitir CLCB (mais simples) "
            "em vez de AVCB. Tabela 6.A do IT-01/2019."
        ),
        "base_legal": "Instrução Técnica 01/2019 CB-PMESP (tabela 6.A)",
        "link_lei": (
            "https://www.policiamilitar.sp.gov.br/hotsites/ccb/"
            "instrucoes-tecnicas/"
        ),
    },

    # =============================================================
    # SAÚDE
    # =============================================================
    {
        "cnae": "8630-5/01",   # Atividade médica ambulatorial
        "orgao_sigla": "CRM",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Clínica médica precisa de registro PJ no CRM do estado "
            "+ Responsável Técnico médico com CRM ativo na mesma UF. "
            "Resolução CFM 997/2012 e CFM 2.255/2019."
        ),
        "base_legal": (
            "Lei 3.268/57 + Resolução CFM 997/2012 + CFM 2.255/2019"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l3268.htm",
    },
    {
        "cnae": "8630-5/01",
        "orgao_sigla": "CVS-SP",
        "orgao_uf": "SP",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Estabelecimento de saúde em SP exige Licença Sanitária "
            "estadual ALTO RISCO. Vistoria obrigatória na abertura."
        ),
        "base_legal": "Portaria CVS 4/2011 + RDC ANVISA 50/2002",
        "link_lei": (
            "http://www.cvs.saude.sp.gov.br/zip/E_PT-CVS-04_140711.pdf"
        ),
    },
    {
        "cnae": "8630-5/03",   # Atividade médica ambulatorial restrita
        "orgao_sigla": "CRM",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Consultório médico precisa de registro PJ no CRM e RT "
            "médico. Mesmo regime do 8630-5/01."
        ),
        "base_legal": (
            "Lei 3.268/57 + Resolução CFM 997/2012"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l3268.htm",
    },
    {
        "cnae": "8650-0/04",   # Fisioterapia
        "orgao_sigla": "CREFITO",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Clínica de fisioterapia precisa de registro PJ no "
            "CREFITO regional + RT fisioterapeuta. Lei 6.316/75."
        ),
        "base_legal": (
            "Lei 6.316/75 + Resolução COFFITO 401/2011"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6316.htm",
    },

    # =============================================================
    # EDUCAÇÃO
    # =============================================================
    {
        "cnae": "8513-9/00",   # Ensino fundamental
        "orgao_sigla": "CBPMESP",
        "orgao_uf": "SP",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Escolas/creches exigem AVCB independente do tamanho "
            "(ocupação E pela IT-01/2019 — escolar). Vistoria "
            "rigorosa por concentração de pessoas vulneráveis."
        ),
        "base_legal": "Instrução Técnica 01/2019 CB-PMESP",
        "link_lei": (
            "https://www.policiamilitar.sp.gov.br/hotsites/ccb/"
            "instrucoes-tecnicas/"
        ),
    },

    # =============================================================
    # ESTÉTICA / BELEZA — caso do botox
    # =============================================================
    {
        "cnae": "9602-5/02",   # Atividades de estética
        "orgao_sigla": "CRM",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Procedimentos INVASIVOS (botox, preenchimento, "
            "harmonização facial, peelings profundos, lasers "
            "ablativos) são privativos de médicos. PJ que executa "
            "esses procedimentos precisa de Responsável Técnico "
            "médico + registro CRM. Resolução CFM 2.225/2019."
        ),
        "condicoes_dispensa": (
            "Estética NÃO INVASIVA (depilação, massagem, "
            "limpeza de pele, manicure, sobrancelha, cabelo) "
            "dispensa registro no CRM. Cada profissional tem seu "
            "conselho (esteticista, podólogo, manicure)."
        ),
        "observacoes": (
            "Botox e similares são ATO MÉDICO. Salão que aplica "
            "sem médico responde por exercício ilegal da medicina."
        ),
        "base_legal": (
            "Lei 12.842/2013 (Lei do Ato Médico) + Resolução CFM "
            "2.225/2019"
        ),
        "link_lei": (
            "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/"
            "2013/lei/l12842.htm"
        ),
    },
    {
        "cnae": "9602-5/02",
        "orgao_sigla": "ANVISA",
        "obrigatoriedade": "condicional",
        "condicoes_obrigatorio": (
            "Exigido se a empresa MANIPULA medicamentos/cosméticos "
            "(formulação própria) — precisa de AFE. Salão comum "
            "apenas aplica produtos já registrados, dispensa AFE."
        ),
        "condicoes_dispensa": (
            "Salão/clínica de estética que apenas USA produtos "
            "industrializados (cosméticos com registro ANVISA) sem "
            "manipulação própria não precisa de AFE."
        ),
        "base_legal": "Lei 6.360/76 + RDC ANVISA 16/2014",
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l6360.htm",
    },

    # =============================================================
    # TRANSPORTE DE CARGA
    # =============================================================
    {
        "cnae": "4930-2/02",   # Transporte rodoviário de carga - intermunicipal
        "orgao_sigla": "ANTT",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Empresa de transporte rodoviário de cargas precisa de "
            "Registro Nacional de Transportadores Rodoviários de "
            "Cargas (RNTRC) — ETC (Empresa de Transporte de Cargas) "
            "ou CTC (Cooperativa)."
        ),
        "base_legal": (
            "Lei 11.442/2007 + Resolução ANTT 5.862/2019"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/_ato2007-"
                    "2010/2007/lei/l11442.htm",
    },

    # =============================================================
    # CONSTRUÇÃO CIVIL
    # =============================================================
    {
        "cnae": "4120-4/00",   # Construção de edifícios
        "orgao_sigla": "CREA",
        "obrigatoriedade": "sim",
        "condicoes_obrigatorio": (
            "Construtora precisa de registro PJ no CREA do estado "
            "+ Responsável Técnico engenheiro/arquiteto. Cada obra "
            "exige ART/RRT específica."
        ),
        "base_legal": (
            "Lei 5.194/66 + Resolução CONFEA 1.121/2019"
        ),
        "link_lei": "https://www.planalto.gov.br/ccivil_03/leis/l5194.htm",
    },
]


def main():
    init_db()
    print("Populando regras OFICIAIS por CNAE × órgão...")
    print("=" * 65)
    n, falhas = 0, 0
    for r in REGRAS:
        try:
            upsert_regra_oficial(
                **r,
                autor="seed (popular_regras_oficiais.py)",
            )
            obg = r["obrigatoriedade"].upper()
            cor = {"SIM": "🔴", "NAO": "🟢", "CONDICIONAL": "🟡"}.get(obg, "  ")
            uf = f"/{r.get('orgao_uf')}" if r.get("orgao_uf") else ""
            print(
                f"  {cor} {r['cnae']:12s} → {r['orgao_sigla']:8s}{uf:4s} "
                f"{obg}"
            )
            n += 1
        except Exception as exc:
            falhas += 1
            print(f"  ✗ {r['cnae']:12s} → {r['orgao_sigla']:8s} ERRO: {exc}")
    print("=" * 65)
    print(f"Total: {n}/{len(REGRAS)} regras cadastradas/atualizadas.")
    if falhas:
        print(f"⚠️  {falhas} falhas — confira os logs acima.")


if __name__ == "__main__":
    main()
