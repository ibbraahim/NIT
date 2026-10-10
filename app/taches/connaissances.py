"""Outil RAG de Workly : retrouve, dans la base de connaissances d'exploitation, les passages qui
éclairent une panne, pour les donner aux agents (Agentic AI) avec le bilan.

La base est ``docs/base_connaissances_exploitation.md`` (ou le fichier désigné par
``WORKLY_BASE_CONNAISSANCES``). Elle est découpée par section (``## titre``) ; chaque section est
un passage. La recherche classe les passages par pertinence avec BM25, un classement lexical
classique, en bibliothèque standard seulement : aucun modèle d'embeddings, aucun service externe.

    GET /connaissances?question=<texte>&k=3   passages les plus proches de la question
    GET /bilan?connaissances=1                le bilan, plus les passages utiles à ses pannes
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

from app.journal import journal

_log = journal(__name__)

FICHIER_DEFAUT = Path(__file__).resolve().parents[2] / "docs" / "base_connaissances_exploitation.md"
K1, B = 1.5, 0.75
PASSAGES_PAR_DEFAUT = 3
PASSAGES_MAX = 10
LONGUEUR_MAX = 1500

MOTS_VIDES = frozenset(
    "a au aux avec ce ces dans de des du elle en et eux il ils je la le les leur lui ma mais me "
    "meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te "
    "tes toi ton tu un une vos votre vous est sont etre a ete si ainsi comme plus tout tous "
    "cette cet y d l n s c j m t qu".split()
)


class ErreurConnaissances(Exception):
    """Base de connaissances introuvable ou vide."""


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def _normaliser(mot: str) -> str:
    return mot[:-1] if len(mot) > 4 and mot.endswith("s") else mot


def mots(texte: str) -> list[str]:
    """Mots significatifs : sans accents, en minuscules, sans mots vides ; un nom comme
    ``kpi_quotidiens`` compte pour lui-même et pour chacune de ses parties."""
    resultat = []
    for brut in re.findall(r"[a-z0-9_]+", _sans_accents(texte).lower()):
        morceaux = [brut, *brut.split("_")] if "_" in brut else [brut]
        for morceau in morceaux:
            if len(morceau) > 1 and morceau not in MOTS_VIDES:
                resultat.append(_normaliser(morceau))
    return resultat


def decouper(markdown: str) -> list[tuple[str, str]]:
    """Sections ``## titre`` du document, sous la forme (titre, texte). Ce qui précède la première
    section (titre général, introduction) n'est pas un passage."""
    passages: list[tuple[str, list[str]]] = []
    for ligne in markdown.splitlines():
        if ligne.startswith("## "):
            passages.append((ligne[3:].strip(), []))
        elif passages:
            passages[-1][1].append(ligne)
    return [(titre, " ".join(" ".join(corps).split())) for titre, corps in passages]


class Base:
    """Index BM25 des passages ; le titre compte double."""

    def __init__(self, passages: list[tuple[str, str]]):
        if not passages:
            raise ErreurConnaissances("La base de connaissances ne contient aucune section.")
        self.passages = passages
        self.termes = [Counter(mots(t) * 2 + mots(c)) for t, c in passages]
        self.longueurs = [sum(c.values()) for c in self.termes]
        self.moyenne = sum(self.longueurs) / len(self.longueurs) or 1.0
        nb_docs = Counter(m for c in self.termes for m in c)
        n = len(passages)
        self.idf = {m: math.log(1 + (n - df + 0.5) / (df + 0.5)) for m, df in nb_docs.items()}

    def rechercher(self, question: str, k: int = PASSAGES_PAR_DEFAUT) -> list[dict]:
        requete = set(mots(question))
        scores = []
        for i, termes in enumerate(self.termes):
            score = 0.0
            for m in requete:
                f = termes.get(m, 0)
                if f:
                    norme = f + K1 * (1 - B + B * self.longueurs[i] / self.moyenne)
                    score += self.idf[m] * f * (K1 + 1) / norme
            if score > 0:
                scores.append((score, i))
        scores.sort(key=lambda s: (-s[0], s[1]))
        resultats = []
        for score, i in scores[: max(1, min(k, PASSAGES_MAX))]:
            titre, texte = self.passages[i]
            resultats.append(
                {"section": titre, "score": round(score, 2), "texte": texte[:LONGUEUR_MAX]}
            )
        return resultats


_cache: dict = {}


def charger(chemin: Path | None = None) -> Base:
    """Base indexée, rechargée si le fichier a changé."""
    chemin = chemin or Path(os.environ.get("WORKLY_BASE_CONNAISSANCES") or FICHIER_DEFAUT)
    try:
        modifie = chemin.stat().st_mtime
    except OSError as exc:
        raise ErreurConnaissances(f"Base de connaissances introuvable : {chemin}") from exc
    if _cache.get("cle") != (chemin, modifie):
        _cache["cle"] = (chemin, modifie)
        _cache["base"] = Base(decouper(chemin.read_text(encoding="utf-8")))
        _log.info("Base de connaissances indexée : %d section(s).", len(_cache["base"].passages))
    return _cache["base"]


def rechercher(
    question: str, k: int = PASSAGES_PAR_DEFAUT, chemin: Path | None = None
) -> list[dict]:
    return charger(chemin).rechercher(question, k)


def question_depuis_bilan(bilan: dict) -> str:
    """Question construite à partir des pannes du bilan ; vide quand tout va bien."""
    if bilan.get("statut_global") == "succes":
        return ""
    morceaux = [f"statut {bilan.get('statut_global', '')}"]
    morceaux += [f"étape manquante {nom}" for nom in bilan.get("etapes_nuit_manquantes", [])]
    for echec in bilan.get("echecs_recents", [])[:3]:
        morceaux.append(f"{echec.get('tache', '')} {str(echec.get('message', ''))[:120]}")
    return " ; ".join(morceaux)


def connaissances_pour_bilan(bilan: dict, k: int = PASSAGES_PAR_DEFAUT) -> list[dict]:
    """Passages utiles à l'analyse du bilan (liste vide si la nuit est réussie)."""
    question = question_depuis_bilan(bilan)
    return rechercher(question, k) if question else []
