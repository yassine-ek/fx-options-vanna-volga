# results/ : sorties

Les chiffres du README de la racine sont lus ici. **Les cotations de l'exemple sont illustratives, pas des données de marché.**

| Fichier | Produit par | Contenu |
|---|---|---|
| `exemple_eurusd_1m.json` | `scripts/run_exemple.py` | Entrées (spot, taux, ATM, RR25, BF25), forward, vols et strikes pivots, strike 25D par convention, écart CM contre exact, densité minimale, vols aux bornes. |
| `validation.json` | `scripts/generer_vitrine_06.py` | Toutes les erreurs mesurées : prix GK contre Black-Scholes sur le spot et Monte Carlo (8 cas), parité, grecques contre différences finies, aller-retour des 4 conventions de delta, DNS, pivots du smile, écart CM, densité (raisonnable et cas extrême). |
| `variantes_conventions.json` | `scripts/generer_vitrine_06.py` | Pour chaque convention de delta : strikes et vols pivots, vol aux strikes fixes pour les 3 méthodes (vanna-volga exact, CM, vol plate), écarts, densité minimale, écart de vol à la convention spot sur une grille de strikes. |
