# Convertisseur de schematics EarthQuest / NationsGlory

Ce dossier contient `schematic_converter.py`, un convertisseur de fichiers `.schematic`
Minecraft 1.6/1.7.

## Utilisation

Convertir un schematic NationsGlory vers EarthQuest:

```powershell
python .\schematic_converter.py "C:\chemin\maison.schematic" --from nationsglory --to earthquest
```

Convertir un schematic EarthQuest vers NationsGlory:

```powershell
python .\schematic_converter.py "C:\chemin\maison.schematic" --from earthquest --to nationsglory
```

Si `--to` n'est pas donne, le script choisit automatiquement l'autre pack.

## Sortie

Par defaut, le fichier converti est cree a cote du schematic source:

```text
maison.converted-earthquest.schematic
maison.converted-earthquest.schematic.report.json
```

Le rapport JSON indique combien de blocs ont ete changes et quels blocs connus
n'ont pas eu de correspondance.

## Options utiles

Garder les blocs sans correspondance, comportement par defaut:

```powershell
python .\schematic_converter.py "maison.schematic" --from nationsglory --unmapped-known keep
```

Remplacer par de l'air les blocs connus du pack source mais sans correspondance:

```powershell
python .\schematic_converter.py "maison.schematic" --from nationsglory --unmapped-known air
```

Arreter la conversion si un bloc connu n'a pas de correspondance:

```powershell
python .\schematic_converter.py "maison.schematic" --from nationsglory --unmapped-known error
```

Afficher seulement les statistiques du mapping:

```powershell
python .\schematic_converter.py --from nationsglory --to earthquest --show-map
```

## Limites

- Le script convertit les IDs de blocs dans `Blocks`, `Data` et `AddBlocks`.
- Les items stockes dans les coffres ou autres TileEntities ne sont pas convertis.
- Les correspondances automatiques reposent sur les noms de blocs extraits dans:
  - `earthquest_block_ids.csv`
  - `nationsglory_block_ids.csv`
- Les blocs sans nom equivalent exact sont laisses intacts par defaut.
