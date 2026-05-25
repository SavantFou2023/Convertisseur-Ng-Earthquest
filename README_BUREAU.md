# Convertisseur Schematic EarthQuest / NationsGlory

## Site web local

Double-clique sur:

```text
ouvrir_site.bat
```

Ou ouvre directement:

```text
index.html
```

Le site fonctionne hors ligne dans le navigateur. Il permet de choisir un fichier
`.schematic`, le pack source, le pack cible, puis il genere un fichier converti.

## Convertisseur Python

Le script en ligne de commande reste disponible:

```powershell
python .\schematic_converter.py "C:\chemin\build.schematic" --from nationsglory --to earthquest
```

## Donnees incluses

- `earthquest_block_ids.csv`
- `nationsglory_block_ids.csv`
- `nationsglory_to_earthquest_map.csv`
- `earthquest_to_nationsglory_map.csv`

Les blocs sans correspondance exacte sont gardes tels quels par defaut.
