# tests/ : 42 vérifications

Lancer depuis la racine du dépôt : `python -m pytest -q`. Dernière sortie : `results/pytest_resultat.txt`. Les erreurs mesurées contre les tolérances sont dans le README de la racine et dans `results/validation.json`.

| Fichier | Contenu |
|---|---|
| `test_options_fx.py` | Un seul fichier, sept familles : (a) GK = Black-Scholes-Merton écrit sur le spot, 5 strikes × call/put (10 tests) ; (b) parité call-put et call = put au forward (2) ; (c) grecques analytiques contre différences finies, 3 strikes × call/put (6) ; (d) aller-retour strike → delta → strike pour les 4 conventions × call/put, non-monotonie du call premium-adjusted, ATM DNS (10) ; (e) le smile vanna-volga repasse par les 3 pivots, pivots au delta 25, approximation CM proche de l'exact (4) ; (f) Monte Carlo contre GK à moins de 3 erreurs-types, 4 strikes × call/put (8) ; (g) densité implicite positive pour des cotations raisonnables, et cas extrême documenté où elle devient négative (2). |

Les tests Monte Carlo ont une graine fixe : avec une autre graine, un écart à 3 erreurs-types peut échouer rarement (probabilité d'environ 0,3 % par cas).
