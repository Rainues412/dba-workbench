import { argon2id } from "hash-wasm";

export type VaultProfile = {
  envelope_version: number;
  kdf_name: "argon2id";
  kdf_salt: string;
  kdf_memory_kib: number;
  kdf_iterations: number;
  kdf_parallelism: number;
  wrapped_dek: string;
  wrapped_dek_nonce: string;
  recovery_wrapped_dek: string;
  recovery_key_id: string;
  recovery_confirmed_at?: string | null;
};

export type VaultCipherItem = {
  id: number;
  item_key: string;
  envelope_version: number;
  ciphertext: string;
  nonce: string;
  aad: string;
  revision: number;
};

export type VaultSecret = {
  site: string;
  url: string;
  username: string;
  password: string;
  category: string;
  notes: string;
  favorite: boolean;
};

export type RecoveryPublicKey = {
  algorithm: string;
  key_id: string;
  public_key_pem: string;
};

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function encodeBase64(value: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < value.length; index += 0x8000) {
    binary += String.fromCharCode(...value.subarray(index, index + 0x8000));
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeBase64(value: string): Uint8Array<ArrayBuffer> {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(normalized);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function deriveKek(password: string, profile: Pick<VaultProfile, "kdf_salt" | "kdf_memory_kib" | "kdf_iterations" | "kdf_parallelism">) {
  return argon2id({
    password,
    salt: decodeBase64(profile.kdf_salt),
    iterations: profile.kdf_iterations,
    parallelism: profile.kdf_parallelism,
    memorySize: profile.kdf_memory_kib,
    hashLength: 32,
    outputType: "binary",
  });
}

async function importAesKey(raw: Uint8Array<ArrayBufferLike>) {
  return crypto.subtle.importKey("raw", new Uint8Array(raw), "AES-GCM", false, ["encrypt", "decrypt"]);
}

function profileAad(userId: number) {
  return encoder.encode(`dba-vault:profile:${userId}:v1`);
}

export async function createVaultProfile(masterPassword: string, userId: number, recovery: RecoveryPublicKey) {
  const dek = crypto.getRandomValues(new Uint8Array(32));
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const parameters = { kdf_salt: encodeBase64(salt), kdf_memory_kib: 65536, kdf_iterations: 3, kdf_parallelism: 1 };
  const kek = await deriveKek(masterPassword, parameters);
  const wrapped = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, additionalData: profileAad(userId), tagLength: 128 },
    await importAesKey(kek),
    dek,
  );
  kek.fill(0);
  const publicDer = pemToDer(recovery.public_key_pem);
  const publicKey = await crypto.subtle.importKey(
    "spki", publicDer, { name: "RSA-OAEP", hash: "SHA-256" }, false, ["encrypt"],
  );
  const recoveryWrapped = await crypto.subtle.encrypt(
    { name: "RSA-OAEP", label: encoder.encode("dba-vault-recovery-v1") },
    publicKey,
    dek,
  );
  return {
    dek,
    profile: {
      envelope_version: 1,
      kdf_name: "argon2id",
      ...parameters,
      wrapped_dek: encodeBase64(new Uint8Array(wrapped)),
      wrapped_dek_nonce: encodeBase64(nonce),
      recovery_wrapped_dek: encodeBase64(new Uint8Array(recoveryWrapped)),
      recovery_key_id: recovery.key_id,
    },
  };
}

export async function unlockVault(masterPassword: string, userId: number, profile: VaultProfile) {
  const kek = await deriveKek(masterPassword, profile);
  try {
    const plaintext = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: decodeBase64(profile.wrapped_dek_nonce),
        additionalData: profileAad(userId),
        tagLength: 128,
      },
      await importAesKey(kek),
      decodeBase64(profile.wrapped_dek),
    );
    return new Uint8Array(plaintext);
  } finally {
    kek.fill(0);
  }
}

export async function rewrapVaultProfile(dek: Uint8Array<ArrayBuffer>, masterPassword: string, userId: number) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const parameters = { kdf_salt: encodeBase64(salt), kdf_memory_kib: 65536, kdf_iterations: 3, kdf_parallelism: 1 };
  const kek = await deriveKek(masterPassword, parameters);
  try {
    const wrapped = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: nonce, additionalData: profileAad(userId), tagLength: 128 },
      await importAesKey(kek),
      dek,
    );
    return { ...parameters, wrapped_dek: encodeBase64(new Uint8Array(wrapped)), wrapped_dek_nonce: encodeBase64(nonce) };
  } finally {
    kek.fill(0);
  }
}

export async function encryptSecret(dek: Uint8Array<ArrayBuffer>, userId: number, secret: VaultSecret, itemKey = crypto.randomUUID().replaceAll("-", "")) {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aad = `dba-vault:item:${userId}:${itemKey}:v1`;
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, additionalData: encoder.encode(aad), tagLength: 128 },
    await importAesKey(dek),
    encoder.encode(JSON.stringify(secret)),
  );
  return { item_key: itemKey, envelope_version: 1, ciphertext: encodeBase64(new Uint8Array(ciphertext)), nonce: encodeBase64(nonce), aad };
}

export async function decryptSecret(dek: Uint8Array<ArrayBuffer>, item: VaultCipherItem): Promise<VaultSecret> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: decodeBase64(item.nonce), additionalData: encoder.encode(item.aad), tagLength: 128 },
    await importAesKey(dek),
    decodeBase64(item.ciphertext),
  );
  return JSON.parse(decoder.decode(plaintext)) as VaultSecret;
}

function pemToDer(pem: string): Uint8Array<ArrayBuffer> {
  const base64 = pem.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}
