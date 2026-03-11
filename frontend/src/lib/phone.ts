export function formatPhoneForDisplay(phone: string | null | undefined): string {
  const raw = String(phone ?? "").trim();
  if (!raw) return "-";

  if (raw.startsWith("+")) return raw;
  if (raw.startsWith("00")) return `+${raw.slice(2)}`;

  // Add a leading plus for digit-based phone values.
  if (/^[0-9][0-9\s()\-]*$/.test(raw)) {
    return `+${raw}`;
  }

  return raw;
}