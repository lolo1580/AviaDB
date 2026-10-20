# Journal des modifications

Toutes les évolutions notables de ce projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [0.2.0] — 2026-10-20

### Ajouté

- **Statistiques enrichies** : valeur par classe, par emplacement et par année,
  plus-values / moins-values, meilleures progressions et pertes ; carte
  « plus-value » dans la collection. Les objets **recherchés** et en
  **précommande** sont exclus des valeurs (ils restent dans les effectifs).
- **Précommande** : statut `PREORDER`, champs dédiés (date de sortie prévue,
  boutique/fournisseur, acompte versé), section dans le formulaire, export/import.
- **Rapports PDF** : inventaire complet (totaux + liste) et fiche objet (photo,
  caractéristiques, liens, historique de prix).
- **Journal d'activité (audit)** : écritures tracées (compte, méthode, route,
  code de retour), onglet **Administration → Journal**, élagage borné
  (`ACTIVITY_KEEP`).
- **Étiquettes QR** imprimables (`/etiquettes`), avec lien profond
  `/?item=<id>` qui rouvre la fiche de l'objet.
- **Alertes de budget** sur les souhaits (badge sur la carte + notification,
  sans doublon par objet et par relevé).
- **Export Excel** multi-feuilles : **Collection**, **Souhaits**,
  **Précommandes** et **Synthèse** (en-têtes français, dates et montants typés,
  filtres, volets figés). Le CSV technique reste le format d'import.
- **Images** : rotation 90° et recadrage manuel, dédoublonnage global
  (SHA-256 + empreinte perceptuelle dHash), vignettes générées à la volée
  (`?w=`), nettoyage périodique des fichiers orphelins, retrait automatique des
  anciennes vignettes `_thumb.webp`.
- **Migrations Alembic** : schéma versionné, application automatique au
  démarrage, adoption d'une base existante par estampillage de la révision de
  référence.
- **Sauvegardes planifiées** : service Compose `backup` (archive ZIP complète,
  rétention `BACKUP_KEEP`).
- **Qualité** : tests Vitest (composables et composants), tests E2E Playwright,
  couverture, Ruff, ESLint/Prettier, CI à trois jobs.
- **Documentation** : README complété (images, migrations, exports, proxy TLS).

### Modifié

- Le backend s'exécute en **utilisateur non privilégié** (UID/GID 1000) : le
  point d'entrée rend la propriété des volumes puis abandonne les privilèges.
- Le paquet frontend initial passe d'environ **517 ko à 229 ko** : les vues
  lourdes (Chart.js, qrcode, administration) sont chargées à la demande.
- L'export CSV est complété (colonnes de précommande) et reste destiné au
  ré-import ; l'Excel est le format recommandé pour la lecture.
- HTTPS est délégué à un **proxy en amont** ; activer `ADMIN_COOKIE_SECURE=true`
  pour le cookie de session.

### Corrigé

- Échappement XML des noms d'objets dans le PDF (noms contenant `&` ou `<`).
- Séparateur de milliers du PDF compatible avec l'encodage WinAnsi (montants
  supérieurs ou égaux à 1 000).
- Élagage du journal d'activité : une entrée de trop était conservée.
- `isTempId()` ne reconnaissait pas les identifiants à préfixe (`item-…`).
- Le champ « nouvelle classe racine » était ignoré par le bouton d'ajout.
- Page d'administration vide pour un compte lecteur sur un onglet réservé.
- Les détails par emplacement/objet des statistiques restent réservés à la
  session (jamais exposés par l'API publique).

### Technique

- Backend : **136 tests** pytest, Ruff, migrations Alembic vérifiées en CI.
- Frontend : **49 tests** Vitest, ESLint, build, tests E2E Playwright.
- Nouvelles dépendances : `reportlab`, `openpyxl`, `alembic`, `qrcode`.

## [0.1.0] — 2026-10-17

- Version initiale : CRUD des objets, photos WebP, statistiques, devises et taux,
  sauvegarde/restauration, administration, API publique par clé.
