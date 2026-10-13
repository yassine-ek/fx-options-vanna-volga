# scripts/ : exemple et génération des tableaux

À lancer depuis la racine du dépôt. Aucune donnée externe : **cotations EURUSD 1M illustratives, pas des données de marché.**

| Fichier | Rôle | Produit |
|---|---|---|
| `run_exemple.py` | Exemple chiffré EURUSD 1M : forward, vols et strikes pivots, strike 25D selon les 4 conventions, écart entre l'approximation CM et le vanna-volga exact, densité implicite minimale, smile contre le strike et contre le delta. | `results/exemple_eurusd_1m.json`, `figures/smile_vv.png` |
| `generer_vitrine_06.py` | Recalcule toutes les vérifications avec leurs erreurs (prix contre Black-Scholes sur le spot et Monte Carlo, parité, grecques, conventions de delta, smile), les **variantes** (4 conventions de delta × 3 méthodes), trace les figures, et réécrit les blocs de tableaux du `README.md` entre les marqueurs `<!-- BEGIN:nom -->` et `<!-- END:nom -->`. Lit `results/exemple_eurusd_1m.json` et `results/pytest_resultat.txt`. | `results/validation.json`, `results/variantes_conventions.json`, `figures/hero_smile.png`, `variantes_conventions.png`, `validation_erreurs.png`, blocs du README |
