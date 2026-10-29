---
pdf:
  titulo: "Formalization — Case 003"
  subtitulo: "State liability for a crime committed by an escaped prisoner"
  autor: "Rafael Nobre"
  data: "2026-09-07"
  saida: "docs/figures/case-003-manual.pdf"
  remover: "andaime"
---

# Formalization — Case 003

## Legend

**Perspectives**

```
RTE_ (Appellant — State of Mato Grosso)          party
RDO_ (Respondent — Victim’s family)   party
MA_  (Marco Aurélio — reporting justice)         adjudicator
EF_  (Edson Fachin)                    adjudicator
AM_  (Alexandre de Moraes)             adjudicator
```

**Rules** — theory layer

```
→    strict rule
⇒    defeasible rule
```

**Attacks** — graph layer, derived from conclusions

```
↣    Undermining     attacks a premise
⤅    Rebutting       attacks a conclusion
⇏    Undercutting    attacks a rule
```

---

## Atoms

**CIF — factual causal mechanism**

```
OmiEstatal   the State failed in its custody of the prisoner
RegFechado   the prisoner was serving a sentence in a closed prison regime
FugaPreso    the prisoner escaped from the prison system
Latrocinio   the escaped prisoner committed robbery resulting in the victim’s death
MorteVitima  the victim was killed during the robbery
Danos        the victim’s family suffered material and non-material harm
```

**LRC — legal qualifications and attribution**

```
LapsoTemporal         the crime was committed three months after the escape
FormacaoQuad          the crime was committed by a group of offenders
DeverEspec            the State had a specific duty of custody over the prisoner
OmissaoGenerica       the State’s omission is classified as generic given the elapsed time and joint offending
AtoTerceiro           the crime after the escape is a third-party act (an independent superseding cause)
PremedAlvo            the crime against a specific target was planned before the escape (RE 136.247)
SeqImediata           a logical and immediate sequence linked the escape and crime (RE 136.247)
ProvidenciasCabiveis  the State took the appropriate measures to prevent the escape
MeiosDisponiveis      the State had material means available to act
```

`PremedAlvo` and `SeqImediata` belong to the vocabulary but not the factual base. They represent the distinguishing of RE 136.247 used in the judgment’s theory; their conditions are not realized in this case.

---

## CIF

### Rule inventory

```
r0 : OmiEstatal               ⇒ FugaPreso    [RDO_]
r1 : OmiEstatal ∧ RegFechado  ⇒ FugaPreso    [MA_, EF_, AM_]
r2 : FugaPreso                ⇒ Latrocinio   [RDO_, MA_, EF_, RTE_, AM_]
r3 : Latrocinio               ⇒ MorteVitima  [RDO_, MA_, EF_, RTE_, AM_]
r4 : MorteVitima              ⇒ Danos        [RDO_, MA_, EF_, RTE_, AM_]
```

### By perspective

**RDO_ (Respondent)**

```
Premises   OmiEstatal, RegFechado
Rules       r0, r2, r3, r4
```

**RTE_ (Appellant)**

```
Premises   —
Rules       r2, r3, r4
```

**MA_ (Marco Aurélio — reporting justice)**

```
Premises   OmiEstatal, RegFechado
Rules       r1, r2, r3, r4
```

**EF_ (Edson Fachin)**

```
Premises   OmiEstatal, RegFechado
Rules       r1, r2, r3, r4
```

**AM_ (Alexandre de Moraes)**

```
Premises   OmiEstatal
Rules       r1, r2, r3, r4
```

### Attack graph

```
none — this layer models the factual mechanism; all controversy has moved to LRC

output  caFa(OmiEstatal, Danos) = true
```

### Preference-sensitive points

```
none — there are no attacks in this layer
```

---

## LRC

### Rule inventory

```
dvesp_q0  : RegFechado                                 ⇒ DeverEspec               [RDO_, MA_, EF_]
suca_q3   : LapsoTemporal                              ⇒ AtoTerceiro              [RTE_]
u_corte   : LapsoTemporal                              ⇒ ¬suca_q3                 [AM_]
suca_q4   : Latrocinio ∧ LapsoTemporal ∧ FormacaoQuad  ⇒ AtoTerceiro              [AM_]
q_reab    : PremedAlvo ∧ SeqImediata                   ⇒ ¬suca_q4                 [AM_]
cf2lrc_q5 : CaFa_OmiEstatal_Danos                      ⇒ LeReCa_OmiEstatal_Danos  [RDO_, MA_, EF_]
sc_q6     : AtoTerceiro                                ⇒ ¬cf2lrc_q5               [RTE_, AM_]
dvpre_q8  : DeverEspec                                 ⇒ ¬sc_q6                   [MA_, EF_]
og_q9     : OmiEstatal ∧ LapsoTemporal ∧ FormacaoQuad  ⇒ OmissaoGenerica          [AM_]
og_q10    : OmissaoGenerica                            ⇒ ¬cf2lrc_q5               [AM_]
q11       : ¬ProvidenciasCabiveis                      ⇒ ¬suca_q3                 [EF_]
```

### By perspective

**RDO_ (Respondent)**

```
Premises   OmiEstatal, RegFechado, Latrocinio
Rules       dvesp_q0, cf2lrc_q5
```

**RTE_ (Appellant)**

```
Premises   LapsoTemporal, Latrocinio
Rules       suca_q3, sc_q6
```

**MA_ (Marco Aurélio — reporting justice)**

```
Premises   OmiEstatal, RegFechado, Latrocinio
Rules       dvesp_q0, cf2lrc_q5, dvpre_q8
```

**EF_ (Edson Fachin)**

```
Premises   OmiEstatal, RegFechado, Latrocinio, ¬ProvidenciasCabiveis
Rules       dvesp_q0, cf2lrc_q5, dvpre_q8, q11
```

**AM_ (Alexandre de Moraes)**

```
Premises   OmiEstatal, LapsoTemporal, FormacaoQuad, Latrocinio
Rules       u_corte, suca_q4, q_reab, sc_q6, og_q9, og_q10
```

### Attack graph

```
ARGUMENTATION PHASE — parties

  RTE_    suca_q3 + sc_q6  ⇏  cf2lrc_q5   undercutting
                                          (prevails by dialectical default)

FASE DE DECISÃO — adjudicatores

  MA_     dvpre_q8         ⇏  sc_q6       undercutting
  EF_     dvpre_q8         ⇏  sc_q6       undercutting
          q11              ⇏  suca_q3     undercutting
  AM_     u_corte          ⇏  suca_q3     undercutting
          suca_q4 + sc_q6  ⇏  cf2lrc_q5   undercutting   (Path 1)
          og_q9 + og_q10   ⇏  cf2lrc_q5   undercutting   (Path 2)
          q_reab           ⇏  suca_q4     undercutting   (inactive in this case)
```

### Preference-sensitive points

```
none — all attacks are undercuts; the theory uses no weights
```
