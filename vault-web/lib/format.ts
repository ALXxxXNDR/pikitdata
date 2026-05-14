const EVM_ADDR = /^0x[a-fA-F0-9]{40}$/;
const TX_HASH = /^0x[a-fA-F0-9]{64}$/;

export function isEvmAddress(s: unknown): s is string {
  return typeof s === "string" && EVM_ADDR.test(s);
}

export function isTxHash(s: unknown): s is string {
  return typeof s === "string" && TX_HASH.test(s);
}
