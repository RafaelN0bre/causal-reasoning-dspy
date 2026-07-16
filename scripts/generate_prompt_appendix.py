# -*- coding: utf-8 -*-
"""Gera monografia/apendice_prompts.tex a partir do export de traces do Langfuse.

Reproduz na íntegra os prompts finais de cada estratégia (baseline, zero-shot,
few-shot, MIPROv2) para o mesmo caso de entrada, verificando byte a byte a
igualdade entre os blocos declarados idênticos.

Uso:
    uv run scripts/generate_prompt_appendix.py
"""
import csv, json, sys, textwrap, hashlib

csv.field_size_limit(sys.maxsize)
import os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO, "outputs-observability", "prompts",
                   "lf-export-cmqtnlxsp0006rgnkfwwdi41r-2026-07-08T00_28_47.626Z.csv")
OUT = os.path.join(REPO, "monografia", "apendice_prompts.tex")
MARK = "In adhering to this structure, your objective is:"
CASE_KEY = "bulldog calls the otter"
WIDTH = 88

rows = list(csv.DictReader(open(CSV, newline="", encoding="utf-8")))

samples = {}   # (opt, module) -> msgs do caso bulldog
baseline = None
for r in rows:
    tags = json.loads(r["traceTags"] or "[]")
    opt = next((t.split(":", 1)[1] for t in tags if t.startswith("optimizer:")), "?")
    if opt == "baseline":
        content = json.loads(r["input"])
        if CASE_KEY in content and baseline is None:
            baseline = content
        continue
    msgs = json.loads(r["input"])
    if CASE_KEY not in msgs[-1]["content"]:
        continue
    head = msgs[0]["content"].split("Your output fields")[0]
    module = "kb" if "`goal` (str)" in head else "rules"
    samples[(opt, module)] = msgs

assert baseline and len(samples) == 6, (len(samples), bool(baseline))

# verificações de igualdade
h = lambda s: hashlib.md5(s.encode()).hexdigest()
sys_kb = samples[("zero-shot", "kb")][0]["content"]
assert h(sys_kb) == h(samples[("few-shot", "kb")][0]["content"]) == h(samples[("mipro", "kb")][0]["content"])
sys_rules = samples[("zero-shot", "rules")][0]["content"]
assert h(sys_rules) == h(samples[("few-shot", "rules")][0]["content"])
sys_rules_mipro = samples[("mipro", "rules")][0]["content"]
pre_z, obj_z = sys_rules.split(MARK)
pre_m, obj_m = sys_rules_mipro.split(MARK)
assert pre_z == pre_m  # tudo antes da instrução é idêntico
assert h(samples[("zero-shot", "kb")][-1]["content"]) == h(samples[("few-shot", "kb")][-1]["content"]) == h(samples[("mipro", "kb")][-1]["content"])


def wrap(text):
    out = []
    for line in text.split("\n"):
        if len(line) <= WIDTH:
            out.append(line)
        else:
            out.extend(textwrap.wrap(line, WIDTH, subsequent_indent="  ",
                                     break_long_words=False, break_on_hyphens=False) or [""])
    return "\n".join(out)


def verb(text):
    return "\\begin{footnotesize}\n\\begin{verbatim}\n" + wrap(text) + "\n\\end{verbatim}\n\\end{footnotesize}\n"


def demos_of(msgs):
    inner = msgs[1:-1]
    return [(inner[i]["content"], inner[i + 1]["content"]) for i in range(0, len(inner), 2)]


p = []
p.append("""% Apêndice gerado a partir do export de traces do Langfuse
% (outputs-observability/prompts/lf-export-cmqtnlxsp0006rgnkfwwdi41r-2026-07-08T00_28_47.626Z.csv).
% Incluir no arquivo principal dentro do ambiente de apêndices, ex.:
%   \\begin{apendicesenv} ... \\include{apendice_prompts} ... \\end{apendicesenv}
% Obs.: os blocos verbatim contêm os glifos UTF-8 ¬ e —, presentes nos prompts
% originais; se o pdfLaTeX acusar erro de caractere, compilar com LuaLaTeX/XeLaTeX
% ou carregar o pacote textcomp.

\\chapter{Prompts Finais Enviados ao Modelo de Linguagem}
\\label{apendice:prompts}

Este apêndice reproduz, na íntegra, os \\textit{prompts} finais enviados ao LLM por cada estratégia avaliada no BoardgameQA, conforme capturados pelos \\textit{traces} de observabilidade (Seção \\ref{sec:langfuse}) na variante \\textit{Main-depth2}. Todas as reproduções referem-se ao mesmo caso de entrada, o que permite comparar as estratégias sobre insumo idêntico.

Nas estratégias neuro-simbólicas, o DSPy monta o \\textit{prompt} como uma conversa: uma mensagem de sistema (descrição tipada dos campos de entrada e saída, o esquema de resposta e, ao final, a instrução da assinatura), seguida das demonstrações injetadas pela compilação (pares de mensagens usuário/assistente) e da mensagem final de usuário com o caso a resolver. Para evitar repetição, cada bloco é reproduzido uma única vez e a composição de cada estratégia é declarada explicitamente; a igualdade entre blocos declarados idênticos foi verificada byte a byte no export. Em síntese, o que muda entre as estratégias é o seguinte: o \\textit{zero-shot} usa apenas mensagem de sistema e caso; o \\textit{few-shot} usa as mesmas mensagens de sistema e acrescenta quatro demonstrações por módulo; o MIPROv2 mantém o módulo de base de conhecimento idêntico ao \\textit{zero-shot}, e, no módulo de regras, substitui a instrução da assinatura por uma versão reescrita e acrescenta duas demonstrações.
""")

p.append("\\section{Estratégia Baseline (LLM puro)}\n\nA estratégia \\textit{baseline} envia uma única mensagem, com instrução fixa escrita manualmente, seguida do caso e do formato de resposta:\n")
p.append(verb(baseline))

p.append("\\section{Módulo de Extração da Base de Conhecimento}\n")
p.append("\\subsection{Mensagem de sistema}\n\nIdêntica nas três estratégias neuro-simbólicas (\\textit{zero-shot}, \\textit{few-shot} e MIPROv2); o otimizador MIPROv2 optou por não alterar este módulo:\n")
p.append(verb(sys_kb))
p.append("\\subsection{Mensagem final de usuário (caso avaliado)}\n\nIdêntica nas três estratégias:\n")
p.append(verb(samples[("zero-shot", "kb")][-1]["content"]))
p.append("\\subsection{Demonstrações adicionadas pelo BootstrapFewShot}\n\nPresentes apenas na estratégia \\textit{few-shot} deste módulo, entre a mensagem de sistema e a mensagem final. Cada demonstração é um par usuário/assistente coletado do \\textit{split} de treino pelo próprio \\textit{pipeline}:\n")
for i, (u, a) in enumerate(demos_of(samples[("few-shot", "kb")]), 1):
    p.append(f"\\subsubsection*{{Demonstração {i} (usuário)}}\n")
    p.append(verb(u))
    p.append(f"\\subsubsection*{{Demonstração {i} (assistente)}}\n")
    p.append(verb(a))

p.append("\\section{Módulo de Extração de Regras}\n")
p.append("\\subsection{Mensagem de sistema no zero-shot e no few-shot}\n\nIdêntica nas duas estratégias:\n")
p.append(verb(sys_rules))
p.append("\\subsection{Alteração feita pelo MIPROv2 na mensagem de sistema}\n\nNo MIPROv2, a mensagem de sistema deste módulo é idêntica à anterior até a linha ``In adhering to this structure, your objective is:''. A partir desse ponto, a instrução original da assinatura (as cinco linhas finais do bloco acima) é substituída pelo texto reescrito pelo otimizador, reproduzido a seguir; nada mais muda na mensagem de sistema:\n")
p.append(verb(MARK + obj_m))
p.append("\\subsection{Mensagem final de usuário (caso avaliado)}\n\nReproduz-se a mensagem da execução \\textit{zero-shot}. Nas demais estratégias, a estrutura e o caso são os mesmos e apenas o conteúdo do campo \\texttt{knowledge\\_base} pode variar, por reproduzir a saída do módulo anterior daquela mesma execução:\n")
p.append(verb(samples[("zero-shot", "rules")][-1]["content"]))
p.append("\\subsection{Demonstrações adicionadas pelo BootstrapFewShot}\n\nQuatro demonstrações, presentes apenas na estratégia \\textit{few-shot}:\n")
for i, (u, a) in enumerate(demos_of(samples[("few-shot", "rules")]), 1):
    p.append(f"\\subsubsection*{{Demonstração {i} (usuário)}}\n")
    p.append(verb(u))
    p.append(f"\\subsubsection*{{Demonstração {i} (assistente)}}\n")
    p.append(verb(a))
p.append("\\subsection{Demonstrações adicionadas pelo MIPROv2}\n\nDuas demonstrações, selecionadas pela busca Bayesiana:\n")
for i, (u, a) in enumerate(demos_of(samples[("mipro", "rules")]), 1):
    p.append(f"\\subsubsection*{{Demonstração {i} (usuário)}}\n")
    p.append(verb(u))
    p.append(f"\\subsubsection*{{Demonstração {i} (assistente)}}\n")
    p.append(verb(a))

open(OUT, "w", encoding="utf-8").write("\n".join(p))
print(f"gerado {OUT} ({len(chr(10).join(p))} chars)")
print("instrução original (regras):", len(obj_z), "chars | reescrita mipro:", len(obj_m), "chars")
