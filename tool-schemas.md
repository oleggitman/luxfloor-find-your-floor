# Find Your Floor — Tool Schemas (v1)

> The tools the assistant calls. Anthropic tool-use format (`name` + `description` + `input_schema`). The backend implements the handlers in Phase 1 (search_products, estimate_shipping) / Phase 2 (create_lead) against the live WooCommerce + Bitrix24 instances. These schemas are the locked contract; only enum values may be tuned once the live catalog/CRM fields are confirmed in Phase 0.

---

## 1. `search_products`

Queries the live WooCommerce catalog for products matching the captured customer profile, already ranked by the recommendation-priority rule (fit gate → Eigenmarke on promotion → rest). Returns 2-3 product cards.

```json
{
  "name": "search_products",
  "description": "Search the Lux-Floor WooCommerce catalog for floors matching the customer's profile and constraints. Returns up to `limit` products as cards (name, image, key specs, price, sale flag, own-brand flag, product URL), pre-ranked: fitting Eigenmarke-on-promotion first, then other fitting products. Only call once you have enough of the profile (look + material direction + at least the room or key constraints). Never recommend a product this tool did not return.",
  "input_schema": {
    "type": "object",
    "properties": {
      "surface":   { "type": "string", "enum": ["Hochglanz", "Matt", "Strukturiert"], "description": "Oberfläche preference, if stated." },
      "format":    { "type": "string", "enum": ["Diele", "Breitdiele", "Fliese", "Herringbone", "Quadratisch"], "description": "Plank/tile format, if stated." },
      "design":    { "type": "string", "enum": ["Holzoptik", "Steinoptik", "Uni", "Marmoroptik"], "description": "Look/design, if stated." },
      "color":     { "type": "string", "enum": ["hell", "dunkel", "braun", "grau"], "description": "Colour leaning, if stated." },
      "material_type": {
        "type": "string",
        "enum": ["Klick-Vinyl", "Klebe-Vinyl", "SPC-Rigid-Vinyl", "Laminat", "Echtholz", "lose-Verlegung"],
        "description": "Resolved material type after applying the constraints (e.g. waterproof+rigid -> SPC-Rigid-Vinyl)."
      },
      "constraints": {
        "type": "array",
        "description": "Hard constraints from Step 3 that must be honored.",
        "items": {
          "type": "string",
          "enum": ["underfloor_heating", "low_build_height", "install_on_top", "rigid", "waterproof", "durable_high_traffic", "removable_later", "eco_natural"]
        }
      },
      "room": { "type": "string", "enum": ["Wohnzimmer", "Kueche", "Flur", "Bad", "Schlafzimmer", "Gewerbe"], "description": "Target room from Step 2b." },
      "usage_class_min": { "type": "integer", "description": "Minimum Nutzungsklasse the room needs (e.g. 22 living, 23 kitchen/hall, 31-33 commercial)." },
      "budget_max_eur_per_sqm": { "type": "number", "description": "Upper budget per m2, if the customer signaled price sensitivity. Omit if unknown." },
      "limit": { "type": "integer", "default": 3, "description": "Max products to return (2-3)." }
    },
    "required": ["constraints"]
  }
}
```

**Handler responsibility (backend, not the model):**
- Translate fields into WooCommerce REST queries (product attributes/categories + `on_sale`/`sale_price` + the `Eigenmarke` tag).
- Apply the ranking: fitting `Eigenmarke && on_sale` first, then other fitting products. Fit is a hard filter on constraints.
- Return per product: `name`, `sku`, `image_url`, `price`, `sale_price`, `on_sale` (bool), `is_eigenmarke` (bool), `nutzungsklasse`, `material_type`, `surface`, `format`, `url`, **`weight_kg_per_ve`**, **`sqm_per_ve`** (the last two feed `estimate_shipping`).

---

## 2. `estimate_shipping`

Estimates domestic (Germany mainland) shipping for the selected product(s) and area, using the published weight/VE rate table (knowledge base, Section C). Deterministic lookup in the backend so the model never does the arithmetic. Domestic only; abroad is escalated, not estimated.

```json
{
  "name": "estimate_shipping",
  "description": "Estimate domestic German (Festland) shipping cost for the chosen product(s) and area in m2. Returns the flat rate from the weight/VE table plus the computed total weight and VE count. Germany mainland only. For abroad, do NOT call this; escalate to info@lux-floor.de. Present the result to the customer as an estimate ('ca. X EUR, final bei Bestellung').",
  "input_schema": {
    "type": "object",
    "properties": {
      "items": {
        "type": "array",
        "description": "The product(s) and area the customer wants shipped.",
        "items": {
          "type": "object",
          "properties": {
            "sku":      { "type": "string", "description": "Product SKU from search_products." },
            "area_sqm": { "type": "number", "description": "Area for this product in m2." }
          },
          "required": ["sku", "area_sqm"]
        }
      },
      "country": { "type": "string", "default": "DE", "description": "Destination country. Only 'DE' (Festland) is calculable; anything else returns 'escalate'." }
    },
    "required": ["items"]
  }
}
```

**Handler responsibility (backend, not the model):**
- For each item: packages (VE) = ceil(area_sqm / `sqm_per_ve`); weight = packages × `weight_kg_per_ve` (from Woo product data).
- Sum weight + VE across items, look up the flat rate in the KB rate table, return `{ rate_eur, total_weight_kg, total_ve, tier_label }`.
- For `country != DE`, return `{ status: "escalate", channel: "info@lux-floor.de" }`.
- Optional robustness: cross-check against WooCommerce's own cart shipping calculation (same engine as checkout) and prefer it if available, so the estimate never drifts from what the customer pays.

---

## 3. `create_lead`

Creates a scored lead in Bitrix24 from the completed profile. Call only after DSGVO consent and the minimum contact fields are collected. The backend computes `estimated_value` and `lead_score` and assigns the responsible users (Alisa + Alexey); the model does not set those.

```json
{
  "name": "create_lead",
  "description": "Create a lead in Bitrix24 with the captured profile, contact, and consent. Call once: after the customer has given DSGVO consent and at least Name + (Telefon/WhatsApp OR E-Mail) + Stadt + PLZ. Do NOT call without consent. The backend computes the estimated value and HOT/Warm score and notifies the team; you only pass honest captured data.",
  "input_schema": {
    "type": "object",
    "properties": {
      "name":              { "type": "string", "description": "Customer name." },
      "phone_or_whatsapp": { "type": "string", "description": "Phone or WhatsApp number. At least this OR email is required." },
      "email":             { "type": "string", "description": "Email. Required only if no phone/WhatsApp given." },
      "stadt":             { "type": "string", "description": "City." },
      "plz":               { "type": "string", "description": "Postal code (needed for the delivery-cost estimate)." },
      "strasse":           { "type": "string", "description": "Full street address. Provide ONLY if collected for a sample request or delivery estimate; otherwise omit." },
      "interested_products": {
        "type": "array",
        "description": "SKUs of the product(s) recommended/of interest from search_products.",
        "items": { "type": "string" }
      },
      "area_sqm":          { "type": "number", "description": "Approximate area in m2 from Step 2b." },
      "budget_eur_per_sqm": { "type": "number", "description": "Customer's budget per m2 in EUR, if stated in Step 2. Omit if not mentioned." },
      "verlegung_wanted":  { "type": "boolean", "description": "Does the customer also want installation (Verlegung), not just material?" },
      "zubehoer_interest": { "type": "string", "description": "Any accessories interest (Sockelleisten, Trittschalldämmung, etc.). Optional." },
      "profile": {
        "type": "object",
        "description": "The captured qualification profile (Steps 1-3), structured.",
        "properties": {
          "optik":       { "type": "string", "description": "Look: colour, design, surface, edge, pattern as captured." },
          "material":    { "type": "string", "description": "Material direction + budget sense." },
          "constraints": { "type": "array", "items": { "type": "string" }, "description": "Hard constraints from Step 3." }
        }
      },
      "urgency":       { "type": "string", "enum": ["needed_now", "has_time", "needs_storage"], "description": "From Step 4. 'needed_now' (incl. install within ~2-3 weeks) is the HOT signal." },
      "info_note":     { "type": "string", "description": "Free-text description / situation from the customer. Optional." },
      "action":        { "type": "string", "enum": ["none", "sample_request", "showroom_booking"], "description": "Any v1 action the customer chose. Default 'none'." },
      "showroom_slot": { "type": "string", "description": "Preferred showroom slot, if action = showroom_booking." },
      "dsgvo_consent": { "type": "boolean", "description": "MUST be true. Explicit consent to store and be contacted. Never call this tool with false." }
    },
    "required": ["name", "stadt", "plz", "urgency", "dsgvo_consent"]
  }
}
```

**Handler responsibility (backend, not the model):**
- Map inputs onto Bitrix24 lead fields per the locked §4.2 field map (internal field codes set in Phase 0).
- Set `Quelle (Von)` = "Website-Assistent" automatically.
- Compute `Geschätzter Auftragswert` = area_sqm × product price + delivery (delivery from `estimate_shipping`, the weight/VE rate table, not PLZ).
- Compute `Dringlichkeit / Lead-Score` = HOT only if contact + urgency=needed_now + concrete project (room + size + material) all present; else Warm.
- Assign responsible = Alisa + Alexey (Bitrix notifies them natively).
- If HOT, fire the Smart Buzz Telegram alert to Ilya.
- Reject / refuse to write if `dsgvo_consent` is not true.
- Do NOT touch fulfillment fields (VPE, Gepackt, Versanddienst, Datum Versand, Zahlung, RE) — those are the deal/order stage / Lexware.

---

## 4. `lookup_product`

Resolves a SPECIFIC product the visitor names (article number/SKU, exact product name, or a pasted lux-floor.de link) into full product cards. Complements `search_products` (which is profile/attribute-based): use `lookup_product` when the customer already references a concrete product. Read-only against WooCommerce.

```json
{
  "name": "lookup_product",
  "description": "Look up a specific product the visitor names: an article number/SKU (e.g. CheckOne-2157, D2935), an exact product name, or a pasted lux-floor.de link. Use whenever the customer references a concrete product rather than a profile. Returns up to `limit` full cards (name, sku, price, on-sale, surface/optik/format, usage class, url, m2-per-package, weight). If count is 0, say so plainly and offer to help differently or pass it to the team; never invent a price or specs.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "The article number, product name, or shop link the visitor gave." },
      "limit": { "type": "integer", "default": 3, "description": "Max products to return." }
    },
    "required": ["query"]
  }
}
```

**Handler responsibility (backend, not the model):**
- Try, in order, stopping once enough hits: exact WooCommerce `sku=`, then free-text `search=` on the whole query, then `search=` on the code-like tokens inside it (a bare SKU like `CheckOne-2157` is matched exactly; `search=` only finds the code core such as `2157` or `D2935`, so the tokens matter).
- A pasted shop link: strip to the last path slug and search that.
- Return the same card shape as `search_products`, deduped by product id, up to `limit`.
- `count: 0` means nothing matched: the model must escalate honestly, not fabricate.

---

*v1. Contract locked off find-your-floor-spec.md §4.2. Enum values may be tuned to the live catalog/CRM in Phase 0; structure is fixed.*
