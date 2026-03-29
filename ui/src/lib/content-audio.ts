export type SpeakableEntry = {
  label: string;
  locale?: string;
  textParts: string[];
};

const TEXT_KEYS = ["title", "summary", "caption", "text", "script", "headline", "description"];

function buildEntry(source: Record<string, unknown>, label: string): SpeakableEntry | null {
  const textParts = TEXT_KEYS
    .map((k) => source[k])
    .filter((v): v is string => typeof v === "string")
    .map((v) => v.trim())
    .filter(Boolean);

  if (textParts.length === 0) return null;
  const locale = typeof source.locale === "string" ? source.locale : undefined;
  return { label: locale ? `${label} (${locale})` : label, locale, textParts };
}

function fromObject(obj: Record<string, unknown>, fallbackLabel: string): SpeakableEntry[] {
  const out: SpeakableEntry[] = [];

  const direct = buildEntry(obj, fallbackLabel);
  if (direct) out.push(direct);

  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) {
      v.forEach((item, idx) => {
        if (item && typeof item === "object" && !Array.isArray(item)) {
          const entry = buildEntry(item as Record<string, unknown>, `${k} ${idx + 1}`);
          if (entry) out.push(entry);
        }
      });
      continue;
    }
    if (v && typeof v === "object") {
      const entry = buildEntry(v as Record<string, unknown>, k);
      if (entry) out.push(entry);
    }
  }

  const dedup = new Map<string, SpeakableEntry>();
  out.forEach((e) => {
    const key = `${e.locale ?? ""}|${e.textParts.join("||")}`;
    if (!dedup.has(key)) dedup.set(key, e);
  });
  return Array.from(dedup.values());
}

export function extractSpeakableEntries(payload: unknown, fallbackLabel: string): SpeakableEntry[] {
  if (!payload) return [];

  if (typeof payload === "string" && payload.trim()) {
    return [{ label: fallbackLabel, textParts: [payload.trim()] }];
  }

  if (Array.isArray(payload)) {
    const out: SpeakableEntry[] = [];
    payload.forEach((item, idx) => {
      out.push(...extractSpeakableEntries(item, `${fallbackLabel} ${idx + 1}`));
    });
    return out;
  }

  if (typeof payload === "object") {
    return fromObject(payload as Record<string, unknown>, fallbackLabel);
  }

  return [];
}
