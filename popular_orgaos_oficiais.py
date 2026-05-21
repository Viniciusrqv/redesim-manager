"""
popular_orgaos_oficiais.py
--------------------------
Popula a tabela `orgaos_oficiais` com os principais órgãos brasileiros
de regulação/fiscalização que aparecem nas análises de CNAE.

Cada entrada tem:
  - sigla, nome
  - categoria   : 'conselho' | 'vigilancia' | 'ambiental' | 'bombeiros'
                  | 'cadastro' | 'transportes' | 'agricultura' | 'outros'
  - esfera      : 'federal' | 'estadual' | 'municipal'
  - uf          : se estadual/municipal (ex.: 'SP')
  - link_consulta / link_cadastro
  - descricao   : o que o órgão regula
  - observacoes : dicas práticas

Rode 1x (idempotente):
    python redesim_manager/popular_orgaos_oficiais.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db, upsert_orgao_oficial  # noqa: E402

# =====================================================================
# CATÁLOGO
# =====================================================================
ORGAOS = [
    # ---------------- CADASTROS FEDERAIS ----------------
    {
        "sigla": "RFB",
        "nome": "Receita Federal do Brasil — Cadastro CNPJ",
        "categoria": "cadastro", "esfera": "federal",
        "descricao": "Cadastro Nacional da Pessoa Jurídica. Toda PJ "
                     "precisa ter CNPJ ativo e situação cadastral OK.",
        "link_consulta": "https://solucoes.receita.fazenda.gov.br/"
                         "Servicos/cnpjreva/cnpjreva_solicitacao.asp",
        "link_cadastro": "https://www.gov.br/empresas-e-negocios/"
                         "pt-br/redesim",
        "observacoes": "Consulta via BrasilAPI/ReceitaWS já é "
                       "automática no app — esta página é só pra "
                       "confirmar manualmente.",
    },
    {
        "sigla": "SIMPLES",
        "nome": "Simples Nacional — Receita Federal",
        "categoria": "cadastro", "esfera": "federal",
        "descricao": "Regime tributário simplificado pra ME e EPP. "
                     "Verifica enquadramento e CNAEs permitidos.",
        "link_consulta": "https://www8.receita.fazenda.gov.br/"
                         "SimplesNacional/Aplicacoes/ATSPO/"
                         "ConsultaOptantes.app/",
        "link_cadastro": "https://www8.receita.fazenda.gov.br/"
                         "SimplesNacional/",
        "observacoes": "Anexo I a V — verifique se o CNAE é permitido.",
    },
    {
        "sigla": "REDESIM",
        "nome": "Rede Nacional para Simplificação do Registro e "
                "Legalização de Empresas e Negócios",
        "categoria": "cadastro", "esfera": "federal",
        "descricao": "Portal unificado pra abertura, alteração e baixa "
                     "de empresas (viabilidade + licenciamento).",
        "link_consulta": "https://www.gov.br/empresas-e-negocios/"
                         "pt-br/redesim",
        "link_cadastro": "https://www.gov.br/empresas-e-negocios/"
                         "pt-br/redesim/abertura-de-empresa",
    },
    # ---------------- VIGILÂNCIA SANITÁRIA ----------------
    {
        "sigla": "ANVISA",
        "nome": "Agência Nacional de Vigilância Sanitária",
        "categoria": "vigilancia", "esfera": "federal",
        "descricao": "Regula medicamentos, alimentos, cosméticos, "
                     "saneantes, dispositivos médicos, produtos pra "
                     "saúde. AFE/AE pra empresas do setor.",
        "link_consulta": "https://consultas.anvisa.gov.br/",
        "link_cadastro": "https://www.gov.br/anvisa/pt-br/sistemas/"
                         "peticionamento",
        "observacoes": "Empresas com CNAE de saúde, medicamentos, "
                       "cosméticos ou alimentos podem precisar de AFE.",
    },
    {
        "sigla": "CVS-SP",
        "nome": "Centro de Vigilância Sanitária do Estado de SP",
        "categoria": "vigilancia", "esfera": "estadual", "uf": "SP",
        "descricao": "Regula vigilância sanitária estadual em SP. "
                     "Portaria CVS 04/2011 + 06/99 classifica risco.",
        "link_consulta": "http://www.cvs.saude.sp.gov.br/",
        "link_cadastro": "http://siteapp.saude.sp.gov.br/sivisa-web/",
        "observacoes": "Risco I (baixo) — comunicado; Risco II/III/IV "
                       "(médio/alto) — licença sanitária + vistoria.",
    },
    {
        "sigla": "COVISA-SP",
        "nome": "Coord. de Vigilância em Saúde — Município de SP",
        "categoria": "vigilancia", "esfera": "municipal", "uf": "SP",
        "municipio": "São Paulo",
        "descricao": "Vigilância sanitária do município de SP. "
                     "Emite Licença Sanitária Municipal.",
        "link_consulta": "https://www.prefeitura.sp.gov.br/cidade/"
                         "secretarias/saude/vigilancia_em_saude/",
        "link_cadastro": "https://www.prefeitura.sp.gov.br/cidade/"
                         "secretarias/saude/vigilancia_em_saude/"
                         "vigilancia_sanitaria/index.php",
    },
    # ---------------- BOMBEIROS ----------------
    {
        "sigla": "CBPMESP",
        "nome": "Corpo de Bombeiros — PM do Estado de SP (Via Fácil)",
        "categoria": "bombeiros", "esfera": "estadual", "uf": "SP",
        "descricao": "Emite AVCB (Auto de Vistoria) e CLCB "
                     "(Certificado de Licença) conforme IT-01 e o grau "
                     "de risco da edificação.",
        "link_consulta": "https://www.viafacil.sp.gov.br/sccdwe/"
                         "consultaAvcb.do",
        "link_cadastro": "https://www.viafacil.sp.gov.br/",
        "observacoes": "Renovação anual ou trienal conforme tipo. "
                       "App tem alertas automáticos 60d antes.",
    },
    # ---------------- AMBIENTAL ----------------
    {
        "sigla": "CETESB",
        "nome": "Companhia Ambiental do Estado de SP",
        "categoria": "ambiental", "esfera": "estadual", "uf": "SP",
        "descricao": "Licenciamento ambiental no estado de SP "
                     "(LP, LI, LO + CADRI pra resíduos).",
        "link_consulta": "https://e.cetesb.sp.gov.br/sigam/",
        "link_cadastro": "https://servicos.cetesb.sp.gov.br/",
    },
    {
        "sigla": "IBAMA",
        "nome": "Instituto Brasileiro do Meio Ambiente — CTF/APP",
        "categoria": "ambiental", "esfera": "federal",
        "descricao": "Cadastro Técnico Federal de Atividades "
                     "Potencialmente Poluidoras. Obrigatório pra muitos "
                     "CNAEs industriais e de transporte.",
        "link_consulta": "https://www.ibama.gov.br/servicosonline/"
                         "ctf-app",
        "link_cadastro": "https://servicos.ibama.gov.br/",
        "observacoes": "Verifica se o CNAE consta na lista do Anexo "
                       "da IN IBAMA 06/2013 (atualizada).",
    },
    # ---------------- AGRICULTURA / VETERINÁRIO ----------------
    {
        "sigla": "MAPA",
        "nome": "Ministério da Agricultura — SIPEAGRO",
        "categoria": "agricultura", "esfera": "federal",
        "descricao": "Sistema Integrado de Produtos e Estabelecimentos "
                     "Agropecuários. Obrigatório p/ comércio de insumos "
                     "agrícolas, sementes, fertilizantes, agrotóxicos.",
        "link_consulta": "https://sistemasweb.agricultura.gov.br/"
                         "sipeagro/login.action",
        "link_cadastro": "https://www.gov.br/agricultura/pt-br/"
                         "assuntos/insumos-agropecuarios",
    },
    {
        "sigla": "SIF",
        "nome": "Serviço de Inspeção Federal — produtos animais",
        "categoria": "agricultura", "esfera": "federal",
        "descricao": "Inspeção de produtos de origem animal "
                     "(carnes, leite, ovos, mel, pescado).",
        "link_consulta": "https://www.gov.br/agricultura/pt-br/"
                         "assuntos/inspecao/produtos-animal",
        "link_cadastro": "https://www.gov.br/agricultura/pt-br/"
                         "assuntos/inspecao",
    },
    # ---------------- TRANSPORTES / TELECOM / ENERGIA ----------------
    {
        "sigla": "ANTT",
        "nome": "Agência Nacional de Transportes Terrestres — RNTRC",
        "categoria": "transportes", "esfera": "federal",
        "descricao": "Registro Nacional de Transportadores Rodoviários "
                     "de Cargas. Obrigatório p/ TAC, ETC e CTC.",
        "link_consulta": "https://www.gov.br/antt/pt-br/assuntos/"
                         "rntrc-nova-pagina",
        "link_cadastro": "https://portalrntrc.antt.gov.br/",
    },
    {
        "sigla": "ANAC",
        "nome": "Agência Nacional de Aviação Civil",
        "categoria": "transportes", "esfera": "federal",
        "descricao": "Regula aviação civil — empresas aéreas, "
                     "escolas de aviação, manutenção de aeronaves.",
        "link_consulta": "https://www.gov.br/anac/pt-br",
        "link_cadastro": "https://www.gov.br/anac/pt-br/assuntos/setor-"
                         "regulado",
    },
    {
        "sigla": "ANEEL",
        "nome": "Agência Nacional de Energia Elétrica",
        "categoria": "outros", "esfera": "federal",
        "descricao": "Regula geração, transmissão, distribuição e "
                     "comercialização de energia elétrica.",
        "link_consulta": "https://www.gov.br/aneel/pt-br",
        "link_cadastro": "https://www.gov.br/aneel/pt-br/assuntos/"
                         "regulacao",
    },
    {
        "sigla": "ANATEL",
        "nome": "Agência Nacional de Telecomunicações",
        "categoria": "outros", "esfera": "federal",
        "descricao": "Telecom — operadoras, provedores, revendas, "
                     "telefonia, TV por assinatura.",
        "link_consulta": "https://sistemas.anatel.gov.br/sa/",
        "link_cadastro": "https://www.gov.br/anatel/pt-br",
    },
    # ---------------- FINANCEIRO / BANCÁRIO ----------------
    {
        "sigla": "BACEN",
        "nome": "Banco Central do Brasil",
        "categoria": "outros", "esfera": "federal",
        "descricao": "Regula instituições financeiras, cooperativas "
                     "de crédito, factorings, corretoras.",
        "link_consulta": "https://www.bcb.gov.br/",
        "link_cadastro": "https://www.bcb.gov.br/estabilidadefinanceira/"
                         "regulacao",
    },
    {
        "sigla": "CVM",
        "nome": "Comissão de Valores Mobiliários",
        "categoria": "outros", "esfera": "federal",
        "descricao": "Regula mercado de capitais — gestores, "
                     "consultores, agentes autônomos.",
        "link_consulta": "https://www.gov.br/cvm/pt-br",
        "link_cadastro": "https://sistemas.cvm.gov.br/",
    },
    {
        "sigla": "SUSEP",
        "nome": "Superintendência de Seguros Privados",
        "categoria": "outros", "esfera": "federal",
        "descricao": "Regula seguros, capitalização e previdência "
                     "complementar aberta. Corretores precisam de "
                     "habilitação SUSEP.",
        "link_consulta": "https://www.gov.br/susep/pt-br",
        "link_cadastro": "https://www2.susep.gov.br/safe/Corretores/",
    },
    # ---------------- CONSELHOS PROFISSIONAIS (FEDERAIS) ----------------
    {
        "sigla": "CFC",
        "nome": "Conselho Federal de Contabilidade",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Contadores e técnicos em contabilidade. "
                     "Escritório precisa de registro CRC.",
        "link_consulta": "https://www3.cfc.org.br/spw/ConsultaNacional/",
        "link_cadastro": "https://cfc.org.br/registro/",
    },
    {
        "sigla": "CFM",
        "nome": "Conselho Federal de Medicina",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Médicos. Clínica/consultório precisa de "
                     "Responsável Técnico (RT) com CRM e registro "
                     "PJ no CRM estadual.",
        "link_consulta": "https://portal.cfm.org.br/busca-medicos/",
        "link_cadastro": "https://portal.cfm.org.br/",
    },
    {
        "sigla": "CFO",
        "nome": "Conselho Federal de Odontologia",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Dentistas. Consultório/clínica precisa de "
                     "registro no CRO + RT.",
        "link_consulta": "https://website.cfo.org.br/",
        "link_cadastro": "https://website.cfo.org.br/profissionais/",
    },
    {
        "sigla": "CFF",
        "nome": "Conselho Federal de Farmácia",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Farmacêuticos. Farmácias, drogarias e "
                     "manipulação precisam de RT farmacêutico.",
        "link_consulta": "https://www.cff.org.br/",
        "link_cadastro": "https://www.cff.org.br/pagina.php?id=164",
    },
    {
        "sigla": "CONFEA",
        "nome": "Conselho Federal de Engenharia e Agronomia (CONFEA/CREA)",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Engenheiros, agrônomos, geólogos, geógrafos, "
                     "técnicos industriais e agrícolas. PJ que presta "
                     "serviço técnico precisa de ART e registro CREA.",
        "link_consulta": "https://www.confea.org.br/",
        "link_cadastro": "https://www.confea.org.br/atendimento",
    },
    {
        "sigla": "CFN",
        "nome": "Conselho Federal de Nutricionistas",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Nutricionistas. Estabelecimentos que prestam "
                     "serviço de nutrição precisam de RT.",
        "link_consulta": "https://www.cfn.org.br/",
        "link_cadastro": "https://www.cfn.org.br/",
    },
    {
        "sigla": "CFP",
        "nome": "Conselho Federal de Psicologia",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Psicólogos. Clínica de psicologia precisa de "
                     "RT psicólogo + registro PJ no CRP estadual.",
        "link_consulta": "https://site.cfp.org.br/",
        "link_cadastro": "https://transparencia.cfp.org.br/",
    },
    {
        "sigla": "COFEN",
        "nome": "Conselho Federal de Enfermagem",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Enfermeiros, técnicos e auxiliares de "
                     "enfermagem. Estabelecimentos de saúde com "
                     "serviço de enfermagem precisam de RT.",
        "link_consulta": "http://www.cofen.gov.br/",
        "link_cadastro": "http://www.cofen.gov.br/",
    },
    {
        "sigla": "COFFITO",
        "nome": "Conselho Federal de Fisioterapia e Terapia Ocupacional",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Fisioterapeutas e terapeutas ocupacionais. "
                     "Clínicas precisam de RT.",
        "link_consulta": "https://www.coffito.gov.br/",
        "link_cadastro": "https://www.coffito.gov.br/",
    },
    {
        "sigla": "CFMV",
        "nome": "Conselho Federal de Medicina Veterinária",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Veterinários e zootecnistas. Pet shops com "
                     "banho/tosa OK sem RT, com clínica/cirurgia "
                     "precisam de RT.",
        "link_consulta": "https://www.cfmv.gov.br/",
        "link_cadastro": "https://www.cfmv.gov.br/",
    },
    {
        "sigla": "CRESS",
        "nome": "Conselho Regional de Serviço Social",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Assistentes sociais. PJ que presta serviço "
                     "social precisa de registro CRESS estadual.",
        "link_consulta": "http://www.cfess.org.br/",
        "link_cadastro": "http://www.cfess.org.br/",
    },
    {
        "sigla": "OAB",
        "nome": "Ordem dos Advogados do Brasil",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Advogados. Sociedade de advogados deve ser "
                     "registrada na OAB seccional do estado.",
        "link_consulta": "https://cna.oab.org.br/",
        "link_cadastro": "https://oab.org.br/",
    },
    {
        "sigla": "CFB",
        "nome": "Conselho Federal de Biologia",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Biólogos. Laboratórios e empresas de análise "
                     "biológica precisam de RT.",
        "link_consulta": "https://www.cfbio.gov.br/",
        "link_cadastro": "https://www.cfbio.gov.br/",
    },
    {
        "sigla": "CFBM",
        "nome": "Conselho Federal de Biomedicina",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Biomédicos. Laboratórios de análises clínicas "
                     "e imagem podem ter RT biomédico.",
        "link_consulta": "https://cfbm.gov.br/",
        "link_cadastro": "https://cfbm.gov.br/",
    },
    {
        "sigla": "CONFEF",
        "nome": "Conselho Federal de Educação Física",
        "categoria": "conselho", "esfera": "federal",
        "descricao": "Profissionais de Educação Física. Academias, "
                     "estúdios e crossfit precisam de RT.",
        "link_consulta": "https://www.confef.org.br/",
        "link_cadastro": "https://www.confef.org.br/",
    },
    # ---------------- BOMBEIROS DE OUTROS ESTADOS (exemplos) ----------------
    # Adicione mais conforme o escritório atende.
]


def main():
    init_db()
    print("Populando catálogo de órgãos oficiais...")
    print("=" * 60)
    n = 0
    for o in ORGAOS:
        try:
            upsert_orgao_oficial(**o)
            n += 1
            print(f"  ✓ {o['sigla']:10s} {o['nome'][:55]}")
        except Exception as exc:
            print(f"  ✗ {o['sigla']:10s} ERRO: {exc}")
    print("=" * 60)
    print(f"Total: {n}/{len(ORGAOS)} órgãos cadastrados/atualizados.")


if __name__ == "__main__":
    main()
