"""Vérifications du projet 06 : GK, grecques, conventions de delta, smile vanna-volga, Monte Carlo, arbitrage."""
import numpy as np
import pytest
from scipy.special import ndtr

from fxopt import garman_kohlhagen as gk
from fxopt.deltas import CONVENTIONS, delta, strike_atm, strike_depuis_delta
from fxopt.monte_carlo import gbm_terminal, prix_mc
from fxopt.vanna_volga import SmileVV

S, T, RD, RF, SIG = 1.10, 0.25, 0.04, 0.02, 0.08


# ---------------------------------------------------------------- (a) GK = Black-Scholes avec dividende continu
def bs_dividende(S0, K, T, r, q, sigma, phi):
    """Black-Scholes-Merton écrit indépendamment (sur le spot, sans passer par le forward)."""
    d1 = (np.log(S0 / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return phi * (S0 * np.exp(-q * T) * ndtr(phi * d1) - K * np.exp(-r * T) * ndtr(phi * d2))


@pytest.mark.parametrize("phi", [1, -1])
@pytest.mark.parametrize("K", [0.95, 1.05, 1.10, 1.13, 1.30])
def test_gk_egal_black_scholes_dividende(K, phi):
    assert gk.prix(S, K, T, RD, RF, SIG, phi) == pytest.approx(bs_dividende(S, K, T, RD, RF, SIG, phi), abs=1e-13)


# ---------------------------------------------------------------- (b) parité call-put
def test_parite_call_put():
    K = np.linspace(0.9, 1.3, 25)
    assert np.max(np.abs(gk.parite_ecart(S, K, T, RD, RF, SIG))) < 1e-14


def test_forward_est_le_strike_ou_call_egal_put_en_valeur_actualisee():
    F = gk.forward(S, T, RD, RF)
    assert F == pytest.approx(S * np.exp((RD - RF) * T))
    assert gk.prix(S, F, T, RD, RF, SIG, 1) == pytest.approx(gk.prix(S, F, T, RD, RF, SIG, -1), abs=1e-14)


# ---------------------------------------------------------------- (c) grecques analytiques vs différences finies
@pytest.mark.parametrize("phi", [1, -1])
@pytest.mark.parametrize("K", [1.02, 1.10, 1.18])
def test_grecques_vs_differences_finies(K, phi):
    g = gk.grecques(S, K, T, RD, RF, SIG, phi)
    p = lambda s_=S, sg=SIG: gk.prix(s_, K, T, RD, RF, sg, phi)
    hs, hv = 1e-4, 1e-5
    delta_fd = (p(S + hs) - p(S - hs)) / (2 * hs)
    gamma_fd = (p(S + hs) - 2 * p() + p(S - hs)) / hs**2
    vega_fd = (p(sg=SIG + hv) - p(sg=SIG - hv)) / (2 * hv)
    volga_fd = (p(sg=SIG + 1e-3) - 2 * p() + p(sg=SIG - 1e-3)) / 1e-3**2
    # vanna = d(delta_spot)/d(sigma)
    dsp = lambda sg: (p(S + hs, sg) - p(S - hs, sg)) / (2 * hs)
    vanna_fd = (dsp(SIG + 1e-4) - dsp(SIG - 1e-4)) / 2e-4
    assert g["delta_spot"] == pytest.approx(delta_fd, rel=1e-5)
    assert g["gamma"] == pytest.approx(gamma_fd, rel=1e-4)
    assert g["vega"] == pytest.approx(vega_fd, rel=1e-6)
    assert g["volga"] == pytest.approx(volga_fd, rel=1e-3)
    assert g["vanna"] == pytest.approx(vanna_fd, rel=1e-4)
    # delta forward = delta spot * e^{rf T} : mêmes N(phi d1) sans l'escompte étranger
    assert g["delta_forward"] == pytest.approx(g["delta_spot"] * np.exp(RF * T), rel=1e-12)


# ---------------------------------------------------------------- (d) aller-retour strike -> delta -> strike
@pytest.mark.parametrize("conv", CONVENTIONS)
@pytest.mark.parametrize("phi", [1, -1])
def test_aller_retour_strike_delta_strike(conv, phi):
    F = gk.forward(S, T, RD, RF)
    # pour le call premium-adjusted : seule la branche K >= K* est inversible (voir deltas.py)
    K0 = F * np.exp(np.array([-0.04, -0.015, 0.0, 0.015, 0.04, 0.08]))
    if conv.endswith("pa") and phi == 1:
        K0 = K0[K0 >= F * 1.0]          # bien à droite du pic K* (< F), cf. test dédié
    d = delta(conv, S, K0, T, RD, RF, SIG, phi)
    K1 = np.array([strike_depuis_delta(conv, di, S, T, RD, RF, SIG, phi) for di in d])
    assert np.max(np.abs(K1 / K0 - 1)) < 1e-9


def test_call_premium_adjusted_non_monotone_branche_haute():
    """Le delta PA d'un call a un maximum ; l'inversion renvoie la branche K >= K*, et refuse une cible trop haute."""
    F = gk.forward(S, T, RD, RF)
    Ks = F * np.exp(np.linspace(-0.3, 0.3, 4001))
    d = delta("forward_pa", S, Ks, T, RD, RF, SIG, 1)
    i = int(np.argmax(d))
    assert 0 < i < len(Ks) - 1                       # le maximum est bien intérieur : non monotone
    K25 = strike_depuis_delta("forward_pa", 0.25, S, T, RD, RF, SIG, 1)
    assert K25 >= Ks[i]                              # branche haute
    with pytest.raises(ValueError):
        strike_depuis_delta("forward_pa", d.max() + 0.01, S, T, RD, RF, SIG, 1)
    # le put PA est, lui, monotone
    dp = delta("forward_pa", S, Ks, T, RD, RF, SIG, -1)
    assert np.all(np.diff(dp) < 0)


def test_atm_dns_et_forward():
    F = gk.forward(S, T, RD, RF)
    assert strike_atm("forward", S, T, RD, RF, SIG) == pytest.approx(F)
    for type_atm, conv in [("dns", "spot"), ("dns", "forward"), ("dns_pa", "spot_pa"), ("dns_pa", "forward_pa")]:
        K = strike_atm(type_atm, S, T, RD, RF, SIG)
        somme = delta(conv, S, K, T, RD, RF, SIG, 1) + delta(conv, S, K, T, RD, RF, SIG, -1)
        assert abs(somme) < 1e-14, (type_atm, conv)


# ---------------------------------------------------------------- (e) le smile VV passe par les 3 pivots
@pytest.mark.parametrize("conv,type_atm", [("spot", "dns"), ("forward", "forward"), ("spot_pa", "dns_pa")])
def test_vv_repasse_par_les_pivots(conv, type_atm):
    sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.01, 0.0025, conv=conv, type_atm=type_atm)
    assert sm.K[0] < sm.K[1] < sm.K[2]
    assert np.allclose(sm.vol(sm.K), sm.vols, atol=1e-9)
    assert np.allclose(sm.vol_cm(sm.K), sm.vols, atol=1e-9)                  # CM aussi exact aux pivots
    for k, v in zip(sm.K, sm.vols):                                          # les pivots ont bien le delta voulu
        phi = 1 if k == sm.K[2] else -1
        if k != sm.K[1]:
            assert delta(conv, 1.10, k, 1 / 12, 0.04, 0.02, v, phi) == pytest.approx(phi * 0.25, abs=1e-9)


def test_vv_premier_ordre_proche_de_exact():
    sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.01, 0.0025)
    K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 30)
    ecart = np.abs(sm.vol_cm(K) - sm.vol(K))
    assert ecart.max() < 2e-3                    # < 0,2 point de vol sur [K_25P -3 %, K_25C +3 %]


# ---------------------------------------------------------------- (f) Monte Carlo à moins de 3 erreurs-types
@pytest.mark.parametrize("phi", [1, -1])
@pytest.mark.parametrize("K", [1.05, 1.10, 1.1055, 1.15])
def test_monte_carlo_vs_gk(K, phi):
    ST = gbm_terminal(S, RD, SIG, T, 400_000, q=RF, graine=7, antithetique=True)
    mc, es = prix_mc(ST, K, T, RD, phi)
    assert abs(mc - gk.prix(S, K, T, RD, RF, SIG, phi)) < 3 * es


# ---------------------------------------------------------------- (g) arbitrage papillon
def test_pas_d_arbitrage_papillon_cotations_raisonnables():
    sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.01, 0.0025)
    K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 80)
    assert sm.densite(K).min() > -1e-8           # densité >= 0 (au bruit numérique près)


def test_arbitrage_papillon_cas_extreme_documente():
    """RR et BF démesurés pour 1M (RR -3, BF 1,5 sur ATM 7) : VV extrapole mal, la densité devient négative."""
    sm = SmileVV(1.10, 1 / 12, 0.04, 0.02, 0.07, -0.03, 0.015)
    K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 80)
    assert sm.densite(K).min() < -0.1
