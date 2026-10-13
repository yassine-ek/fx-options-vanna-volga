"""Monte Carlo minimal pour valider les prix Garman-Kohlhagen.

Copie réduite de `gbm_exact` du laboratoire Monte Carlo du même auteur (projet 01, `mclab/modeles.py`,
MIT). Le projet 06 étant un dépôt autonome, on ne dépend pas de `mclab` : seule la brique utile ici est
reprise (GBM, schéma exact, variables antithétiques, un seul pas de temps jusqu'à l'échéance).
"""
import numpy as np


def gbm_terminal(S0, r, sigma, T, n_chemins, q=0.0, graine=None, antithetique=True):
    """S_T d'un GBM risque-neutre : ln S_T = ln S0 + (r - q - sigma^2/2) T + sigma sqrt(T) Z (schéma exact).

    Pour un taux domestique r et un taux étranger q (FX), la dérive est r - q. Avec `antithetique=True`,
    le résultat est rangé [S_T ; S_T miroir] (n_chemins pair) : la deuxième moitié utilise -Z.
    """
    rng = np.random.default_rng(graine)
    if antithetique:
        if n_chemins % 2:
            raise ValueError("antithetique=True demande un n_chemins pair")
        Z = rng.standard_normal(n_chemins // 2)
        Z = np.concatenate([Z, -Z])
    else:
        Z = rng.standard_normal(n_chemins)
    return S0 * np.exp((r - q - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)


def prix_mc(ST, K, T, rd, phi=1):
    """Prix Monte Carlo d'une option européenne et son erreur-type, pour des S_T antithétiques.

    L'erreur-type se calcule sur les paires (S_T, miroir) moyennées : ce sont elles qui sont indépendantes.
    """
    pay = np.exp(-rd * T) * np.maximum(phi * (ST - K), 0.0)
    paires = 0.5 * (pay[: len(pay) // 2] + pay[len(pay) // 2:])
    return float(paires.mean()), float(paires.std(ddof=1) / np.sqrt(len(paires)))
