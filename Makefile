# Makefile du plugin pretix-payment-fees
# - Traductions (cibles historiques)
# - Build et déploiement reproductible (build / deploy / test)

.PHONY: help init extract compile update clean docker-extract docker-compile \
        build deploy deploy-dev test test-docker version

# Variables
PLUGIN_NAME = pretix_payment_fees
LOCALE_DIR = $(PLUGIN_NAME)/locale
DOCKER_CONTAINER ?= pretix-dev
LANGUAGES = fr en de es nl it pt pl

# Version lue depuis __init__.py (source de vérité)
VERSION := $(shell grep -E '^__version__' $(PLUGIN_NAME)/__init__.py | cut -d '"' -f 2)
WHEEL   := dist/$(PLUGIN_NAME)-$(VERSION)-py3-none-any.whl

# Cible par défaut
help:
	@echo "Plugin pretix-payment-fees v$(VERSION)"
	@echo ""
	@echo "Build & déploiement (reproductible):"
	@echo "  make build           - Construire la wheel dans dist/"
	@echo "  make deploy          - Build puis pip install --force-reinstall"
	@echo "                         dans le container \$$DOCKER_CONTAINER (=$(DOCKER_CONTAINER))"
	@echo "                         puis redémarrer le container"
	@echo "  make test-docker     - Lancer les tests unitaires dans le container"
	@echo "  make version         - Afficher la version courante"
	@echo ""
	@echo "Traductions:"
	@echo "  make init            - Initialiser la structure locale"
	@echo "  make extract         - Extraire les chaînes traduisibles"
	@echo "  make compile         - Compiler les traductions"
	@echo "  make update          - Tout mettre à jour (extract + compile)"
	@echo "  make clean           - Nettoyer les fichiers compilés"
	@echo "  make docker-extract  - Extraire via Docker"
	@echo "  make docker-compile  - Compiler via Docker"
	@echo ""
	@echo "Variables surchargeable: DOCKER_CONTAINER (défaut: pretix-dev)"
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

# -----------------------------------------------------------------------------
# Build & déploiement reproductible
# -----------------------------------------------------------------------------

version:
	@echo "$(VERSION)"

# Construit la wheel dans dist/.
# Utilise le Python du container Docker (qui a pretix + build installé),
# pour ne dépendre d'aucun Python hôte. Portable.
build:
	@echo "🔨 Build du plugin $(PLUGIN_NAME) v$(VERSION) via $(DOCKER_CONTAINER)..."
	@rm -rf build/ dist/*.whl dist/*.tar.gz $(PLUGIN_NAME).egg-info 2>/dev/null || true
	@mkdir -p dist
	@docker exec -u root $(DOCKER_CONTAINER) rm -rf /tmp/$(PLUGIN_NAME)-build
	@docker cp . $(DOCKER_CONTAINER):/tmp/$(PLUGIN_NAME)-build
	@# docker cp préserve l'uid hôte, on réaligne sur l'user du container.
	@CONTAINER_USER=$$(docker exec $(DOCKER_CONTAINER) id -un) ; \
	 docker exec -u root $(DOCKER_CONTAINER) \
		chown -R $$CONTAINER_USER:$$CONTAINER_USER /tmp/$(PLUGIN_NAME)-build
	@docker exec -w /tmp/$(PLUGIN_NAME)-build $(DOCKER_CONTAINER) sh -c '\
		rm -rf build dist *.egg-info ; \
		pip install --quiet --disable-pip-version-check build 2>/dev/null || true ; \
		if python -c "import build" 2>/dev/null ; then \
			python -m build --wheel --outdir dist/ . ; \
		else \
			python setup.py bdist_wheel --dist-dir dist/ ; \
		fi'
	@docker cp $(DOCKER_CONTAINER):/tmp/$(PLUGIN_NAME)-build/dist/. dist/
	@docker exec -u root $(DOCKER_CONTAINER) rm -rf /tmp/$(PLUGIN_NAME)-build
	@echo "✅ Wheel construite: $(WHEEL)"

# Déploie la version courante dans le container Docker cible.
# Utilisation:
#   make deploy                           # -> container pretix-dev
#   make deploy DOCKER_CONTAINER=pretix   # -> n'importe quel container pretix
deploy: build
	@echo "🚀 Déploiement de $(PLUGIN_NAME) v$(VERSION) dans $(DOCKER_CONTAINER)..."
	@docker cp $(WHEEL) $(DOCKER_CONTAINER):/tmp/$(notdir $(WHEEL))
	@# Installation en root pour écrire dans le site-packages système,
	@# sinon pip retombe sur ~/.local et Pretix ne voit pas la nouvelle version.
	@docker exec -u root $(DOCKER_CONTAINER) pip install --force-reinstall --no-deps \
		/tmp/$(notdir $(WHEEL))
	@docker exec -u root $(DOCKER_CONTAINER) rm -f /tmp/$(notdir $(WHEEL))
	@echo "🔄 Redémarrage du container $(DOCKER_CONTAINER)..."
	@docker restart $(DOCKER_CONTAINER) >/dev/null
	@echo "✅ $(PLUGIN_NAME) v$(VERSION) déployé et container redémarré"

# Alias explicite pour le dev local.
deploy-dev: deploy

# Lance les tests unitaires dans le container Pretix (qui a Django/pretix configurés).
# Les tests sont copiés depuis le source courant, pas depuis la wheel installée,
# pour pouvoir tester une version en cours de modification.
# Installe pytest à la volée s'il n'est pas présent (cas d'une image pretix vanilla).
test-docker:
	@echo "🧪 Tests unitaires dans $(DOCKER_CONTAINER)..."
	@docker cp $(PLUGIN_NAME)/tests $(DOCKER_CONTAINER):/tmp/pretix_payment_fees_tests
	@docker exec -u root $(DOCKER_CONTAINER) sh -c '\
		python -c "import pytest" 2>/dev/null || pip install --quiet pytest'
	@docker exec $(DOCKER_CONTAINER) \
		python -m pytest -x -v /tmp/pretix_payment_fees_tests/ \
		|| (echo "❌ Tests échoués" && exit 1)
	@echo "✅ Tests passés"

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