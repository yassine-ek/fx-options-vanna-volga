"""Tableau de validation, variantes (conventions de delta x méthodes), figures et blocs du README.

COTATIONS EURUSD 1M ILLUSTRATIVES, PAS DES DONNÉES DE MARCHÉ : tout est calculé par les formules du paquet
`fxopt`, comparé à une référence écrite indépendamment (Black-Scholes sur le spot, différences finies,
Monte Carlo). Rien n'est tapé à la main dans le README : les blocs sont réécrits à partir de results/.

Usage (depuis la racine du projet) :  python scripts/generer_vitrine_06.py
Lit    : results/exemple_eurusd_1m.json (cotations)
Écrit  : results/validation.json, results/variantes_conventions.json,
         figures/hero_smile.png, figures/variantes_conventions.png, figures/validation_erreurs.png,
         et les blocs <!-- BEGIN:nom --> ... <!-- END:nom --> de README.md
"""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import ndtr

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fxopt import garman_kohlhagen as gk
from fxopt.deltas import CONVENTIONS, delta, strike_atm, strike_depuis_delta
from fxopt.monte_carlo import gbm_terminal, prix_mc
from fxopt.vanna_volga import SmileVV, bf_smile_depuis_marche, strangle_de_marche

RES, FIG = RACINE / "results", RACINE / "figures"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
NB = " "
DPI = 130
plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False})
AVERT = "COTATIONS ILLUSTRATIVES, pas des données de marché"

# Paramètres des vérifications (les mêmes que tests/test_options_fx.py)
S, T, RD, RF, SIG = 1.10, 0.25, 0.04, 0.02, 0.08
ATM_PAR_CONV = {"spot": "dns", "forward": "dns", "spot_pa": "dns_pa", "forward_pa": "dns_pa"}
LIBELLE_CONV = {"spot": "delta spot", "forward": "delta forward", "spot_pa": "delta spot premium-adjusted",
                "forward_pa": "delta forward premium-adjusted"}


# ------------------------------------------------------------------ formats français
def nb(x, nd=2):
    return f"{x:,.{nd}f}".replace(",", NB).replace(".", ",")


def sci(x):
    """1.2e-14 -> « 1,2e-14 » ; 0 -> « 0 »."""
    if x == 0:
        return "0"
    m, e = f"{x:.1e}".split("e")
    return f"{m.replace('.', ',')}e{int(e)}"


def tableau(entetes, lignes, align=None):
    align = align or ["---"] * len(entetes)
    out = ["| " + " | ".join(entetes) + " |", "|" + "|".join(align) + "|"]
    out += ["| " + " | ".join(str(c) for c in l) + " |" for l in lignes]
    return "\n".join(out)


def sauver(fig, nom):
    fig.savefig(FIG / nom, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("  ->", (FIG / nom).relative_to(RACINE))


# ------------------------------------------------------------------ références indépendantes
def bs_dividende(S0, K, T_, r, q, sigma, phi):
    """Black-Scholes-Merton écrit sur le spot (sans passer par le forward) : référence indépendante de GK."""
    d1 = (np.log(S0 / K) + (r - q + 0.5 * sigma**2) * T_) / (sigma * np.sqrt(T_))
    d2 = d1 - sigma * np.sqrt(T_)
    return phi * (S0 * np.exp(-q * T_) * ndtr(phi * d1) - K * np.exp(-r * T_) * ndtr(phi * d2))


# ------------------------------------------------------------------ validation
def calculer_validation():
    v = {"parametres": {"S": S, "T": T, "rd": RD, "rf": RF, "sigma": SIG}}

    # 1) prix : GK contre Black-Scholes sur le spot, et contre Monte Carlo
    lignes, ecarts_bs, zs = [], [], []
    ST = gbm_terminal(S, RD, SIG, T, 400_000, q=RF, graine=7, antithetique=True)
    for K in (1.05, 1.10, 1.1055, 1.15):
        for phi in (1, -1):
            g = float(gk.prix(S, K, T, RD, RF, SIG, phi))
            b = float(bs_dividende(S, K, T, RD, RF, SIG, phi))
            mc, es = prix_mc(ST, K, T, RD, phi)
            z = (mc - g) / es
            ecarts_bs.append(abs(g - b))
            zs.append(abs(z))
            lignes.append({"K": K, "type": "call" if phi == 1 else "put", "gk": g, "bsm_spot": b, "ecart_bsm": abs(g - b),
                           "mc": mc, "erreur_type_mc": es, "z_mc": z})
    v["prix"] = {"lignes": lignes, "n_chemins_mc": 400_000, "graine_mc": 7, "max_ecart_bsm": max(ecarts_bs), "max_abs_z_mc": max(zs)}
    cinq = [(K, phi) for K in (0.95, 1.05, 1.10, 1.13, 1.30) for phi in (1, -1)]
    v["prix"]["max_ecart_bsm_5_strikes"] = max(abs(float(gk.prix(S, K, T, RD, RF, SIG, phi)) - float(bs_dividende(S, K, T, RD, RF, SIG, phi))) for K, phi in cinq)

    # 2) parité
    Ks = np.linspace(0.9, 1.3, 25)
    F = float(gk.forward(S, T, RD, RF))
    v["parite"] = {"max_ecart_parite": float(np.max(np.abs(gk.parite_ecart(S, Ks, T, RD, RF, SIG)))),
                   "ecart_call_put_au_forward": abs(float(gk.prix(S, F, T, RD, RF, SIG, 1)) - float(gk.prix(S, F, T, RD, RF, SIG, -1)))}

    # 3) grecques analytiques contre différences finies
    erreurs = {k: 0.0 for k in ("delta", "gamma", "vega", "vanna", "volga")}
    for K in (1.02, 1.10, 1.18):
        for phi in (1, -1):
            g = gk.grecques(S, K, T, RD, RF, SIG, phi)
            p = lambda s_=S, sg=SIG: float(gk.prix(s_, K, T, RD, RF, sg, phi))
            hs, hv = 1e-4, 1e-5
            fd = {"delta": (p(S + hs) - p(S - hs)) / (2 * hs),
                  "gamma": (p(S + hs) - 2 * p() + p(S - hs)) / hs**2,
                  "vega": (p(sg=SIG + hv) - p(sg=SIG - hv)) / (2 * hv),
                  "volga": (p(sg=SIG + 1e-3) - 2 * p() + p(sg=SIG - 1e-3)) / 1e-3**2}
            dsp = lambda sg: (p(S + hs, sg) - p(S - hs, sg)) / (2 * hs)
            fd["vanna"] = (dsp(SIG + 1e-4) - dsp(SIG - 1e-4)) / 2e-4
            ana = {"delta": g["delta_spot"], "gamma": g["gamma"], "vega": g["vega"], "vanna": g["vanna"], "volga": g["volga"]}
            for k in erreurs:
                erreurs[k] = max(erreurs[k], abs(float(ana[k]) / fd[k] - 1))
    v["grecques"] = {"max_erreur_relative": erreurs, "methode": "différences finies centrées, 3 strikes x call/put"}

    # 4) conventions de delta : aller-retour strike -> delta -> strike, par convention
    ar = {}
    for conv in CONVENTIONS:
        pire = 0.0
        for phi in (1, -1):
            K0 = F * np.exp(np.array([-0.04, -0.015, 0.0, 0.015, 0.04, 0.08]))
            if conv.endswith("pa") and phi == 1:
                K0 = K0[K0 >= F]            # call premium-adjusted : seule la branche haute est inversible
            d = delta(conv, S, K0, T, RD, RF, SIG, phi)
            K1 = np.array([strike_depuis_delta(conv, di, S, T, RD, RF, SIG, phi) for di in d])
            pire = max(pire, float(np.max(np.abs(K1 / K0 - 1))))
        ar[conv] = pire
    dns = {}
    for type_atm, conv in (("dns", "spot"), ("dns", "forward"), ("dns_pa", "spot_pa"), ("dns_pa", "forward_pa")):
        K = strike_atm(type_atm, S, T, RD, RF, SIG)
        dns[f"{type_atm}/{conv}"] = abs(float(delta(conv, S, K, T, RD, RF, SIG, 1) + delta(conv, S, K, T, RD, RF, SIG, -1)))
    Fx = np.exp(np.linspace(-0.3, 0.3, 4001)) * F
    dpa = delta("forward_pa", S, Fx, T, RD, RF, SIG, 1)
    i = int(np.argmax(dpa))
    v["deltas"] = {"aller_retour_max_erreur_relative_strike": ar, "dns_somme_deltas_call_put": dns,
                   "call_pa_non_monotone": {"delta_max": float(dpa.max()), "strike_du_max": float(Fx[i]), "monotone": bool(np.all(np.diff(dpa) < 0))},
                   "put_pa_monotone": bool(np.all(np.diff(delta("forward_pa", S, Fx, T, RD, RF, SIG, -1)) < 0))}

    # 5) smile vanna-volga
    pivots = {}
    for conv, type_atm in (("spot", "dns"), ("forward", "forward"), ("spot_pa", "dns_pa")):
        sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.01, 0.0025, conv=conv, type_atm=type_atm)
        err_delta = 0.0
        for k, vol_k, phi in ((sm.K[0], sm.vols[0], -1), (sm.K[2], sm.vols[2], 1)):
            err_delta = max(err_delta, abs(float(delta(conv, 1.10, k, 1 / 12, 0.04, 0.02, vol_k, phi)) - phi * 0.25))
        pivots[f"{conv}/{type_atm}"] = {"ecart_vol_exacte": float(np.max(np.abs(sm.vol(sm.K) - sm.vols))),
                                        "ecart_vol_cm": float(np.max(np.abs(sm.vol_cm(sm.K) - sm.vols))),
                                        "ecart_delta_25": err_delta}
    sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.01, 0.0025)
    K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 30)
    ecart_cm = float(np.max(np.abs(sm.vol_cm(K) - sm.vol(K))) * 100)
    Kd = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 80)
    extr = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.03, 0.015)
    Ke = np.linspace(extr.K[0] * 0.97, extr.K[2] * 1.03, 80)
    # butterfly de marché : le smile issu de `depuis_marche` reprice le strangle de marché (call + put à vol unique)
    reprice = {}
    for conv, type_atm in (("spot", "dns"), ("forward", "forward"), ("spot_pa", "dns_pa")):
        a = (1.10, 1 / 12, 0.04, 0.02)
        smm = SmileVV.depuis_marche(*a, 0.07, -0.01, 0.0025, conv=conv, type_atm=type_atm)
        kc, kp, cible = strangle_de_marche(*a, 0.07, 0.0025, conv)
        parite_put = a[0] * np.exp(-a[3] * a[1]) - kp * np.exp(-a[2] * a[1])
        reprice[f"{conv}/{type_atm}"] = abs(float(smm.prix_call(kc) + smm.prix_call(kp) - parite_put - cible))
    v["smile"] = {"pivots": pivots, "ecart_max_cm_vs_exact_points_de_vol": ecart_cm,
                  "reprice_strangle_de_marche_ecart_prix": reprice,
                  "densite_min_cotations_raisonnables": float(sm.densite(Kd).min()),
                  "densite_min_cas_extreme": float(extr.densite(Ke).min()),
                  "cas_extreme": {"ATM": 0.07, "RR25": -0.03, "BF25": 0.015}}
    return v


# ------------------------------------------------------------------ variantes : conventions de delta x méthodes
def calculer_variantes(ex):
    e = ex["entrees"]
    S0, T0, rd, rf = e["S"], e["T_ans"], e["rd"], e["rf"]
    atm, rr, bf = e["ATM"], e["RR25"], e["BF25"]
    K_fixes = [1.0600, 1.0820, 1.1000]
    out = {"entrees": e, "K_fixes": K_fixes, "conventions": {}}
    ref = None
    for conv in CONVENTIONS:
        sm = SmileVV(S0, T0, rd, rf, atm, rr, bf, conv=conv, type_atm=ATM_PAR_CONV[conv])
        K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 60)
        vv, cm = sm.vol(K), sm.vol_cm(K)
        grille = np.linspace(1.04, 1.13, 46)
        d = {"type_atm": ATM_PAR_CONV[conv], "K_pivots": [float(k) for k in sm.K], "vols_pivots": [float(x) for x in sm.vols],
             "vv_exact": [float(x) for x in sm.vol(K_fixes)], "cm_1er_ordre": [float(x) for x in sm.vol_cm(K_fixes)],
             "vol_plate": [atm] * len(K_fixes),
             "ecart_max_cm_vs_vv_points": float(np.max(np.abs(cm - vv)) * 100),
             "ecart_max_plate_vs_vv_points": float(np.max(np.abs(atm - vv)) * 100),
             "densite_min": float(sm.densite(K).min()),
             "grille_K": [float(x) for x in grille], "vv_sur_grille": [float(x) for x in sm.vol(grille)]}
        out["conventions"][conv] = d
        if conv == "spot":
            ref = d
    cas = (("cotations de l'exemple", atm, rr, bf), ("cas large (RR -1,0 ; BF 0,75)", 0.07, -0.010, 0.0075),
           ("cas extrême (RR -3,0 ; BF 1,5)", 0.07, -0.03, 0.015))
    out["butterfly_marche"] = []
    for nom, a_, r_, b_ in cas:
        s_smile = SmileVV(S0, T0, rd, rf, a_, r_, b_)
        s_marche = SmileVV.depuis_marche(S0, T0, rd, rf, a_, r_, b_)
        Kc = np.linspace(s_smile.K[0] * 0.97, s_smile.K[2] * 1.03, 60)
        out["butterfly_marche"].append({"cas": nom, "ATM": a_, "RR25": r_, "BF_marche": b_, "BF_smile_equivalent": s_marche.bf,
                                        "ecart_bf_points_de_vol": (s_marche.bf - b_) * 100,
                                        "ecart_max_vol_points": float(np.max(np.abs(s_marche.vol(Kc) - s_smile.vol(Kc))) * 100)})
    for conv, d in out["conventions"].items():
        d["ecart_vv_vs_spot_bp_vol"] = [(a - b) * 1e4 for a, b in zip(d["vv_sur_grille"], ref["vv_sur_grille"])]
        d["ecart_strikes_pivots_vs_spot_pips"] = [(a - b) * 1e4 for a, b in zip(d["K_pivots"], ref["K_pivots"])]
    return out


# ------------------------------------------------------------------ figures
def fig_hero(ex):
    """Figure héro : 2 panneaux, 10 x 4,6 pouces, textes >= 11 pt (lisible une fois réduite à la largeur du README)."""
    e = ex["entrees"]
    sm = SmileVV(e["S"], e["T_ans"], e["rd"], e["rf"], e["ATM"], e["RR25"], e["BF25"], conv="spot", type_atm="dns")
    K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 200)
    vv, cm = sm.vol(K) * 100, sm.vol_cm(K) * 100
    dK = gk.grecques(sm.S, K, sm.T, sm.rd, sm.rf, vv / 100)["delta_spot"]
    d_piv = [float(gk.grecques(sm.S, k, sm.T, sm.rd, sm.rf, vol)["delta_spot"]) for k, vol in zip(sm.K, sm.vols)]
    noms = ["25D put", "ATM", "25D call"]
    with plt.rc_context({"font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11, "legend.fontsize": 11,
                         "xtick.labelsize": 11, "ytick.labelsize": 11}):
        fig, ax = plt.subplots(1, 2, figsize=(10, 4.6))
        ax[0].axhline(e["ATM"] * 100, color="grey", ls=":", lw=1.4, label="vol plate (ATM)")
        ax[0].plot(K, vv, color="#2f6fb0", lw=2.4, label="vanna-volga exact")
        ax[0].plot(K, cm, color="#e08a1e", ls="--", lw=1.8, label="Castagna-Mercurio")
        ax[0].scatter(sm.K, sm.vols * 100, c="k", s=60, zorder=4, label="cotations (pivots)")
        for k, vol, nom, dec in zip(sm.K, sm.vols * 100, noms, ((-8, 10), (0, -42), (34, -30))):
            ax[0].annotate(f"{nom}\n{nb(vol)} %", (k, vol), textcoords="offset points", xytext=dec,
                           ha="center", fontsize=11)
        ax[0].set_ylim(6.2, 9.4)
        ax[0].set_xlabel("strike K"), ax[0].set_ylabel("volatilité implicite (%)"), ax[0].set_title("Smile contre le strike")
        ax[0].legend(loc="upper center", frameon=False)
        ax[1].plot(dK, vv, color="#2f6fb0", lw=2.4)
        ax[1].scatter(d_piv, sm.vols * 100, c="k", s=60, zorder=4)
        ax[1].set_xlabel("delta call spot (axe inversé)"), ax[1].set_title("Smile contre le delta")
        ax[1].invert_xaxis()
        fig.suptitle("Smile vanna-volga EURUSD 1M (cotations illustratives)", fontsize=12.5, y=1.0)
        fig.tight_layout()
        sauver(fig, "hero_smile.png")


def fig_variantes(var):
    couleurs = {"spot": "#2f6fb0", "forward": "#e08a1e", "spot_pa": "#3a9d5d", "forward_pa": "#a63603"}
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(2)
    larg = 0.2
    for i, conv in enumerate(CONVENTIONS):
        pips = var["conventions"][conv]["ecart_strikes_pivots_vs_spot_pips"]
        ax[0].bar(x + (i - 1.5) * larg, [pips[0], pips[2]], larg, color=couleurs[conv], label=LIBELLE_CONV[conv])
    ax[0].axhline(0, color="k", lw=0.8)
    ax[0].set_xticks(x, ["strike du 25D put", "strike du 25D call"]), ax[0].set_ylabel("écart au strike de la convention spot (pips)")
    ax[0].set_ylim(-3.0, 1.6)
    ax[0].set_title("Le même « 25 delta » n'est pas au même strike"), ax[0].legend(fontsize=8, loc="upper left", ncol=2)
    for conv in CONVENTIONS:
        d = var["conventions"][conv]
        ax[1].plot(d["grille_K"], d["ecart_vv_vs_spot_bp_vol"], color=couleurs[conv], lw=2, label=LIBELLE_CONV[conv])
    ax[1].axhline(0, color="k", lw=0.8)
    ax[1].set_xlabel("strike K"), ax[1].set_ylabel("vol VV de la convention - vol VV spot (points de base de vol)")
    ax[1].set_title("Se tromper de convention, c'est lire une autre vol"), ax[1].legend(fontsize=8)
    fig.suptitle(f"Quatre conventions de delta, mêmes cotations ({AVERT})", fontsize=10, y=1.02)
    sauver(fig, "variantes_conventions.png")


def lignes_validation(v):
    """(libellé, valeur mesurée, tolérance du test, famille) : alimente le tableau et la figure."""
    p, g, d, s = v["prix"], v["grecques"]["max_erreur_relative"], v["deltas"], v["smile"]
    ar = d["aller_retour_max_erreur_relative_strike"]
    return [
        ("Prix : GK contre sa réécriture Black-Scholes-Merton sur le spot (même formule, 5 strikes x call/put)", p["max_ecart_bsm_5_strikes"], 1e-13, "prix"),
        (f"Prix : Monte Carlo ({nb(p['n_chemins_mc'], 0)} chemins antithétiques) contre GK, z maximal en valeur absolue sur 8 cas", p["max_abs_z_mc"], 3.0, "prix"),
        ("Parité call - put, 25 strikes", v["parite"]["max_ecart_parite"], 1e-14, "parité"),
        ("Call = put au strike forward", v["parite"]["ecart_call_put_au_forward"], 1e-14, "parité"),
        ("Grecques contre différences finies : delta", g["delta"], 1e-5, "grecques"),
        ("Grecques : gamma", g["gamma"], 1e-4, "grecques"),
        ("Grecques : vega", g["vega"], 1e-6, "grecques"),
        ("Grecques : vanna", g["vanna"], 1e-4, "grecques"),
        ("Grecques : volga", g["volga"], 1e-3, "grecques"),
        *[(f"Delta, aller-retour strike → delta → strike : {LIBELLE_CONV[c]}", ar[c], 1e-9, "conventions de delta") for c in CONVENTIONS],
        ("ATM DNS : delta call + delta put = 0 (4 conventions)", max(d["dns_somme_deltas_call_put"].values()), 1e-14, "conventions de delta"),
        ("Smile VV : écart aux 3 pivots, vol exacte (3 couples convention / ATM)", max(x["ecart_vol_exacte"] for x in s["pivots"].values()), 1e-9, "smile"),
        ("Smile VV : écart aux 3 pivots, approximation CM", max(x["ecart_vol_cm"] for x in s["pivots"].values()), 1e-9, "smile"),
        ("Smile VV : pivots bien au delta 25", max(x["ecart_delta_25"] for x in s["pivots"].values()), 1e-9, "smile"),
        ("Smile VV : écart CM contre exact (points de vol, sur [K25P -3 %, K25C +3 %])", s["ecart_max_cm_vs_exact_points_de_vol"], 0.2, "smile"),
        ("Smile VV issu d'un BF de marché : reprice du strangle de marché à vol unique (3 couples convention / ATM)", max(s["reprice_strangle_de_marche_ecart_prix"].values()), 1e-12, "smile"),
    ]


def fig_validation(v):
    lig = lignes_validation(v)
    fig, ax = plt.subplots(figsize=(12.5, 0.34 * len(lig) + 1.6))
    y = np.arange(len(lig))[::-1]
    mesure = [max(m, 1e-17) for _, m, _, _ in lig]
    tol = [t for _, _, t, _ in lig]
    ax.barh(y, mesure, color="#2f6fb0", height=0.55, label="erreur mesurée")
    ax.scatter(tol, y, marker="|", s=260, color="#c0504d", zorder=3, label="tolérance du test")
    ax.set_yticks(y, [l for l, _, _, _ in lig], fontsize=7.5)
    ax.set_xscale("log"), ax.set_xlim(1e-17, 10)
    ax.set_xlabel("erreur (échelle log). Deux lignes ne sont pas des erreurs relatives : z du Monte Carlo (seuil 3) et écart CM en points de vol (seuil 0,2)")
    ax.set_title("Chaque vérification : erreur mesurée (bleu) bien en dessous de la tolérance (trait rouge)", fontsize=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, fontsize=8)
    sauver(fig, "validation_erreurs.png")


# ------------------------------------------------------------------ blocs de README
def bloc_badges():
    return "\n".join([
        "[![tests](https://github.com/yassine-ek/fx-options-vanna-volga/actions/workflows/tests.yml/badge.svg)]"
        "(https://github.com/yassine-ek/fx-options-vanna-volga/actions/workflows/tests.yml)",
        "![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)",
        "![licence MIT](https://img.shields.io/badge/licence-MIT-blue)",
        "![données](https://img.shields.io/badge/donn%C3%A9es%20de%20march%C3%A9-aucune-lightgrey)",
    ])


def bloc_cles(ex, v, var):
    p, g, d, s = v["prix"], v["grecques"]["max_erreur_relative"], v["deltas"], v["smile"]
    zs = [l["z_mc"] for l in p["lignes"]]
    signes = "tous du même signe et corrélés car tirés sur les mêmes chemins" if (all(z < 0 for z in zs) or all(z > 0 for z in zs)) else "corrélés car tirés sur les mêmes chemins"
    ar = max(d["aller_retour_max_erreur_relative_strike"].values())
    spot = var["conventions"]["spot"]["K_pivots"]
    pips = max(abs((var["conventions"][c]["K_pivots"][i] - spot[i]) * 1e4) for c in ("spot_pa", "forward_pa") for i in (0, 2))   # strikes 25D put et call
    pb = max(abs(x) for c in CONVENTIONS for x in var["conventions"][c]["ecart_vv_vs_spot_bp_vol"])
    ex_bf = var["butterfly_marche"][0]
    pire_g = max(g.values())
    ok_cm = ex["ecart_max_CM_vs_exact_vol_points"]
    return "\n".join([
        f"- **Pricer Garman-Kohlhagen cohérent avec lui-même** : GK et sa réécriture Black-Scholes-Merton sur le spot coïncident à {sci(p['max_ecart_bsm_5_strikes'])}. "
        f"*Réserve : c'est une cohérence entre deux écritures de la même formule (forward contre spot), pas une validation externe ; les grecques sont validées contre des différences finies "
        f"(écart relatif maximal {sci(pire_g)}) et les prix contre Monte Carlo (|z| ≤ {nb(max(abs(z) for z in zs))} sur 8 cas, {signes} : pas huit validations indépendantes). "
        "Aucune référence externe (QuantLib, tables publiées) n'est utilisée.*",
        f"- **Quatre conventions de delta, avec conversion strike ↔ delta** : aller-retour exact à {sci(ar)} près, delta d'un call premium-adjusted non monotone géré (branche haute, maximum {nb(d['call_pa_non_monotone']['delta_max'], 4)}). "
        f"Le même « 25 delta » change de strike d'environ {nb(pips, 1)} pips entre delta spot et premium-adjusted, soit jusqu'à {nb(pb, 1)} pb de vol lus de travers. "
        "*Réserve : cotations EURUSD 1M illustratives, aucune donnée de marché.*",
        f"- **Smile vanna-volga** : repasse par les 3 cotations (écart {sci(max(x['ecart_vol_exacte'] for x in s['pivots'].values()))}), approximation de Castagna-Mercurio à {nb(ok_cm, 3)} point de vol de l'exact, "
        f"densité négative mise en évidence dans un cas extrême (VV n'exclut pas l'arbitrage). Le BF de marché (broker) est géré en plus du BF smile : écart de {nb(ex_bf['ecart_max_vol_points'], 3)} point de vol sur les cotations de l'exemple. "
        "*Réserve : cohérence interne seulement, aucun calibrage ni smile de marché ; un seul smile 1M, ni structure par terme ni pricing d'exotique.*",
    ])


def bloc_hypotheses(ex, v):
    e = ex["entrees"]
    return tableau(["Hypothèse", "Valeur"], [
        ("Données, frais, split", "**Cotations EURUSD 1M ILLUSTRATIVES, pas des données de marché** : aucune donnée de volatilité réelle dans le dépôt. Sans objet : frais, split TRAIN / VAL / TEST (ce n'est pas une stratégie, aucun PnL, aucun backtest)."),
        ("Cotations de l'exemple", f"spot S = {nb(e['S'], 4)} ; taux USD rd = {nb(e['rd'] * 100)} % ; taux EUR rf = {nb(e['rf'] * 100)} % ; maturité T = 1/12 an ; "
                                   f"ATM (DNS) = {nb(e['ATM'] * 100)} % ; RR25 = {nb(e['RR25'] * 100)} pt ; BF25 = {nb(e['BF25'] * 100)} pt ; delta {e['convention_delta']}"),
        ("Ce que ça valide", "La **mécanique** : formules, conventions de delta, cohérence interne du smile. **Pas** un smile réel, pas de calibrage, pas de validation par une bibliothèque externe."),
        ("Convention du butterfly", "BF25 de l'exemple lu comme BF « smile » (forme simple). Le BF coté par les courtiers est un BF de marché (strangle à vol unique) : `SmileVV.depuis_marche` le gère, écart chiffré [plus bas](#convention-du-butterfly)."),
        ("Vérifications", f"S = {nb(v['parametres']['S'])}, T = {nb(v['parametres']['T'])} an, rd = {nb(v['parametres']['rd'] * 100)} %, rf = {nb(v['parametres']['rf'] * 100)} %, σ = {nb(v['parametres']['sigma'] * 100)} % "
                          f"(les mêmes que `tests/test_options_fx.py`) ; Monte Carlo : {nb(v['prix']['n_chemins_mc'], 0)} chemins antithétiques, graine {v['prix']['graine_mc']}, critère moins de 3 erreurs-types."),
        ("Références", "Black-Scholes-Merton écrit sur le spot (**réécriture de la même formule**), différences finies centrées, formule fermée du delta, Monte Carlo."),
    ])


def bloc_bf(var):
    lignes = [(c["cas"], nb(c["ATM"] * 100), nb(c["RR25"] * 100), nb(c["BF_marche"] * 100, 3), nb(c["BF_smile_equivalent"] * 100, 4),
               nb(c["ecart_bf_points_de_vol"], 4), nb(c["ecart_max_vol_points"], 3)) for c in var["butterfly_marche"]]
    t = tableau(["Cotations (EURUSD 1M, delta spot)", "ATM (%)", "RR25 (pt)", "BF de marché (pt)", "BF smile équivalent (pt)", "écart de BF (pt)", "écart max de vol du smile (pt)"],
                lignes, ["---", "--:", "--:", "--:", "--:", "--:", "--:"])
    return ("Le BF25 que cotent les courtiers est un butterfly **de marché** : une vol unique σ_ST = ATM + BF, des strikes 25Δ calculés avec cette vol, et le prix du strangle correspondant. "
            "Le smile a une vol différente sur chaque jambe : son butterfly est (σ25C + σ25P)/2 − ATM (« BF smile »). Les deux ne sont pas égaux, car les strikes et les vols diffèrent.\n\n"
            "`SmileVV(..., bf=...)` prend le BF smile : c'est la **forme simple utilisée dans tout ce dépôt, exemple compris**. "
            "`SmileVV.depuis_marche(..., bf_marche=...)` fait la conversion : il cherche le BF smile dont le smile vanna-volga reprice exactement le strangle de marché (équation à une inconnue, `brentq`). "
            "Écart de vol du smile entre les deux lectures, sur [K25P −3 %, K25C +3 %] :\n\n" + t)


def bloc_validation(v):
    p = v["prix"]
    t1 = tableau(["K", "type", "GK", "BSM sur le spot (réécriture)", "écart", "Monte Carlo ± erreur-type", "z"], [
        (nb(l["K"], 4), l["type"], nb(l["gk"], 6), nb(l["bsm_spot"], 6), sci(l["ecart_bsm"]), f"{nb(l['mc'], 6)} ± {nb(l['erreur_type_mc'], 6)}", nb(l["z_mc"], 2))
        for l in p["lignes"]], ["--:", "---", "--:", "--:", "--:", "--:", "--:"])
    t2 = tableau(["Famille", "Vérification", "Erreur mesurée", "Tolérance du test", "Résultat"], [
        (fam, lib, nb(m, 2) if t >= 0.1 else sci(m), nb(t, 1) if t >= 0.1 else sci(t), "OK" if m <= t else "ÉCHEC") for lib, m, t, fam in lignes_validation(v)],
        ["---", "---", "--:", "--:", "---"])
    ex = v["deltas"]["call_pa_non_monotone"]
    return (f"**Prix contre la réécriture BSM et contre Monte Carlo** (S = {nb(v['parametres']['S'])}, T = {nb(v['parametres']['T'])} an, rd = {nb(v['parametres']['rd'] * 100)} %, "
            f"rf = {nb(v['parametres']['rf'] * 100)} %, σ = {nb(v['parametres']['sigma'] * 100)} %, prix en monnaie domestique par unité de notionnel étranger)\n\n" + t1 +
            "\n\n**Parité, grecques, conventions de delta, smile** (`results/validation.json`)\n\n" + t2 +
            f"\n\nCas particulier vérifié : le delta d'un call premium-adjusted n'est **pas monotone** en K (maximum {nb(ex['delta_max'], 4)} atteint en K = {nb(ex['strike_du_max'], 4)}) ; "
            f"le code retient la branche des strikes élevés et refuse une cible au-dessus du maximum. Le put premium-adjusted est monotone : {'oui' if v['deltas']['put_pa_monotone'] else 'non'}.")


def bloc_variantes(var):
    K = var["K_fixes"]
    lignes = []
    for conv in CONVENTIONS:
        d = var["conventions"][conv]
        pivots = f"{nb(d['K_pivots'][0], 5)} / {nb(d['K_pivots'][1], 5)} / {nb(d['K_pivots'][2], 5)}"
        for meth, cle, ecart in (("vanna-volga exact", "vv_exact", "référence"), ("Castagna-Mercurio 1er ordre", "cm_1er_ordre", f"{nb(d['ecart_max_cm_vs_vv_points'], 3)} pt"),
                                 ("vol plate (Black-Scholes ATM)", "vol_plate", f"{nb(d['ecart_max_plate_vs_vv_points'], 3)} pt")):
            lignes.append((f"{LIBELLE_CONV[conv]} ({d['type_atm']})" if cle == "vv_exact" else "", meth, pivots if cle == "vv_exact" else "",
                           *[nb(x * 100, 3) for x in d[cle]], ecart, nb(d["densite_min"], 2) if cle == "vv_exact" else ""))
    t = tableau(["Convention de delta (ATM)", "Méthode", "K 25P / ATM / 25C", *[f"vol (%) à K = {nb(k, 4)}" for k in K],
                 "écart max à VV exact (points de vol)", "densité implicite min"], lignes, ["---", "---", "---", "--:", "--:", "--:", "--:", "--:"])
    spot = var["conventions"]["spot"]["K_pivots"]
    dif = {c: [(a - b) * 1e4 for a, b in zip(var["conventions"][c]["K_pivots"], spot)] for c in CONVENTIONS}
    t2 = tableau(["Convention", "strike 25D put (écart à spot, pips)", "strike ATM (pips)", "strike 25D call (pips)", "écart max de vol VV à la convention spot (pb de vol)"], [
        (LIBELLE_CONV[c], nb(dif[c][0], 2), nb(dif[c][1], 2), nb(dif[c][2], 2), nb(max(abs(x) for x in var["conventions"][c]["ecart_vv_vs_spot_bp_vol"]), 1))
        for c in CONVENTIONS], ["---", "--:", "--:", "--:", "--:"])
    return ("**Smile par convention de delta × méthode** (cotations illustratives, `results/variantes_conventions.json` ; chaque ligne « vanna-volga exact » donne les "
            "strikes pivots de la convention, les lignes suivantes comparent les méthodes aux mêmes strikes)\n\n" + t +
            "\n\n**Effet de la convention seule** (mêmes cotations, mêmes vols pivots) :\n\n" + t2)


def injecter(blocs):
    chemin = RACINE / "README.md"
    txt = chemin.read_text(encoding="utf-8")
    for nom, contenu in blocs.items():
        motif = re.compile(rf"(<!-- BEGIN:{nom} -->).*?(<!-- END:{nom} -->)", re.S)
        if not motif.search(txt):
            raise SystemExit(f"marqueur {nom} absent du README")
        txt = motif.sub(lambda m: m.group(1) + "\n" + contenu.strip("\n") + "\n" + m.group(2), txt)
    chemin.write_text(txt, encoding="utf-8")
    print("  -> README.md (blocs :", ", ".join(blocs), ")")


if __name__ == "__main__":
    ex = json.loads((RES / "exemple_eurusd_1m.json").read_text(encoding="utf-8"))
    print("validation :")
    v = calculer_validation()
    (RES / "validation.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")
    var = calculer_variantes(ex)
    (RES / "variantes_conventions.json").write_text(json.dumps(var, indent=2, ensure_ascii=False), encoding="utf-8")
    fig_hero(ex)
    fig_variantes(var)
    fig_validation(v)
    injecter({"badges": bloc_badges(), "cles": bloc_cles(ex, v, var), "hypotheses": bloc_hypotheses(ex, v), "validation": bloc_validation(v),
              "variantes": bloc_variantes(var), "bf": bloc_bf(var)})
