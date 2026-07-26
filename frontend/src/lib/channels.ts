const CHANNEL_LABELS: Record<string, string> = {
  bitcointalk: "BitcoinTalk",
  mailing_list: "Mailing List",
  cryptography: "Cryptography List",
  "bitcoin-list": "bitcoin-list",
  "p2p-research": "P2P Research",
}

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel
}
