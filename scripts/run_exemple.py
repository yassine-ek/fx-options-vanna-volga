"""Exemple chiffré EURUSD 1M. COTATIONS ILLUSTRATIVES, PAS DES DONNÉES DE MARCHÉ (aucune donnée de vol dans le dépôt).

Produit results/exemple_eurusd_1m.json et figures/smile_vv.png.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fxopt import garman_kohlhagen as gk
from fxopt.deltas import CONVENTIONS, strike_depuis_delta
from fxopt.vanna_volga import SmileVV

# --- cotations illustratives (hypothèses, pas du marché)
S, T, RD, RF = 1.0800, 1 / 12, 0.0450, 0.0250      # rd = USD, rf = EUR
ATM, RR, BF = 0.0700, -0.0040, 0.0020              # 7,00 % ; RR25 = -0,40 pt ; BF25 = 0,20 pt

sm = SmileVV(S, T, RD, RF, ATM, RR, BF, conv="spot", type_atm="dns")
F = float(gk.forward(S, T, RD, RF))

# strike 25D call / put selon les 4 conventions (même vol 7 % pour isoler l'effet de convention)
conv = {c: {"K_25C": float(strike_depuis_delta(c, 0.25, S, T, RD, RF, ATM, 1)),
            "K_25P": float(strike_depuis_delta(c, -0.25, S, T, RD, RF, ATM, -1))} for c in CONVENTIONS}

K = np.linspace(sm.K[0] * 0.97, sm.K[2] * 1.03, 200)
vol_vv, vol_cm = sm.vol(K), sm.vol_cm(K)
delta_k = gk.grecques(S, K, T, RD, RF, vol_vv)["delta_spot"]          # delta call spot sur le smile

dens = sm.densite(K)
res = {
    "avertissement": "Cotations illustratives, PAS des données de marché.",
    "entrees": {"S": S, "T_ans": T, "rd": RD, "rf": RF, "ATM": ATM, "RR25": RR, "BF25": BF,
                "convention_delta": "spot", "ATM_type": "DNS"},
    "forward": F,
    "vols_pivots": {"25P": sm.vols[0], "ATM": sm.vols[1], "25C": sm.vols[2]},
    "strikes_pivots": {"K_25P": sm.K[0], "K_ATM_DNS": sm.K[1], "K_25C": sm.K[2]},
    "strikes_25D_par_convention_vol_ATM": conv,
    "ecart_max_CM_vs_exact_vol_points": float(np.max(np.abs(vol_cm - vol_vv)) * 100),
    "densite_implicite_min": float(dens.min()),
    "vol_vv_aux_extremes": {"K_min": float(K[0]), "vol": float(vol_vv[0]), "K_max": float(K[-1]), "vol": float(vol_vv[-1])},
}
res["vol_vv_aux_extremes"] = {"K_min": float(K[0]), "vol_K_min": float(vol_vv[0]),
                              "K_max": float(K[-1]), "vol_K_max": float(vol_vv[-1])}
for cle in ("vols_pivots", "strikes_pivots"):
    res[cle] = {k: float(v) for k, v in res[cle].items()}
(RACINE / "results").mkdir(exist_ok=True)
(RACINE / "results" / "exemple_eurusd_1m.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

# --- figure
fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
ax[0].plot(K, vol_vv * 100, label="vanna-volga exact")
ax[0].plot(K, vol_cm * 100, "--", label="Castagna-Mercurio 1er ordre")
ax[0].scatter(sm.K, sm.vols * 100, c="k", zorder=3, label="pivots 25P / ATM / 25C")
ax[0].set_xlabel("strike K"); ax[0].set_ylabel("vol implicite (%)"); ax[0].set_title("Smile vs strike")
ax[1].plot(delta_k, vol_vv * 100)
ax[1].scatter([0.75, 0.50, 0.25], sm.vols * 100, c="k", zorder=3)   # delta call spot ~ 0.75 (25P), ~0.5, 0.25
ax[1].set_xlabel("delta call spot"); ax[1].set_title("Smile vs delta"); ax[1].invert_xaxis()
for a in ax:
    a.grid(alpha=.3)
ax[0].legend()
fig.suptitle("EURUSD 1M, cotations ILLUSTRATIVES (pas des données de marché)", fontsize=10)
fig.tight_layout()
(RACINE / "figures").mkdir(exist_ok=True)
fig.savefig(RACINE / "figures" / "smile_vv.png", dpi=130)
print(json.dumps(res, indent=2, ensure_ascii=False))
