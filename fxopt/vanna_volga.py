"""Smile de volatilité par vanna-volga (Castagna-Mercurio 2007) à partir de ATM / RR25 / BF25.

Cotations marché -> trois vols pivots (convention « smile strangle » simple) :
    sigma_25C = ATM + BF + RR/2        sigma_25P = ATM + BF - RR/2
Strikes pivots : K_25P < K_ATM < K_25C, par conversion delta -> strike avec la convention choisie
(delta 25 évalué avec la vol du pivot, ATM par `strike_atm`).

LIMITE (documentée) : le « BF25 » coté par les brokers est en général le « broker fly » (vol du strangle
de marché, dont le prix = prix à la vol ATM + BF, strikes déterminés avec une vol unique). Il diffère de
la définition « smile strangle » ci-dessus ; en tenir compte exige une correction itérative. On
implémente ici la forme simple ; l'écart est de second ordre mais non nul.

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

from fxopt import garman_kohlhagen as gk
from fxopt.deltas import strike_atm, strike_depuis_delta


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
