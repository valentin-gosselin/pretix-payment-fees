# Makefile pour gérer les traductions du plugin pretix-payment-fees

.PHONY: help init extract compile update clean docker-extract docker-compile

# Variables
PLUGIN_NAME = pretix_payment_fees
LOCALE_DIR = $(PLUGIN_NAME)/locale
DOCKER_CONTAINER = pretix-dev
LANGUAGES = fr en de es nl it pt pl

# Cible par défaut
help:
	@echo "Commandes disponibles pour gérer les traductions:"
	@echo ""
	@echo "  make init       - Initialiser la structure locale"
	@echo "  make extract    - Extraire les chaînes traduisibles"
	@echo "  make compile    - Compiler les traductions"
	@echo "  make update     - Tout mettre à jour (extract + compile)"
	@echo "  make clean      - Nettoyer les fichiers compilés"
	@echo ""
	@echo "Commandes Docker (recommandées):"
	@echo "  make docker-extract - Extraire via Docker"
	@echo "  make docker-compile - Compiler via Docker"
	@echo ""
	@echo "Langues configurées: $(LANGUAGES)"

# Initialiser la structure locale
init:
	@echo "📁 Création de la structure locale..."
	@mkdir -p $(LOCALE_DIR)
	@for lang in $(LANGUAGES); do \
		mkdir -p $(LOCALE_DIR)/$$lang/LC_MESSAGES; \
		echo "  ✓ Créé $$lang/LC_MESSAGES"; \
	done
	@echo "✅ Structure locale initialisée!"

# Extraire les messages (local)
extract: init
	@echo "🔍 Extraction des messages traduisibles..."
	@for lang in $(LANGUAGES); do \
		echo "  → Extraction pour $$lang..."; \
		cd $(CURDIR) && python -m django makemessages \
			--locale=$$lang \
			--domain=django \
			--extension=py,html \
			--ignore="*.pyc" \
			--ignore="build/*" \
			--ignore="dist/*" \
			--no-wrap \
			--keep-pot \
			2>/dev/null || echo "  ⚠ Échec pour $$lang"; \
	done
	@echo "✅ Extraction terminée!"

# Compiler les messages (local)
compile:
	@echo "⚙️  Compilation des traductions..."
	@for lang in $(LANGUAGES); do \
		if [ -f $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po ]; then \
			echo "  → Compilation de $$lang..."; \
			cd $(CURDIR) && python -m django compilemessages --locale=$$lang 2>/dev/null || echo "  ⚠ Échec pour $$lang"; \
		fi \
	done
	@echo "✅ Compilation terminée!"

# Extraire via Docker (recommandé)
docker-extract: init
	@echo "🐳 Extraction des messages via Docker..."
	@# Copier le plugin dans le conteneur
	@docker cp $(CURDIR) $(DOCKER_CONTAINER):/tmp/pretix-payment-fees
	@# Extraire pour chaque langue
	@for lang in $(LANGUAGES); do \
		echo "  → Extraction pour $$lang..."; \
		docker exec -w /tmp/pretix-payment-fees $(DOCKER_CONTAINER) \
			python -m pretix makemessages \
			--locale=$$lang \
			--domain=django \
			--extension=py,html \
			--no-wrap \
			2>/dev/null || echo "  ⚠ Création fichier vide pour $$lang"; \
	done
	@# Récupérer les fichiers générés
	@docker cp $(DOCKER_CONTAINER):/tmp/pretix-payment-fees/$(LOCALE_DIR) $(CURDIR)/$(PLUGIN_NAME)/
	@echo "✅ Extraction Docker terminée!"

# Compiler via Docker (recommandé)
docker-compile:
	@echo "🐳 Compilation des traductions via Docker..."
	@# Copier le plugin dans le conteneur
	@docker cp $(CURDIR) $(DOCKER_CONTAINER):/tmp/pretix-payment-fees
	@# Compiler chaque langue
	@docker exec -w /tmp/pretix-payment-fees $(DOCKER_CONTAINER) \
		python -m pretix compilemessages 2>/dev/null || echo "  ⚠ Erreur de compilation"
	@# Récupérer les fichiers compilés
	@docker cp $(DOCKER_CONTAINER):/tmp/pretix-payment-fees/$(LOCALE_DIR) $(CURDIR)/$(PLUGIN_NAME)/
	@echo "✅ Compilation Docker terminée!"

# Mise à jour complète
update: docker-extract docker-compile
	@echo "🎉 Mise à jour complète terminée!"
	@echo ""
	@echo "📊 Statistiques des traductions:"
	@for lang in $(LANGUAGES); do \
		if [ -f $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po ]; then \
			total=$$(grep -c "^msgid " $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po 2>/dev/null || echo "0"); \
			echo "  $$lang: $$total chaînes"; \
		fi \
	done

# Nettoyer les fichiers compilés
clean:
	@echo "🧹 Nettoyage des fichiers compilés..."
	@find $(LOCALE_DIR) -name "*.mo" -delete
	@find $(LOCALE_DIR) -name "*~" -delete
	@echo "✅ Nettoyage terminé!"

# Statistiques des traductions
stats:
	@echo "📊 Statistiques des traductions:"
	@for lang in $(LANGUAGES); do \
		if [ -f $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po ]; then \
			total=$$(grep -c "^msgid " $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po 2>/dev/null || echo "0"); \
			translated=$$(grep -B1 "^msgstr \"[^\"]\+" $(LOCALE_DIR)/$$lang/LC_MESSAGES/django.po | grep -c "^msgid " 2>/dev/null || echo "0"); \
			percent=$$((translated * 100 / total)); \
			printf "  %-5s: %3d/%3d (%3d%%)\n" $$lang $$translated $$total $$percent; \
		else \
			printf "  %-5s: Fichier manquant\n" $$lang; \
		fi \
	done