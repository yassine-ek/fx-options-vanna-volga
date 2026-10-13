"""Garman-Kohlhagen : pricing et grecques analytiques d'options européennes FX.

Convention : paire FOR/DOM (ex. EURUSD : étranger = EUR, domestique = USD). S = nombre d'unités
domestiques par unité étrangère. Le prix est exprimé en monnaie domestique, pour 1 unité de notionnel étranger.
  rd = taux domestique, rf = taux étranger (continus), T en années, sigma = vol lognormale.
  phi = +1 pour un call, -1 pour un put.

Les fonctions acceptent des tableaux numpy (diffusion habituelle).
"""
import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr

_RAC2PI = np.sqrt(2.0 * np.pi)


def npdf(x):
    return np.exp(-0.5 * np.asarray(x) ** 2) / _RAC2PI


def forward(S, T, rd, rf):
    """Forward FX par parité des taux couverte : F = S exp((rd - rf) T)."""
    return S * np.exp((rd - rf) * T)


def d1_d2(S, K, T, rd, rf, sigma):
    sd = sigma * np.sqrt(T)
    d1 = (np.log(forward(S, T, rd, rf) / K) + 0.5 * sigma**2 * T) / sd
    return d1, d1 - sd


def prix(S, K, T, rd, rf, sigma, phi=1):
    """Prix GK : phi [ S e^{-rf T} N(phi d1) - K e^{-rd T} N(phi d2) ]."""
    d1, d2 = d1_d2(S, K, T, rd, rf, sigma)
    return phi * (S * np.exp(-rf * T) * ndtr(phi * d1) - K * np.exp(-rd * T) * ndtr(phi * d2))


def parite_ecart(S, K, T, rd, rf, sigma):
    """Call - Put - (S e^{-rf T} - K e^{-rd T}) ; doit valoir 0 (arrondi machine)."""
    return (prix(S, K, T, rd, rf, sigma, 1) - prix(S, K, T, rd, rf, sigma, -1)
            - (S * np.exp(-rf * T) - K * np.exp(-rd * T)))


def grecques(S, K, T, rd, rf, sigma, phi=1):
    """Grecques analytiques (dérivées du prix en monnaie domestique).

    delta_spot  = dV/dS = phi e^{-rf T} N(phi d1)
    delta_fwd   = phi N(phi d1)                    (delta « forward » non ajusté de la prime)
    gamma       = e^{-rf T} n(d1) / (S sigma sqrt T)
    vega        = S e^{-rf T} n(d1) sqrt T        (par unité de vol, pas par point)
    vanna       = d(delta_spot)/d(sigma) = d(vega)/dS = -e^{-rf T} n(d1) d2 / sigma
    volga       = d(vega)/d(sigma) = vega d1 d2 / sigma   (aussi appelée vomma)
    """
    d1, d2 = d1_d2(S, K, T, rd, rf, sigma)
    er = np.exp(-rf * T)
    vega = S * er * npdf(d1) * np.sqrt(T)
    return {
        "delta_spot": phi * er * ndtr(phi * d1),
        "delta_forward": phi * ndtr(phi * d1),
        "gamma": er * npdf(d1) / (S * sigma * np.sqrt(T)),
        "vega": vega,
        "vanna": -er * npdf(d1) * d2 / sigma,
        "volga": vega * d1 * d2 / sigma,
    }


def vol_implicite(valeur, S, K, T, rd, rf, phi=1, bornes=(1e-4, 5.0)):
    """Inverse le prix GK par brentq ; renvoie nan si le prix sort des bornes d'absence d'arbitrage."""
    f = lambda s: prix(S, K, T, rd, rf, s, phi) - valeur
    lo, hi = bornes
    if not (f(lo) <= 0.0 <= f(hi)):
        return np.nan
    return brentq(f, lo, hi, xtol=1e-14)
