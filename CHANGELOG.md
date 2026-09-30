# Changelog

## 0.5.0-beta.2 - correction asyncio #185

- Ouvre et ferme le lecteur temporaire de l'upload FileStation dans
  l'executor Home Assistant ; aucun appel `open` du composant ne bloque
  la boucle asyncio pendant `BackupAgent.async_upload_backup`.

## 0.5.0-beta.1 - candidate #185 (SANDBOX reel, pas release GitHub)

- Migration franche BackupAgent natif HA >= 2026.9.3, flux FileStation sans scan local.
- Flux HA spoule dans un TemporaryFile non nomme 0600, puis upload FileStation
  a taille connue : evite la corruption multipart chunked observee en SANDBOX.
- SHA-256 et taille verifies sur le tar reel avant publication des metadonnees.
- List/get/download/delete natifs, namespace par entree et retries idempotents.
- Retention NAS preservee, courant protege, erreurs partielles visibles.
- Migration entree v2 ; options polling et service sync_now retires.
- Entites recyclees sans changement de unique_id, warning retention distinct.
- Bibliotheque DSM fournie exclusivement par HA pour eviter un conflit de versions.
- Anciens tar conserves hors retention ; rollback pre-migration documente.
- 34 tests unitaires PASS ; cycle SANDBOX HA -> NAS et SHA-256 reels PASS le
  2026-09-29. Download/delete/retention > seuil et HAOS restent a valider.

## 0.4.0

Premiere release stable (promue depuis v0.4.0-beta.1, meme contenu,
validee SANDBOX et DEV - voir issues #161 et #175). Couvre l'ensemble
du travail depuis la version initiale : pivot vers la reutilisation de
la connexion `synology_dsm`, verification round-trip SHA-256, 3 bugs
de fiabilite reels trouves et corriges en RECETTE (crash sur fichier
orphelin, nettoyage NAS non verifie, file de synchronisation bloquee),
icone, branding NR, documentation enrichie, reconfigure flow.

## 0.4.0-beta.1

- Nouveau : icone du composant (`icon.png`), dessinee sur le modele de
  l'identite visuelle NetRunner Nexus (degrade bleu-cyan-violet avec
  glow, fond bleu nuit, accent ambre "verification checksum") -
  visible dans HACS et l'ecran d'ajout d'integration.
- Renommage : "Backup NAS Sync" -> "NR Backup NAS Sync" (branding
  NetRunner) dans `manifest.json`, `hacs.json` et le titre des entrees
  de configuration. Aucun impact sur le `domain` (`backup_nas_sync`)
  ni sur les entites/unique_id existants.
- Nouveau : possibilite de modifier les parametres (repertoire NAS,
  repertoire local, intervalle, retention, delai de stabilisation,
  choix de l'integration Synology DSM) apres la creation de
  l'integration, via Configurer - reconfigure flow natif HA, rechargement
  automatique sans redemarrage. Le nom du site reste non modifiable
  (double comme identifiant unique de l'entree).
- README enrichi (schema du flux, tableau des parametres, section
  modification des parametres).
- Prerequis releve : `homeassistant >= 2024.11.0` (requis par le
  reconfigure flow natif).

## 0.3.4-beta.4

- Corrige un bug bloquant reel constate en RECETTE : `_find_next_candidate`
  selectionne toujours le fichier local non-synchronise **le plus
  ancien**, sans jamais tenir compte d'un abandon definitif
  (`pending_retries` epuise). Consequence : un unique fichier
  definitivement abandonne (voir v0.3.4-beta.1/.2/.3) bloquait *pour
  toujours* la synchronisation de tout backup plus recent, y compris
  une sauvegarde manuelle fraichement creee pour tester le correctif -
  elle n'etait jamais prise en compte tant que l'ancien fichier
  abandonne restait le plus ancien fichier local non marque
  synchronise. Un fichier ayant atteint `MAX_RETRIES_PER_FILE` est
  desormais exclu de la selection de candidat, permettant a la
  synchronisation de progresser sur les backups suivants au lieu de
  rester bloquee indefiniment sur un seul echec definitif.

## 0.3.4-beta.3

- Ajoute la journalisation manquante sur les cycles de synchronisation
  en echec (`_sync_one`) : chaque tentative echouee (upload temporaire,
  verification, upload final, abandon apres 3 tentatives) est desormais
  loguee avec le detail de l'erreur - jusqu'ici invisible, un echec
  gere proprement (capture SynologyDSMException, v0.3.4-beta.1) ne
  laissait plus aucune trace exploitable dans les logs.
- Corrige `_safe_delete` : le retour de l'API `delete_file` du NAS
  (qui peut signaler un echec `success=False` sans lever d'exception)
  n'etait jamais verifie - un nettoyage de fichier temporaire
  silencieusement refuse par le NAS n'etait ni detecte ni logue,
  laissant le meme fichier `.uploading` orphelin bloquer indefiniment
  les tentatives suivantes jusqu'a l'abandon definitif, sans aucun
  indice sur la cause reelle. Repere en RECETTE en testant le
  correctif v0.3.4-beta.1/.2 sur le fichier orphelin reel.

## 0.3.4-beta.2

- Corrige `manifest.json` "documentation" qui pointait vers le depot
  Gitea prive (`git.famille-henrion.fr/...`, non accessible) au lieu du
  depot GitHub public - le bouton d'aide ("?") du depot dans HACS
  renvoyait vers une page inaccessible pour l'utilisateur. Repere en
  usage reel par le PO.

## 0.3.4-beta.1

- Corrige un bug reel constate en RECETTE au redemarrage HA : un cycle de
  synchronisation interrompu en cours de transfert (ex. redemarrage HA)
  laisse un fichier temporaire `.uploading` orphelin sur le NAS. Au cycle
  suivant, la nouvelle tentative sur le meme fichier echouait avec
  `SynologyDSMAPIErrorException` (code 414 "File already exists"), une
  exception de la librairie non capturee par le composant : elle
  echappait au comptage des tentatives (`pending_retries`) et au
  nettoyage du fichier temporaire, provoquant un echec identique
  indefiniment repete a chaque cycle sans jamais s'auto-corriger ni
  abandonner apres le nombre maximal de tentatives.
  `SynologyDSMException` (base de la librairie `synology_dsm`) est
  desormais interceptee au meme titre que `BackupNasSyncError` dans
  `_sync_one` : le fichier temporaire orphelin est supprime, la
  tentative est comptabilisee, et la synchronisation se retablit
  normalement au cycle suivant.

## 0.3.3-beta.1

- Amelioration des libelles et de l'aide contextuelle du config_flow,
  suite a une confusion reelle en usage (RECETTE) : ajout de
  `data_description` par champ, avec un exemple explicite correct vs
  incorrect pour `remote_base_dir`.
- Nouvelle validation proactive : rejette un chemin commencant par
  `/volumeN/` avec un message explicite (FileStation adresse le
  dossier partage directement par son nom, pas par le chemin systeme
  de fichiers) - erreur reellement rencontree par le PO en configurant
  RECETTE.

## 0.3.2-beta.1

- Corrige une erreur de rendu du config_flow : le libelle du champ
  `remote_base_dir` contenait `<site>` (exemple de chemin), interprete
  par le moteur de traduction du frontend HA comme une balise HTML non
  fermee ("Translation error: UNCLOSED_TAG"), bloquant l'affichage du
  champ. Detecte par test SANDBOX reel. Remplace par
  `NOM_DU_SITE` (pas de chevrons).

## 0.3.1-beta.1

- `remote_base_dir` devient le chemin NAS cible complet et definitif
  (plus de composition automatique avec `site_name`) : s'aligne sur la
  convention deja en place sur le NAS de production
  (`/BackUpHA/ha_backup_<site>`), un parametre pour gerer librement le
  repertoire cible par instance. Champ desormais requis, valide (doit
  commencer par `/`).
- Ajout `translations/en.json` et `translations/fr.json` (les messages
  d'erreur/abandon du config_flow s'affichaient en brut faute de
  traduction compilee - `strings.json` seul ne suffit pas pour un
  composant custom hors pipeline HA Core).

## 0.3.0-beta.1

- Changement d'architecture majeur : reutilise la connexion DSM d'une
  integration `synology_dsm` deja configuree au lieu de demander des
  identifiants NAS dedies (host/port/utilisateur/mot de passe). Le
  composant depend desormais de `synology_dsm` (manifest.json
  `dependencies`). Installation identique et simple sur plusieurs
  instances Home Assistant partageant le meme NAS distant en HTTPS.
- Le nom d'environnement fixe (sandbox/dev/recette/prod) est remplace
  par un nom de site libre (`site_name`), plus adapte a un usage
  multi-installations independantes.
- Verification d'integrite par round-trip (upload temporaire ->
  retelechargement -> comparaison SHA-256) : pas d'API de checksum
  distant native dans l'API FileStation Synology.

## 0.1.0-beta.1

- Version initiale (abandonnee) : transfert SSH/SFTP direct avec compte
  dedie. Remplacee par l'approche FileStation/synology_dsm ci-dessus
  pour simplifier le deploiement multi-instances.
