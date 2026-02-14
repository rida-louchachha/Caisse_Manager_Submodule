# Social Inbox - Checklist Credentials (Odoo 18)

## Objectif
Ce document liste exactement les informations a fournir pour activer WhatsApp, Instagram et Facebook Messenger dans le module `cm_whatsapp_subscription_sender`.

---

## 1) Pre-requis techniques

- URL Odoo publique en HTTPS (pas seulement `localhost`).
- Domaine stable pour les webhooks (ou tunnel type ngrok en test).
- Module installe et a jour dans l'environnement Docker actif.
- Acces administrateur Odoo + acces Meta Developer (manager/IT).

---

## 2) Valeurs a configurer dans Odoo

### A. Parametres systeme (`ir.config_parameter`)

- `web.base.url` = URL publique Odoo (ex: `https://crm.example.com`)
- `whatsapp.verify_token` = token de verification webhook WhatsApp
- `instagram.verify_token` = token de verification webhook Instagram
- `facebook.verify_token` = token de verification webhook Messenger

### B. Menu `Social Inbox` -> `Channels`

#### WhatsApp
- `channel_type`: WhatsApp
- `access_token`: Meta WhatsApp Cloud API token
- `whatsapp_phone_number_id`: Phone Number ID
- `whatsapp_business_account_id`: Business Account ID

#### Instagram
- `channel_type`: Instagram
- `access_token`: Meta access token
- `instagram_page_id`: Instagram sender/page ID
- `graph_api_version`: ex `v19.0` (ou version valide)

#### Facebook Messenger
- `channel_type`: Messenger (ou Facebook)
- `access_token`: Meta Page token
- `facebook_page_id`: Facebook Page ID
- `graph_api_version`: ex `v19.0`

---

## 3) URLs webhook a configurer cote Meta

- WhatsApp webhook: `{web.base.url}/whatsapp/webhook`
- Instagram webhook: `{web.base.url}/instagram/webhook`
- Messenger webhook: `{web.base.url}/facebook/webhook`

Exemple:
- `https://crm.example.com/whatsapp/webhook`

---

## 3b) Instagram – valeurs pour l’ecran « 2. Configure webhooks » (Meta)

A remplir dans **Meta for Developers** > ton app > **Instagram** > **Configure webhooks** (ou **Webhooks** selon l’interface) :

| Champ Meta        | Valeur a saisir |
|-------------------|-----------------|
| **Callback URL**  | `https://TON_DOMAINE_ODOO/instagram/webhook` |
| **Verify token**  | La meme valeur que le parametre Odoo `instagram.verify_token` (voir ci-dessous) |

- Remplace `TON_DOMAINE_ODOO` par l’URL de base de ton Odoo (sans slash final), par ex. :
  - Production : `https://crm.tonentreprise.com`
  - Test (ngrok) : `https://xxxx-xx-xx-xx-xx.ngrok-free.app`
- En local : `http://localhost:8069` (Meta exige souvent une URL publique en HTTPS ; en dev, utiliser ngrok.)

**Verify token :**

1. Dans Odoo : **Parametres** > **Technique** > **Parametres** > **Parametres systeme**.
2. Cherche ou cree la cle `instagram.verify_token`.
3. Valeur par defaut du module : `my_verify_token`. Tu peux la garder ou en mettre une autre (ex. une phrase secrete).
4. **Copie exactement cette valeur** dans le champ **Verify token** de l’ecran Meta « 2. Configure webhooks ».

Puis clique sur **Verify and save**. Si l’URL est joignable par Meta et le token identique, la verification reussit.

---

## 4) Permissions Meta minimales a verifier

La liste exacte depend du type d'app et de la review Meta, mais au minimum:
- Lecture/reception des messages entrants
- Envoi/reponse des messages
- Abonnement webhook sur les events messages

Important:
- Sans permissions valides, le code peut etre correct mais l'envoi/reception reel echoue.

---

## 5) Qui fournit quoi (RACI simple)

- Manager/IT Meta:
  - Access tokens
  - IDs pages/comptes (WA/IG/FB)
  - Validation webhooks + permissions
- Admin Odoo:
  - Saisie des credentials dans Odoo
  - Parametrage tokens de verification
  - Test fonctionnel de bout en bout

---

## 6) Verification rapide apres saisie

- Ouvrir `Social Inbox`.
- Verifier que chaque canal est en etat connecte.
- Envoyer un message test depuis un compte client reel vers:
  - WhatsApp
  - Instagram DM
  - Messenger
- Verifier:
  - reception dans l'inbox Odoo
  - reponse depuis Odoo recue cote client

---

## 7) Limites a communiquer au management

- Le MVP couvre la messagerie centralisee.
- Les appels natifs WhatsApp/Instagram ne sont pas couverts par les APIs de messagerie standard.
- Pour les appels, prevoir une integration telephonie separee (VoIP/call center).

//////////////////////////////
Pour avoir un module vraiment “type GoHighLevel”, il faut penser en produit, pas juste en “connexion Instagram”.
Ce que doit contenir ton module (version pro)
Inbox omnicanale: WhatsApp, Instagram, Messenger, email, SMS dans une seule vue.
Routing & attribution: assigner conversations aux commerciaux, files d’attente, tags.
Automations: règles “si message entrant alors…”, réponses auto, relances.
CRM pipeline: conversation -> lead -> opportunité -> vente.
Campagnes: broadcast, templates, séquences, scheduling.
Reporting: temps de réponse, taux conversion, performance par agent/canal.
Administration simple: connect/disconnect comptes sans développeur.
Plan réaliste en 4 phases
Phase 1 (stabilité)
Finir 1 compte Instagram + WA + Messenger fiable (entrant/sortant + logs + erreurs claires).
Phase 2 (ops sales)
Ajout: assignation agent, statuts conversation, notes internes, tags, filtres avancés.
Phase 3 (automation)
Règles automatiques, templates, campagnes, rappels, SLA.
Phase 4 (scale enterprise)
Multi-comptes (plusieurs pages), OAuth self-service, rôles/permissions fins, audit, dashboard.
Équipe minimum recommandée
1 dev Odoo backend
1 dev frontend OWL
1 QA/UAT (métier sales)
1 PO (toi/manager) pour prioriser les besoins
Ce que je te conseille maintenant (très concret)
Écrire un cahier des charges V1 (10-15 user stories max)
Prioriser Must-have vs Nice-to-have
Lancer d’abord un pilote 1 canal/1 équipe sales
Mesurer 3 KPI: temps de réponse, conversations traitées, taux conversion
Si tu veux, je te rédige maintenant un backlog prêt à développer (user stories + priorités + estimation) pour construire ton “mini GoHighLevel” sur Odoo.