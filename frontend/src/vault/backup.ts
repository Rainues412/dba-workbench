import { decodeBase64, decryptSecret, deriveKek, encodeBase64, importAesKey, unlockVault, type VaultCipherItem, type VaultProfile, type VaultSecret } from "./crypto";

const portable = "dba-vault-backup-v2";
const legacy = "dba-vault-backup-v1";
const text = new TextEncoder();
const backupSizeLimit = 64 * 1024 * 1024;

type Cipher = Pick<VaultCipherItem, "item_key" | "envelope_version" | "nonce" | "ciphertext" | "aad" | "revision">;
type Seal = { salt: string; nonce: string; wrapped_keys: string };
export type LegacyBackup = { format: typeof legacy; digest: string; profile: VaultProfile; items: Cipher[] };
export type PortableBackup = Seal & { format: typeof portable; source_user_id: number; items: Cipher[]; mac: string };
export type VaultBackup = PortableBackup | LegacyBackup;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function encoded(value: unknown, length?: number): value is string {
  return typeof value === "string" && (length === undefined || value.length === length)
    && value.length % 4 !== 1 && /^[A-Za-z0-9_-]+$/.test(value);
}

function within(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && min <= value && value <= max;
}

function legacyProfile(value: unknown): boolean {
  return isRecord(value) && value.envelope_version === 1 && value.kdf_name === "argon2id"
    && encoded(value.kdf_salt) && value.kdf_salt.length >= 16 && value.kdf_salt.length <= 128
    && within(value.kdf_memory_kib, 65536, 262144) && within(value.kdf_iterations, 3, 12)
    && within(value.kdf_parallelism, 1, 4) && encoded(value.wrapped_dek, 64)
    && encoded(value.wrapped_dek_nonce, 16)
    && encoded(value.recovery_wrapped_dek) && typeof value.recovery_key_id === "string";
}

function validItem(value: unknown): boolean {
  return isRecord(value) && typeof value.item_key === "string" && /^[A-Za-z0-9_-]{16,80}$/.test(value.item_key)
    && value.envelope_version === 1 && encoded(value.ciphertext) && value.ciphertext.length >= 22
    && value.ciphertext.length <= 131072 && encoded(value.nonce, 16) && typeof value.aad === "string"
    && within(value.revision, 1, Number.MAX_SAFE_INTEGER);
}

function hexDigest(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

export function parseBackup(value: unknown): VaultBackup {
  if (isRecord(value) && Array.isArray(value.items) && value.items.every(validItem)) {
    if (value.format === portable && Object.keys(value).length === 7
      && within(value.source_user_id, 1, Number.MAX_SAFE_INTEGER)
      && encoded(value.salt, 22) && encoded(value.nonce, 16) && encoded(value.wrapped_keys, 107)
      && hexDigest(value.mac)) {
      return value as PortableBackup;
    }
    if (value.format === legacy && hexDigest(value.digest) && legacyProfile(value.profile)) return value as LegacyBackup;
  }
  throw new Error("请选择工作台生成且支持的密码库加密备份文件。");
}

export async function readBackupFile(file: File): Promise<VaultBackup> {
  if (file.size > backupSizeLimit) throw new Error("备份文件不能超过 64 MiB。");
  try { return parseBackup(JSON.parse(await file.text())); }
  catch { throw new Error("请选择工作台生成且支持的密码库加密备份文件。"); }
}

function secret(value: unknown): VaultSecret {
  if (!isRecord(value) || typeof value.site !== "string" || typeof value.url !== "string"
    || typeof value.username !== "string" || typeof value.password !== "string"
    || typeof value.category !== "string" || typeof value.notes !== "string" || typeof value.favorite !== "boolean") {
    throw new Error("备份中的条目格式无效。");
  }
  return { site: value.site, url: value.url, username: value.username, password: value.password,
    category: value.category, notes: value.notes, favorite: value.favorite };
}

async function backupKey(password: string, salt: string) {
  const raw = await deriveKek(password, { kdf_salt: salt, kdf_memory_kib: 65536, kdf_iterations: 3, kdf_parallelism: 1 });
  try { return await importAesKey(raw); }
  finally { raw.fill(0); }
}

function sealAad(userId: number) {
  return text.encode(portable + ":keys:" + userId);
}

// The server keeps only this password-wrapped envelope and the MAC key. It can
// authenticate an automatic snapshot, but cannot unwrap the vault's data key.
export async function createBackupSeal(password: string, userId: number, dek: Uint8Array<ArrayBuffer>) {
  const keys = new Uint8Array(64);
  keys.set(dek);
  const signingKey = crypto.getRandomValues(keys.subarray(32));
  const salt = encodeBase64(crypto.getRandomValues(new Uint8Array(16)));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  try {
    const wrapped = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, additionalData: sealAad(userId) },
      await backupKey(password, salt), keys);
    return { seal: { salt, nonce: encodeBase64(nonce), wrapped_keys: encodeBase64(new Uint8Array(wrapped)) },
      signing_key: encodeBase64(signingKey) };
  } finally { keys.fill(0); }
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (isRecord(value)) return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
  return JSON.stringify(value);
}

async function entries(items: Cipher[], dek: Uint8Array<ArrayBuffer>, userId: number) {
  const unique = new Set(items.map((item) => item.item_key));
  if (unique.size !== items.length || items.some(({ aad, item_key }) => aad !== "dba-vault:item:" + userId + ":" + item_key + ":v1")) {
    throw new Error("备份的条目关联校验失败。");
  }
  return Promise.all(items.map(async (item) => secret(await decryptSecret(dek, item))));
}

async function openLegacy(backup: LegacyBackup, password: string, userId: number) {
  const { format, digest, items, profile } = backup;
  const hash = await crypto.subtle.digest("SHA-256", text.encode(canonical({ format, profile, items })));
  const computed = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (computed !== digest) throw new Error("旧版备份完整性校验失败。");
  if (items.some(({ aad }) => !aad.startsWith("dba-vault:item:" + userId + ":"))) {
    throw new Error("旧版备份绑定原账户。换机请使用新版备份文件。");
  }
  const dek = await unlockVault(password, userId, profile);
  try { return await entries(items, dek, userId); }
  finally { dek.fill(0); }
}

export async function openBackup(backup: VaultBackup, password: string, userId: number): Promise<VaultSecret[]> {
  try {
    if (backup.format === legacy) return await openLegacy(backup, password, userId);
    const { mac, ...document } = backup;
    const keys = new Uint8Array(await crypto.subtle.decrypt({
      name: "AES-GCM", iv: decodeBase64(backup.nonce), additionalData: sealAad(backup.source_user_id),
    }, await backupKey(password, backup.salt), decodeBase64(backup.wrapped_keys)));
    try {
      const signingKey = await crypto.subtle.importKey("raw", keys.subarray(32), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
      const signature = Uint8Array.from(mac.match(/../g) ?? [], (byte) => Number.parseInt(byte, 16));
      if (!await crypto.subtle.verify("HMAC", signingKey, signature, text.encode(canonical(document)))) {
        throw new Error("加密备份完整性校验失败。");
      }
      return await entries(backup.items, keys.subarray(0, 32), backup.source_user_id);
    } finally { keys.fill(0); }
  } catch (cause) {
    if (cause instanceof DOMException) throw new Error("备份密码不正确，或加密备份已损坏。");
    throw cause;
  }
}
