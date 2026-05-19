"""
popular_nr04_graus.py
---------------------
Popula o campo `grau_risco` (1..4) na tabela cnae_risco com os graus
oficiais do Quadro I da NR-04 (MTE), Portaria 8.873/2022 e atualizações.

A NR-04 cobre TODOS os CNAEs do Brasil — quando falta cobertura local,
o sistema usa inferência por SEÇÃO CNAE (prefixo de 2 dígitos), que
nunca está 100% correta mas evita o "não cadastrado".

Uso:
    python redesim_manager\\popular_nr04_graus.py
    python redesim_manager\\popular_nr04_graus.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db, get_conn, registrar_atualizacao_norma


# =====================================================================
# Quadro I NR-04 — GRAU OFICIAL POR CNAE (subclasse 9999-9/99)
# Fonte: Portaria SEPRT 8.873/2022 (NR-04, anexo Quadro I)
# =====================================================================
# Cada tupla: (cnae, grau_risco, descricao_curta)
# Lista curada pelo escopo do escritório do Eduardo (CSM):
# contabilidade, comércio, serviços pessoais/estética, restaurantes,
# saúde, educação, transporte, intermediação, construção.

NR04_GRAUS_OFICIAIS = [
    # ============ INDÚSTRIA (graus 3-4 majoritariamente) ============
    ("1011-2/01", 3, "Frigorífico - abate de bovinos"),
    ("1012-1/01", 3, "Abate de aves"),
    ("1013-9/01", 3, "Fabricação de produtos de carne"),
    ("1052-0/00", 3, "Fabricação de laticínios"),
    ("1071-6/00", 3, "Fabricação de açúcar em bruto"),
    ("1091-1/02", 3, "Fabricação de produtos de padaria e confeitaria"),
    ("1112-7/00", 3, "Fabricação de vinho"),
    ("1311-1/00", 3, "Preparação e fiação de fibras de algodão"),
    ("1610-2/03", 3, "Serrarias com desdobramento de madeira"),
    ("1721-4/00", 3, "Fabricação de papel"),
    ("2011-8/00", 3, "Fabricação de cloro e álcalis"),
    ("2092-4/02", 4, "Fabricação de pólvoras, explosivos e detonantes"),
    ("2330-3/02", 3, "Fabricação de artefatos de cimento"),
    ("2511-0/00", 3, "Fabricação de estruturas metálicas"),
    ("2592-6/01", 3, "Serviços de usinagem"),
    ("2949-2/99", 3, "Fabricação de peças e acessórios para veículos"),

    # ============ CONSTRUÇÃO (grau 3) ============
    ("4120-4/00", 3, "Construção de edifícios"),
    ("4211-1/01", 3, "Construção de rodovias e ferrovias"),
    ("4221-9/04", 3, "Construção de estações e redes de telecomunicações"),
    ("4313-4/00", 3, "Obras de terraplenagem"),
    ("4321-5/00", 3, "Instalação e manutenção elétrica"),
    ("4322-3/01", 3, "Instalação e manutenção hidráulica"),
    ("4399-1/03", 3, "Obras de alvenaria"),
    ("4399-1/05", 3, "Aplicação de revestimentos e resinas em interiores"),

    # ============ COMÉRCIO VAREJISTA (grau 2 majoritário) ============
    ("4711-3/01", 2, "Hipermercados"),
    ("4711-3/02", 2, "Supermercados"),
    ("4712-1/00", 2, "Mercearias e armazéns"),
    ("4713-0/02", 2, "Lojas de variedades"),
    ("4721-1/02", 2, "Padaria e confeitaria com predominância de revenda"),
    ("4721-1/03", 2, "Comércio varejista de laticínios e frios"),
    ("4722-9/01", 2, "Comércio varejista de carnes - açougues"),
    ("4729-6/01", 2, "Tabacaria"),
    ("4729-6/99", 2, "Comércio varejista de produtos alimentícios em geral"),
    ("4744-0/01", 2, "Comércio varejista de ferragens"),
    ("4751-2/01", 2, "Comércio varejista de informática"),
    ("4754-7/01", 2, "Comércio varejista de móveis"),
    ("4757-1/00", 2, "Comércio varejista de equipamentos eletrônicos"),
    ("4759-8/01", 2, "Comércio varejista de eletrodomésticos"),
    ("4761-0/01", 2, "Comércio varejista de livros"),
    ("4763-6/01", 2, "Comércio varejista de brinquedos"),
    ("4771-7/01", 2, "Comércio varejista de medicamentos com manipulação"),
    ("4771-7/02", 2, "Comércio varejista de medicamentos sem manipulação"),
    ("4772-5/00", 2, "Comércio varejista de cosméticos"),
    ("4773-3/00", 2, "Comércio varejista de artigos médicos e ortopédicos"),
    ("4774-1/00", 2, "Comércio varejista de artigos de óptica"),
    ("4781-4/00", 2, "Comércio varejista de artigos do vestuário"),
    ("4782-2/01", 2, "Comércio varejista de calçados"),
    ("4789-0/05", 2, "Comércio varejista de produtos saneantes domissanitários"),

    # ============ COMÉRCIO ATACADISTA / VEÍCULOS (grau 2-3) ============
    ("4511-1/01", 3, "Comércio a varejo de automóveis novos"),
    ("4520-0/01", 3, "Serviços de manutenção e reparação de automóveis"),
    ("4530-7/03", 3, "Comércio a varejo de peças e acessórios para veículos"),

    # ============ ALIMENTAÇÃO (grau 2) ============
    ("5611-2/01", 2, "Restaurantes e similares"),
    ("5611-2/03", 2, "Lanchonetes, casas de chá, sucos e similares"),
    ("5611-2/04", 2, "Bares e outros estabelecimentos especializados em bebidas"),
    ("5611-2/05", 2, "Bares com entretenimento"),
    ("5612-1/00", 2, "Serviços ambulantes de alimentação"),
    ("5620-1/01", 2, "Fornecimento de alimentos preparados (cozinha industrial)"),
    ("5620-1/02", 2, "Catering para eventos"),
    ("5620-1/03", 2, "Cantinas - serviços de alimentação privativos"),
    ("5620-1/04", 2, "Fornecimento de alimentos preparados predominantemente para consumo domiciliar"),

    # ============ HOSPEDAGEM (grau 2) ============
    ("5510-8/01", 2, "Hotéis"),
    ("5510-8/02", 2, "Apart-hotéis"),
    ("5590-6/01", 2, "Albergues, exceto assistenciais"),

    # ============ TRANSPORTE (grau 3 em geral) ============
    ("4921-3/01", 3, "Transporte rodoviário coletivo de passageiros - urbano"),
    ("4923-0/01", 2, "Serviço de táxi"),
    ("4929-9/01", 3, "Transporte rodoviário coletivo - intermunicipal"),
    ("4930-2/02", 3, "Transporte rodoviário de carga - intermunicipal"),
    ("5320-2/02", 2, "Serviços de entrega rápida (motoboy)"),

    # ============ INFORMAÇÃO / TI (grau 1-2) ============
    ("6201-5/01", 1, "Desenvolvimento de programas de computador"),
    ("6202-3/00", 1, "Desenvolvimento e licenciamento de software customizável"),
    ("6203-1/00", 1, "Licenciamento de software não-customizável"),
    ("6204-0/00", 1, "Consultoria em tecnologia da informação"),
    ("6209-1/00", 1, "Suporte técnico em tecnologia da informação"),
    ("6311-9/00", 1, "Tratamento de dados, hospedagem e atividades relacionadas"),

    # ============ FINANCEIRO / SEGUROS (grau 1) ============
    ("6422-1/00", 1, "Bancos múltiplos com carteira comercial"),
    ("6435-2/01", 1, "Banco Central"),
    ("6511-1/01", 1, "Seguros de vida"),
    ("6611-8/01", 1, "Bolsa de valores"),
    ("6619-3/02", 1, "Correspondentes de instituições financeiras"),

    # ============ ATIVIDADES IMOBILIÁRIAS (grau 1-2) ============
    ("6810-2/01", 1, "Compra e venda de imóveis próprios"),
    ("6810-2/02", 1, "Aluguel de imóveis próprios"),
    ("6822-6/00", 1, "Gestão e administração da propriedade imobiliária"),

    # ============ ATIVIDADES PROFISSIONAIS (grau 1) ============
    ("6911-7/01", 1, "Serviços advocatícios"),
    ("6911-7/02", 1, "Atividades auxiliares da justiça"),
    ("6912-5/00", 1, "Cartórios"),
    ("6920-6/01", 1, "Atividades de contabilidade"),
    ("6920-6/02", 1, "Atividades de consultoria e auditoria contábil e tributária"),
    ("7020-4/00", 1, "Atividades de consultoria em gestão empresarial"),
    ("7111-1/00", 2, "Serviços de arquitetura"),
    ("7112-0/00", 2, "Serviços de engenharia"),
    ("7311-4/00", 1, "Agências de publicidade"),
    ("7320-3/00", 1, "Pesquisas de mercado e de opinião pública"),
    ("7410-2/02", 1, "Design de interiores"),
    ("7420-0/01", 1, "Serviços de fotografia"),
    ("7490-1/01", 1, "Atividades de medição e despachante"),
    ("7490-1/04", 1, "Atividades de intermediação e agenciamento de serviços e negócios"),

    # ============ EDUCAÇÃO (grau 1-2) ============
    ("8511-2/00", 2, "Educação infantil - creche"),
    ("8512-1/00", 2, "Educação infantil - pré-escola"),
    ("8513-9/00", 2, "Ensino fundamental"),
    ("8520-1/00", 2, "Ensino médio"),
    ("8531-7/00", 1, "Educação superior - graduação"),
    ("8550-3/02", 1, "Atividades de apoio à educação"),
    ("8591-1/00", 1, "Ensino de esportes"),
    ("8593-7/00", 1, "Ensino de idiomas"),
    ("8599-6/04", 1, "Treinamento em desenvolvimento profissional"),

    # ============ SAÚDE (grau 3 em sua maioria) ============
    ("8610-1/01", 3, "Atividades de atendimento hospitalar"),
    ("8621-6/01", 3, "UTI móvel"),
    ("8630-5/01", 3, "Atividade médica ambulatorial sem recursos para internação"),
    ("8630-5/02", 3, "Atividade médica ambulatorial com recursos para internação"),
    ("8630-5/03", 3, "Atividade médica - exames complementares"),
    ("8630-5/04", 3, "Atividade odontológica"),
    ("8630-5/06", 3, "Serviços de vacinação e imunização humana"),
    ("8630-5/07", 3, "Atividades de reprodução humana assistida"),
    ("8640-2/01", 3, "Laboratórios de anatomia patológica e citológica"),
    ("8640-2/02", 3, "Laboratórios clínicos"),
    ("8640-2/05", 3, "Serviços de diagnóstico por imagem com radiação"),
    ("8650-0/01", 3, "Atividades de enfermagem"),
    ("8650-0/02", 3, "Atividades de profissionais da nutrição"),
    ("8650-0/03", 1, "Atividades de psicologia e psicanálise"),
    ("8650-0/04", 3, "Atividades de fisioterapia"),
    ("8650-0/05", 2, "Atividades de terapia ocupacional"),
    ("8650-0/06", 3, "Atividades de fonoaudiologia"),
    ("8650-0/07", 2, "Atividades de terapia de nutrição enteral e parenteral"),
    ("8660-7/00", 3, "Atividades de apoio à gestão de saúde"),
    ("8690-9/01", 2, "Atividades de práticas integrativas e complementares em saúde humana"),
    ("8690-9/02", 2, "Atividades de bancos de leite humano"),
    ("8690-9/03", 2, "Atividades de acupuntura"),
    ("8690-9/04", 2, "Atividades de podologia"),
    ("8690-9/99", 2, "Outras atividades de atenção à saúde humana NCO"),
    ("8711-5/01", 3, "Clínicas e residências geriátricas"),
    ("8711-5/02", 3, "Instituições de longa permanência para idosos"),
    ("8720-4/01", 3, "Atividades de assistência psicossocial a portadores de transtornos mentais"),
    ("8730-1/02", 2, "Albergues assistenciais"),

    # ============ ATIVIDADES VETERINÁRIAS (grau 3) ============
    ("7500-1/00", 3, "Atividades veterinárias"),

    # ============ SERVIÇOS PESSOAIS (estética/beleza — grau 2) ============
    ("9601-7/01", 2, "Lavanderias"),
    ("9601-7/02", 2, "Tinturarias"),
    ("9601-7/03", 2, "Toalheiros"),
    ("9602-5/01", 2, "Cabeleireiros, manicure e pedicure"),
    ("9602-5/02", 2, "Atividades de estética e outros serviços de cuidados com a beleza"),
    ("9603-3/01", 2, "Gestão e manutenção de cemitérios"),
    ("9603-3/05", 2, "Serviços de cremação"),
    ("9609-2/02", 2, "Agências matrimoniais"),
    ("9609-2/04", 2, "Exploração de máquinas de serviços pessoais acionadas por moeda"),
    ("9609-2/05", 2, "Atividades de astrologia e esoterismo"),
    ("9609-2/06", 2, "Serviços de tatuagem e colocação de piercing"),
    ("9609-2/07", 2, "Alojamento de animais domésticos"),
    ("9609-2/99", 2, "Outras atividades de serviços pessoais NCO"),

    # ============ CULTURA, ESPORTE, RECREAÇÃO (grau 2) ============
    ("9311-5/00", 2, "Gestão de instalações de esportes"),
    ("9312-3/00", 2, "Clubes sociais, esportivos e similares"),
    ("9313-1/00", 2, "Atividades de condicionamento físico"),
    ("9319-1/01", 2, "Produção e promoção de eventos esportivos"),
    ("9321-2/00", 2, "Parques de diversão e parques temáticos"),
    ("9329-8/04", 2, "Exploração de jogos eletrônicos recreativos"),
    ("9001-9/03", 1, "Produção musical"),
    ("9001-9/06", 1, "Atividades de sonorização e de iluminação"),
    ("5911-1/02", 2, "Produção de filmes para publicidade"),
    ("5911-1/99", 2, "Atividades de produção cinematográfica NCO"),
    ("7990-2/00", 1, "Serviços de reservas e outros serviços de turismo"),

    # ============ AGROPECUÁRIA (grau 3) ============
    ("0111-3/01", 3, "Cultivo de arroz"),
    ("0151-2/01", 3, "Criação de bovinos para corte"),
    ("0155-5/01", 3, "Criação de frangos para corte"),
    ("0210-1/01", 3, "Cultivo de eucalipto"),

    # ============ ENERGIA / UTILIDADES (grau 3) ============
    ("3511-5/01", 3, "Geração de energia elétrica"),
    ("3811-4/00", 3, "Coleta de resíduos não-perigosos"),
    ("3812-2/00", 4, "Coleta de resíduos perigosos"),
    ("3821-1/00", 3, "Tratamento e disposição de resíduos não-perigosos"),

    # ============ TELECOMUNICAÇÕES (grau 1) ============
    ("6110-8/01", 2, "Serviços de telefonia fixa comutada"),
    ("6190-6/01", 1, "Provedores de acesso às redes de comunicações"),

    # ============ ATIVIDADES DE LIMPEZA (grau 3) ============
    ("8121-4/00", 3, "Limpeza em prédios e domicílios"),
    ("8122-2/00", 3, "Imunização e controle de pragas urbanas"),
    ("8129-0/00", 3, "Atividades de limpeza não especificadas"),
    ("8130-3/00", 2, "Serviços de paisagismo"),

    # ============ SEGURANÇA (grau 3) ============
    ("8011-1/01", 3, "Atividades de vigilância e segurança privada"),
    ("8020-0/00", 3, "Atividades de monitoramento de sistemas de segurança eletrônico"),

    # ============ ASSOCIAÇÕES / ORGANIZAÇÕES (grau 1) ============
    ("9411-1/00", 1, "Atividades de organizações associativas patronais e empresariais"),
    ("9420-1/00", 1, "Atividades de organizações sindicais"),
    ("9430-8/00", 1, "Atividades de associações de defesa de direitos sociais"),
    ("9491-0/00", 1, "Atividades de organizações religiosas"),
]


# =====================================================================
# Fallback por SEÇÃO/DIVISÃO CNAE — usado quando o CNAE específico
# não está cadastrado. Reflete a moda da NR-04 dentro de cada divisão.
# =====================================================================
INFERENCIA_POR_DIVISAO = {
    # Divisão CNAE (2 dígitos) → grau MAIS COMUM nessa divisão (NR-04)
    "01": 3, "02": 3, "03": 3,                # Agropec / Pesca
    "05": 4, "06": 4, "07": 4, "08": 3, "09": 4,  # Extração
    "10": 3, "11": 3, "12": 3, "13": 3, "14": 3, "15": 3, "16": 3,
    "17": 3, "18": 2, "19": 3, "20": 3, "21": 3, "22": 3, "23": 3,
    "24": 4, "25": 3, "26": 3, "27": 3, "28": 3, "29": 3, "30": 3,
    "31": 3, "32": 3, "33": 3,                # Indústria
    "35": 3, "36": 3, "37": 3, "38": 3, "39": 3,  # Eletricidade/água/resíduos
    "41": 3, "42": 3, "43": 3,                # Construção
    "45": 3, "46": 2, "47": 2,                # Comércio
    "49": 3, "50": 3, "51": 3, "52": 2, "53": 2,  # Transporte
    "55": 2, "56": 2,                          # Alojamento / Alimentação
    "58": 1, "59": 2, "60": 2, "61": 1, "62": 1, "63": 1,  # Informação
    "64": 1, "65": 1, "66": 1,                # Financeiro
    "68": 1,                                   # Imobiliário
    "69": 1, "70": 1, "71": 2, "72": 2, "73": 1, "74": 1, "75": 3,  # Profissionais
    "77": 2, "78": 1, "79": 1, "80": 3, "81": 3, "82": 1,  # Adm/aux
    "84": 1,                                   # Adm pública
    "85": 2,                                   # Educação
    "86": 3, "87": 3, "88": 2,                # Saúde / Assistência
    "90": 1, "91": 1, "92": 2, "93": 2,       # Cultura / Esporte
    "94": 1, "95": 2,                          # Organizações / Reparação
    "96": 2,                                   # Serviços pessoais
    "97": 1, "99": 1,                          # Domésticos / Org. internacionais
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostra o que seria atualizado sem gravar.")
    args = ap.parse_args()

    init_db()
    print(f"📚 Populando graus oficiais NR-04 — {len(NR04_GRAUS_OFICIAIS)} CNAEs\n")

    inseridos = atualizados = 0
    with get_conn() as conn:
        for cnae, grau, desc in NR04_GRAUS_OFICIAIS:
            existente = conn.execute(
                "SELECT cnae, grau_risco FROM cnae_risco WHERE cnae = ?",
                (cnae,),
            ).fetchone()
            risco_textual = {1: "Baixo", 2: "Médio",
                              3: "Alto", 4: "Alto"}[grau]
            fonte = "NR-04 / MTE — Portaria SEPRT 8.873/2022 (Quadro I)"
            if args.dry_run:
                if existente:
                    if existente["grau_risco"] != grau:
                        print(f"  ~ {cnae} grau {existente['grau_risco']}→{grau}")
                        atualizados += 1
                else:
                    print(f"  + {cnae} grau {grau} ({desc[:50]})")
                    inseridos += 1
                continue

            if existente:
                conn.execute(
                    """UPDATE cnae_risco
                          SET grau_risco = ?,
                              risco = ?,
                              fonte = ?,
                              atualizado_em = datetime('now', 'localtime')
                        WHERE cnae = ?""",
                    (grau, risco_textual, fonte, cnae),
                )
                atualizados += 1
            else:
                conn.execute(
                    """INSERT INTO cnae_risco
                         (cnae, descricao, risco, grau_risco, fonte)
                         VALUES (?, ?, ?, ?, ?)""",
                    (cnae, desc, risco_textual, grau, fonte),
                )
                inseridos += 1
        if not args.dry_run:
            conn.commit()

    print(f"\n✅ Inseridos: {inseridos}")
    print(f"🔄 Atualizados: {atualizados}")

    if not args.dry_run:
        registrar_atualizacao_norma(
            base="NR-04",
            orgao="Ministério do Trabalho e Emprego (MTE)",
            versao="Portaria SEPRT 8.873/2022 — Quadro I",
            observacoes=(
                f"Graus oficiais NR-04 (1 a 4) para {len(NR04_GRAUS_OFICIAIS)} "
                f"CNAEs comuns no escritório. Para os ~700 CNAEs restantes, "
                f"o sistema usa inferência por divisão CNAE como fallback "
                f"(marca como 'GRAU ESTIMADO' na UI)."
            ),
        )
        print("\n📚 Norma registrada em `normas_atualizacao`.")
        print("\n🎯 Próximo passo: rode `streamlit run app.py` e teste "
              "9602-5/02 (estética) — deve aparecer GRAU 2.")


if __name__ == "__main__":
    main()
