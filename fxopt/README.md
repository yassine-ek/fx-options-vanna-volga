# fxopt/ : le paquet

Options FX européennes. Les fonctions acceptent des tableaux numpy. Convention de paire FOR/DOM (EURUSD : étranger = EUR, domestique = USD) ; les prix sont en monnaie domestique pour une unité de notionnel étranger.

| Fichier | Contenu |
|---|---|
| `__init__.py` | Docstring et version du paquet. |
| `garman_kohlhagen.py` | Forward par parité des taux, `d1` / `d2`, prix call / put, écart de parité, grecques analytiques (delta spot, delta forward, gamma, vega, vanna, volga), vol implicite par `brentq`. |
| `deltas.py` | Les 4 conventions de delta (`spot`, `forward`, `spot_pa`, `forward_pa`), conversion **delta → strike** (fermée en non ajusté ; numérique sur la branche des strikes élevés en premium-adjusted, car le delta d'un call PA n'est pas monotone), strike ATM (forward, DNS, DNS premium-adjusted). |
| `vanna_volga.py` | `SmileVV` : pivots 25P / ATM / 25C depuis ATM / RR25 / BF25, poids vanna-volga (système 3x3 vega / vanna / volga), prix, vol implicite exacte, approximation du premier ordre de Castagna-Mercurio, densité implicite (test d'arbitrage papillon). `strangle_de_marche`, `bf_smile_depuis_marche` et `SmileVV.depuis_marche` convertissent un butterfly de marché (broker fly, strangle à vol unique) en BF smile. |
| `monte_carlo.py` | Copie minimale (GBM exact à un pas, variables antithétiques, prix et erreur-type) du moteur du dépôt monte-carlo-pricing-risk-lab du même auteur : sert uniquement à valider les prix GK. |
