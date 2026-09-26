# Changelog

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
