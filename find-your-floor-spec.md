# "Find Your Floor" — Site Assistant Spec (v1 design)

| | |
|---|---|
| **Date** | 2026-06-08 |
| **Status** | Draft for review (revisit 2026-06-09 AM to scope the build) |
| **Inputs** | Ilya's 4-step qualification flow + the scraped site FAQ ([faq-baseline-site.md](faq-baseline-site.md)) + CONTEXT.md |
| **Gate** | Ilya confirms the cleaned 4-step flow matches how he sells, before any build plan |

> **What this is:** the design for Lux-Floor's site assistant. Not a support bot. A guiding, selling assistant that qualifies a buyer the way Ilya does, explains trade-offs from the FAQ, narrows to products, and captures the lead into the CRM.
>
> **What this is not:** a build plan or a stack decision. Those come next, off this spec.

---

## 1. The core idea

Ilya's document revealed the real vision: the assistant should **sell, not just answer.** It is built as three layers that lock together. The flow asks the question; the FAQ supplies the answer; the output captures the lead.

| Layer | Source | Role |
|---|---|---|
| **1. Spine** | Ilya's 4-step flow | Leads the customer through Look, Material, Constraints, Urgency |
| **2. Answer bank** | The site FAQ | Explains every trade-off the flow raises |
| **3. Output** | Catalog + Bitrix24 | Recommends products, captures a scored lead |

The two source documents are not competing versions of one thing. They are two different layers of the same assistant.

---

## 2. Layer 1 — The qualification flow (the spine)

Ilya's four steps, cleaned up: duplicates removed, options structured. German is customer-facing; English is for our reference.

### Step 1 — Optik (the look) · soft preferences

| Dimension | Options (DE) | English |
|---|---|---|
| Farbe (Color) | hell, dunkel, braun, grau | light, dark, brown, grey |
| Design | Holzoptik, Steinoptik, Marmoroptik | wood, stone, marble look |
| Oberfläche (Surface) | matt, Hochglanz | matte, high-gloss |
| Kante (Edge) | mit Fuge, mit Fase, ohne | with joint, with bevel, none |
| Muster (Pattern) | Diele, Fischgrät | plank, herringbone |
| ↳ if herringbone | Chevron, Englisch | chevron (45° V), english (90° blocks) |

### Step 2 — Material · type leaning + budget

| Dimension | Options (DE) | Meaning |
|---|---|---|
| Typ-Tendenz (Type) | dünn, Klick, Echt Holz, wasserfest, robust | thin / low height, click, real wood, waterproof, durable |
| Preis (Budget) | range or sensitivity | which collections to show |

### Step 2b — Raum & Projekt (the "clear picture" layer · added 2026-06-09)

Purpose (Oleg, 2026-06-09): help the customer see for themselves whether the material they pictured actually fits, and let them self-assess the better option with the assistant's help. Doubles as project sizing and as a lead-quality signal.

| Field | Captures | Why it matters |
|---|---|---|
| Raum (room) | living, kitchen, hall, bath, commercial | drives Nutzungsklasse + UFH/waterproof logic |
| Fläche (size, m²) | approx. area | sample/quote sizing; quantity for the offer |
| Beschreibung (free text) | what they imagine, the situation | fit-check + enriches the lead |
| Foto (optional) | photo of the room/old floor | **deferred to Phase 1.5** — image handling adds weight; v1 stays text + the product cards we already pull from Woo (those carry the visuals) |

The "picture" the customer sees comes from the **live WooCommerce product cards** (image + specs) the assistant returns, matched against this room/size/description. Customer photo-upload is a later add, not v1.

### Step 3 — Probleme nennen (the hard constraints)

These rule options in or out. This is where the FAQ does the heavy lifting (see the reasoning table in section 3).

| Constraint (DE) | English |
|---|---|
| Fußbodenheizung vorhanden | underfloor heating present |
| Alter Belag darf nicht entfernt werden | old floor stays, install on top |
| Belag darf nicht hoch sein | low build height required |
| Muss formstabil / steif sein (= hart, geklärt) | must be rigid / no flex underfoot (the "hard" = rigidity reading, confirmed 2026-06-09) |
| Muss strapazierfähig sein | must be durable / high traffic |
| Muss wasserfest sein | must be waterproof |
| Muss später leicht entfernbar sein | must be removable later |
| Muss ein Bio-Material sein | must be eco / natural |

> *Deduped from Ilya's notes:* "wasserfest" appeared in Steps 2 and 3 (kept once, here). "Fußbodenheizung" and "für Fußbodenheizung geeignet" merged into one.

### Step 4 — Verfügbarkeit (urgency = the lead signal)

| Answer (DE) | English | Lead score | Action |
|---|---|---|---|
| Wird jetzt dringend benötigt | needed urgently now | **HOT** | real-time alert to Ilya / Alisa |
| Hat Zeit | has time | Warm | normal pipeline |
| Muss eingelagert werden | must be stored | Warm + logistics | note free 30-day storage (FAQ) |

---

## 3. Layer 2 — Constraint → FAQ → recommendation

The assistant's reasoning table. Each Step-3 constraint resolves using the FAQ as the answer bank.

| Constraint | FAQ fact | Recommendation |
|---|---|---|
| Underfloor heating | PE-foam underlay OK; cork and polystyrene not for UFH; glue-vinyl ideal | Vinyl + correct underlay; avoid cork/polystyrene |
| Low height / old floor stays | Glue-down vinyl has the lowest build height | Glue-down vinyl, or a thin click floor |
| Removable later | Glue removal destroys the plank; click is liftable | Click system, not glue |
| Waterproof | Vinyl is waterproof; laminate (HDF core) is not | Vinyl over laminate |
| Durable / high traffic | Nutzungsklassen 21-43 by room | Match class to room: 22 living, 23 kitchen/hall, 31-33 commercial |
| Eco / natural | Cork is 100% recyclable; real wood is natural | Cork underlay or real-wood parquet |
| Must be hard (= rigidity, confirmed by Ilya 2026-06-09) | Rigid core resists flex; SPC vinyl and laminate are stiff, flexible glue-down vinyl is not | Rigid-core SPC vinyl or laminate; avoid soft glue-down |

---

## 4. Layer 3 — Recommendation + lead capture (the output)

### 4.1 Narrowing to products

The customer profile maps directly onto filters that **already exist on the shop**:

| Shop filter | Values |
|---|---|
| Surface | Hochglanz, Matt, Strukturiert |
| Format | Diele, Breitdiele, Fliese, Herringbone, Quadratisch |
| Design | Holzoptik, Steinoptik, Uni, Marmoroptik |

**Decided 2026-06-09:** live catalog pull (rich). The assistant connects to WooCommerce and shows 2-3 concrete products in the chat (image, key specs, link to product), not just a filtered link. It closes the customer inside the conversation instead of bouncing them to the shop. (799 products available.)

**Recommendation priority (Oleg, 2026-06-09).** Fit is always the gate — never surface a product that does not match the profile. Within the fitting set, the assistant leads with **Luxfloor own-brand products that are on promotion**, then everything else that fits. House brand + active discount is the single top pick (best margin and a price hook in one); the rest of the matching catalog follows after.

### 4.2 Lead capture (the kicker)

At the end, the assistant collects name + contact, attaches the filled profile and urgency, and pushes a **lead into Bitrix24** — Luxfloor's chosen CRM (Ilya's final decision, in scope and mid-rollout, see [CONTEXT.md](../CONTEXT.md) phases). The Bitrix lead fields are **mapped from Alisa's current working file** (the Sheet she uses today) so the team keeps the exact fields they already work with and Bitrix becomes usable fast. **Field map locked 2026-06-09** — see the table below; only Bitrix internal field names get finalized at build on the live instance.

**Lead score — HOT definition (2026-06-09).** A lead is **HOT** (fires the real-time alert) only when all three hold:
1. **Contact left** — phone or WhatsApp, not just a name.
2. **Urgency** — "needed now" or an install date within ~2-3 weeks.
3. **Concrete project** — room + size + material direction captured (Step 2b completed).

Missing any one → **Warm** (normal pipeline, no alarm). Strict on purpose, so the alert stays trustworthy and Ilya/Alisa never get false "hot" pings.

**Notifications — two layers (2026-06-09).**
- **Worker notification = native Bitrix.** The lead is created in Bitrix24 and assigned to the responsible person(s) — **Alisa and Alexey** (both are set as responsible and have the Bitrix24 app, confirmed 2026-06-09). **Bitrix notifies them itself** — in-app + mobile push — no extra build. Standard Bitrix behavior, or a one-line lead-automation rule. The assistant needs no separate channel to the workers.
- **Oversight alert = Smart Buzz → Ilya (Telegram).** HOT leads *also* fire a Telegram alert to **Ilya** (v1, control mode), so he sees the hot lead landed and confirms Alisa/Alexey are working it. **This is the Smart Buzz hot-lead alert from the Neuss Day 4 build** ([smart-buzz-deep-dive-ru.md](../audit-kit/smart-buzz-deep-dive-ru.md)) — same component, same Python + launchd inside Ilya's AIOS. Can widen to Alisa/Alexey once Ilya trusts the flow.

> **Build note — Smart Buzz source changed.** The deep-dive was written 2026-05-25 against **HubSpot** and is forced to *poll* (HubSpot Free has no outbound webhooks). CRM is now **Bitrix24**, which *does* support webhooks/automation robots. So Smart Buzz becomes **event-driven off Bitrix** (fire on HOT-lead creation), or the assistant triggers the alert directly at lead-creation time — no polling. Resolve the exact trigger in `/create-plan`; update the Smart Buzz deep-dive doc to match.

**v1 actions (decided 2026-06-09).** Beyond the recommendation, the assistant can also:
- **request a free sample** — customer leaves a full shipping address, sample is sent;
- **book a showroom visit** — capture a slot (the visit itself stays with a human, per Phase-1 digital-only rule).

#### Bitrix lead field map (locked 2026-06-09)

Built from Alisa's current file columns + the gaps Oleg approved. The file is an **order/fulfillment tracker**, so its fields split: the assistant fills **lead-stage** fields only; fulfillment fields stay on the Bitrix deal/order stage (or in Lexware). Bitrix internal field names finalized at build on the live instance; the map below is conceptual and locked.

| Bitrix lead field | From Alisa's file | Required | Filled by | Notes |
|---|---|---|---|---|
| Name | Name | **yes** | assistant | |
| Telefon / WhatsApp | — (gap) | **yes** (≥1 channel) | assistant | at least one reachable channel (this or e-mail) |
| E-Mail | — (gap) | conditional | assistant | required only if no phone/WhatsApp |
| Stadt | Stadt | **yes** | assistant | |
| PLZ | — (gap) | **yes** | assistant | needed for the delivery-cost estimate |
| Straße / full address | — (gap) | **progressive** | assistant | asked only on sample request or delivery estimate, not upfront |
| Quelle (Von) | Von: | **yes** | auto | = "Website-Assistent" |
| Interessiertes Produkt | Artikel Bodenbelag | **yes** | assistant | recommended SKU(s) from Woo |
| Menge / m² | Anzahl | **yes** | assistant | room size from Step 2b |
| Verlegung gewünscht? | VERLEGEARBEITEN | **yes** (y/n) | assistant | install/laying interest — qualification + upsell |
| Zubehör-Interesse | Zubehör | no | assistant | optional |
| Geschätzter Auftragswert | — (gap) | auto | computed | = m² × product price **+ delivery**; team confirms at order |
| Dringlichkeit / Lead-Score | — (gap) | **yes** | assistant | HOT / Warm — drives Smart Buzz |
| Profil | — (gap) | **yes** | assistant | look + material + constraints (structured, Steps 1-3) |
| Info / Notiz | Info | no | assistant | free description |
| DSGVO-Einwilligung | — (gap) | **yes (legal)** | assistant | consent checkbox, required in v1 (Germany) |

**Fulfillment fields — NOT touched by the assistant** (stay on the Bitrix deal/order stage or in Lexware): VPE, Gepackt, Versanddienst, Datum Versand, Zahlung, RE (invoice → Lexware).

Net effect: the assistant is a salesperson and a CRM feeder in one pass. It turns anonymous site traffic into qualified, scored leads.

### 4.3 Versandkosten — the assistant calculates (added 2026-06-09)

Oleg, 2026-06-09: the assistant must **calculate domestic shipping**, not hand it to a human. The data exists on the site ([lux-floor.de/lieferung](https://lux-floor.de/lieferung/), captured into the knowledge base).

- **Domestic (Germany mainland / Festland):** a **flat, weight/VE-based rate table** (NOT PLZ-dependent). The assistant estimates total weight from m² (via each product's weight + m²-per-package from Woo), looks up the rate tier, and gives the customer "Versand ca. X EUR (Festland), final bei Bestellung". Feeds the `Geschätzter Auftragswert` on the lead.
- **Abroad (Ausland):** genuinely variable (the carrier must be asked per the site) → escalate: capture article + quantity + full address + country/PLZ, route to info@lux-floor.de.
- **Lean approach (per "simple for Oleg, effective for Ilya"):** don't build a bespoke rate calculator. The rate table lives in the knowledge base; a small deterministic `estimate_shipping` tool does the lookup so the model never does the arithmetic. Optionally cross-check against WooCommerce's own shipping engine (same one the checkout uses) so the estimate never drifts.

### 4.4 Escalation

Out-of-flow items and the case-by-case FAQ (shipping **abroad**, order changes/cancellations, deep product-specific questions) → graceful handoff to a human (phone, WhatsApp, email, showroom). Domestic shipping is no longer escalated — the assistant calculates it (§4.3).

### 4.5 Languages

Site is German-only today. v1 ships **German first.** RU/EN later (logic is language-agnostic; only surface copy changes).

### 4.6 Build principle (Oleg, 2026-06-09)

Keep the build **simple for Oleg to maintain and maximally effective for Ilya**. Concretely: reuse what exists (Woo shipping engine, Woo filters, Bitrix native notifications) before building anything custom; keep the knowledge base in a simple editable format (who maintains it — Alexey vs Ilya vs Oleg-remote — is TBD); favor lean managed hosting over server admin. Borrow before build.

---

## 5. Decisions to make tomorrow (2026-06-09 AM)

| # | Decision | Options / note |
|---|---|---|
| 1 | ~~"Hard" (Step 3) meaning~~ | RESOLVED 2026-06-09: means rigidity (stiff core, no flex underfoot), not scratch resistance. Step-3 label to read "жёсткое основание, не пружинит" / rigid, no flex. |
| 2 | ~~Catalog connection~~ | RESOLVED 2026-06-09: live WooCommerce pull (rich) — show 2-3 real products in chat, not just a filtered link. |
| 3 | ~~Lead destination + alert~~ | RESOLVED: lead → **Bitrix24**; field map **locked** (table in §4.2, contacts + PLZ + Verlegung + est. value incl. delivery + GDPR consent); HOT = contact + urgency + concrete project; Alisa + Alexey notified natively by Bitrix; HOT Telegram alert → **Ilya** (control mode, v1). Only Bitrix internal field names finalized at build. |
| 4 | ~~v1 actions~~ | RESOLVED 2026-06-09: recommend + request free sample + book showroom visit. |
| 5 | ~~v1 channel~~ | RESOLVED 2026-06-09: website widget first, WhatsApp Phase 2. |
| 6 | ~~Confirm the flow with Ilya~~ | RESOLVED 2026-06-09: 4-step flow confirmed to match how Ilya sells. |
| 7 | ~~Recommendation priority~~ | RESOLVED 2026-06-09: fit-gated, then own-brand-on-promotion first, then the rest. |
| 8 | ~~"Clear picture" layer~~ | RESOLVED 2026-06-09: Step 2b captures room + size + description; customer photo deferred to Phase 1.5. |

## 6. Open for the build plan (not decided here)

- The stack (Claude-powered widget, kept lean, decided at build).
- Hosting, embedding method, the knowledge-base format the widget reads.
- How the FAQ + flow are stored and kept current (single source of truth).
- **Bitrix internal field names** — the conceptual field map is locked (§4.2); only the live-instance internal field codes get set at build.
- **Smart Buzz trigger** — assistant fires alert directly for website channel vs Smart Buzz polls Bitrix vs both (see [smart-buzz-deep-dive-ru.md](../audit-kit/smart-buzz-deep-dive-ru.md) v3 retarget).

## 7. Deliverable — context doc for Ilya's AIOS (after build plan)

Once the spec is locked and `/create-plan` produces the build plan, write a clean **context + work-plan doc into Ilya's own AIOS** (his Windows/WSL workspace) so his Claude knows the full picture of the Find-Your-Floor assistant: what it does, the 4-step flow, the Bitrix lead + Smart Buzz wiring, the build phases, and how to operate/change it. This is the handoff artifact, built WITH him (advisor posture), not a black box. Produce it after the plan exists, not now.

---

*Next: spec logic + Bitrix field map locked (2026-06-09). Ready for `/create-plan` to build off this spec, then write the Ilya-AIOS context doc (§7).*
