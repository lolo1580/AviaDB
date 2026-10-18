# AviaDB

Gestion de collection aviation : maquettes diecast **et** patches, dans une seule
base. Backend **FastAPI + SQLAlchemy (PostgreSQL)**, frontend **Vue 3 + Vite +
Tailwind**, le tout orchestré par **Docker Compose**.

## Sommaire

- [Base de données](#base-de-données)
- [Démarrage rapide](#démarrage-rapide)
- [Développement local](#développement-local)
- [Architecture](#architecture)
- [Modèle de données](#modèle-de-données)
- [API](#api)
- [Accès & administration](#accès--administration)
- [Sauvegarde & échange de données](#sauvegarde--échange-de-données)
- [Devises & taux de change](#devises--taux-de-change)
- [Autres écrans](#autres-écrans)
- [Interface](#interface)
- [Modales réutilisables](#modales-réutilisables)
- [Réactivité de l'interface (mises à jour optimistes)](#réactivité-de-linterface-mises-à-jour-optimistes)
- [Thème clair / sombre](#thème-clair--sombre)
- [Variables d'environnement](#variables-denvironnement)
- [Tests](#tests)

## Base de données

L'application est adossée à **PostgreSQL** (18), via SQLAlchemy et le pilote
`psycopg`. L'URL est fournie par `DATABASE_URL` :

```
DATABASE_URL=postgresql+psycopg://aviadb:motdepasse@db:5432/aviadb      # compose
DATABASE_URL=postgresql+psycopg://aviadb:motdepasse@localhost:5434/aviadb
```

- Le service `db` (image `postgres:18-alpine`) publie **5434** côté hôte — 5432
  est souvent déjà pris par un PostgreSQL système, 5433 par un autre projet. En
  interne, le backend joint la base par `db:5432`.
- Les données vivent dans le volume Docker `aviadb-pgdata` ; `./data` ne contient
  plus que les images.
- Le pilote `psycopg` est fourni en binaire : aucune compilation, aucune
  dépendance système à installer.
- **Sauvegarde de la base** :

  ```bash
  docker exec aviadb-db pg_dump -U aviadb aviadb | gzip > aviadb-pg.sql.gz
  ```

## Démarrage rapide

```bash
cp .env.example .env      # puis renseignez ADMIN_PASSWORD et POSTGRES_PASSWORD
docker compose up -d --build
```

Le fichier `docker-compose.yml` démarre trois services : **db** (PostgreSQL 18),
**backend** (FastAPI) et **frontend** (Nginx qui sert la SPA et relaie `/api`).

- Interface : <http://localhost:8080>
- API (Swagger) : <http://localhost:8000/docs>
- PostgreSQL : `localhost:5434` (5432 est réservé au PostgreSQL du système)

Les objets et les comptes vivent dans le volume Docker `aviadb-pgdata` ; les images
WebP sont dans `./data/uploads`. Les deux survivent à `docker compose down`.

```bash
docker compose down          # arrêter
docker compose up -d --build # reconstruire après modification
docker compose logs -f backend
```

### Réseau hôte (optionnel)

Pour exposer l'application directement sur la pile réseau de la machine, sans
publication de ports :

```bash
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d --build
```

- Interface : `http://<ip-hote>/` (port **80**)
- API : `http://<ip-hote>:8000/` (Swagger sur `/docs`)

Nginx proxifie alors vers `127.0.0.1:8000` au lieu du DNS Compose (`BACKEND_URL`).
Les ports 80 et 8000 doivent être libres sur l'hôte.

## Développement local

PostgreSQL est le seul moteur : le plus simple est de lancer la base du compose,
puis le backend et le frontend à la main.

```bash
docker compose up -d db            # PostgreSQL sur le port 5434
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://aviadb:<motdepasse>@localhost:5434/aviadb
uvicorn app.main:app --reload      # http://localhost:8000
```

Les tables sont créées automatiquement au démarrage, les images vont dans
`./uploads/` (variable `UPLOAD_DIR`).

**Frontend** (depuis `frontend/`) :

```bash
npm install
npm run dev                        # http://localhost:5173
```

Vite proxifie `/api` et `/uploads` vers `http://localhost:8000`.

## Architecture

```
aviadb/
├── backend/
│   ├── app/
│   │   ├── database.py   # engine PostgreSQL, session, pool_pre_ping
│   │   ├── models.py     # tables SQLAlchemy
│   │   ├── schemas.py    # schémas Pydantic (entrées/sorties, gardes)
│   │   ├── crud.py       # création d'items + résolution des tags (partagé)
│   │   ├── currency.py   # devises, taux de change, conversions
│   │   ├── media.py      # upload, conversion WebP, vignettes
│   │   ├── auth.py       # comptes, rôles, jetons, require_admin
│   │   ├── admin.py      # bulk, import/export, comptes, tags, taux
│   │   ├── backup.py     # sauvegarde / restauration ZIP
│   │   ├── migrations.py # ajout idempotent des colonnes manquantes
│   │   └── main.py       # routes FastAPI
│   ├── tests/            # suite pytest (conftest.py, helpers.py, 7 modules)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── layout/       # navItems, icons (SVG inline), modalStack
│   │   ├── components/
│   │   │   ├── ui/       # AppModal, AppButton, ConfirmDialog, PromptDialog
│   │   │   ├── layout/   # AppShell, AppSidebar, AppTopbar, notifications, avatar
│   │   │   └── …         # LoginPanel, ThemeToggle, PhotoLightbox, StatsPanel, …
│   │   ├── views/        # Collection, Souhaits, Statistiques, Admin
│   │   ├── composables/  # useItemList, useConfirm, usePrompt, useFocusTrap…
│   │   ├── auth.js       # session et rôle
│   │   ├── settings.js   # devise de référence et taux
│   │   ├── optimistic.js # registre des opérations + helper optimiste
│   │   ├── toast.js      # notifications (rollback, « Réessayer »)
│   │   ├── notifications.js  # centre de notifications (cloche)
│   │   ├── ui.js         # état d'interface persistant (rail, vue grille/liste)
│   │   ├── theme.js      # thème clair/sombre (persistant)
│   │   ├── router.js     # /, /souhaits, /statistiques, /admin
│   │   └── api.js        # client REST
│   ├── nginx.conf.template  # SPA + proxy /api et /uploads (BACKEND_URL)
│   ├── Dockerfile        # multi-stage : build Vite → Nginx
│   └── package.json
├── .github/workflows/ci.yml  # intégration continue (pytest PostgreSQL, build)
├── .env.example          # modèle de configuration
├── data/                 # images uploadées (la base est dans le volume Docker)
├── docker-compose.yml    # db + backend + frontend
└── docker-compose.host.yml   # surcharge réseau hôte
```

## Modèle de données

Une table socle `items` décrit aussi bien un avion en métal qu'un écusson en tissu,
via des tables d'attributs spécifiques :

```
[items]
   ├── [diecast_details]   1-to-1 optionnel
   ├── [patch_details]     1-to-1 optionnel
   ├── [item_photos]       1-to-N
   └── [tags]              N-to-N (via item_tags)
```

`items` : `name`, `item_type` (DIECAST/PATCH/OTHER), `country`, `aircraft_model`,
`storage_location`, `status` (EXHIBITED/STORED_BOX/WANTED/TRANSIT),
`purchase_date`, `purchase_price`, `estimated_value`, `currency`,
`purchase_eur_value` (prix d'achat figé en EUR au taux du jour d'achat),
`purchase_rate_date`, `notes`, `created_at`, `updated_at`.

`diecast_details` : `scale`, `manufacturer`, `part_number`, `registration_number`,
`configuration`.

`patch_details` : `unit_squadron`, `base`, `material`, `attachment_type`, `shape`,
`event_or_mission`.

`item_photos` : `file_path`, `thumb_path`, `is_primary`, `caption`.

Les suppressions cascadent (détails, photos) et les fichiers images sont effacés du
disque avec l'objet.

## API

Toutes les routes sont préfixées par `/api`.

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/health` | état du service |
| GET | `/api/items` | lister (filtres, tri, pagination) → `{total, items}` |
| POST | `/api/items` | créer un objet (détails + tags) |
| GET | `/api/items/{item_id}` | détail |
| PATCH / PUT | `/api/items/{item_id}` | mise à jour partielle (fusion imbriquée) |
| DELETE | `/api/items/{item_id}` | supprimer (cascade + fichiers) |
| GET | `/api/items/{item_id}/photos` | photos d'un objet |
| POST | `/api/items/{item_id}/photos` | upload (`file`, `caption`, `is_primary`) |
| PATCH | `/api/photos/{photo_id}` | légende / photo principale |
| POST | `/api/photos/{photo_id}/primary` | désigner la photo principale |
| DELETE | `/api/photos/{photo_id}` | supprimer la photo + le fichier |
| GET | `/api/stats` | compteurs, valeurs, répartitions |
| GET | `/api/meta/facets` | valeurs distinctes pour les filtres |
| GET | `/api/meta/enums` | valeurs d'énumération |
| GET | `/api/tags` | vocabulaire de tags |
| GET | `/uploads/...` | images (statique) |
| POST | `/api/admin/login` | connexion (`username` + `password`) → cookie HttpOnly + token |
| POST | `/api/admin/logout` | déconnexion |
| GET | `/api/admin/session` | état de la session (rôle et identifiant inclus) |
| GET | `/api/meta/settings` | devise de référence, devises, taux courants |
| PUT | `/api/admin/settings` | changer la devise de référence *(ADMIN)* |
| PUT | `/api/admin/rates` | corriger les taux à la main *(ADMIN)* |
| POST | `/api/admin/rates/refresh` | récupérer les taux de la BCE *(ADMIN)* |
| POST | `/api/admin/bulk` | actions en masse : `delete`, `set_status`, `add_tags`, `remove_tags` |
| GET | `/api/admin/export` | export JSON complet |
| GET | `/api/admin/export.csv` | export CSV (tableur) |
| GET | `/api/admin/backup` | sauvegarde ZIP (JSON + toutes les images) |
| POST | `/api/admin/restore` | restauration ZIP (`mode=merge` ou `replace`) |
| POST | `/api/admin/import` | import JSON |
| POST | `/api/admin/import.csv` | import CSV (colonnes de l'export) |
| POST | `/api/items/{item_id}/photos/reorder` | réordonner les photos |
| GET | `/api/admin/users` | lister les comptes *(ADMIN)* |
| POST | `/api/admin/users` | créer un compte *(ADMIN)* |
| PATCH | `/api/admin/users/{user_id}` | rôle / mot de passe / activation *(ADMIN)* |
| DELETE | `/api/admin/users/{user_id}` | supprimer un compte *(ADMIN)* |
| PATCH | `/api/admin/tags/{tag_id}` | renommer un tag *(ADMIN)* |
| DELETE | `/api/admin/tags/{tag_id}` | supprimer un tag et ses associations *(ADMIN)* |

> Toutes les routes `/api/*` et les images `/uploads/*` exigent une session admin
> (cookie `HttpOnly` ou en-tête `Authorization: Bearer`). Seules restent publiques
> `/api/health`, `/api/admin/login` et `/api/admin/session` (nécessaires avant la
> connexion).

**Filtres de `/api/items`** (répétables = OR) : `q`, `item_type`, `status`,
`country`, `aircraft_model`, `storage_location`, `scale`, `manufacturer`, `tag`,
`value_min`, `value_max`, `sort` (`name`, `country`, `aircraft_model`, `status`,
`purchase_date`, `estimated_value`, `created_at`, `updated_at`), `order`
(`asc`/`desc`), `skip`, `limit`.

Exemple :

```
/api/items?q=tiger&item_type=PATCH&country=France&sort=estimated_value&order=desc
```

## Accès & administration

Principe : **accès protégé** — identifiant et mot de passe sont demandés dès
l'arrivée sur le site, avant même de voir la collection.

Deux rôles :

- **ADMIN** : lecture, écriture, import, gestion des comptes et des tags ;
- **VIEWER** : lecture seule (consultation, filtres, statistiques, export).

L'accès est protégé dès qu'un compte existe. `ADMIN_PASSWORD` crée le premier
compte administrateur au démarrage (identifiant `ADMIN_USERNAME`, `admin` par
défaut) ; ensuite, gérez les comptes depuis l'interface — le mot de passe
d'environnement n'est jamais réécrit.

Connexion : `http://<hote>/` — le formulaire s'affiche en premier.
Panneau d'administration : `http://<hote>/admin` (tableau, actions en masse,
tags, comptes, sauvegarde).

Authentification : mots de passe hachés en **PBKDF2-SHA256** (stdlib), jetons
**HMAC-SHA256** signés transmis en cookie `HttpOnly` ou en en-tête
`Authorization: Bearer`. Blocage temporaire après `ADMIN_MAX_FAILURES` échecs.

> En HTTP simple sur le réseau local, le mot de passe circule en clair. Pour un
> usage hors LAN, placez l'application derrière HTTPS et activez
> `ADMIN_COOKIE_SECURE=true`.

## Sauvegarde & échange de données

- **Sauvegarder (ZIP)** : archive contenant `aviadb.json` (objets, détails, tags,
  photos), **tous les réglages** (devise de référence, taux, cache des taux
  historiques), **les comptes** (empreintes PBKDF2, jamais de mot de passe en
  clair) et toutes les images. Un seul fichier à conserver — et le moyen
  portable de changer de moteur de base de données.
- **Restaurer (ZIP)** : l'interface propose **remplacer** la collection ou
  **fusionner** avec l'existant. Les comptes déjà présents ne sont jamais
  écrasés (on ne se verrouille pas dehors) ; les autres sont recréés.
- **Export / import JSON** et **export / import CSV** (colonnes identiques, donc
  aller-retour possible avec un tableur).
- **Sauvegarde au niveau PostgreSQL** :

  ```bash
  docker exec aviadb-db pg_dump -U aviadb aviadb | gzip > aviadb-pg.sql.gz
  ```

## Devises & taux de change

Chaque objet porte sa **devise** (`currency`, pré-remplie avec la devise par
défaut). La **devise de référence** — réglable dans l'administration — sert à
exprimer tous les totaux, graphiques et budgets.

- **Taux courants** : bouton « Actualiser depuis la BCE » (frankfurter.dev,
  données BCE, sans clé d'API). Les taux sont éditables à la main si besoin.
  Convention affichée : *nombre d'unités de la devise pour 1 EUR*.
- **Valeur estimée** : convertie aux taux courants.
- **Prix d'achat** : converti avec le **taux du jour de l'achat** (repli sur le
  dernier jour ouvré connu), puis figé en EUR sur l'objet. Les totaux d'achat ne
  bougent donc pas quand les taux évoluent, et changer la devise de référence ne
  fausse rien.
- Les objets créés avant cette fonctionnalité sont repris automatiquement au
  démarrage (devise de référence, équivalent EUR au taux courant).

```
1 EUR = 1,1253 USD   →  110 USD ≈ 97,75 €
Prix d'achat du 01/05/2024 en USD : taux du 30/04/2024 → figé
```

## Autres écrans

- **Souhaits** (`/souhaits`) : pièces au statut « Recherché », avec budget
  estimé cumulé et bouton « marquer comme acquis ».
- **Statistiques** (`/statistiques`) : graphiques (type, statut, pays, valeur par
  pays, acquisitions par année, échelle, matière des patchs) via Chart.js.

> La gestion des prêts a été retirée de l'interface. Le backend la conserve
> (colonnes `loaned_to`, `loan_date`, `loan_due_date`, filtre `has_loan`) : elle
> est donc réactivable sans migration.

## Interface

Le shell du dashboard est modulaire et réutilisable (`src/components/layout/`) :

- **`AppShell.vue`** — ossature : barre latérale + barre du haut + `<main>` avec
  un emplacement (`slot`). C'est le seul point à toucher pour ajouter une page.
- **`AppSidebar.vue`** — navigation latérale alimentée par `layout/navItems.js` :
  icônes SVG inline, **infobulles** Tailwind maison (`AppTooltip.vue`), repliable
  en rail d'icônes sur bureau, tiroir coulissant + voile sur mobile.
- **`AppTopbar.vue`** — titre et sous-titre issus de `meta` de la route, indicateur
  de synchronisation, **cloche de notifications** (badge non-lues, panneau
  déroulant) et **menu utilisateur** (avatar à initiales, rôle, déconnexion).
- **`AppNotifications.vue`** / **`AppUserMenu.vue`** — panneaux flottants, fermés
  au clic extérieur ou avec Échap (`composables/useClickOutside.js`).
- **`AppIcon.vue`** + **`layout/icons.js`** — jeu d'icônes SVG inline, aucune
  librairie externe.

Le **contenu principal** s'affiche en grille de cartes **ou** en liste compacte,
au choix (`ViewToggle.vue` + `ItemListRow.vue`) ; le mode, comme l'état replié de
la barre latérale, est mémorisé dans le navigateur (`src/ui.js`).

Tout est construit avec les seules classes utilitaires Tailwind — pas de
librairie de composants.

## Modales réutilisables

Un seul socle (`src/components/ui/`) porte toutes les fenêtres de l'application —
formulaires, fiches et confirmations.

- **`AppModal.vue`** — `<Teleport>` vers `body`, transitions fondu + glissement
  (désactivées si `prefers-reduced-motion`), tailles `sm → full`, emplacements
  `header` / `default` / `footer`, thème sombre, mode `bare` et fond `dark` pour
  la visionneuse photo.
- **`AppButton.vue`** — boutons de pied de modale (primary, secondary, danger,
  ghost) avec état de chargement.
- **`ConfirmDialog.vue`** + **`useConfirm.js`** — confirmations asynchrones :
  `if (await confirm({ title, message, danger: true })) …`, avec une troisième
  issue possible (`alternateLabel`) pour les choix à trois branches.
- **`PromptDialog.vue`** + **`usePrompt.js`** — saisie asynchrone :
  `const nom = await prompt({ title, label, value, minLength })`, avec validation
  (obligatoire, longueur, `validate()`) et focus automatique sur le champ.
  Toutes les boîtes natives du navigateur (`confirm` et `prompt`) ont été
  remplacées : plus aucune fenêtre non stylée.

Le contenu peut désigner l'élément à focaliser à l'ouverture avec
`data-autofocus` ; à défaut, le premier élément focalisable reçoit le focus.

Accessibilité : `role="dialog"`, `aria-modal`, `aria-labelledby` (titre) et
`aria-describedby` (sous-titre), bouton de fermeture `aria-label`, **piège de
focus** (Tab et Maj+Tab bouclent, `composables/useFocusTrap.js`), focus rendu à
l'élément déclencheur, verrouillage du défilement compensé
(`composables/useScrollLock.js`) et fermeture par `Échap` ou clic sur le fond.

Les modales empilées sont gérées par `layout/modalStack.js` : `Échap` ne ferme
que celle du dessus, le verrou de défilement n'est levé qu'à la fermeture dela
dernière, et les confirmations s'affichent au-dessus (`level="top"`).

## Réactivité de l'interface (mises à jour optimistes)

Toute action est appliquée **immédiatement** dans l'interface, puis confirmée par
le serveur. Si le serveur refuse, la modification est **annulée** et expliquée.

- **Mutation locale d'abord** : le changement est visible sans attendre le réseau
  (`src/optimistic.js`).
- **Rollback automatique** : l'état précédent est restauré si la requête échoue,
  avec un message clair (« *Suppression annulée — ...* ») et un bouton
  **Réessayer**.
- **Identifiants temporaires** : un objet créé reçoit un `id` local (`temp-…`),
  apparaît aussitôt avec un badge « envoi… », puis est remplacé par la réponse du
  serveur (`src/composables/useItemList.js`).
- **Indicateurs discrets** : pastille tournante sur la ligne / la carte concernée,
  opacité réduite pendant la synchronisation, et bandeau « Synchronisation… »
  dans l'en-tête dès qu'une opération est en cours.
- **Réconciliation en arrière-plan** : les statistiques et les facettes de filtre
  sont rafraîchies après coup, sans jamais bloquer l'interface.
- **Transitions** courtes à l'ajout et au retrait (`.card-*` dans `style.css`).

Périmètre couvert : créer / modifier / supprimer un objet, changement de statut,
actions groupées (suppression, statut, tags), photos (envoi avec aperçu local,
photo de couverture, légende, suppression, réordonnancement), comptes
utilisateurs et vocabulaire de tags.

> Les suppressions restent confirmées par une boîte de dialogue : les fichiers
> images sont effacés côté serveur, il n'y a donc pas d'annulation après coup.

## Thème clair / sombre

Un bouton (soleil / lune) dans l'en-tête — et sur l'écran de connexion — bascule
l'interface entre thème clair et sombre.

- Le choix est mémorisé dans le navigateur (`localStorage`).
- Au premier lancement, la préférence système (`prefers-color-scheme`) est utilisée.
- Un script inline dans `index.html` applique le thème avant le rendu, pour éviter
  tout flash de thème clair au chargement.
- Implémentation Tailwind v4 : variante `dark` pilotée par la classe `.dark` sur
  `<html>` (`@custom-variant dark` dans `src/style.css`).

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://aviadb:change-me@localhost:5434/aviadb` | URL PostgreSQL |
| `POSTGRES_PASSWORD` | `change-me` | mot de passe du conteneur `db` |
| `UPLOAD_DIR` | `./uploads` | dossier des images |
| `IMAGE_MAX_DIMENSION` | `1600` | taille max de l'image principale (px) |
| `IMAGE_THUMB_DIMENSION` | `480` | taille max de la vignette (px) |
| `IMAGE_WEBP_QUALITY` | `85` | qualité WebP de l'image principale |
| `IMAGE_THUMB_QUALITY` | `80` | qualité WebP de la vignette |
| `MAX_UPLOAD_BYTES` | `15728640` | taille max d'un upload (15 Mo) |
| `BACKEND_URL` | `http://backend:8000` | URL du backend utilisée par Nginx (frontend) |
| `RATES_API_URL` | `https://api.frankfurter.dev/v1` | fournisseur de taux de change |
| `ADMIN_PASSWORD` | *(vide)* | mot de passe du premier admin. **Vide = aucune protection** |
| `ADMIN_USERNAME` | `admin` | identifiant du premier compte admin |
| `SECRET_KEY` | *(dérivé d'`ADMIN_PASSWORD`)* | clé de signature des jetons |
| `ADMIN_TOKEN_TTL` | `43200` | durée de vie d'une session (secondes) |
| `ADMIN_COOKIE_SECURE` | `false` | passe le cookie en `Secure` (à activer en HTTPS) |
| `ADMIN_MAX_FAILURES` | `10` | tentatives de connexion avant blocage temporaire |

Ces valeurs sont lues depuis le fichier `.env` (voir `.env.example`), qui n'est
**jamais versionné**. Copie du fichier :

```bash
cp .env.example .env
chmod 600 .env
```

En Compose, `DATABASE_URL` vise le service `db` (`db:5432` en réseau bridge,
`127.0.0.1:5434` en réseau hôte) et `UPLOAD_DIR` pointe vers `/app/data/uploads`,
monté sur `./data` de l'hôte.

## Tests

La suite s'exécute sur **PostgreSQL** (c'est le seul moteur). Le plus simple est
une base jetable dédiée :

```bash
docker run -d --rm --name aviadb-test-db \
  -e POSTGRES_PASSWORD=test -e POSTGRES_USER=aviadb -e POSTGRES_DB=aviadb_test \
  -p 55432:5432 postgres:18-alpine

cd backend
pip install -r requirements-dev.txt
pytest                     # utilise par défaut la base ci-dessus
# ou, pour viser une autre base :
DATABASE_URL=postgresql+psycopg://aviadb:test@localhost:5432/aviadb_test pytest
```

La suite (`backend/tests/`, **67 tests**) couvre le CRUD, la validation (dont les
dates invalides), la cascade, l'upload WebP et les vignettes, l'ordre des photos,
les filtres, les statistiques et les graphiques, les devises et taux de change,
l'authentification et les rôles, les actions en masse, l'import/export JSON et
CSV, la sauvegarde/restauration (objets, réglages et comptes) et le mode sans
protection. **Aucun test ne fait d'appel réseau** : le fournisseur de taux est
simulé et un garde-fou fait échouer toute tentative.

Chaque test repart d'un schéma vide (`drop_all` / `create_all`), d'où une
exécution d'une minute environ.

L'intégration continue (`.github/workflows/ci.yml`) lance deux jobs à chaque push
et pull request : `backend` (pytest, avec un service PostgreSQL) et `frontend`
(build Vite).

> Note : le conteneur backend tourne en `root`, les fichiers de `./data` sont donc
> créés avec l'UID root sur l'hôte.
