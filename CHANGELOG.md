# Changelog

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
