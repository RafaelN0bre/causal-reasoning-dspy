"""Executa o solver ASPIC+ deste trabalho (src/solver.py) sobre a formalização
de um processo judicial real.

O caso é o RE 608.880/MT (Tema 362 do STF), responsabilidade civil do Estado
por crime praticado por detento foragido. A formalização não foi produzida por
este trabalho: ela vem do projeto jurix26, onde o acórdão foi anotado por
juristas em cinco perspectivas argumentativas e transcrito à mão para ASPIC+.
Os registros de origem estão em `data/caso-real/fonte/`. Aqui eles entram
apenas como entrada: nenhum literal, nenhuma regra e nenhum veredito da corte
é alterado.

A formalização tem duas camadas, na arquitetura de Pisano, Prakken & Sartor
(ICAIL 2025/2026):

1. causa de fato (CIF): a cadeia causal do caso, testada contrafactualmente;
2. relevância jurídica (LRC): um segundo framework cuja base de conhecimento
   recebe, como axiomas, os literais `CaFa_φ_ψ`/`ButFor_φ_ψ` que a primeira
   camada estabeleceu, e cujas regras são os esquemas doutrinários do acórdão.

A fronteira entre as camadas é determinística: os literais de ponte são
calculados pelo solver deste trabalho, nunca copiados do registro de origem.
É isso que impede a segunda camada de reivindicar relevância jurídica para uma
causa que o teste contrafactual não estabeleceu.

Duas noções causais são reportadas:

* `but_for`   — o teste nativo desta monografia (Seção "Validação causal"):
  φ é causa de ψ se ψ está na extensão fundamentada do framework base e deixa
  de estar quando ¬φ é acrescentado como axioma. Corresponde à Definição 3.5
  do ICAIL 2026.
* `ness`      — diagnóstico calculado sobre as saídas do mesmo solver, sem
  alterá-lo: φ é causa de ψ se a intervenção ¬φ retira da extensão *algum*
  argumento do conjunto-suporte de ψ, ainda que ψ continue derivável por outra
  via (Definição 4.3 do ICAIL 2025, renomeada "NESS" na Definição 3.4 do ICAIL
  2026). O conjunto-suporte usado aqui é o fecho estrutural de subargumentos
  que o próprio solver expõe em `_get_explanation`; ele coincide com as
  explicações da Definição 3.3 quando a camada não tem derrotas, o que o script
  verifica em tempo de execução e registra no resultado.

O solver não é modificado. A única adaptação é sintática: os identificadores de
regra da formalização de origem (`suca_q3`, `cf2lrc_q5`, ...) são renomeados
para a convenção `rN` que `src/solver.py` exige para reconhecer um undercutter
(`_identify_attacks` procura conclusões da forma `¬rN`). O mapa de renomeação
é gravado junto ao resultado, de modo que toda regra executada pode ser lida
de volta na formalização original.

Uso:
    uv run scripts/run_real_case.py
    uv run scripts/run_real_case.py --case case-003-final-cif
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.solver import Argument, ArgumentationFramework  # noqa: E402

FONTE = ROOT / "data" / "caso-real" / "fonte"
RESULTADO = ROOT / "outputs" / "caso-real"

# Átomos que condicionam uma inferência sem nunca serem causa candidata: um
# dever é o que torna uma conduta imputável e uma prova é o que permite dar um
# fato por estabelecido. Perguntar se "o dever de custódia causou a morte" é
# erro de categoria. Critério herdado de `formalize.bridge.NON_CANDIDATE_KINDS`
# no projeto de origem, para que a lista de candidatos seja a mesma.
TIPOS_NAO_CANDIDATOS = frozenset({"dever", "prova"})


# ----------------------------------------------------------------------
# Vocabulário da camada de relevância jurídica
# ----------------------------------------------------------------------
def _token(literal: str) -> str:
    """`¬PaCo` -> `notPaCo`, convenção de nomes do ICAIL 2026."""
    return f"not{literal[1:]}" if literal.startswith("¬") else literal


def cafa(phi: str, psi: str) -> str:
    return f"CaFa_{_token(phi)}_{_token(psi)}"


def but_for_literal(phi: str, psi: str) -> str:
    return f"ButFor_{_token(phi)}_{_token(psi)}"


def lereca(phi: str, psi: str) -> str:
    return f"LeReCa_{_token(phi)}_{_token(psi)}"


# ----------------------------------------------------------------------
# Tradução: identificadores de regra da formalização -> convenção do solver
# ----------------------------------------------------------------------
def _rule_id(regra: str) -> str:
    return regra.split(":", 1)[0].strip()


def _rule_body(regra: str) -> str:
    return regra.split(":", 1)[1].strip()


def _consequent(regra: str) -> str:
    corpo = _rule_body(regra)
    separador = "=>" if "=>" in corpo else "->"
    return corpo.split(separador, 1)[1].strip()


def construir_mapa(*grupos: Sequence[str]) -> Dict[str, str]:
    """Um identificador `rN` para cada regra, em espaço de nomes único entre as
    duas camadas (os ids de origem já são disjuntos entre elas)."""
    mapa: Dict[str, str] = {}
    for grupo in grupos:
        for regra in grupo:
            antigo = _rule_id(regra)
            if antigo not in mapa:
                mapa[antigo] = f"r{len(mapa)}"
    return mapa


def traduzir(regra: str, mapa: Dict[str, str]) -> str:
    """Renomeia o identificador da regra e, no consequente, a referência a
    outra regra que um undercutter nega."""
    corpo = _rule_body(regra)
    separador = "=>" if "=>" in corpo else "->"
    antecedente, consequente = (parte.strip() for parte in corpo.split(separador, 1))
    if consequente.startswith("¬") and consequente[1:] in mapa:
        consequente = f"¬{mapa[consequente[1:]]}"
    return f"{mapa[_rule_id(regra)]}: {antecedente} {separador} {consequente}"


def separar(regras: Sequence[str], mapa: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Separa regras comuns de undercutters (as que concluem a negação de outra
    regra), que é a forma como `src/solver.py` recebe um modelo causal."""
    comuns, undercutters = [], []
    for regra in regras:
        alvo = undercutters if _consequent(regra).lstrip("¬") in mapa else comuns
        alvo.append(traduzir(regra, mapa))
    return comuns, undercutters


# ----------------------------------------------------------------------
# As duas noções causais, sobre o solver deste trabalho
# ----------------------------------------------------------------------
def _assinatura(arg: Argument) -> Tuple:
    """Identidade estrutural de um argumento, estável entre dois frameworks
    (os ids `A0, A1, ...` são posicionais e não são comparáveis)."""
    return (
        frozenset(arg.premises),
        arg.conclusion,
        tuple(sorted(arg.defeasible_rules)),
        tuple(sorted(arg.strict_rules)),
    )


def _conclusoes(af: ArgumentationFramework) -> Set[str]:
    extensao, _, _ = af.compute_grounded_extension()
    return {af.arguments[a].conclusion for a in extensao}


def _conjunto_suporte(af: ArgumentationFramework, psi: str) -> Set[FrozenSet]:
    """Assinaturas de todo argumento que sustenta algum argumento justificado
    para ψ, incluindo os próprios."""
    extensao, _, _ = af.compute_grounded_extension()
    suporte: Set[FrozenSet] = set()
    for arg_id in extensao:
        arg = af.arguments[arg_id]
        if arg.conclusion != psi:
            continue
        for apoio_id in af._get_explanation(arg):
            suporte.add(_assinatura(af.arguments[apoio_id]))
    return suporte


def expandir(kb: Dict[str, Any], modelo: Dict[str, Any],
             novos_axiomas: Sequence[str]) -> ArgumentationFramework:
    """K + L da Definição 4.2: mesmo Kp, mesmas regras, axiomas acrescidos."""
    expandido = dict(kb)
    expandido["axioms"] = list(dict.fromkeys([*kb.get("axioms", []), *novos_axiomas]))
    return ArgumentationFramework(expandido, modelo)


def _negar(literal: str) -> str:
    return literal[1:] if literal.startswith("¬") else f"¬{literal}"


def avaliar_par(af: ArgumentationFramework, kb: Dict[str, Any], modelo: Dict[str, Any],
                phi: str, psi: str) -> Dict[str, bool]:
    """Os dois vereditos para o par (φ, ψ), sobre o mesmo framework base."""
    if psi not in _conclusoes(af):
        return {"ness": False, "but_for": False}
    suporte = _conjunto_suporte(af, psi)
    expandido = expandir(kb, modelo, [_negar(phi)])
    extensao, _, _ = expandido.compute_grounded_extension()
    assinaturas = {_assinatura(expandido.arguments[a]) for a in extensao}
    conclusoes = {expandido.arguments[a].conclusion for a in extensao}
    return {
        "ness": not suporte.issubset(assinaturas),
        "but_for": psi not in conclusoes,
    }


# ----------------------------------------------------------------------
# Execução das duas camadas
# ----------------------------------------------------------------------
def candidatos(caso: Dict[str, Any]) -> List[str]:
    """As premissas do framework causal, menos deveres e provas, mais o lado φ
    de cada pergunta que o próprio processo faz."""
    excluidos = {atomo["code"] for atomo in caso.get("atoms", [])
                 if atomo.get("kind") in TIPOS_NAO_CANDIDATOS}
    literais = [p for p in caso["knowledge_base"].get("premises", [])
                if p.lstrip("¬") not in excluidos]
    literais += [consulta["phi"] for consulta in caso.get("queries", [])]
    return list(dict.fromkeys(literais))


def alvos(caso: Dict[str, Any]) -> List[str]:
    literais = [caso.get("effect", "")] + [c["psi"] for c in caso.get("queries", [])]
    return list(dict.fromkeys(l for l in literais if l))


def executar_cif(caso: Dict[str, Any], mapa: Dict[str, str]) -> Dict[str, Any]:
    """Primeira camada: a cadeia causal do processo e os testes contrafactuais."""
    kb = {
        "premises": list(caso["knowledge_base"].get("premises", [])),
        "axioms": list(caso["knowledge_base"].get("axioms", [])),
        "preferences": {},
    }
    comuns, undercutters = separar(caso["causal_model"].get("defeasible_rules", []), mapa)
    estritas, _ = separar(caso["causal_model"].get("strict_rules", []), mapa)
    modelo = {
        "strict_rules": estritas,
        "defeasible_rules": comuns,
        "undercutter_rules": undercutters,
    }

    af = ArgumentationFramework(kb, modelo)
    extensao, _, derrotas = af.compute_grounded_extension()

    pares = []
    for psi in alvos(caso):
        for phi in candidatos(caso):
            if phi == psi:
                continue
            pares.append({"phi": phi, "psi": psi, **avaliar_par(af, kb, modelo, phi, psi)})

    return {
        "knowledge_base": kb,
        "causal_model": modelo,
        "argumentos": len(af.arguments),
        "ataques": len(af.attacks),
        "derrotas": len(derrotas),
        "extensao_fundamentada": sorted(extensao),
        "conclusoes_fundamentadas": sorted(_conclusoes(af)),
        "pares_causais": pares,
    }


def literais_ponte(pares: Sequence[Dict[str, Any]], notacao: str) -> List[str]:
    """Os `CaFa_*`/`ButFor_*` que a primeira camada entrega à segunda, sob a
    noção causal escolhida. São calculados, nunca transcritos."""
    literais: List[str] = []
    for par in pares:
        if par["ness" if notacao == "ness" else "but_for"]:
            literais.append(cafa(par["phi"], par["psi"]))
        if par["but_for"]:
            literais.append(but_for_literal(par["phi"], par["psi"]))
    return list(dict.fromkeys(literais))


def executar_lrc(caso: Dict[str, Any], mapa: Dict[str, str],
                 ponte: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Segunda camada: os esquemas doutrinários do acórdão, sobre a ponte."""
    bloco = caso.get("lrc")
    if not bloco or not bloco.get("scheme_rules"):
        return None

    kb = {
        "premises": list(dict.fromkeys(p["literal"] for p in bloco["doctrinal_premises"])),
        "axioms": list(ponte),
        "preferences": {},
    }
    regras = [r["rule"] for r in bloco["scheme_rules"]]
    comuns, undercutters = separar(regras, mapa)
    modelo = {"strict_rules": [], "defeasible_rules": comuns, "undercutter_rules": undercutters}

    af = ArgumentationFramework(kb, modelo)
    extensao, _, derrotas = af.compute_grounded_extension()
    justificadas = _conclusoes(af)
    inverso = {novo: antigo for antigo, novo in mapa.items()}

    relatorio = []
    for alvo in bloco.get("targets", []):
        argumentos = [a for a in af.arguments.values() if a.conclusion == alvo]
        bloqueios, vistos = [], set()
        for argumento in argumentos:
            if argumento.id in extensao:
                continue
            for derrota in derrotas:
                ataque = derrota.attack
                if ataque.target_id != argumento.id or ataque.attacker_id not in extensao:
                    continue
                chave = (ataque.attacker_id, argumento.id, ataque.attack_type)
                if chave in vistos:
                    continue
                vistos.add(chave)
                atacante = af.arguments[ataque.attacker_id]
                bloqueios.append({
                    "regra_undercut": inverso.get(ataque.rule_id or "", ataque.rule_id),
                    "atacante": atacante.id,
                    "regras_do_atacante": sorted(inverso.get(r, r) for r
                                                 in atacante.defeasible_rules + atacante.strict_rules),
                    "argumento_atacado": argumento.id,
                    "tipo_de_ataque": ataque.attack_type,
                })
        if alvo in justificadas:
            situacao = "reconhecida"
        elif argumentos:
            situacao = "afastada"
        else:
            situacao = "nao_formulada"
        relatorio.append({
            "alvo": alvo,
            "justificada": alvo in justificadas,
            "derivavel": bool(argumentos),
            "situacao": situacao,
            "bloqueada_por": bloqueios,
        })

    return {
        "knowledge_base": kb,
        "causal_model": modelo,
        "argumentos": len(af.arguments),
        "ataques": len(af.attacks),
        "derrotas": len(derrotas),
        "extensao_fundamentada": sorted(extensao),
        "conclusoes_fundamentadas": sorted(justificadas),
        "relevancia": relatorio,
    }


# ----------------------------------------------------------------------
# Confronto com a decisão da corte e com o solver de origem
# ----------------------------------------------------------------------
def _veredito(causa: bool, relevante: Optional[bool], tem_lrc: bool) -> Tuple[str, str]:
    if not causa:
        return "não é causa de fato", "rejeitada"
    if tem_lrc and relevante is False:
        return "é causa de fato, mas não juridicamente relevante", "rejeitada"
    if tem_lrc and relevante is True:
        return "é causa de fato e juridicamente relevante", "acolhida"
    return "é causa de fato", "acolhida"


def confrontar(caso: Dict[str, Any], cif: Dict[str, Any], lrc: Optional[Dict[str, Any]],
               referencia: Dict[str, Any]) -> Dict[str, Any]:
    tem_lrc = lrc is not None
    justificadas = set(lrc["conclusoes_fundamentadas"]) if lrc else set()
    derivaveis = {r["alvo"] for r in lrc["relevancia"]} if lrc else set()
    por_par = {(p["phi"], p["psi"]): p for p in cif["pares_causais"]}
    ref_por_par = {(r["phi"], r["psi"]): r for r in referencia.get("comparison", [])}

    linhas = []
    for consulta in caso.get("queries", []):
        phi, psi = consulta["phi"], consulta["psi"]
        par = por_par.get((phi, psi), {"ness": False, "but_for": False})
        alvo = lereca(phi, psi)
        relevante = (alvo in justificadas) if alvo in derivaveis else None

        linha = {"phi": phi, "psi": psi, "pergunta_pt": consulta.get("question_pt", ""),
                 "corte": consulta.get("court_verdict", ""),
                 "razao_da_corte_pt": consulta.get("court_rationale_pt", ""),
                 "relevancia_juridica": relevante}
        for notacao in ("but_for", "ness"):
            rotulo, veredito = _veredito(par[notacao], relevante, tem_lrc)
            linha[notacao] = {
                "causa_de_fato": par[notacao],
                "rotulo_pt": rotulo,
                "veredito": veredito,
                "acordo": ("indefinido" if linha["corte"] in ("", "nao_decidida")
                           else "match" if veredito == linha["corte"] else "mismatch"),
            }
        referencia_par = ref_por_par.get((phi, psi))
        if referencia_par:
            linha["origem"] = {
                "ness": referencia_par.get("ness"),
                "but_for": referencia_par.get("but_for"),
                "relevancia_juridica": referencia_par.get("legally_relevant"),
                "veredito": referencia_par.get("solver_verdict"),
                "acordo": referencia_par.get("agreement"),
                "reproduz_ness": referencia_par.get("ness") == par["ness"],
                "reproduz_but_for": referencia_par.get("but_for") == par["but_for"],
            }
        linhas.append(linha)

    def contar(notacao: str) -> Dict[str, Any]:
        contagem = {chave: sum(1 for l in linhas if l[notacao]["acordo"] == chave)
                    for chave in ("match", "mismatch", "indefinido")}
        decididas = contagem["match"] + contagem["mismatch"]
        contagem["taxa_de_acordo"] = round(contagem["match"] / decididas, 3) if decididas else None
        return contagem

    return {"consultas": linhas, "acordo_but_for": contar("but_for"), "acordo_ness": contar("ness")}


# ----------------------------------------------------------------------
def executar(case_id: str) -> Dict[str, Any]:
    caso = json.loads((FONTE / f"{case_id}.json").read_text(encoding="utf-8"))
    referencia = json.loads((FONTE / f"referencia-{case_id}.json").read_text(encoding="utf-8"))

    bloco = caso.get("lrc") or {}
    mapa = construir_mapa(
        caso["causal_model"].get("strict_rules", []),
        caso["causal_model"].get("defeasible_rules", []),
        [r["rule"] for r in bloco.get("scheme_rules", [])],
    )

    cif = executar_cif(caso, mapa)
    ponte = literais_ponte(cif["pares_causais"], "ness")
    ponte_but_for = literais_ponte(cif["pares_causais"], "but_for")
    lrc = executar_lrc(caso, mapa, ponte)
    comparacao = confrontar(caso, cif, lrc, referencia)

    ponte_origem = list(bloco.get("bridged_premises", []))
    return {
        "caso": {
            "id": caso["case"]["id"],
            "titulo": caso["case"]["title"],
            "ordem_das_camadas": caso.get("layer_order", "cif_first"),
            "pergunta_central": caso.get("central_question", ""),
            "origem": "jurix26 / data/translated (formalização manual do RE 608.880/MT)",
            "source_sha256": caso["case"].get("source_sha256", ""),
        },
        "solver": "src/solver.py (esta monografia), sem modificação",
        "mapa_de_regras": mapa,
        "camada_causa_de_fato": cif,
        "ponte": {
            "notacao_usada": "ness",
            "literais": ponte,
            "literais_sob_but_for": ponte_but_for,
            "literais_na_origem": ponte_origem,
            "reproduz_origem": sorted(ponte) == sorted(ponte_origem),
            "ausentes_em_relacao_a_origem": sorted(set(ponte_origem) - set(ponte)),
            "excedentes_em_relacao_a_origem": sorted(set(ponte) - set(ponte_origem)),
        },
        "camada_relevancia_juridica": lrc,
        "comparacao": comparacao,
        "nota_sobre_o_conjunto_suporte": (
            "O conjunto-suporte usado no diagnóstico NESS é o fecho de subargumentos que "
            "`_get_explanation` expõe. Ele coincide com as explicações da Definição 3.3 "
            "quando a camada não tem derrotas; a camada de causa de fato deste caso tem "
            f"{cif['derrotas']} derrota(s)."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", default="todos",
                        choices=["todos", "case-003-final", "case-003-final-cif"],
                        help="registro a executar (padrão: os dois)")
    parser.add_argument("--log", default="WARNING", help="nível de log do solver")
    args = parser.parse_args()

    logging.getLogger("ASPIC+").setLevel(getattr(logging, args.log.upper()))
    RESULTADO.mkdir(parents=True, exist_ok=True)

    casos = (["case-003-final", "case-003-final-cif"] if args.case == "todos" else [args.case])
    for case_id in casos:
        resultado = executar(case_id)
        destino = RESULTADO / f"{case_id}.json"
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"\n{'=' * 78}\n{resultado['caso']['id']}  ({resultado['caso']['ordem_das_camadas']})\n{'=' * 78}")
        cif = resultado["camada_causa_de_fato"]
        print(f"CIF: {cif['argumentos']} argumentos, {cif['ataques']} ataques, "
              f"{cif['derrotas']} derrotas, {len(cif['extensao_fundamentada'])} na extensão")
        lrc = resultado["camada_relevancia_juridica"]
        if lrc:
            print(f"LRC: {lrc['argumentos']} argumentos, {lrc['ataques']} ataques, "
                  f"{lrc['derrotas']} derrotas, {len(lrc['extensao_fundamentada'])} na extensão")
            for item in lrc["relevancia"]:
                print(f"     {item['alvo']}: {item['situacao']}")
        print(f"\n{'φ':<14} {'ψ':<8} {'estrito':<8} {'NESS':<6} {'relev.':<8} "
              f"{'ver. estrito':<13} {'ver. NESS':<11} {'corte':<11} acordo (NESS)")
        for linha in resultado["comparacao"]["consultas"]:
            marca = lambda v: "—" if v is None else ("sim" if v else "não")  # noqa: E731
            print(f"{linha['phi']:<14} {linha['psi']:<8} "
                  f"{marca(linha['but_for']['causa_de_fato']):<8} "
                  f"{marca(linha['ness']['causa_de_fato']):<6} "
                  f"{marca(linha['relevancia_juridica']):<8} "
                  f"{linha['but_for']['veredito']:<13} {linha['ness']['veredito']:<11} "
                  f"{linha['corte']:<11} {linha['ness']['acordo']}")
        acordo = resultado["comparacao"]
        print(f"\nacordo com a corte  but-for: {acordo['acordo_but_for']}")
        print(f"acordo com a corte  NESS   : {acordo['acordo_ness']}")
        print(f"ponte reproduz a origem: {resultado['ponte']['reproduz_origem']}")
        print(f"resultado gravado em {destino.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
