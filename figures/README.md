# figures/ : une ligne par image

PNG en 130 dpi. Toutes les cotations sont **illustratives, pas des données de marché**. Chaque image est commentée (« Comment lire ce graphique ») dans le README de la racine.

| Image | Ce qu'elle montre | Script |
|---|---|---|
| `hero_smile.png` | Figure héro : smile vanna-volga exact et approximation CM contre les trois points de cotation, contre le strike et contre le delta ; vol plate en référence. | `scripts/generer_vitrine_06.py` |
| `validation_erreurs.png` | Erreur mesurée de chaque vérification (barre) contre la tolérance du test (trait rouge), échelle log. | `scripts/generer_vitrine_06.py` |
| `variantes_conventions.png` | Effet de la convention de delta : écart des strikes 25D (pips) et écart de vol vanna-volga (points de base) par rapport à la convention spot. | `scripts/generer_vitrine_06.py` |
| `smile_vv.png` | Figure historique de l'exemple : smile contre le strike et contre le delta call spot, pivots en noir. | `scripts/run_exemple.py` |
