"""Conventions de delta FX et conversion strike <-> delta.

Quatre conventions (phi = +1 call, -1 put ; F = forward ; s = sigma sqrt T) :
  "spot"        : Delta = phi e^{-rf T} N(phi d1)                 (usage courant, maturités <= 1 an)
  "forward"     : Delta = phi N(phi d1)                           (maturités longues)
  "spot_pa"     : Delta = phi e^{-rf T} (K/F) N(phi d2)           (= delta - V/S, prime payée en étranger)
  "forward_pa"  : Delta = phi (K/F) N(phi d2)
« pa » = premium-adjusted : le delta est net de la prime quand celle-ci est réglée en monnaie étrangère.

Inversion delta -> strike
  - spot / forward : fermée, d1 = phi N^{-1}(phi Delta / escompte), K = F exp(-d1 s + s^2/2).
  - premium-adjusted : g(K) = (K/F) N(phi d2) n'est PAS monotone pour un call (g -> 0 quand K -> 0 ET
    quand K -> inf, avec un maximum en K*). Un delta cible a donc 0 ou 2 solutions. On prend la branche
    des strikes ELEVES (K >= K*), la seule où le delta décroît avec le strike comme pour un call ordinaire
    (c'est la convention de marché). Si la cible dépasse g(K*), aucun strike n'existe : ValueError.
    Pour un put, g(K) = (K/F) N(-d2) est monotone croissante : solution unique.
    Résolution numérique : K* par minimisation bornée de -g en x = ln(K/F) sur [-12 s, 12 s],
    puis brentq sur [K*, borne haute élargie jusqu'à g < cible].
"""
import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import ndtr, ndtri

from fxopt.garman_kohlhagen import d1_d2, forward

CONVENTIONS = ("spot", "forward", "spot_pa", "forward_pa")


def delta(conv, S, K, T, rd, rf, sigma, phi=1):
    d1, d2 = d1_d2(S, K, T, rd, rf, sigma)
    F = forward(S, T, rd, rf)
    er = np.exp(-rf * T)
    if conv == "spot":
        return phi * er * ndtr(phi * d1)
    if conv == "forward":
        return phi * ndtr(phi * d1)
    if conv == "spot_pa":
        return phi * er * (K / F) * ndtr(phi * d2)
    if conv == "forward_pa":
        return phi * (K / F) * ndtr(phi * d2)
    raise ValueError(f"convention inconnue : {conv}")


def _g_pa(x, phi, s):
    """g en fonction de x = ln(K/F) : (K/F) N(phi d2), avec d2 = (-x - s^2/2)/s."""
    return np.exp(x) * ndtr(phi * (-x - 0.5 * s * s) / s)


def _x_pa(cible, phi, s):
    """Résout g(x) = cible (x = ln(K/F)) sur la branche correcte."""
    if cible <= 0:
        raise ValueError("delta cible nul ou de mauvais signe")
    if phi == 1:
        res = minimize_scalar(lambda x: -_g_pa(x, 1, s), bounds=(-12 * s, 12 * s), method="bounded",
                              options={"xatol": 1e-12})
        x_star, g_max = res.x, -res.fun
        if cible > g_max:
            raise ValueError(f"delta PA cible {cible:.4f} > maximum atteignable {g_max:.4f} (call PA non monotone)")
        hi = x_star + 12 * s + 1.0
        while _g_pa(hi, 1, s) > cible:      # g -> 0 à droite : on élargit jusqu'à passer sous la cible
            hi += 12 * s + 1.0
        return brentq(lambda x: _g_pa(x, 1, s) - cible, x_star, hi, xtol=1e-14)
    lo, hi = -40.0, 1.0                      # put : g monotone croissante de 0 à +inf
    while _g_pa(hi, -1, s) < cible:
        hi += 1.0
    return brentq(lambda x: _g_pa(x, -1, s) - cible, lo, hi, xtol=1e-14)


def strike_depuis_delta(conv, delta_cible, S, T, rd, rf, sigma, phi=1):
    """Strike dont le delta (signé : > 0 pour un call, < 0 pour un put) vaut delta_cible, selon `conv`."""
    if phi * delta_cible <= 0:
        raise ValueError("delta_cible doit avoir le signe de phi")
    F = forward(S, T, rd, rf)
    s = sigma * np.sqrt(T)
    a = phi * delta_cible                                  # delta en valeur absolue
    if conv in ("spot", "spot_pa"):
        a = a * np.exp(rf * T)                             # on se ramène au delta « forward »
    if conv in ("spot", "forward"):
        if not 0 < a < 1:
            raise ValueError("delta hors de ]0, escompte[")
        d1 = phi * ndtri(a)
        return F * np.exp(-d1 * s + 0.5 * s * s)
    if conv in ("spot_pa", "forward_pa"):
        return F * np.exp(_x_pa(a, phi, s))
    raise ValueError(f"convention inconnue : {conv}")


def strike_atm(type_atm, S, T, rd, rf, sigma):
    """Strike ATM.
      "forward"  : K = F
      "dns"      : delta-neutral straddle, delta call + delta put = 0 (conventions NON ajustées :
                   d1 = 0)  ->  K = F exp(+sigma^2 T / 2)
      "dns_pa"   : idem pour les conventions premium-adjusted (d2 = 0)  ->  K = F exp(-sigma^2 T / 2)
    (l'escompte étant commun au call et au put, spot et forward donnent le même strike DNS.)
    """
    F = forward(S, T, rd, rf)
    if type_atm == "forward":
        return F
    if type_atm == "dns":
        return F * np.exp(0.5 * sigma**2 * T)
    if type_atm == "dns_pa":
        return F * np.exp(-0.5 * sigma**2 * T)
    raise ValueError(f"type ATM inconnu : {type_atm}")
