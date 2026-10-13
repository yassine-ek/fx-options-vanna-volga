"""Smile de volatilité par vanna-volga (Castagna-Mercurio 2007) à partir de ATM / RR25 / BF25.

Cotations -> trois vols pivots (convention « BF smile », la forme simple) :
    sigma_25C = ATM + BF + RR/2        sigma_25P = ATM + BF - RR/2
Strikes pivots : K_25P < K_ATM < K_25C, par conversion delta -> strike avec la convention choisie
(delta 25 évalué avec la vol du pivot, ATM par `strike_atm`).

DEUX BUTTERFLIES, À NE PAS CONFONDRE.
  - BF « smile » : (sigma_25C + sigma_25P)/2 - ATM. C'est ce que prend `SmileVV(..., bf=...)`.
  - BF « de marché » (broker fly) : c'est celui que les courtiers cotent. On définit une vol unique
    sigma_ST = ATM + BF_marché ; le strangle de marché est le call 25D + le put 25D dont les strikes sont
    calculés avec cette vol unique, et son prix est celui à sigma_ST. Les strikes et les vols diffèrent
    de ceux du smile, donc BF_marché != BF_smile (l'écart est petit mais non nul).
`bf_smile_depuis_marche` / `SmileVV.depuis_marche` retrouvent le BF smile tel que le smile vanna-volga
reprice exactement ce strangle de marché (une équation à une inconnue, résolue par `brentq`).

Prix vanna-volga (vol de référence sigma0 = ATM) :
    C_VV(K) = C_BS(K, s0) + sum_i x_i(K) [ C_BS(K_i, sigma_i) - C_BS(K_i, s0) ]
où x(K) résout  sum_i x_i G(K_i) = G(K),  G dans {vega, vanna, volga}  (système 3x3 exact).
Le prix VV repasse exactement par les 3 pivots (x = e_j en K = K_j).

Approximation du premier ordre de Castagna-Mercurio : avec les poids de Lagrange en ln K
    y_1 = ln(K2/K) ln(K3/K) / [ln(K2/K1) ln(K3/K1)],  y_2 = ln(K/K1) ln(K3/K) / [ln(K2/K1) ln(K3/K2)],
    y_3 = ln(K/K1) ln(K/K2) / [ln(K3/K1) ln(K3/K2)],
    D1 = sum y_i (sigma_i - s0),  D2 = sum y_i d1(K_i) d2(K_i) (sigma_i - s0)^2,
    sigma(K) = s0 + [ -s0 + sqrt( s0^2 + d1 d2 (2 s0 D1 + D2) ) ] / (d1 d2)    (d1, d2 en K, à la vol s0).
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from fxopt import garman_kohlhagen as gk
from fxopt.deltas import strike_atm, strike_depuis_delta


def strangle_de_marche(S, T, rd, rf, atm, bf_marche, conv="spot"):
    """Strangle de marché 25D (une seule vol sigma_ST = ATM + BF_marché pour les deux jambes).

    Renvoie (K_call, K_put, prix) : strikes 25D calculés à sigma_ST et prix call + put à sigma_ST.
    """
    sig = atm + bf_marche
    kc = float(strike_depuis_delta(conv, 0.25, S, T, rd, rf, sig, phi=1))
    kp = float(strike_depuis_delta(conv, -0.25, S, T, rd, rf, sig, phi=-1))
    prix = float(gk.prix(S, kc, T, rd, rf, sig, 1) + gk.prix(S, kp, T, rd, rf, sig, -1))
    return kc, kp, prix


def bf_smile_depuis_marche(S, T, rd, rf, atm, rr, bf_marche, conv="spot", type_atm="dns", largeur=0.01):
    """BF « smile » dont le smile vanna-volga reprice le strangle de marché de BF `bf_marche`.

    On cherche bf_smile tel que (call VV au strike K_call + put VV au strike K_put) = prix du strangle de marché ;
    le put se déduit du call VV par la parité. Le prix du strangle croît avec bf_smile : racine unique, cherchée
    par `brentq` dans bf_marche +/- `largeur` (ValueError si elle n'y est pas).
    """
    kc, kp, cible = strangle_de_marche(S, T, rd, rf, atm, bf_marche, conv)
    parite_p = S * np.exp(-rf * T) - kp * np.exp(-rd * T)        # call - put au strike kp

    def ecart(bf_smile):
        sm = SmileVV(S, T, rd, rf, atm, rr, bf_smile, conv=conv, type_atm=type_atm)
        return sm.prix_call(kc) + sm.prix_call(kp) - parite_p - cible

    return float(brentq(ecart, bf_marche - largeur, bf_marche + largeur, xtol=1e-15))


@dataclass
class SmileVV:
    S: float
    T: float
    rd: float
    rf: float
    atm: float
    rr: float
    bf: float
    conv: str = "spot"          # convention de delta des 25D
    type_atm: str = "dns"       # "dns" | "dns_pa" | "forward"

    @classmethod
    def depuis_marche(cls, S, T, rd, rf, atm, rr, bf_marche, conv="spot", type_atm="dns"):
        """Smile construit à partir d'un BF de MARCHÉ (broker fly) : on résout le BF smile équivalent (`.bf`)."""
        bf = bf_smile_depuis_marche(S, T, rd, rf, atm, rr, bf_marche, conv, type_atm)
        sm = cls(S, T, rd, rf, atm, rr, bf, conv=conv, type_atm=type_atm)
        sm.bf_marche = bf_marche
        return sm

    def __post_init__(self):
        self.vols = np.array([self.atm + self.bf - self.rr / 2,      # 25P
                              self.atm,
                              self.atm + self.bf + self.rr / 2])     # 25C
        a = (self.S, self.T, self.rd, self.rf)
        self.K = np.array([strike_depuis_delta(self.conv, -0.25, *a, self.vols[0], phi=-1),
                           strike_atm(self.type_atm, *a, self.atm),
                           strike_depuis_delta(self.conv, 0.25, *a, self.vols[2], phi=1)])
        self.prix_marche = np.array([gk.prix(self.S, k, self.T, self.rd, self.rf, v)
                                     for k, v in zip(self.K, self.vols)])
        self.prix_ref = np.array([gk.prix(self.S, k, self.T, self.rd, self.rf, self.atm) for k in self.K])

    def _grecques_ref(self, K):
        g = gk.grecques(self.S, K, self.T, self.rd, self.rf, self.atm)
        return np.array([g["vega"], g["vanna"], g["volga"]])

    def poids(self, K):
        """Poids exacts x_i(K) (système vega/vanna/volga)."""
        A = np.column_stack([self._grecques_ref(k) for k in self.K])
        return np.linalg.solve(A, self._grecques_ref(K))

    def prix_call(self, K):
        """Prix VV d'un call de strike K (scalaire ou tableau)."""
        corr = self.prix_marche - self.prix_ref
        un = lambda k: float(gk.prix(self.S, k, self.T, self.rd, self.rf, self.atm) + self.poids(k) @ corr)
        K = np.asarray(K, float)
        return un(float(K)) if K.ndim == 0 else np.array([un(k) for k in K])

    def vol(self, K):
        """Vol implicite du prix VV (exacte). nan si le prix VV viole les bornes d'arbitrage."""
        K = np.atleast_1d(np.asarray(K, float))
        return np.array([gk.vol_implicite(self.prix_call(k), self.S, k, self.T, self.rd, self.rf, 1) for k in K])

    def vol_cm(self, K):
        """Approximation du premier ordre de Castagna-Mercurio."""
        K = np.atleast_1d(np.asarray(K, float))
        K1, K2, K3 = self.K
        s0 = self.atm
        ds = self.vols - s0
        d1i, d2i = gk.d1_d2(self.S, self.K, self.T, self.rd, self.rf, s0)
        out = []
        for k in K:
            y = np.array([np.log(K2 / k) * np.log(K3 / k) / (np.log(K2 / K1) * np.log(K3 / K1)),
                          np.log(k / K1) * np.log(K3 / k) / (np.log(K2 / K1) * np.log(K3 / K2)),
                          np.log(k / K1) * np.log(k / K2) / (np.log(K3 / K1) * np.log(K3 / K2))])
            D1 = y @ ds
            D2 = y @ (d1i * d2i * ds**2)
            d1, d2 = gk.d1_d2(self.S, k, self.T, self.rd, self.rf, s0)
            g = d1 * d2
            if abs(g) < 1e-12:                       # limite g -> 0 : sigma = s0 + D1
                out.append(s0 + D1)
                continue
            out.append(s0 + (-s0 + np.sqrt(s0**2 + g * (2 * s0 * D1 + D2))) / g)
        return np.array(out)

    def densite(self, K, h_rel=1e-3):
        """Densité implicite risque-neutre e^{rd T} d2C/dK2 (différences finies centrées sur le prix VV)."""
        K = np.atleast_1d(np.asarray(K, float))
        h = h_rel * K
        c = lambda x: np.array([self.prix_call(xi) for xi in x])
        return np.exp(self.rd * self.T) * (c(K + h) - 2 * c(K) + c(K - h)) / h**2
