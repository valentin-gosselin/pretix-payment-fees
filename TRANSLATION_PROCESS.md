# Processus de Traduction Optimal

## Principe
Utiliser le **français comme langue source de référence** (100% complète et vérifiée) pour traduire vers les autres langues, garantissant ainsi une qualité maximale.

## Étape 1 : Extraction des paires FR

```python
# extract_fr_translations.py
import re

def extract_french_pairs():
    """Extrait toutes les paires msgid/msgstr du français"""
    with open('pretix_payment_fees/locale/fr/LC_MESSAGES/django.po', 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'msgid "([^"]+)"\nmsgstr "([^"]*)"'
    matches = re.findall(pattern, content, re.MULTILINE)

    # Créer un dictionnaire anglais -> français
    fr_dict = {}
    for msgid, msgstr in matches:
        if msgid and msgstr and msgid != msgstr:
            fr_dict[msgid] = msgstr

    return fr_dict
```

## Étape 2 : Traduire FR → Langue cible

```python
def translate_fr_to_target(fr_text, target_lang):
    """
    Traduit du français vers la langue cible

    Args:
        fr_text: Texte en français
        target_lang: 'de', 'es', 'nl', 'it', 'pt', 'pl'

    Returns:
        Texte traduit
    """

    # Dictionnaire de traductions manuelles FR → Cible
    # À compléter pour chaque langue

    translations = {
        'de': {
            # Termes techniques
            'Frais bancaires': 'Bankgebühren',
            'Synchronisation': 'Synchronisation',
            'Configuration': 'Konfiguration',
            'Exporter': 'Exportieren',
            # ... (compléter avec toutes les traductions)
        },
        'es': {
            'Frais bancaires': 'Comisiones bancarias',
            'Synchronisation': 'Sincronización',
            'Configuration': 'Configuración',
            'Exporter': 'Exportar',
        },
        # ... autres langues
    }

    return translations.get(target_lang, {}).get(fr_text, fr_text)
```

## Étape 3 : Générer le fichier .po cible

```python
def generate_po_from_french(target_lang):
    """Génère un fichier .po pour la langue cible à partir du français"""

    # 1. Lire le template FR
    fr_pairs = extract_french_pairs()

    # 2. Traduire chaque paire
    target_pairs = {}
    for en_msgid, fr_msgstr in fr_pairs.items():
        # Traduire le français vers la langue cible
        target_msgstr = translate_fr_to_target(fr_msgstr, target_lang)
        target_pairs[en_msgid] = target_msgstr

    # 3. Lire le template .po existant
    template_path = f'pretix_payment_fees/locale/{target_lang}/LC_MESSAGES/django.po'
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # 4. Remplacer les msgstr
    for msgid, msgstr in target_pairs.items():
        # Échapper les caractères spéciaux
        msgid_escaped = re.escape(msgid)
        pattern = f'msgid "{msgid_escaped}"\\nmsgstr "[^"]*"'
        replacement = f'msgid "{msgid}"\\nmsgstr "{msgstr}"'
        template = re.sub(pattern, replacement, template)

    # 5. Sauvegarder
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(template)

    print(f"✅ {target_lang.upper()} généré avec succès")
```

## Étape 4 : Workflow complet

```bash
#!/bin/bash
# retranslate_from_french.sh

LANG=$1  # de, es, nl, it, pt, pl

echo "🔄 Re-traduction ${LANG} depuis le français..."

# 1. Extraire le français
python3 extract_fr_translations.py > /tmp/fr_strings.json

# 2. Traduire vers la langue cible
python3 translate_to_${LANG}.py

# 3. Compiler
msgfmt -o pretix_payment_fees/locale/${LANG}/LC_MESSAGES/django.mo \
       pretix_payment_fees/locale/${LANG}/LC_MESSAGES/django.po

# 4. Vérifier
echo "📊 Vérification ${LANG}:"
python3 verify_translation.py ${LANG}

echo "✅ ${LANG} terminé"
```

## Étape 5 : Vérification qualité

```python
def verify_translation(lang):
    """Vérifie qu'aucune string n'est identique à l'anglais"""

    with open(f'pretix_payment_fees/locale/{lang}/LC_MESSAGES/django.po', 'r') as f:
        content = f.read()

    pattern = r'msgid "([^"]+)"\nmsgstr "([^"]*)"'
    matches = re.findall(pattern, content)

    # Exclusions (noms propres, termes techniques)
    exclusions = ['Mollie', 'SumUp', 'OAuth', 'Gosselico', 'Status', 'EUR', 'PDF']

    untranslated = []
    for msgid, msgstr in matches:
        if msgid and msgid == msgstr and msgid not in exclusions:
            untranslated.append(msgid)

    if untranslated:
        print(f"⚠️  {lang.upper()}: {len(untranslated)} strings non traduites")
        for msg in untranslated[:10]:
            print(f"  - {msg}")
        return False
    else:
        print(f"✅ {lang.upper()}: 100% traduit ({len(matches)} strings)")
        return True
```

## Exemple d'utilisation

```bash
# Re-traduire l'allemand depuis le français
./retranslate_from_french.sh de

# Vérifier toutes les langues
for lang in de es nl it pt pl; do
    python3 verify_translation.py $lang
done
```

## Avantages de cette méthode

✅ **Source unique** : Le français sert de référence (100% vérifié)
✅ **Cohérence** : Même processus pour toutes les langues
✅ **Qualité** : Pas de copier-coller entre langues
✅ **Vérifiable** : Script de vérification automatique
✅ **Répétable** : Processus documenté et scriptable
✅ **Maintenance** : Ajout de nouvelles strings facile

## Structure des fichiers

```
pretix-payment-fees/
├── translation_tools/
│   ├── extract_fr_translations.py
│   ├── translate_to_de.py
│   ├── translate_to_es.py
│   ├── translate_to_nl.py
│   ├── translate_to_it.py
│   ├── translate_to_pt.py
│   ├── translate_to_pl.py
│   ├── verify_translation.py
│   └── retranslate_all.sh
└── pretix_payment_fees/
    └── locale/
        ├── fr/ (SOURCE DE RÉFÉRENCE)
        ├── de/
        ├── es/
        ├── nl/
        ├── it/
        ├── pt/
        └── pl/
```

## Notes importantes

1. **Ne jamais modifier le français directement** - C'est la source de vérité
2. **Utiliser des traducteurs natifs** pour valider les traductions automatiques
3. **Conserver les termes techniques** en anglais quand approprié (OAuth, API, etc.)
4. **Vérifier le contexte** : certaines traductions dépendent du contexte d'utilisation
5. **Pluriels** : Respecter les règles de pluriel de chaque langue (voir Plural-Forms dans l'en-tête)
