"""
popular_cnae_bases.py
---------------------
Popula as bases auxiliares do Consultor de CNAE com mapeamentos
curados e fundamentados em legislação:
  - cnae_conselho   → CNAE × conselho profissional
  - cnae_ambiental  → CNAE × CETESB/IBAMA
  - cnae_anvisa     → CNAE × ANVISA

Cada entrada tem `fonte` apontando para a base legal.

Uso:
    python redesim_manager\\popular_cnae_bases.py

Roda como UPSERT — pode rodar várias vezes sem duplicar.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import (
    init_db,
    upsert_cnae_conselho,
    upsert_cnae_ambiental,
    upsert_cnae_anvisa,
    upsert_cnae_outro_registro,
    upsert_cnae_habilitacao_profissional,
)


# =====================================================================
# CONSELHOS PROFISSIONAIS
# Mapeamento conservador — cada linha indica que o CNAE EXIGE registro
# (ou inscrição do responsável técnico) no conselho indicado.
# =====================================================================
CONSELHOS = [
    # ---- MEDICINA HUMANA → CRM (PJ deve registrar + RT) ----
    ("8610-1/01", "CRM", "Conselho Regional de Medicina", "AMBOS",
     "Hospitais — exige inscrição da PJ + RT médico. Lei 3.268/57 + Resoluções CFM."),
    ("8610-1/02", "CRM", "Conselho Regional de Medicina", "AMBOS",
     "Pronto-socorro — PJ + RT. Lei 3.268/57."),
    ("8630-5/01", "CRM", "Conselho Regional de Medicina", "AMBOS",
     "Atividade médica ambulatorial com cirurgia — PJ + RT. Lei 3.268/57."),
    ("8630-5/02", "CRM", "Conselho Regional de Medicina", "AMBOS",
     "Ambulatorial com recursos diagnósticos — PJ + RT. Lei 3.268/57."),
    ("8630-5/03", "CRM", "Conselho Regional de Medicina", "AMBOS",
     "Atividade médica ambulatorial sem cirurgia — PJ + RT. Lei 3.268/57."),

    # ---- ODONTOLOGIA → CRO ----
    ("8630-5/04", "CRO", "Conselho Regional de Odontologia", "AMBOS",
     "Atividade odontológica — PJ + RT. Lei 4.324/64."),

    # ---- ENFERMAGEM → COREN ----
    ("8650-0/01", "COREN", "Conselho Regional de Enfermagem", "AMBOS",
     "Atividades de enfermagem — PJ + RT. Lei 5.905/73."),

    # ---- FISIOTERAPIA / TERAPIA OCUPACIONAL → CREFITO ----
    ("8650-0/04", "CREFITO", "Conselho Regional de Fisioterapia e Terapia Ocupacional", "AMBOS",
     "Fisioterapia — PJ + RT. Lei 6.316/75."),

    # ---- PSICOLOGIA → CRP ----
    ("8650-0/03", "CRP", "Conselho Regional de Psicologia", "AMBOS",
     "Psicologia — PJ + RT. Lei 4.119/62."),

    # ---- NUTRIÇÃO → CRN ----
    ("8690-9/03", "CRN", "Conselho Regional de Nutricionistas", "AMBOS",
     "Nutrição — PJ + RT. Lei 6.583/78."),

    # ---- VETERINÁRIA → CRMV ----
    ("7500-1/00", "CRMV", "Conselho Regional de Medicina Veterinária", "AMBOS",
     "Veterinária — PJ + RT. Lei 5.517/68."),

    # ---- FARMÁCIA → CRF (drogarias só RT, indústria PJ+RT) ----
    ("4771-7/01", "CRF", "Conselho Regional de Farmácia", "RT_OBRIGATORIO",
     "Drogaria — apenas RT farmacêutico durante o atendimento. Lei 3.820/60."),
    ("4771-7/02", "CRF", "Conselho Regional de Farmácia", "AMBOS",
     "Farmácia de manipulação — PJ + RT integral. Lei 3.820/60 + RDC 67/07."),
    ("4771-7/03", "CRF", "Conselho Regional de Farmácia", "RT_OBRIGATORIO",
     "Farmácia homeopática — RT. Lei 3.820/60."),
    ("8630-5/06", "CRF", "Conselho Regional de Farmácia", "RT_OBRIGATORIO",
     "Vacinação humana — RT farmacêutico. Lei 3.820/60."),

    # ---- ENGENHARIA / ARQUITETURA → CREA / CAU (PJ + ART) ----
    ("7110-1/00", "CREA", "Conselho Regional de Engenharia e Agronomia", "AMBOS",
     "Serviços de engenharia — PJ + ART. Lei 5.194/66."),
    ("7111-1/00", "CAU", "Conselho de Arquitetura e Urbanismo", "AMBOS",
     "Arquitetura — PJ + RRT. Lei 12.378/10."),
    ("7112-0/00", "CREA", "Conselho Regional de Engenharia e Agronomia", "AMBOS",
     "Engenharia — PJ + ART. Lei 5.194/66."),
    ("7119-7/01", "CREA", "Conselho Regional de Engenharia e Agronomia", "AMBOS",
     "Cartografia — PJ + ART. Lei 5.194/66."),
    ("7119-7/03", "CREA", "Conselho Regional de Engenharia e Agronomia", "AMBOS",
     "Desenho técnico — PJ + ART. Lei 5.194/66."),

    # ---- QUÍMICA → CRQ ----
    ("7120-1/00", "CRQ", "Conselho Regional de Química", "AMBOS",
     "Análises técnicas — PJ + RT químico. Lei 2.800/56."),

    # ---- CONTABILIDADE → CRC ----
    ("6920-6/01", "CRC", "Conselho Regional de Contabilidade", "AMBOS",
     "Escritório contábil — PJ + RT. Decreto-Lei 9.295/46."),
    ("6920-6/02", "CRC", "Conselho Regional de Contabilidade", "AMBOS",
     "Auditoria contábil — PJ + RT. DL 9.295/46."),

    # ---- ADVOCACIA → OAB (sociedade de advogados) ----
    ("6911-7/01", "OAB", "Ordem dos Advogados do Brasil", "AMBOS",
     "Sociedade de advogados — registro na OAB-SP + advogados habilitados. Lei 8.906/94."),
    ("6911-7/02", "OAB", "Ordem dos Advogados do Brasil", "RT_OBRIGATORIO",
     "Atividades auxiliares — depende do escopo. Lei 8.906/94."),

    # ---- ECONOMIA → CORECON ----
    ("7020-4/00", "CORECON", "Conselho Regional de Economia", "AMBOS",
     "Consultoria empresarial econômica — PJ + RT. Lei 1.411/51."),

    # ---- BIOLOGIA → CRBio ----
    ("7490-1/01", "CRBio", "Conselho Regional de Biologia", "RT_OBRIGATORIO",
     "Apoio agropecuário — RT biólogo. Lei 6.684/79."),

    # ---- BIOMEDICINA → CRBM ----
    ("8630-5/06", "CRBM", "Conselho Regional de Biomedicina", "RT_OBRIGATORIO",
     "Análises clínicas — RT biomédico. Lei 6.684/79."),

    # ---- EDUCAÇÃO FÍSICA → CREF ----
    ("9313-1/00", "CREF", "Conselho Regional de Educação Física", "AMBOS",
     "Academia/condicionamento — PJ + RT. Lei 9.696/98."),
    ("8550-3/02", "CREF", "Conselho Regional de Educação Física", "RT_OBRIGATORIO",
     "Atividades de apoio à educação — RT. Lei 9.696/98."),

    # ---- AUDITORIA INDEPENDENTE → CVM (apenas se cliente é cia aberta) ----
    ("6920-6/02", "CVM", "Comissão de Valores Mobiliários", "INSCRICAO_PJ",
     "Apenas se auditar cias abertas. Instrução CVM 308/99."),
]


# =====================================================================
# OUTROS REGISTROS FEDERAIS — CTF/IBAMA, MAPA, INMETRO
# =====================================================================
OUTROS_REGISTROS = [
    # ---- CTF/IBAMA — atividades potencialmente poluidoras (Lei 6.938/81) ----
    ("4731-8/00", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Postos de combustível — categoria 17 do CTF.",
     "Lei 6.938/81 + IN IBAMA 6/13."),
    ("9601-7/01", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Lavanderia industrial — efluentes.",
     "Lei 6.938/81 + IN IBAMA 6/13."),
    ("4520-0/01", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Oficina mecânica — geração de óleos usados (resíduo perigoso).",
     "Lei 6.938/81 + IN IBAMA 6/13."),
    ("2511-0/00", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Estruturas metálicas — emissões e resíduos.",
     "Lei 6.938/81."),
    ("1011-2/01", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Frigorífico — efluentes orgânicos pesados.",
     "Lei 6.938/81."),
    ("2011-8/00", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Indústria química básica — alta periculosidade.",
     "Lei 6.938/81."),
    ("1610-2/03", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Atividades poluidoras", "OBRIGATORIO",
     "Serraria — material particulado.",
     "Lei 6.938/81."),
    ("3811-4/00", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Resíduos sólidos", "OBRIGATORIO",
     "Coleta de resíduos não-perigosos.",
     "Lei 6.938/81."),
    ("3812-2/00", "CTF_IBAMA", "IBAMA — Cadastro Técnico Federal",
     "Resíduos perigosos", "OBRIGATORIO",
     "Coleta de resíduos perigosos — autorização especial.",
     "Lei 6.938/81 + Resolução CONAMA 313/02."),

    # ---- MAPA — alimentos animais, sementes, agrotóxicos, fertilizantes ----
    ("1011-2/01", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Produtos de origem animal (frigorífico)", "OBRIGATORIO",
     "Frigorífico bovino — SIF (Serviço de Inspeção Federal).",
     "Decreto 9.013/17 + Lei 1.283/50."),
    ("1012-1/01", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Produtos de origem animal", "OBRIGATORIO",
     "Abate de aves — SIF.",
     "Decreto 9.013/17."),
    ("1013-9/01", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Produtos de origem animal", "OBRIGATORIO",
     "Fabricação de produtos cárneos — SIF.",
     "Decreto 9.013/17."),
    ("1052-0/00", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Laticínios", "OBRIGATORIO",
     "Fabricação de laticínios — SIF (estadual SISBI ou federal SIF).",
     "Decreto 9.013/17."),
    ("4623-1/06", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Defensivos/Agrotóxicos", "OBRIGATORIO",
     "Comércio atacadista de defensivos agrícolas — registro AGROFIT.",
     "Lei 7.802/89 + Decreto 4.074/02."),
    ("4774-1/00", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Sementes", "OBRIGATORIO",
     "Comércio de sementes — Renasem.",
     "Lei 10.711/03 + Decreto 5.153/04."),
    ("1066-0/00", "MAPA", "Ministério da Agricultura, Pecuária e Abastecimento",
     "Alimentação animal", "OBRIGATORIO",
     "Fabricação de ração — registro MAPA.",
     "Decreto 6.296/07 (rações)."),

    # ---- INMETRO — metrologia legal ----
    ("3320-2/01", "INMETRO", "INMETRO — Instituto Nacional de Metrologia",
     "Instrumentos de medição", "OBRIGATORIO",
     "Instalação de balanças/medidores — credenciamento INMETRO.",
     "Lei 9.933/99."),
    ("4541-2/01", "INMETRO", "INMETRO — Instituto Nacional de Metrologia",
     "Veículos", "OBRIGATORIO",
     "Comércio de veículos novos — selos INMETRO em equipamentos.",
     "Resolução INMETRO 11/01."),
    ("4774-1/00", "INMETRO", "INMETRO — Instituto Nacional de Metrologia",
     "Pré-medidos", "DEPENDE",
     "Se vende pré-medidos (sementes embaladas) — RTAC.",
     "Resolução INMETRO 248/2008."),
]


# =====================================================================
# AMBIENTAL — atividades obviamente sujeitas a licença ambiental
# Foco: SP/CETESB. Lista conservadora (apenas os MAIS comuns).
# =====================================================================
AMBIENTAIS = [
    # Postos de combustível — clássico
    ("4731-8/00", True, "CETESB", "M",
     "LP+LI+LO",
     "Posto de combustíveis — atividade poluidora.",
     "Decreto Estadual SP 47.397/02 + Resolução CONAMA 273/00."),
    # Lavanderias industriais
    ("9601-7/01", True, "CETESB", "P",
     "LP+LI+LO",
     "Lavanderia para terceiros — efluentes líquidos.",
     "Decreto Estadual SP 47.397/02."),
    # Oficinas mecânicas (variável)
    ("4520-0/01", True, "CETESB", "P",
     "LP+LI+LO",
     "Oficina mecânica de veículos — geração de resíduos.",
     "Decreto Estadual SP 47.397/02 (verificar porte)."),
    # Serralherias / metalurgia
    ("2511-0/00", True, "CETESB", "P-M",
     "LP+LI+LO",
     "Fabricação de estruturas metálicas — emissões e resíduos.",
     "Decreto Estadual SP 47.397/02."),
    # Tinturaria / lavagem têxtil
    ("1340-5/02", True, "CETESB", "M",
     "LP+LI+LO",
     "Tingimento têxtil — efluentes.",
     "Decreto Estadual SP 47.397/02."),
    # Indústria química básica
    ("2011-8/00", True, "IBAMA", "G",
     "LP+LI+LO",
     "Fabricação de cloro e álcalis — alto potencial poluidor.",
     "Resolução CONAMA 237/97 + IN IBAMA."),
    # Frigoríficos
    ("1011-2/01", True, "CETESB", "M-G",
     "LP+LI+LO",
     "Frigorífico — efluentes orgânicos pesados.",
     "Decreto Estadual SP 47.397/02."),
    # Fabricação de produtos químicos
    ("2029-1/00", True, "CETESB", "M",
     "LP+LI+LO",
     "Fabricação de produtos químicos diversos.",
     "Decreto Estadual SP 47.397/02."),
    # Marcenaria/serraria
    ("1610-2/03", True, "CETESB", "P",
     "LP+LI+LO",
     "Serraria — material particulado.",
     "Decreto Estadual SP 47.397/02."),
]


# =====================================================================
# ANVISA — atividades sob vigilância federal
# =====================================================================
ANVISA = [
    # Alimentos
    ("1066-0/00", True, "Alimentos",
     "Fabricação de alimentos infantis. Notificação ANVISA + RT.",
     "RDC 27/2010, Lei 6.360/76."),
    ("1031-7/00", True, "Alimentos",
     "Fabricação de conservas de frutas/legumes. Boas Práticas + Notificação.",
     "RDC 49/2013, RDC 275/02."),
    ("1099-6/01", True, "Alimentos",
     "Fabricação de outros alimentos. RDC 49 + Boas Práticas.",
     "RDC 49/2013, RDC 275/02."),

    # Cosméticos
    ("4729-6/01", True, "Cosméticos",
     "Comércio varejista de cosméticos. Notificação se importa/fabrica.",
     "RDC 7/2015, Lei 6.360/76."),
    ("4773-3/00", True, "Cosméticos",
     "Comércio varejista de perfumaria.",
     "RDC 7/2015, Lei 6.360/76."),
    ("2063-1/00", True, "Cosméticos",
     "Fabricação de cosméticos/perfumaria. AFE + Notificação obrigatórias.",
     "RDC 7/2015, RDC 16/2014, Lei 6.360/76."),

    # Medicamentos
    ("2110-6/00", True, "Medicamentos",
     "Fabricação de produtos farmoquímicos. AFE + GMP.",
     "Lei 6.360/76, RDC 17/2010."),
    ("2121-1/01", True, "Medicamentos",
     "Fabricação de medicamentos alopáticos.",
     "Lei 6.360/76, RDC 17/2010."),
    ("4771-7/01", True, "Medicamentos",
     "Comércio de medicamentos. AFE + RT farmacêutico.",
     "Lei 5.991/73, RDC 44/2009."),
    ("4771-7/02", True, "Medicamentos",
     "Farmácia de manipulação. AFE + RT + GMP.",
     "RDC 67/07, Lei 5.991/73."),
    ("4644-3/01", True, "Medicamentos",
     "Distribuição de medicamentos. AFE + RT.",
     "Lei 5.991/73."),

    # Saneantes
    ("2061-4/00", True, "Saneantes",
     "Fabricação de sabões/detergentes. Notificação + AFE.",
     "RDC 59/2010, Lei 6.360/76."),

    # Produtos para Saúde / Hospitalar
    ("8610-1/01", True, "Produtos para Saúde",
     "Hospital — alvará sanitário com classificação de risco.",
     "RDC 50/2002, RDC 63/2011."),
    ("8610-1/02", True, "Produtos para Saúde",
     "Pronto-socorro — alvará sanitário.",
     "RDC 50/2002, RDC 63/2011."),
    ("3250-7/01", True, "Produtos para Saúde",
     "Fabricação de instrumentos cirúrgicos. AFE + GMP.",
     "RDC 16/2013, Lei 6.360/76."),
    ("4664-8/00", True, "Produtos para Saúde",
     "Comércio atacadista de máquinas hospitalares.",
     "Lei 6.360/76."),
]


# =====================================================================
# HABILITAÇÃO PROFISSIONAL CONDICIONAL
# Cobre o caso clássico: o CNAE em si NÃO obriga a PJ a se registrar
# em conselho, mas certas atividades dentro dele exigem profissional
# habilitado. Ex.: clínica de estética que aplica botox — a clínica não
# precisa de inscrição PJ no CRM, mas só pode aplicar botox quem é
# médico (ou outro profissional habilitado por lei).
#
# Schema: (cnae, atividade_gatilho, conselho_sigla, quem_executa,
#          nivel_risco, fonte, observacao)
# =====================================================================
HABILITACOES_PROFISSIONAIS = [
    # ---- ESTÉTICA / CUIDADOS COM A BELEZA ----
    ("9602-5/02", "Aplicação de toxina botulínica (botox) e preenchedores",
     "CRM",
     "Médico (CRM); Enfermeiro habilitado em estética (COREN); "
     "Odontólogo (CRO) em região buco-maxilo-facial; "
     "Biomédico esteta (CRBM) com habilitação específica",
     "ALTO",
     "CFM Resolução 2.219/2018; Lei 12.842/2013; "
     "ANVISA RDC 67/2009; Cofen Resolução 626/2020",
     "A clínica/salão não precisa de inscrição PJ em conselho, "
     "mas o procedimento só pode ser executado por profissional "
     "habilitado. Exige licença sanitária para o ambiente."),

    ("9602-5/02", "Microagulhamento profundo / peeling médio ou profundo / "
                  "laser ablativo / plasma rico em plaquetas",
     "CRM",
     "Médico (CRM); Biomédico esteta (CRBM) habilitado",
     "ALTO",
     "ANVISA RDC 36/2008; CFM 2.219/2018",
     "Procedimentos invasivos exigem alvará sanitário do estabelecimento "
     "e habilitação do profissional."),

    ("9602-5/02", "Massagem terapêutica / drenagem linfática terapêutica",
     "CREFITO",
     "Fisioterapeuta (CREFITO); Massoterapeuta com formação reconhecida",
     "MEDIO",
     "Lei 8.856/1994; COFFITO Resolução 380/2010",
     "Diferenciar massagem estética (livre) de massagem terapêutica "
     "(privativa do fisioterapeuta)."),

    ("9609-2/99", "Aplicação de toxina botulínica, preenchedores e "
                  "procedimentos estéticos injetáveis",
     "CRM",
     "Médico (CRM); Enfermeiro habilitado (COREN); Odontólogo (CRO) na "
     "região buco-maxilo-facial; Biomédico esteta (CRBM) habilitado",
     "ALTO",
     "CFM 2.219/2018; Lei 12.842/2013",
     "Mesmo em CNAE residual de serviços pessoais, a aplicação de "
     "injetáveis exige habilitação profissional."),

    # ---- BARBEARIA / SALÃO (caso de tatuagem e piercing) ----
    ("9602-5/01", "Tatuagem e/ou piercing",
     None,
     "Tatuador/piercer com curso de biossegurança reconhecido + alvará "
     "sanitário do estabelecimento. Não há conselho de classe, mas "
     "exige treinamento formal.",
     "MEDIO",
     "ANVISA RDC 55/2008; legislações municipais",
     "Exige licença sanitária do estabelecimento mesmo quando o CNAE "
     "é de baixo risco."),

    # ---- ACADEMIAS / CONDICIONAMENTO FÍSICO ----
    ("9313-1/00", "Prescrição e supervisão de exercício físico",
     "CREF",
     "Profissional de Educação Física registrado no CREF",
     "ALTO",
     "Lei 9.696/1998",
     "A academia precisa ter Responsável Técnico (RT) registrado no "
     "CREF e profissionais habilitados na sala de musculação."),

    # ---- COMÉRCIO DE PRODUTOS DE SAÚDE ----
    ("4771-7/01", "Manipulação ou dispensação de medicamentos",
     "CRF",
     "Farmacêutico (CRF) — Responsável Técnico obrigatório",
     "ALTO",
     "Lei 13.021/2014; ANVISA RDC 44/2009",
     "Drogaria/farmácia exige farmacêutico RT presente no horário "
     "de funcionamento. CNAE 4771-7/01 já tem essa exigência no "
     "cnae_conselho — listado aqui pra cobertura."),

    ("4773-3/00", "Venda de medicamentos isentos de prescrição (OTC) ou "
                  "produtos para saúde regulados pela ANVISA",
     "CRF",
     "Farmacêutico (CRF) como RT (se há manipulação ou OPME); "
     "Engenheiro biomédico em alguns casos de OPME complexo",
     "MEDIO",
     "ANVISA RDC 16/2014; Lei 13.021/2014",
     "Comércio de artigos médicos e ortopédicos. Se vende dispositivos "
     "implantáveis ou OPME complexo, exige RT habilitado."),

    ("4774-1/00", "Confecção e adaptação de lentes oftálmicas",
     None,
     "Técnico em Óptica com curso reconhecido pelo MEC + médico "
     "oftalmologista para receita (não da empresa, mas pré-requisito)",
     "MEDIO",
     "Decreto 24.492/1934; resoluções dos órgãos de classe da óptica",
     "Não há conselho federal único da óptica, mas a habilitação "
     "técnica é exigida."),

    # ---- INTERMEDIAÇÃO / CORRETAGEM ----
    ("7490-1/04", "Corretagem de seguros",
     None,
     "Corretor de seguros habilitado pela Susep (Resolução CNSP)",
     "ALTO",
     "Decreto-Lei 73/1966; Resoluções CNSP",
     "Corretagem exige habilitação da Susep (não é conselho de classe). "
     "A empresa também deve ser registrada como sociedade corretora."),

    ("6822-6/00", "Corretagem ou administração de imóveis",
     "CRECI",
     "Corretor de imóveis registrado no CRECI",
     "ALTO",
     "Lei 6.530/1978",
     "Atividade privativa do corretor. A imobiliária deve ter "
     "inscrição PJ no CRECI."),

    # ---- ALIMENTOS / VIGILÂNCIA ----
    ("5611-2/01", "Manipulação de alimentos em estabelecimento (restaurante)",
     None,
     "Manipulador de alimentos com curso de Boas Práticas reconhecido; "
     "Responsável Técnico — nutricionista (CRN) recomendado para "
     "refeições coletivas",
     "MEDIO",
     "ANVISA RDC 216/2004; Lei 8.234/1991 (nutricionista)",
     "Nutricionista é RT obrigatório em refeições coletivas (UAN) — "
     "ver CNAE 5620-1."),

    ("5620-1/01", "Refeições coletivas / UAN (Unidade de Alimentação e "
                  "Nutrição)",
     "CRN",
     "Nutricionista (CRN) — Responsável Técnico obrigatório",
     "ALTO",
     "Lei 8.234/1991; CFN Resolução 600/2018",
     "Empresas de refeições coletivas devem ter nutricionista "
     "registrado como RT."),

    # ---- EDUCAÇÃO INFANTIL ----
    ("8511-2/00", "Educação infantil — creche",
     None,
     "Pedagogos habilitados + autorização do Conselho de Educação "
     "(estadual ou municipal)",
     "ALTO",
     "Lei 9.394/1996 (LDB); resoluções dos conselhos de educação",
     "Exige autorização específica do Conselho Estadual/Municipal "
     "de Educação."),

    # ---- VETERINÁRIO ----
    ("7500-1/00", "Atividades veterinárias",
     "CRMV",
     "Médico Veterinário (CRMV) — Responsável Técnico obrigatório",
     "ALTO",
     "Lei 5.517/1968",
     "Pet shop com banho/tosa simples NÃO exige RT; clínica/hospital "
     "veterinário SIM."),

    # ---- TRANSPORTE / TÁXI ----
    ("4923-0/01", "Serviço de táxi",
     None,
     "Motorista profissional com curso de transporte de passageiros "
     "(Contran Resolução 168/2004 + lei municipal)",
     "MEDIO",
     "Lei 12.468/2011 (regulamentação do taxista); leis municipais",
     "Atividade privativa do taxista habilitado pelo município."),
]


def main():
    init_db()

    print("📚 Populando bases do Consultor de CNAE...\n")

    # Conselhos (com tipo_registro)
    n = 0
    for cnae, sigla, nome, tipo_reg, fonte in CONSELHOS:
        upsert_cnae_conselho(
            cnae, sigla,
            conselho_nome=nome,
            obrigatoriedade="OBRIGATORIO",
            tipo_registro=tipo_reg,
            fonte=fonte,
        )
        n += 1
    print(f"✅ {n} mapeamentos CNAE × Conselho profissional")

    # Ambiental
    n = 0
    for cnae, exige, orgao, porte, tipo, obs, fonte in AMBIENTAIS:
        upsert_cnae_ambiental(
            cnae, exige_licenca=exige, orgao=orgao,
            porte_padrao=porte, tipo_licenca=tipo,
            observacao=obs, fonte=fonte,
        )
        n += 1
    print(f"✅ {n} mapeamentos CNAE × Licenciamento Ambiental")

    # ANVISA
    n = 0
    for cnae, exige, cat, obs, fonte in ANVISA:
        upsert_cnae_anvisa(
            cnae, exige_anvisa=exige, categoria=cat,
            observacao=obs, fonte=fonte,
        )
        n += 1
    print(f"✅ {n} mapeamentos CNAE × ANVISA")

    # Outros registros (CTF/IBAMA, MAPA, INMETRO)
    n = 0
    for cnae, orgao, nome, cat, obrig, obs, fonte in OUTROS_REGISTROS:
        upsert_cnae_outro_registro(
            cnae, orgao,
            orgao_nome=nome, categoria=cat,
            obrigatoriedade=obrig,
            observacao=obs, fonte=fonte,
        )
        n += 1
    print(f"✅ {n} mapeamentos CNAE × Outros registros (CTF/IBAMA, MAPA, INMETRO)")

    # Habilitações profissionais CONDICIONAIS
    n = 0
    for (cnae, ativ, sigla, quem, nivel, fonte, obs) in HABILITACOES_PROFISSIONAIS:
        upsert_cnae_habilitacao_profissional(
            cnae,
            atividade_gatilho=ativ,
            quem_executa=quem,
            conselho_sigla=sigla,
            nivel_risco=nivel,
            fonte=fonte,
            observacao=obs,
        )
        n += 1
    print(f"✅ {n} habilitações profissionais condicionais "
          f"(ex.: botox em CNAE de estética)")

    print("\n✨ Bases populadas. Teste no app: 🔬 Consultor de CNAE")


if __name__ == "__main__":
    main()
