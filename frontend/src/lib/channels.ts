import type { AppLocale } from "@/lib/locale"

const CHANNEL_LABELS: Record<string, { en: string; es: string }> = {
  bitcointalk: { en: "BitcoinTalk", es: "BitcoinTalk" },
  mailing_list: { en: "Mailing List", es: "Lista de correo" },
  cryptography: { en: "Cryptography List", es: "Lista de criptografía" },
  "bitcoin-list": { en: "bitcoin-list", es: "bitcoin-list" },
  "p2p-research": { en: "P2P Research", es: "Investigación P2P" },
}

export function channelLabel(channel: string, locale: AppLocale = "en"): string {
  return CHANNEL_LABELS[channel]?.[locale] ?? channel
}
