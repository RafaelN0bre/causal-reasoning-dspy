# Execução sobre um processo real — RE 608.880/MT (Tema 362 do STF)

Execução do solver ASPIC+ desta monografia (`src/solver.py`, sem modificação) sobre a
formalização de um acórdão real do Supremo Tribunal Federal: responsabilidade civil do Estado
por crime praticado por detento foragido.

A monografia delimita, na introdução, que a avaliação sistemática não é conduzida sobre objetos
jurídicos reais. Esta pasta registra a exceção a essa delimitação, usando uma formalização
produzida fora do escopo deste trabalho.

## Procedência

A formalização resulta de um estudo paralelo conduzido pelo autor com três anotadores da área
do Direito e com o orientador. Nele, o acórdão foi anotado em cinco perspectivas argumentativas (recorrente,
recorrido, relator, voto convergente e voto divergente), consolidado em uma teoria do caso e
transcrito à mão para ASPIC+. Nenhum literal, nenhuma regra e nenhum veredito da corte foi
alterado aqui: os registros entram como entrada.

| Arquivo em `fonte/` | Conteúdo |
|---|---|
| `formalizacao-caso003.md` | Teoria do caso consolidada, em notação de argumentação |
| `case-003-final.json` | Registro executável, ordem `lrc_first` (qualificação jurídica antes dos fatos) |
| `case-003-final-cif.json` | Mesmo registro na ordem do ICAIL 2026, `cif_first` |
| `referencia-case-003-final.json` | Saída do solver de origem, usada como referência de comparação |
| `referencia-case-003-final-cif.json` | Idem, para a variante `cif_first` |
| `RE-608880-MT-inteiro-teor.pdf` | Inteiro teor do acórdão (STF, Plenário, j. 08/09/2020), documento público de onde a formalização parte |

| Arquivo em `figuras/` | Conteúdo |
|---|---|
| `case-003-final-cif.{pdf,svg}` | Argumentos da camada de causa de fato (r0–r4, sem ataques) |
| `case-003-final-lrc.{pdf,svg}` | Grafo da camada de relevância jurídica |
| `case-003-final-adjudication.{pdf,svg}` | Quem ataca quem entre partes e julgadores, com o desfecho de cada ataque na extensão *grounded* |
| `case-003-final-confrontation.{pdf,svg}` | Confronto entre as perspectivas dos votos |

As figuras foram geradas pela ferramenta de visualização do estudo de origem e são copiadas sem
alteração. A de adjudicação tem rótulos em inglês, como no original.

**Proveniência.** O campo `source_sha256` dos dois registros aponta para uma versão anterior de
`formalizacao-caso003.md` (`5e3e5f02…`); o arquivo copiado aqui é a versão atual (`4888a975…`).
O projeto de origem regenerou o registro a partir dela sem mudar regra, literal ou veredito: só
título, hash e notas de modelagem diferem, e `validation.json` é byte a byte igual a
`referencia-case-003-final-cif.json`. A base de anotação e os dossiês por
anotador ficam no projeto de origem e não são publicadas aqui.

## Arquitetura executada

A formalização segue a arquitetura de duas camadas de Pisano, Prakken e Sartor
(ICAIL 2025/2026):

1. **Causa de fato (CIF)** — a cadeia causal do processo (omissão na custódia → fuga →
   latrocínio → morte → danos), submetida ao teste contrafactual;
2. **Relevância jurídica (LRC)** — um segundo framework cuja base de conhecimento recebe, como
   axiomas, os literais `CaFa_φ_ψ` e `ButFor_φ_ψ` que a primeira camada estabeleceu, e cujas
   regras são os esquemas doutrinários lidos dos votos (dever específico de custódia, ato de
   terceiro, omissão genérica, ônus das cautelas).

A fronteira entre as camadas é determinística: os literais de ponte são **calculados** pelo
solver desta monografia, nunca transcritos do registro de origem. É isso que impede a segunda
camada de reivindicar relevância jurídica para uma causa que o teste contrafactual não
estabeleceu.

## Como reproduzir

```bash
uv run scripts/run_real_case.py                     # os dois registros
uv run scripts/run_real_case.py --case case-003-final-cif
```

O resultado é gravado em [`outputs/caso-real/`](../../outputs/caso-real/), junto dos resultados das
demais execuções da monografia. Não há chamada de LLM: a entrada já está formalizada, e o que se executa é a camada simbólica.

A única adaptação é sintática. Os identificadores de regra da formalização de origem
(`suca_q3`, `cf2lrc_q5`, ...) são renomeados para a convenção `rN`, que `src/solver.py` exige
para reconhecer um *undercutter* (`_identify_attacks` procura conclusões da forma `¬rN`). O mapa
de renomeação é gravado em cada resultado, sob `mapa_de_regras`, de modo que toda regra
executada pode ser lida de volta na formalização original.

## Resultados

Os dois registros produzem resultado idêntico, o que confirma o resultado do estudo de origem:
as duas ordens de execução recuperam a mesma decisão da corte.

### Camada de causa de fato

Quatro pares (φ, ψ) foram testados, com ψ = `Danos`. Duas noções são reportadas:

* **but-for** — o teste nativo desta monografia: ψ está na extensão fundamentada do framework
  base e deixa de estar quando `¬φ` é acrescentado como axioma (Definição 3.5 do ICAIL 2026);
* **NESS** — diagnóstico calculado sobre as saídas do mesmo solver, sem alterá-lo: a intervenção
  `¬φ` retira da extensão algum argumento do conjunto-suporte de ψ, ainda que ψ continue
  derivável por outra via (Definição 4.3 do ICAIL 2025, renomeada "NESS" na Definição 3.4 do
  ICAIL 2026).

| φ | but-for | NESS | Referência (NESS) | Referência (but-for) |
|---|---|---|---|---|
| `OmiEstatal` (omissão na custódia) | sim | sim | sim | sim |
| `RegFechado` (regime fechado) | não | sim | sim | não |
| `FugaPreso` (fuga do detento) | não | sim | sim | sim |
| `Latrocinio` (roubo seguido de morte) | não | sim | sim | sim |

O diagnóstico NESS **reproduz integralmente** os vereditos do solver de origem: os quatro
literais `CaFa_*` da ponte são exatamente os mesmos. O teste but-for diverge em dois pares,
e a causa da divergência é estrutural, não numérica (ver "Limitação exposta" abaixo).

Por isso o resultado grava `"reproduz_origem": false` no bloco `ponte`: a ponte completa difere
da de origem só pela ausência de `ButFor_FugaPreso_Danos` e `ButFor_Latrocinio_Danos`. Nenhuma
regra da camada de relevância jurídica lê um literal `ButFor_*` (a única regra de ponte,
`cf2lrc_q5`, lê `CaFa_OmiEstatal_Danos`), de modo que a diferença não alcança a segunda camada.
Já a divergência em `RegFechado` não é limitação: o solver de origem também nega o but-for ali,
porque `r0` e `r1` são duas rotas para `FugaPreso` e só `r1` passa pelo regime fechado.

### Camada de relevância jurídica

| Alvo | Situação | Bloqueado por |
|---|---|---|
| `LeReCa_OmiEstatal_Danos` | afastada | *undercut* sobre `cf2lrc_q5`, por argumento construído com `og_q9` + `og_q10` |

Idêntico ao solver de origem, inclusive na regra e no esquema responsáveis: a presunção de
relevância jurídica que decorre da causa de fato (`cf2lrc_q5`) é derrubada pela qualificação da
omissão como **genérica**, dado o lapso de três meses somado ao concurso de agentes. É a *ratio
decidendi* do voto vencedor.

### Confronto com a decisão da corte

| Pergunta do processo | Solver (NESS + LRC) | Corte | Acordo |
|---|---|---|---|
| A omissão do Estado causou os danos? | rejeitada (é causa de fato, mas não juridicamente relevante) | rejeitada | match |
| A fuga do detento causou os danos? | acolhida (é causa de fato) | rejeitada | mismatch |
| O latrocínio causou os danos? | acolhida (é causa de fato) | acolhida | match |

Taxa de acordo: **2 de 3 (0,667)**, idêntica à do solver de origem, inclusive na composição:
a única divergência está na pergunta sobre a fuga, que a corte rejeita pela mesma razão de
decidir da primeira pergunta, sem que o registro declare um alvo `LeReCa` para ela. A pergunta
decisiva do processo, a da omissão estatal, é respondida corretamente, e pelo motivo correto.

Sob o teste but-for, a taxa também é de 2 em 3, mas com composição diferente: a pergunta sobre a
fuga passa a coincidir com a corte por acidente (o solver a rejeita por não reconhecê-la como
causa de fato, e não pela ruptura do nexo que a corte invocou), enquanto a pergunta sobre o
latrocínio, incontroversa no processo, passa a divergir. O número agregado esconde a diferença;
a composição, não.

## Limitação exposta

A execução expôs uma limitação estrutural de `src/solver.py` que os casos sintéticos da
monografia não exercitam.

Em ASPIC+, o ataque a um subargumento é ataque ao argumento inteiro. Em `_identify_attacks`,
isso vale para *undermining* (o conjunto de premissas é propagado para cima na construção) e
para *undercutting* (os identificadores de regra também são), mas **não vale para
*rebutting***: o ataque por rebate só é reconhecido contra a conclusão final de um argumento.

Consequência observada, no contrafactual de `Latrocinio`:

```
A5   Latrocinio     ← derrotado por ¬Latrocinio (rebate)
A6   Latrocinio     ← derrotado por ¬Latrocinio (rebate)
A7   MorteVitima    (construído sobre A5)  permanece na extensão
A9   Danos          (construído sobre A7)  permanece na extensão
```

Como `Danos` sobrevive, o teste but-for responde "não é causa" para `Latrocinio` e para
`FugaPreso`. O diagnóstico NESS não é afetado, porque compara conjuntos-suporte e enxerga a
saída de A5 e A6 da extensão.

A limitação não afeta os resultados reportados na monografia: nos 82 pares causais dos conjuntos
de treino e teste de `data/legal/`, **toda** causa candidata é uma premissa ou um axioma, caso em
que a intervenção age por *undermining* e propaga corretamente. O processo real é o primeiro
material em que o próprio caso pergunta por um literal intermediário da cadeia, derivado por
regra, e é isso que torna a limitação visível.

## Arquivos de resultado

| Arquivo em [`outputs/caso-real/`](../../outputs/caso-real/) | Conteúdo |
|---|---|
| `case-003-final.json` | Execução completa da variante `lrc_first` |
| `case-003-final-cif.json` | Execução completa da variante `cif_first` |

Cada arquivo registra o mapa de renomeação de regras, as duas camadas (base de conhecimento,
modelo causal, argumentos, ataques, derrotas e extensão fundamentada), os literais de ponte
calculados, o relatório de relevância jurídica e o confronto com a corte e com o solver de
origem.
