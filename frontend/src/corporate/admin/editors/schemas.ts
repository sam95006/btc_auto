/**
 * Structured CMS schemas per slug. Slugs with a schema get a visual editor;
 * anything else falls back to the raw-JSON editor. Editing a field preserves
 * untouched keys (the form does immutable merges), so partial schemas are safe.
 */
import type { Field } from "./formKit";

export const SCHEMAS: Record<string, { label: string; schema: Field[] }> = {
  site: {
    label: "Website (nav · footer · CTA)",
    schema: [
      { key: "brand", label: "Brand", type: "group", fields: [
        { key: "name", label: "Name", type: "text", required: true },
        { key: "tagline", label: "Tagline", type: "text" },
      ] },
      { key: "nav", label: "Navigation", type: "repeat", addLabel: "nav item", fields: [
        { key: "label", label: "Label", type: "text", required: true },
        { key: "to", label: "Path", type: "text", required: true, placeholder: "/products" },
      ] },
      { key: "cta", label: "Header CTAs", type: "group", fields: [
        { key: "personal", label: "Personal", type: "group", fields: [
          { key: "label", label: "Label", type: "text" },
          { key: "href", label: "Href", type: "text" },
        ] },
        { key: "enterprise", label: "Enterprise", type: "group", fields: [
          { key: "label", label: "Label", type: "text" },
          { key: "href", label: "Href", type: "text" },
        ] },
      ] },
      { key: "footer", label: "Footer", type: "group", fields: [
        { key: "note", label: "Note", type: "textarea" },
        { key: "columns", label: "Columns", type: "repeat", addLabel: "column", fields: [
          { key: "title", label: "Title", type: "text" },
          { key: "links", label: "Links", type: "repeat", addLabel: "link", fields: [
            { key: "label", label: "Label", type: "text" },
            { key: "to", label: "Path", type: "text" },
          ] },
        ] },
      ] },
    ],
  },
  products: {
    label: "Products",
    schema: [
      { key: "title", label: "Title", type: "text", required: true },
      { key: "intro", label: "Intro", type: "textarea" },
      { key: "items", label: "Products", type: "repeat", addLabel: "product", fields: [
        { key: "key", label: "Key", type: "text", required: true, placeholder: "personal" },
        { key: "title", label: "Title", type: "text", required: true },
        { key: "summary", label: "Summary", type: "textarea" },
        { key: "to", label: "Path", type: "text", placeholder: "/personal" },
        { key: "availability", label: "Availability (available / planned / contact)", type: "text" },
        { key: "features", label: "Features", type: "repeat", addLabel: "feature", fields: [
          { key: "label", label: "Label", type: "text" },
          { key: "state", label: "State (available / planned / contact)", type: "text" },
        ] },
      ] },
    ],
  },
  pricing: {
    label: "Pricing",
    schema: [
      { key: "title", label: "Title", type: "text", required: true },
      { key: "note", label: "Note", type: "textarea" },
      { key: "tiers", label: "Tiers", type: "repeat", addLabel: "tier", fields: [
        { key: "code", label: "Code", type: "text" },
        { key: "name", label: "Name", type: "text" },
        { key: "price_display", label: "Price (display)", type: "text", placeholder: "—" },
        { key: "period", label: "Period", type: "text", placeholder: "mo" },
        { key: "features", label: "Features", type: "list" },
      ] },
    ],
  },
  showcase: {
    label: "Showcase (symbols)",
    schema: [
      { key: "symbols", label: "Symbols", type: "list", hint: "One symbol per line, e.g. BTCUSDT" },
    ],
  },
  seo: {
    label: "SEO",
    schema: [
      { key: "default", label: "Default", type: "group", fields: [
        { key: "title", label: "Title", type: "text", required: true },
        { key: "description", label: "Description", type: "textarea" },
        { key: "robots", label: "Robots", type: "text", placeholder: "index,follow" },
        { key: "og_type", label: "OG type", type: "text", placeholder: "website" },
      ] },
    ],
  },
  about: {
    label: "About",
    schema: [
      { key: "title", label: "Title", type: "text", required: true },
      { key: "vision", label: "Vision", type: "textarea" },
      { key: "body", label: "Body", type: "textarea" },
    ],
  },
  security: {
    label: "Security",
    schema: [
      { key: "title", label: "Title", type: "text", required: true },
      { key: "points", label: "Points", type: "repeat", addLabel: "point", fields: [
        { key: "title", label: "Title", type: "text" },
        { key: "body", label: "Body", type: "textarea" },
      ] },
    ],
  },
};
